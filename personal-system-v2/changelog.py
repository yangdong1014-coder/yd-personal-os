import json
import os

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CHANGELOG_PATH = os.path.join(_ROOT_DIR, "changelog.json")

_TYPE_LABELS = {
    "feat": "新功能",
    "fix": "修复",
    "refactor": "重构",
    "docs": "文档",
}


def _load():
    if not os.path.isfile(CHANGELOG_PATH):
        return {"current": "", "entries": []}
    with open(CHANGELOG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"current": "", "entries": []}
    entries = data.get("entries") or []
    if not isinstance(entries, list):
        entries = []
    return {
        "current": (data.get("current") or "").strip(),
        "entries": entries,
    }


def get_current_version():
    return _load()["current"]


def list_entries():
    data = _load()
    entries = []
    for item in data["entries"]:
        if not isinstance(item, dict):
            continue
        entry_type = (item.get("type") or "feat").strip()
        entries.append({
            "version": (item.get("version") or "").strip(),
            "date": (item.get("date") or "").strip(),
            "title": (item.get("title") or "").strip(),
            "type": entry_type,
            "type_label": _TYPE_LABELS.get(entry_type, entry_type),
            "changes": [
                str(line).strip()
                for line in (item.get("items") or item.get("changes") or [])
                if str(line).strip()
            ],
            "is_current": (item.get("version") or "").strip() == data["current"],
            "is_dev": (item.get("version") or "").strip() == "dev",
        })
    return entries