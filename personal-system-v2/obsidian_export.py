import io
import json
import re
import zipfile
from datetime import datetime

import database

SOURCE = "yd-personal-os"
EXPORT_VERSION = "v1.12.0"
ROOT = "Obsidian"
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE = re.compile(r"\s+")

FOLDERS = (
    "Goals",
    "Projects",
    "Tasks",
    "Reviews",
    "Assets",
    "Capabilities",
)

INDEX_BASENAMES = {
    "Goals": "Goals Index",
    "Projects": "Projects Index",
    "Tasks": "Tasks Index",
    "Reviews": "Reviews Index",
    "Assets": "Assets Index",
    "Capabilities": "Capabilities Index",
}


class ObsidianExportError(Exception):
    pass


def zip_filename():
    return datetime.now().strftime("obsidian_export_%Y%m%d_%H%M%S.zip")


def _untitled_fallback(entity_type, entity_id):
    labels = {
        "goal": "Goal",
        "project": "Project",
        "task": "Task",
        "review": "Review",
        "asset": "Asset",
        "capability": "Capability",
    }
    return f"Untitled {labels[entity_type]} {entity_id}"


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


def _base_frontmatter(entity_id, entity_type, created_at, **optional):
    fields = {
        "id": entity_id,
        "type": entity_type,
        "source": SOURCE,
        "created_at": created_at,
        "export_version": EXPORT_VERSION,
    }
    for key, value in optional.items():
        if value is not None and value != "":
            fields[key] = value
    return fields


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


