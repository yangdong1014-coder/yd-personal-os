import io
import json
import re
import zipfile
from datetime import datetime

import database

SOURCE = "yd-personal-os"
ROOT = "Obsidian"
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE = re.compile(r"\s+")


class ObsidianExportError(Exception):
    pass


def zip_filename():
    return datetime.now().strftime("obsidian_export_%Y%m%d_%H%M%S.zip")


def sanitize_filename(name, fallback="untitled", max_len=80):
    text = (name or "").strip() or fallback
    text = INVALID_CHARS.sub("-", text)
    text = re.sub(r"-+", "-", text)
    text = WHITESPACE.sub(" ", text).strip().rstrip(".")
    if len(text) > max_len:
        text = text[:max_len].rstrip()
    return text or fallback


def _yaml_scalar(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    text = str(value)
    return json.dumps(text, ensure_ascii=False)


def _frontmatter(fields):
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def _wiki_link(folder, basename):
    return f"[[{folder}/{basename}]]"


class _NameRegistry:
    def __init__(self):
        self._used = {}

    def assign(self, folder, label, fallback):
        base = sanitize_filename(label, fallback=fallback)
        used = self._used.setdefault(folder, set())
        name = base
        counter = 2
        key = name.lower()
        while key in used:
            name = f"{base}-{counter}"
            key = name.lower()
            counter += 1
        used.add(key)
        return name

    def basename(self, folder, entity_id, mapping):
        return mapping.get(entity_id)


def _build_link_maps(registry, goals, projects, tasks, reviews, assets, entries):
    goal_map = {
        g["id"]: registry.assign("Goals", g["name"], f"goal-{g['id']}")
        for g in goals
    }
    project_map = {
        p["id"]: registry.assign("Projects", p["name"], f"project-{p['id']}")
        for p in projects
    }
    task_map = {
        t["id"]: registry.assign("Tasks", t["name"], f"task-{t['id']}")
        for t in tasks
    }
    review_map = {
        r["id"]: registry.assign(
            "Reviews",
            f"{r['review_date']}-{r['type']}",
            f"review-{r['id']}",
        )
        for r in reviews
    }
    asset_map = {
        a["id"]: registry.assign("Assets", a["title"], f"asset-{a['id']}")
        for a in assets
    }
    entry_map = {
        e["id"]: registry.assign(
            "Capabilities",
            f"{e['module']}-{e['entry_date']}",
            f"entry-{e['id']}",
        )
        for e in entries
    }
    return goal_map, project_map, task_map, review_map, asset_map, entry_map


def _projects_by_goal(projects):
    grouped = {}
    for project in projects:
        grouped.setdefault(project["goal_id"], []).append(project)
    return grouped


def _tasks_by_project(tasks):
    grouped = {}
    for task in tasks:
        grouped.setdefault(task["project_id"], []).append(task)
    return grouped


def _assets_by_review(assets):
    grouped = {}
    for asset in assets:
        review_id = asset.get("source_review_id")
        if review_id is not None:
            grouped.setdefault(review_id, []).append(asset)
    return grouped


def build_obsidian_zip():
    try:
        goals = database.list_goals()
        projects = database.list_projects()
        tasks = database.list_tasks()
        reviews = database.list_reviews()
        assets = database.list_assets()
        entries = database.list_capability_entries()

        registry = _NameRegistry()
        goal_map, project_map, task_map, review_map, asset_map, entry_map = (
            _build_link_maps(
                registry, goals, projects, tasks, reviews, assets, entries
            )
        )

        projects_by_goal = _projects_by_goal(projects)
        tasks_by_project = _tasks_by_project(tasks)
        assets_by_review = _assets_by_review(assets)

        files = {}

        for goal in goals:
            basename = goal_map[goal["id"]]
            links = [
                _wiki_link("Projects", project_map[p["id"]])
                for p in projects_by_goal.get(goal["id"], [])
            ]
            body = [
                f"# {goal['name']}",
                "",
                f"- **类型**：{goal['type']}",
                f"- **创建时间**：{goal['created_at']}",
                "",
                "## 关联项目",
                "",
            ]
            if links:
                body.extend(f"- {link}" for link in links)
            else:
                body.append("- （无）")
            fm = {
                "id": goal["id"],
                "type": "goal",
                "created_at": goal["created_at"],
                "source": SOURCE,
            }
            files[f"{ROOT}/Goals/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        goal_name_by_id = {g["id"]: g["name"] for g in goals}

        for project in projects:
            basename = project_map[project["id"]]
            goal_link = _wiki_link("Goals", goal_map[project["goal_id"]])
            task_links = [
                _wiki_link("Tasks", task_map[t["id"]])
                for t in tasks_by_project.get(project["id"], [])
            ]
            goal_name = goal_name_by_id.get(project["goal_id"], "")
            body = [
                f"# {project['name']}",
                "",
                f"- **所属目标**：{goal_link}（{goal_name}）",
                f"- **创建时间**：{project['created_at']}",
                "",
                "## 关联任务",
                "",
            ]
            if task_links:
                body.extend(f"- {link}" for link in task_links)
            else:
                body.append("- （无）")
            fm = {
                "id": project["id"],
                "type": "project",
                "goal_id": project["goal_id"],
                "created_at": project["created_at"],
                "source": SOURCE,
            }
            files[f"{ROOT}/Projects/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        project_name_by_id = {p["id"]: p["name"] for p in projects}

        for task in tasks:
            basename = task_map[task["id"]]
            project_link = _wiki_link("Projects", project_map[task["project_id"]])
            project_name = project_name_by_id.get(task["project_id"], "")
            progress = ""
            if task.get("today_progress") == 1 and task.get("today_progress_date"):
                progress = f"- **今日推进**：{task['today_progress_date']}\n"
            body = [
                f"# {task['name']}",
                "",
                f"- **状态**：{task['status']}",
                f"- **所属项目**：{project_link}（{project_name}）",
                f"- **创建时间**：{task['created_at']}",
                progress.rstrip(),
                "",
            ]
            body = [line for line in body if line != ""]
            fm = {
                "id": task["id"],
                "type": "task",
                "project_id": task["project_id"],
                "status": task["status"],
                "created_at": task["created_at"],
                "source": SOURCE,
            }
            files[f"{ROOT}/Tasks/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        for review in reviews:
            basename = review_map[review["id"]]
            asset_links = [
                _wiki_link("Assets", asset_map[a["id"]])
                for a in assets_by_review.get(review["id"], [])
            ]
            body = [
                f"# {review['review_date']} · {review['type']}",
                "",
                "## 今天做了什么",
                "",
                review.get("what_done") or "—",
                "",
                "## 卡住了什么",
                "",
                review.get("stuck") or "—",
                "",
                "## 下一步调整",
                "",
                review.get("next_adjust") or "—",
                "",
                "## 可沉淀内容",
                "",
                review.get("depositable") or "—",
                "",
                "## 关联资产",
                "",
            ]
            if asset_links:
                body.extend(f"- {link}" for link in asset_links)
            else:
                body.append("- （无）")
            fm = {
                "id": review["id"],
                "type": "review",
                "review_date": review["review_date"],
                "review_type": review["type"],
                "created_at": review["created_at"],
                "source": SOURCE,
            }
            files[f"{ROOT}/Reviews/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        for asset in assets:
            basename = asset_map[asset["id"]]
            review_line = "—"
            review_id = asset.get("source_review_id")
            if review_id and review_id in review_map:
                review_line = _wiki_link("Reviews", review_map[review_id])
            tags = asset.get("capability_tags") or []
            body = [
                f"# {asset['title']}",
                "",
                f"- **资产类型**：{asset['asset_type']}",
                f"- **能力标签**：{', '.join(tags) if tags else '—'}",
                f"- **来源复盘**：{review_line}",
                f"- **创建时间**：{asset['created_at']}",
                "",
                "## 触发情境",
                "",
                asset.get("trigger_context") or "—",
                "",
                "## 核心内容",
                "",
                asset.get("core_content") or "—",
                "",
            ]
            fm = {
                "id": asset["id"],
                "type": "asset",
                "asset_type": asset["asset_type"],
                "capability_tags": tags,
                "source_review_id": review_id,
                "created_at": asset["created_at"],
                "source": SOURCE,
            }
            files[f"{ROOT}/Assets/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        for entry in entries:
            basename = entry_map[entry["id"]]
            body = [
                f"# {entry['module']} · {entry['entry_date']}",
                "",
                f"- **层级**：{entry['level_type']}",
                f"- **来源项目**：{entry.get('source_project') or '—'}",
                f"- **创建时间**：{entry['created_at']}",
                "",
                "## 进展内容",
                "",
                entry.get("content") or "—",
                "",
            ]
            fm = {
                "id": entry["id"],
                "type": "capability_entry",
                "module": entry["module"],
                "entry_date": entry["entry_date"],
                "level_type": entry["level_type"],
                "created_at": entry["created_at"],
                "source": SOURCE,
            }
            files[f"{ROOT}/Capabilities/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            if not files:
                zf.writestr(f"{ROOT}/.gitkeep", "")
            for path, content in sorted(files.items()):
                zf.writestr(path, content.encode("utf-8"))
        buffer.seek(0)
        return buffer.getvalue()
    except database.ExportError as exc:
        raise ObsidianExportError(str(exc)) from exc
    except Exception as exc:
        raise ObsidianExportError("Obsidian 导出失败，请稍后重试") from exc