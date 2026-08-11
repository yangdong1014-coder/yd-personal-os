"""Authentication rules built on Flask sessions and Werkzeug password hashes."""

import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

import auth_repository

ROLES = ("admin", "user")
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))


class AuthError(ValueError):
    pass


class AuthenticationError(AuthError):
    pass


class ConflictError(AuthError):
    pass


class AuthorizationError(AuthError):
    pass


class AuthenticatedUser(UserMixin):
    def __init__(self, record):
        self.id = int(record["id"])
        self.username = record["username"]
        self.email = record["email"]
        self.role = record["role"]
        self._is_active = bool(record["is_active"])
        self.must_change_password = bool(record["must_change_password"])
        self.auth_version = int(record["auth_version"])
        self.failed_login_count = int(record["failed_login_count"])
        self.locked_until = record.get("locked_until")
        self.last_login_at = record.get("last_login_at")

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self._is_active

    @property
    def is_admin(self):
        return self.role == "admin"

    def to_public_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "must_change_password": self.must_change_password,
            "auth_version": self.auth_version,
            "failed_login_count": self.failed_login_count,
            "locked_until": self.locked_until,
            "last_login_at": self.last_login_at,
        }


def normalize_username(value):
    username = str(value or "").strip().casefold()
    if not username:
        raise AuthError("用户名不能为空")
    if "@" in username:
        raise AuthError("用户名不能包含 @")
    if any(character.isspace() for character in username):
        raise AuthError("用户名不能包含空白字符")
    if len(username) > 64:
        raise AuthError("用户名不能超过 64 个字符")
    return username


def normalize_email(value):
    email = str(value or "").strip().casefold()
    if len(email) > 254 or not _EMAIL_RE.fullmatch(email):
        raise AuthError("邮箱格式不正确")
    return email


def validate_password(password):
    if not isinstance(password, str):
        raise AuthError("密码格式不正确")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"密码至少需要 {MIN_PASSWORD_LENGTH} 个字符")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AuthError(f"密码不能超过 {MAX_PASSWORD_LENGTH} 个字符")
    return password


def _public_user(record):
    user = dict(record)
    user.pop("password_hash", None)
    return user


def get_user(user_id):
    record = auth_repository.get_user_by_id(user_id)
    return AuthenticatedUser(record) if record else None


def list_users():
    return [_public_user(user) for user in auth_repository.list_users()]


def _ensure_unique(username, email):
    if auth_repository.get_user_by_username(username):
        raise ConflictError("用户名已存在")
    if auth_repository.get_user_by_email(email):
        raise ConflictError("邮箱已存在")


def _create_user(username, email, password, *, role, must_change_password):
    username = normalize_username(username)
    email = normalize_email(email)
    password = validate_password(password)
    if role not in ROLES:
        raise AuthError("无效的用户角色")
    _ensure_unique(username, email)
    try:
        record = auth_repository.create_user(
            username,
            email,
            generate_password_hash(password),
            role=role,
            must_change_password=must_change_password,
        )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("用户名或邮箱已存在") from exc
    return _public_user(record)


def bootstrap_admin(username, email, password):
    username = normalize_username(username)
    email = normalize_email(email)
    password = validate_password(password)
    try:
        record = auth_repository.create_bootstrap_admin(
            username,
            email,
            generate_password_hash(password),
        )
    except auth_repository.BootstrapAdminExistsError as exc:
        raise ConflictError("管理员账户已经初始化") from exc
    except sqlite3.IntegrityError as exc:
        raise ConflictError("用户名或邮箱已存在") from exc
    return _public_user(record)


def generate_temporary_password():
    return secrets.token_urlsafe(18)


def create_standard_user(username, email):
    temporary_password = generate_temporary_password()
    user = _create_user(
        username,
        email,
        temporary_password,
        role="user",
        must_change_password=True,
    )
    return user, temporary_password


def _parse_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def authenticate(identifier, password):
    normalized = str(identifier or "").strip().casefold()
    record = auth_repository.get_user_by_identifier(normalized) if normalized else None
    if record is None:
        check_password_hash(_DUMMY_PASSWORD_HASH, str(password or ""))
        raise AuthenticationError("用户名、邮箱或密码不正确")

    if not record["is_active"]:
        raise AuthenticationError("用户名、邮箱或密码不正确")

    now = datetime.now(timezone.utc)
    locked_until = _parse_timestamp(record.get("locked_until"))
    if locked_until and locked_until > now:
        raise AuthenticationError("用户名、邮箱或密码不正确")
    if locked_until:
        auth_repository.clear_login_failures(record["id"])
        record = auth_repository.get_user_by_id(record["id"])

    if not check_password_hash(record["password_hash"], str(password or "")):
        auth_repository.record_login_failure(
            record["id"],
            MAX_FAILED_LOGINS,
            (now + timedelta(minutes=LOCKOUT_MINUTES)).isoformat(timespec="seconds"),
        )
        raise AuthenticationError("用户名、邮箱或密码不正确")

    record = auth_repository.record_login_success(record["id"])
    return AuthenticatedUser(record)


def change_password(user_id, current_password, new_password):
    record = auth_repository.get_user_by_id(user_id)
    if record is None or not record["is_active"]:
        raise AuthenticationError("当前账户不可用")
    if not check_password_hash(record["password_hash"], str(current_password or "")):
        raise AuthenticationError("当前密码不正确")
    new_password = validate_password(new_password)
    if check_password_hash(record["password_hash"], new_password):
        raise AuthError("新密码不能与当前密码相同")
    updated = auth_repository.update_password(
        user_id,
        generate_password_hash(new_password),
        must_change_password=False,
    )
    return AuthenticatedUser(updated)


def revoke_all_sessions(user_id):
    updated = auth_repository.increment_auth_version(user_id)
    if updated is None:
        raise AuthenticationError("当前账户不可用")
    return AuthenticatedUser(updated)


def _get_standard_user(user_id):
    record = auth_repository.get_user_by_id(user_id)
    if record is None:
        raise AuthError("用户不存在")
    if record["role"] != "user":
        raise AuthorizationError("管理员账户不能通过该接口修改")
    return record


def set_standard_user_active(user_id, is_active):
    record = _get_standard_user(user_id)
    desired = bool(is_active)
    if record["is_active"] == desired:
        return _public_user(record)
    return _public_user(auth_repository.set_user_active(user_id, desired))


def reset_standard_user_password(user_id):
    _get_standard_user(user_id)
    temporary_password = generate_temporary_password()
    record = auth_repository.update_password(
        user_id,
        generate_password_hash(temporary_password),
        must_change_password=True,
    )
    return _public_user(record), temporary_password