def _build_link_maps(registry, goals, projects, tasks, reviews, assets, entries):
    goal_map = {
        g["id"]: registry.assign(
            "Goals", g["name"], _untitled_fallback("goal", g["id"])
        )
        for g in goals
    }
    project_map = {
        p["id"]: registry.assign(
            "Projects", p["name"], _untitled_fallback("project", p["id"])
        )
        for p in projects
    }
    task_map = {
        t["id"]: registry.assign(
            "Tasks", t["name"], _untitled_fallback("task", t["id"])
        )
        for t in tasks
    }
    review_map = {
        r["id"]: registry.assign(
            "Reviews",
            f"{r['review_date']}-{r['type']}",
            _untitled_fallback("review", r["id"]),
        )
        for r in reviews
    }
    asset_map = {
        a["id"]: registry.assign(
            "Assets", a["title"], _untitled_fallback("asset", a["id"])
        )
        for a in assets
    }
    entry_map = {
        e["id"]: registry.assign(
            "Capabilities",
            f"{e['module']}-{e['entry_date']}",
            _untitled_fallback("capability", e["id"]),
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


def _export_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _build_readme(export_time):
    body = [
        "# YD Personal OS — Obsidian 导出包",
        "",
        f"- **导出来源**：{SOURCE}",
        f"- **导出时间**：{export_time}",
        "- **数据范围**：Goals、Projects、Tasks、Reviews、Assets、Capabilities",
        "",
        "## 使用方式",
        "",
        "将本 zip 中 `Obsidian/` 文件夹内的内容复制或解压到你的 Obsidian vault。",
        "建议放在独立子目录（如 `YD-OS-Export/`），便于与手写笔记区分。",
        "",
        "入口建议从 `00-Index.md` 开始浏览。",
        "",
        "## 重要限制",
        "",
        "- 当前为**一向导出**（系统 → Obsidian），不会自动同步回 yd-personal-os",
        "- 不会自动删除 Obsidian 中的旧文件；重复导出可能产生同名旁路文件（系统自动加 `-2`、`-3` 后缀）",
        "- 在 Obsidian 中**手动改名**可能导致 `[[内部链接]]` 断开",
        "- 同名实体在导出时会自动加后缀，正文链接已指向最终文件名",
        "",
        f"- **导出版本**：{EXPORT_VERSION}",
        "",
    ]
    return "\n".join(body)


def _build_root_index(export_time):
    body = [
        "# YD Personal OS Export",
        "",
        f"导出时间：{export_time}",
        "",
        "## 模块入口",
        "",
    ]
    for folder in FOLDERS:
        index_name = INDEX_BASENAMES[folder]
        body.append(f"- {_wiki_link(folder, index_name)}")
    body.append("")
    return "\n".join(body)


def _build_folder_index(folder, basenames):
    index_title = INDEX_BASENAMES[folder]
    body = [
        f"# {index_title}",
        "",
    ]
    if basenames:
        for basename in sorted(basenames, key=str.lower):
            body.append(f"- {_wiki_link(folder, basename)}")
    else:
        body.append("- （暂无条目）")
    body.append("")
    return "\n".join(body)


def _add_structure_files(files, export_time, folder_basenames):
    files[f"{ROOT}/README.md"] = _build_readme(export_time)
    files[f"{ROOT}/00-Index.md"] = _build_root_index(export_time)
    for folder in FOLDERS:
        index_name = INDEX_BASENAMES[folder]
        basenames = folder_basenames.get(folder, [])
        files[f"{ROOT}/{folder}/{index_name}.md"] = _build_folder_index(
            folder, basenames
        )


def build_obsidian_zip():
    try:
        export_time = _export_timestamp()

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
        folder_basenames = {folder: [] for folder in FOLDERS}

        for goal in goals:
            basename = goal_map[goal["id"]]
            folder_basenames["Goals"].append(basename)
            links = [
                _wiki_link("Projects", project_map[p["id"]])
                for p in projects_by_goal.get(goal["id"], [])
            ]
            body = [
                f"# {goal['name'] or _untitled_fallback('goal', goal['id'])}",
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
            fm = _base_frontmatter(goal["id"], "goal", goal["created_at"])
            files[f"{ROOT}/Goals/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        goal_name_by_id = {g["id"]: g["name"] for g in goals}

        for project in projects:
            basename = project_map[project["id"]]
            folder_basenames["Projects"].append(basename)
            goal_link = _wiki_link("Goals", goal_map[project["goal_id"]])
            task_links = [
                _wiki_link("Tasks", task_map[t["id"]])
                for t in tasks_by_project.get(project["id"], [])
            ]
            goal_name = goal_name_by_id.get(project["goal_id"], "")
            body = [
                f"# {project['name'] or _untitled_fallback('project', project['id'])}",
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
            fm = _base_frontmatter(
                project["id"],
                "project",
                project["created_at"],
                related_goal_id=project["goal_id"],
            )
            files[f"{ROOT}/Projects/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        project_name_by_id = {p["id"]: p["name"] for p in projects}

        for task in tasks:
            basename = task_map[task["id"]]
            folder_basenames["Tasks"].append(basename)
            project_link = _wiki_link("Projects", project_map[task["project_id"]])
            project_name = project_name_by_id.get(task["project_id"], "")
            progress = ""
            if task.get("today_progress") == 1 and task.get("today_progress_date"):
                progress = f"- **今日推进**：{task['today_progress_date']}\n"
            body = [
                f"# {task['name'] or _untitled_fallback('task', task['id'])}",
                "",
                f"- **状态**：{task['status']}",
                f"- **所属项目**：{project_link}（{project_name}）",
                f"- **创建时间**：{task['created_at']}",
                progress.rstrip(),
                "",
            ]
            body = [line for line in body if line != ""]
            fm = _base_frontmatter(
                task["id"],
                "task",
                task["created_at"],
                status=task["status"],
                related_project_id=task["project_id"],
            )
            files[f"{ROOT}/Tasks/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        for review in reviews:
            basename = review_map[review["id"]]
            folder_basenames["Reviews"].append(basename)
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
            fm = _base_frontmatter(review["id"], "review", review["created_at"])
            files[f"{ROOT}/Reviews/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        for asset in assets:
            basename = asset_map[asset["id"]]
            folder_basenames["Assets"].append(basename)
            review_line = "—"
            review_id = asset.get("source_review_id")
            if review_id and review_id in review_map:
                review_line = _wiki_link("Reviews", review_map[review_id])
            tags = asset.get("capability_tags") or []
            capability = ", ".join(tags) if tags else None
            fields = asset.get("fields") or {}
            body = [
                f"# {asset['title'] or _untitled_fallback('asset', asset['id'])}",
                "",
                f"- **资产类型**：{asset['asset_type']}",
                f"- **成熟度**：{asset.get('maturity') or '—'}",
                f"- **复用次数**：{asset.get('reuse_count', 0)}",
                f"- **能力标签**：{', '.join(tags) if tags else '—'}",
                f"- **来源复盘**：{review_line}",
                f"- **来源类型**：{asset.get('source_type') or '—'}",
                f"- **创建时间**：{asset['created_at']}",
                f"- **更新时间**：{asset.get('updated_at') or asset['created_at']}",
                "",
                "## 简要说明",
                "",
                asset.get("summary") or "—",
                "",
                "## 复用场景",
                "",
                asset.get("reusable_scenario") or "—",
                "",
            ]
            if fields:
                body.extend(["## 结构化字段", ""])
                for key, value in fields.items():
                    if value:
                        body.extend([f"### {key}", "", str(value), ""])
            else:
                body.extend(
                    [
                        "## 触发情境",
                        "",
                        asset.get("trigger_context") or "—",
                        "",
                        "## 核心内容",
                        "",
                        asset.get("core_content") or "—",
                        "",
                    ]
                )
            fm = _base_frontmatter(
                asset["id"],
                "asset",
                asset["created_at"],
                asset_type=asset.get("asset_type"),
                maturity=asset.get("maturity"),
                reuse_count=asset.get("reuse_count"),
                source_review_id=review_id,
                source_type=asset.get("source_type"),
                updated_at=asset.get("updated_at"),
                capability=capability,
            )
            files[f"{ROOT}/Assets/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        for entry in entries:
            basename = entry_map[entry["id"]]
            folder_basenames["Capabilities"].append(basename)
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
            fm = _base_frontmatter(
                entry["id"],
                "capability_entry",
                entry["created_at"],
                capability=entry.get("module"),
            )
            files[f"{ROOT}/Capabilities/{basename}.md"] = (
                _frontmatter(fm) + "\n\n" + "\n".join(body) + "\n"
            )

        _add_structure_files(files, export_time, folder_basenames)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, content in sorted(files.items()):
                zf.writestr(path, content.encode("utf-8"))
        buffer.seek(0)
        return buffer.getvalue()
    except database.ExportError as exc:
        raise ObsidianExportError(str(exc)) from exc
    except Exception as exc:
        raise ObsidianExportError("Obsidian 导出失败，请稍后重试") from exc