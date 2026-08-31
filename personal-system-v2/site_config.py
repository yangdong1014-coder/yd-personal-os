import json
import os


_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_CONFIG_PATH = os.path.join(_ROOT_DIR, "site_config.json")
PERSISTENT_SITE_CONFIG_PATH = "/etc/psy/site_config.json"


def _load_file(path):
    try:
        with open(path, encoding="utf-8") as config_file:
            data = json.load(config_file)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _load():
    data = _load_file(SITE_CONFIG_PATH)
    if os.environ.get("PERSONAL_OS_ENV") == "production":
        data.update(_load_file(PERSISTENT_SITE_CONFIG_PATH))
    return data


def get_icp_filing_number():
    value = _load().get("icp_filing_number", "")
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())
