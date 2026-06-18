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
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
DEEPSEEK_TIMEOUT = int(os.environ.get("DEEPSEEK_TIMEOUT", "60"))


def is_ai_enabled():
    return bool(DEEPSEEK_API_KEY.strip())