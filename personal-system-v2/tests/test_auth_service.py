import sqlite3

import pytest
from werkzeug.security import check_password_hash

import auth_repository
import auth_service
import database


@pytest.fixture
def auth_db(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()
    return db_path


def test_users_schema_is_additive_and_constrained(auth_db):
    conn = sqlite3.connect(auth_db)
    try:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        assert columns == {
            "id",
            "username",
            "email",
            "password_hash",
            "role",
            "is_active",
            "must_change_password",
            "auth_version",
            "failed_login_count",
            "locked_until",
            "last_login_at",
            "created_at",
            "updated_at",
        }

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO users (
                    username, email, password_hash, role, created_at, updated_at
                ) VALUES ('bad@name', 'bad@example.com', 'hash', 'user', 'now', 'now')
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO users (
                    username, email, password_hash, role, created_at, updated_at
                ) VALUES ('valid', 'valid@example.com', 'hash', 'owner', 'now', 'now')
                """
            )
    finally:
        conn.close()


def test_username_and_email_login_are_case_normalized_and_password_is_hashed(auth_db):
    auth_service.bootstrap_admin(
        "  AdminUser  ", "  Admin@Example.COM ", "correct horse battery"
    )

    stored = auth_repository.get_user_by_username("ADMINUSER")
    assert stored["username"] == "adminuser"
    assert stored["email"] == "admin@example.com"
    assert stored["password_hash"] != "correct horse battery"
    assert check_password_hash(stored["password_hash"], "correct horse battery")

    by_username = auth_service.authenticate("ADMINUSER", "correct horse battery")
    by_email = auth_service.authenticate("ADMIN@EXAMPLE.COM", "correct horse battery")
    assert by_username.id == stored["id"]
    assert by_email.id == stored["id"]


def test_invalid_credentials_are_generic_and_failures_lock_account(auth_db):
    auth_service.bootstrap_admin(
        "admin", "admin@example.com", "correct horse battery"
    )

    with pytest.raises(auth_service.AuthenticationError) as missing:
        auth_service.authenticate("missing", "wrong password value")
    assert str(missing.value) == "用户名、邮箱或密码不正确"

    for _ in range(auth_service.MAX_FAILED_LOGINS):
        with pytest.raises(auth_service.AuthenticationError) as invalid:
            auth_service.authenticate("admin", "wrong password value")
        assert str(invalid.value) == "用户名、邮箱或密码不正确"

    stored = auth_repository.get_user_by_username("admin")
    assert stored["failed_login_count"] == auth_service.MAX_FAILED_LOGINS
    assert stored["locked_until"] is not None
    with pytest.raises(auth_service.AuthenticationError):
        auth_service.authenticate("admin", "correct horse battery")


def test_standard_user_uses_temporary_password_and_admin_role_is_not_available(auth_db):
    user, temporary_password = auth_service.create_standard_user(
        "NormalUser", "normal@example.com"
    )
    stored = auth_repository.get_user_by_id(user["id"])

    assert user["role"] == "user"
    assert user["must_change_password"] is True
    assert "password_hash" not in user
    assert temporary_password not in repr(user)
    assert check_password_hash(stored["password_hash"], temporary_password)

    with pytest.raises(auth_service.AuthError):
        auth_service._create_user(
            "owner",
            "owner@example.com",
            "correct horse battery",
            role="owner",
            must_change_password=False,
        )


def test_password_reset_and_disable_increment_auth_version(auth_db):
    user, _ = auth_service.create_standard_user("user", "user@example.com")
    initial_version = user["auth_version"]

    reset_user, temporary_password = auth_service.reset_standard_user_password(
        user["id"]
    )
    assert reset_user["auth_version"] == initial_version + 1
    assert reset_user["must_change_password"] is True
    assert auth_service.authenticate("user", temporary_password).id == user["id"]

    disabled = auth_service.set_standard_user_active(user["id"], False)
    assert disabled["auth_version"] == initial_version + 2
    assert disabled["is_active"] is False
    with pytest.raises(auth_service.AuthenticationError):
        auth_service.authenticate("user", temporary_password)


def test_admin_accounts_cannot_be_changed_by_standard_user_management(auth_db):
    admin = auth_service.bootstrap_admin(
        "admin", "admin@example.com", "correct horse battery"
    )

    with pytest.raises(auth_service.AuthorizationError):
        auth_service.set_standard_user_active(admin["id"], False)
    with pytest.raises(auth_service.AuthorizationError):
        auth_service.reset_standard_user_password(admin["id"])
