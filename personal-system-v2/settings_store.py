import json
import os

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(_ROOT_DIR, "data", "settings.json")


def read_settings():
    if not os.path.isfile(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_settings(updates):
    settings = read_settings()
    settings.update(updates)
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return settings


def get_stored_model():
    return (read_settings().get("deepseek_model") or "").strip()


def set_stored_model(model):
    write_settings({"deepseek_model": model})