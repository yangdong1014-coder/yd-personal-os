import hmac
import math
import os
import re
import secrets
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from ipaddress import ip_address

from flask import g, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(_ROOT_DIR, ".env")
_PRODUCTION_PREFLIGHT_PATH = None

MAX_REQUEST_BYTES = 16 * 1024 * 1024
MAX_FORM_MEMORY_BYTES = 64 * 1024
MAX_FORM_PARTS = 64
SESSION_LIFETIME_HOURS = 12
LOGIN_RATE_LIMIT_ATTEMPTS = 10
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60
PRODUCTION_PORT = 5000

_FORWARDED_ENV_KEYS = frozenset(
    {
        "HTTP_FORWARDED",
        "HTTP_X_FORWARDED_FOR",
        "HTTP_X_FORWARDED_HOST",
        "HTTP_X_FORWARDED_PROTO",
        "HTTP_X_FORWARDED_PORT",
        "HTTP_X_FORWARDED_PREFIX",
        "HTTP_X_FORWARDED_BY",
    }
)
_TRUSTED_FORWARDED_ENV_KEYS = frozenset(
    {
        "HTTP_X_FORWARDED_FOR",
        "HTTP_X_FORWARDED_HOST",
        "HTTP_X_FORWARDED_PROTO",
    }
)
_SECRET_PLACEHOLDER_MARKERS = (
    "changeme",
    "change_me",
    "example",
    "password",
    "placeholder",
    "replace",
    "secret_key",
    "your_key",
)
_DNS_HOST_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)"
    r"(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$"
)


def _load_dotenv():
    """从 .env 加载变量，不覆盖已存在的环境变量。"""
    if not os.path.isfile(_ENV_FILE):
        return
    with open(_ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get(
    "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
)
DEEPSEEK_TIMEOUT = int(os.environ.get("DEEPSEEK_TIMEOUT", "60"))

DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
_ENV_DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "").strip()

AVAILABLE_DEEPSEEK_MODELS = [
    {"id": "deepseek-v4-flash", "label": "DeepSeek V4 Flash（快速）"},
    {"id": "deepseek-v4-pro", "label": "DeepSeek V4 Pro（高质量）"},
    {"id": "deepseek-chat", "label": "DeepSeek Chat（兼容，将弃用）"},
    {"id": "deepseek-reasoner", "label": "DeepSeek Reasoner（推理，将弃用）"},
]


def is_ai_enabled():
    return bool(DEEPSEEK_API_KEY.strip())


def is_model_env_locked():
    return bool(_ENV_DEEPSEEK_MODEL)


def get_deepseek_model():
    if _ENV_DEEPSEEK_MODEL:
        return _ENV_DEEPSEEK_MODEL
    import settings_store

    stored = settings_store.get_stored_model()
    if stored:
        return stored
    return DEFAULT_DEEPSEEK_MODEL


def get_valid_model_ids():
    return {item["id"] for item in AVAILABLE_DEEPSEEK_MODELS}


def is_remote_mode():
    return os.environ.get("PERSONAL_OS_REMOTE", "").strip() == "1"


def is_production():
    return os.environ.get("PERSONAL_OS_ENV", "").strip().lower() in {
        "prod",
        "production",
    }


def is_development():
    return os.environ.get("PERSONAL_OS_ENV", "").strip().lower() in {
        "dev",
        "development",
        "local",
    }


def get_secret_key():
    return os.environ.get("SECRET_KEY", "").strip()


def get_proxy_token(*, required=False):
    token = os.environ.get("PERSONAL_OS_PROXY_TOKEN", "").strip()
    if not token and required:
        raise RuntimeError(
            "生产或远程运行必须显式设置 PERSONAL_OS_PROXY_TOKEN"
        )
    return token


def get_explicit_database_path(*, required=False):
    raw = os.environ.get("YD_OS_DB_PATH", "").strip()
    if not raw:
        if required:
            raise RuntimeError(
                "生产或远程运行必须显式设置绝对路径 YD_OS_DB_PATH"
            )
        return ""
    if not os.path.isabs(raw):
        raise RuntimeError("生产或远程运行的 YD_OS_DB_PATH 必须是绝对路径")
    return os.path.realpath(raw)


def mark_production_preflight_complete(database_path):
    """Authorize app construction only after production.py verifies the DB."""
    global _PRODUCTION_PREFLIGHT_PATH
    expected = get_explicit_database_path(required=True)
    verified = os.path.realpath(os.fspath(database_path))
    if verified != expected:
        raise RuntimeError("生产预检数据库路径与 YD_OS_DB_PATH 不一致")
    _PRODUCTION_PREFLIGHT_PATH = verified


