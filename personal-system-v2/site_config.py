import json
import os


_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_CONFIG_PATH = os.path.join(_ROOT_DIR, "site_config.json")


def _load():
    try:
        with open(SITE_CONFIG_PATH, encoding="utf-8") as config_file:
            data = json.load(config_file)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_icp_filing_number():
    value = _load().get("icp_filing_number", "")
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())
