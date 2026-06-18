import os

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