def _secret_entropy_bits(value):
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    bits_per_character = -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )
    return bits_per_character * length


def _validate_secret_key(secret_key):
    if len(secret_key.encode("utf-8")) < 32:
        raise RuntimeError(
            "非显式本地开发、生产或远程运行的 SECRET_KEY 至少需要 32 字节"
        )
    normalized = secret_key.casefold()
    if any(marker in normalized for marker in _SECRET_PLACEHOLDER_MARKERS):
        raise RuntimeError("SECRET_KEY 不能使用示例值、占位值或口令式弱密钥")
    if len(set(secret_key)) < 8 or _secret_entropy_bits(secret_key) < 128:
        raise RuntimeError(
            "SECRET_KEY 熵不足；请使用 secrets.token_urlsafe(48) 生成强随机值"
        )


def _validate_proxy_token(proxy_token, secret_key):
    if len(proxy_token.encode("utf-8")) < 32:
        raise RuntimeError("PERSONAL_OS_PROXY_TOKEN 至少需要 32 字节")
    normalized = proxy_token.casefold()
    if any(marker in normalized for marker in _SECRET_PLACEHOLDER_MARKERS):
        raise RuntimeError("PERSONAL_OS_PROXY_TOKEN 不能使用示例值或占位值")
    if len(set(proxy_token)) < 8 or _secret_entropy_bits(proxy_token) < 128:
        raise RuntimeError(
            "PERSONAL_OS_PROXY_TOKEN 熵不足；请使用 secrets.token_urlsafe(48) 生成"
        )
    if hmac.compare_digest(proxy_token, secret_key):
        raise RuntimeError("PERSONAL_OS_PROXY_TOKEN 必须与 SECRET_KEY 不同")


def _normalize_trusted_host(value):
    candidate = str(value or "").strip().casefold().rstrip(".")
    if (
        not candidate
        or candidate.startswith(".")
        or candidate == "*"
        or any(character.isspace() for character in candidate)
        or any(character in candidate for character in "/\\@?#")
        or "://" in candidate
    ):
        raise RuntimeError(
            "PERSONAL_OS_TRUSTED_HOSTS 只允许逗号分隔的精确主机名或 IP，禁止通配符、端口和 URL"
        )
    try:
        normalized_ip = str(ip_address(candidate.strip("[]")))
    except ValueError:
        try:
            candidate = candidate.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise RuntimeError("PERSONAL_OS_TRUSTED_HOSTS 包含无效主机名") from exc
        if len(candidate) > 253 or not _DNS_HOST_RE.fullmatch(candidate):
            raise RuntimeError("PERSONAL_OS_TRUSTED_HOSTS 包含无效主机名")
        return candidate
    return normalized_ip


def get_trusted_hosts(*, required=False):
    raw = os.environ.get("PERSONAL_OS_TRUSTED_HOSTS", "")
    if not raw.strip():
        if required:
            raise RuntimeError(
                "生产或远程运行必须显式设置 PERSONAL_OS_TRUSTED_HOSTS"
            )
        return []
    hosts = []
    for item in raw.split(","):
        host = _normalize_trusted_host(item)
        if host not in hosts:
            hosts.append(host)
    if not hosts:
        raise RuntimeError("PERSONAL_OS_TRUSTED_HOSTS 不能为空")
    return hosts


def get_trusted_proxy(*, required=False):
    raw = os.environ.get("PERSONAL_OS_TRUSTED_PROXY", "").strip()
    if not raw:
        if required:
            raise RuntimeError(
                "生产或远程运行必须显式设置 PERSONAL_OS_TRUSTED_PROXY"
            )
        return ""
    if raw == "*" or "," in raw or "/" in raw:
        raise RuntimeError(
            "PERSONAL_OS_TRUSTED_PROXY 必须是单个精确 loopback IP，禁止通配符、列表或 CIDR"
        )
    try:
        proxy = ip_address(raw.strip("[]"))
    except ValueError as exc:
        raise RuntimeError("PERSONAL_OS_TRUSTED_PROXY 必须是有效 IP") from exc
    if not proxy.is_loopback:
        raise RuntimeError(
            "当前生产拓扑只允许 loopback 反向代理连接应用服务器"
        )
    return str(proxy)


