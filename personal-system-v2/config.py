import os
import secrets
from dataclasses import dataclass
from ipaddress import ip_address

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(_ROOT_DIR, ".env")


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
    if safety.hardened and len(secret_key.encode("utf-8")) < 32:
        raise RuntimeError(
            "非显式本地开发、生产、远程或非 loopback 运行的 SECRET_KEY "
            "至少需要 32 字节"
        )
    if safety.non_loopback and not safety.remote:
        raise RuntimeError(
            f"PERSONAL_OS_BIND_HOST={safety.bind_host} 仅在 PERSONAL_OS_REMOTE=1 时允许使用"
        )
    if flask_app is not None and safety.hardened:
        if flask_app.config.get("SESSION_COOKIE_SECURE") is not True:
            raise RuntimeError(
                "生产、远程或非 loopback 运行必须启用 SESSION_COOKIE_SECURE"
            )
        if flask_app.debug:
            raise RuntimeError("生产、远程或非 loopback 运行禁止启用 Flask debug")

    return safety


def configure_flask_app(app):
    safety = validate_production_safety()
    secret_key = get_secret_key()
    if not secret_key:
        secret_key = secrets.token_urlsafe(48)

    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_NAME="psy_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=safety.hardened,
        SESSION_REFRESH_EACH_REQUEST=False,
        WTF_CSRF_TIME_LIMIT=3600,
    )
    if safety.hardened:
        app.config["DEBUG"] = False
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
    return {
        "debug": local_debug,
        "host": safety.bind_host,
        "port": 5000,
        "use_reloader": local_debug,
    }