def _debug_requested():
    return os.environ.get("FLASK_DEBUG", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass(frozen=True)
class RuntimeSafety:
    production: bool
    development: bool
    remote: bool
    bind_host: str
    non_loopback: bool

    @property
    def hardened(self):
        return (
            self.production
            or self.remote
            or self.non_loopback
            or not self.development
        )


def _is_loopback_host(host):
    normalized = str(host or "").strip().lower().strip("[]")
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def get_runtime_safety():
    bind_host = get_bind_host()
    return RuntimeSafety(
        production=is_production(),
        development=is_development(),
        remote=is_remote_mode(),
        bind_host=bind_host,
        non_loopback=not _is_loopback_host(bind_host),
    )


def requires_persistent_secret_key():
    return get_runtime_safety().hardened


def validate_production_safety(flask_app=None):
    """Validate every runtime signal that can expose authenticated data."""
    safety = get_runtime_safety()
    secret_key = get_secret_key()

    if safety.hardened and not secret_key:
        raise RuntimeError(
            "非显式本地开发、生产、远程或非 loopback 运行必须设置持久 "
            "SECRET_KEY（至少 32 字节强随机值）"
        )
    if safety.hardened:
        _validate_secret_key(secret_key)
    if safety.non_loopback and not safety.remote:
        raise RuntimeError(
            f"PERSONAL_OS_BIND_HOST={safety.bind_host} 仅在 PERSONAL_OS_REMOTE=1 时允许使用"
        )
    if safety.hardened and safety.non_loopback:
        raise RuntimeError(
            "生产或远程运行只允许应用服务器监听 loopback；公网入口必须由 HTTPS 反向代理提供"
        )
    if safety.hardened:
        get_explicit_database_path(required=True)
        get_trusted_hosts(required=True)
        get_trusted_proxy(required=True)
        if not safety.production:
            raise RuntimeError(
                "加固或远程运行必须显式设置 PERSONAL_OS_ENV=production"
            )
        if not safety.remote:
            raise RuntimeError(
                "生产运行必须显式设置 PERSONAL_OS_REMOTE=1"
            )
        _validate_proxy_token(
            get_proxy_token(required=True),
            secret_key,
        )
        if _debug_requested():
            raise RuntimeError("生产、远程或加固运行禁止设置 FLASK_DEBUG")
    if flask_app is not None and safety.hardened:
        if _PRODUCTION_PREFLIGHT_PATH != get_explicit_database_path(required=True):
            raise RuntimeError(
                "生产数据库尚未通过同进程只读预检；必须由 production:create_production_app() 启动"
            )
        if flask_app.config.get("SESSION_COOKIE_SECURE") is not True:
            raise RuntimeError(
                "生产、远程或非 loopback 运行必须启用 SESSION_COOKIE_SECURE"
            )
        if flask_app.config.get("SESSION_COOKIE_HTTPONLY") is not True:
            raise RuntimeError(
                "生产、远程或非 loopback 运行必须启用 SESSION_COOKIE_HTTPONLY"
            )
        if flask_app.config.get("SESSION_COOKIE_SAMESITE") not in {"Lax", "Strict"}:
            raise RuntimeError(
                "生产、远程或非 loopback 运行必须设置安全的 SESSION_COOKIE_SAMESITE"
            )
        if not flask_app.config.get("TRUSTED_HOSTS"):
            raise RuntimeError("生产、远程或非 loopback 运行必须配置 TRUSTED_HOSTS")
        if flask_app.debug:
            raise RuntimeError("生产、远程或非 loopback 运行禁止启用 Flask debug")

    return safety


def configure_flask_app(app):
    safety = validate_production_safety()
    secret_key = get_secret_key()
    public_trusted_hosts = get_trusted_hosts(required=safety.hardened)
    if not secret_key:
        secret_key = secrets.token_urlsafe(48)

    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_NAME="psy_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=safety.hardened,
        SESSION_REFRESH_EACH_REQUEST=False,
        REMEMBER_COOKIE_NAME="psy_remember",
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=safety.hardened,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=SESSION_LIFETIME_HOURS),
        MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES,
        MAX_FORM_MEMORY_SIZE=MAX_FORM_MEMORY_BYTES,
        MAX_FORM_PARTS=MAX_FORM_PARTS,
        WTF_CSRF_TIME_LIMIT=3600,
        WTF_CSRF_SSL_STRICT=True,
        TRUSTED_HOSTS=(
            public_trusted_hosts + ["localhost", "127.0.0.1", "::1"]
            if safety.hardened
            else None
        ),
        PSY_PUBLIC_TRUSTED_HOSTS=public_trusted_hosts,
        PSY_HARDENED=safety.hardened,
    )
    if safety.hardened:
        app.config["DEBUG"] = False
        app.wsgi_app = RejectUntrustedProxyHeadersMiddleware(
            ProxyFix(
                app.wsgi_app,
                x_for=1,
                x_proto=1,
                x_host=1,
            ),
            trusted_proxy=get_trusted_proxy(required=True),
            trusted_hosts=app.config["PSY_PUBLIC_TRUSTED_HOSTS"],
            proxy_token=get_proxy_token(required=True),
        )
    validate_production_safety(app)


def get_bind_host():
    explicit = os.environ.get("PERSONAL_OS_BIND_HOST", "").strip()
    return explicit or "127.0.0.1"


def validate_server_config():
    """Backward-compatible CLI validation using the single safety validator."""
    try:
        return validate_production_safety()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


def get_server_run_options(flask_app=None):
    """Return Flask run options with hardened modes forced out of debug."""
    try:
        safety = validate_production_safety(flask_app)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    background = os.environ.get("PERSONAL_OS_BG", "").strip() == "1"
    local_debug = not safety.hardened and not background
    if safety.hardened:
        raise SystemExit(
            "生产、远程或加固运行禁止使用 Flask 开发服务器；请使用 active-release launcher"
        )
    return {
        "debug": local_debug,
        "host": safety.bind_host,
        "port": PRODUCTION_PORT,
        "use_reloader": local_debug,
    }


class RejectUntrustedProxyHeadersMiddleware:
    """Reject spoofed forwarding headers unless the direct peer is the proxy."""

    def __init__(self, app, *, trusted_proxy, trusted_hosts, proxy_token):
        self.app = app
        self.trusted_proxy = str(ip_address(trusted_proxy))
        self.trusted_hosts = frozenset(trusted_hosts)
        self.proxy_token = str(proxy_token)

    @staticmethod
    def _reject(start_response):
        body = b'{"ok":false,"error":"invalid proxy headers"}'
        start_response(
            "400 Bad Request",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
                ("Referrer-Policy", "no-referrer"),
                ("X-Frame-Options", "DENY"),
                ("Strict-Transport-Security", "max-age=31536000"),
            ],
        )
        return [body]

    def __call__(self, environ, start_response):
        forwarded = _FORWARDED_ENV_KEYS.intersection(environ)
        supplied_proxy_token = str(
            environ.pop("HTTP_X_PSY_PROXY_TOKEN", "")
        )
        if not forwarded:
            if supplied_proxy_token:
                return self._reject(start_response)
            return self.app(environ, start_response)

        try:
            peer = str(ip_address(str(environ.get("REMOTE_ADDR", "")).strip("[]")))
        except ValueError:
            peer = ""

        if (
            peer != self.trusted_proxy
            or not _TRUSTED_FORWARDED_ENV_KEYS.issubset(forwarded)
            or not hmac.compare_digest(supplied_proxy_token, self.proxy_token)
        ):
            return self._reject(start_response)

        forwarded_for = str(environ.get("HTTP_X_FORWARDED_FOR", "")).strip()
        forwarded_proto = str(environ.get("HTTP_X_FORWARDED_PROTO", "")).strip()
        forwarded_host = str(environ.get("HTTP_X_FORWARDED_HOST", "")).strip()
        if any(
            "," in value
            for value in (forwarded_for, forwarded_proto, forwarded_host)
        ):
            return self._reject(start_response)
        try:
            ip_address(forwarded_for.strip("[]"))
            normalized_host = _normalize_trusted_host(forwarded_host)
        except (ValueError, RuntimeError):
            return self._reject(start_response)
        if (
            forwarded_proto.casefold() != "https"
            or normalized_host not in self.trusted_hosts
        ):
            return self._reject(start_response)

        for key in forwarded - _TRUSTED_FORWARDED_ENV_KEYS:
            environ.pop(key, None)
        environ["psy.proxy_verified"] = "1"
        return self.app(environ, start_response)


def register_request_security(app):
    """Require the trusted proxy to attest HTTPS for every hardened request."""

    @app.before_request
    def prepare_secure_request():
        g.csp_nonce = secrets.token_urlsafe(24)
        direct_loopback_health = False
        if request.path == "/api/health" and not request.environ.get(
            "psy.proxy_verified"
        ):
            try:
                direct_loopback_health = ip_address(
                    str(request.remote_addr or "").strip("[]")
                ).is_loopback
            except ValueError:
                pass
        proxy_verified = request.environ.get("psy.proxy_verified") == "1"
        if (
            app.config.get("PSY_HARDENED") is True
            and not direct_loopback_health
            and (not proxy_verified or not request.is_secure)
        ):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "HTTPS required",
                        "code": "https_required",
                    }
                ),
                400,
            )

    @app.context_processor
    def inject_csp_nonce():
        return {"csp_nonce": getattr(g, "csp_nonce", "")}
