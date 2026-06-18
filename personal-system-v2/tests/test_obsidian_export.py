import io
import zipfile

import database
import obsidian_export


def _read_zip(response_data):
    return zipfile.ZipFile(io.BytesIO(response_data), "r")


def _read_md(zf, path):
    return zf.read(path).decode("utf-8")


def _assert_export_version(content):
    assert "export_version:" in content
    assert "v1.10.1" in content


STRUCTURE_FILES = (
    "Obsidian/README.md",
    "Obsidian/00-Index.md",
    "Obsidian/Goals/Goals Index.md",
    "Obsidian/Projects/Projects Index.md",
    "Obsidian/Tasks/Tasks Index.md",
    "Obsidian/Reviews/Reviews Index.md",
    "Obsidian/Assets/Assets Index.md",
    "Obsidian/Capabilities/Capabilities Index.md",
)


def test_export_obsidian_empty_database(client):
    response = client.get("/api/export/obsidian.zip")
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert "attachment" in response.headers.get("Content-Disposition", "")

    zf = _read_zip(response.data)
    names = zf.namelist()
    for path in STRUCTURE_FILES:
        assert path in names

    readme = _read_md(zf, "Obsidian/README.md")
    assert "yd-personal-os" in readme
    assert "一向导出" in readme

    root_index = _read_md(zf, "Obsidian/00-Index.md")
    assert "YD Personal OS Export" in root_index
    assert "[[Goals/Goals Index]]" in root_index

    goals_index = _read_md(zf, "Obsidian/Goals/Goals Index.md")
    assert "（暂无条目）" in goals_index


def test_export_obsidian_zip_structure(client):
    goal = client.post(
        "/api/goals",
        json={"name": "Obsidian目标", "type": "年度"},
    ).get_json()["data"]
    project = client.post(
        "/api/projects",
        json={"goal_id": goal["id"], "name": "Obsidian项目"},
    ).get_json()["data"]
    client.post(
        "/api/tasks",
        json={"project_id": project["id"], "name": "Obsidian任务"},
    )
    client.post(
        "/api/reviews",
        json={
            "review_date": "2026-06-18",
            "type": "每日",
            "what_done": "做了事",
            "stuck": "",
            "next_adjust": "",
            "depositable": "可沉淀",
        },
    )
    client.post(
        "/api/assets",
        json={
            "title": "Obsidian资产",
            "trigger_context": "情境",
            "core_content": "内容",
            "asset_type": "知识卡片",
            "capability_tags": ["本质力"],
        },
    )
    client.post(
        "/api/capability-entries",
        json={
            "module": "本质力",
            "entry_date": "2026-06-18",
            "content": "能力进展",
            "source_project": "",
            "level_type": "能力层",
        },
    )

    response = client.get("/api/export/obsidian.zip")
    assert response.status_code == 200
    zf = _read_zip(response.data)
    names = zf.namelist()

    for path in STRUCTURE_FILES:
        assert path in names

    for folder in (
        "Obsidian/Goals/",
        "Obsidian/Projects/",
        "Obsidian/Tasks/",
        "Obsidian/Reviews/",
        "Obsidian/Assets/",
        "Obsidian/Capabilities/",
    ):
        assert any(
            n.startswith(folder) and n.endswith(".md") and "Index" not in n
            for n in names
        )


def test_export_obsidian_frontmatter_and_links(client):
    goal = client.post(
        "/api/goals",
        json={"name": "链接目标", "type": "季度"},
    ).get_json()["data"]
    client.post(
        "/api/projects",
        json={"goal_id": goal["id"], "name": "链接项目"},
    )

    response = client.get("/api/export/obsidian.zip")
    zf = _read_zip(response.data)

    goal_file = next(
        n
        for n in zf.namelist()
        if n.startswith("Obsidian/Goals/") and "Index" not in n
    )
    goal_md = _read_md(zf, goal_file)

    assert goal_md.startswith("---\n")
    assert "id:" in goal_md
    assert "type:" in goal_md
    assert "created_at:" in goal_md
    assert 'source: "yd-personal-os"' in goal_md or "source: yd-personal-os" in goal_md
    _assert_export_version(goal_md)
    assert "[[Projects/" in goal_md


def test_export_obsidian_index_lists_entity_links(client):
    goal = client.post(
        "/api/goals",
        json={"name": "索引目标", "type": "年度"},
    ).get_json()["data"]
    client.post(
        "/api/projects",
        json={"goal_id": goal["id"], "name": "索引项目"},
    )

    response = client.get("/api/export/obsidian.zip")
    zf = _read_zip(response.data)

    goals_index = _read_md(zf, "Obsidian/Goals/Goals Index.md")
    assert "[[Goals/索引目标]]" in goals_index

    projects_index = _read_md(zf, "Obsidian/Projects/Projects Index.md")
    assert "[[Projects/索引项目]]" in projects_index


def test_export_obsidian_duplicate_names_get_suffix(client):
    client.post("/api/goals", json={"name": "重复名称", "type": "年度"})
    client.post("/api/goals", json={"name": "重复名称", "type": "季度"})

    response = client.get("/api/export/obsidian.zip")
    zf = _read_zip(response.data)
    names = zf.namelist()

    goal_files = [
        n
        for n in names
        if n.startswith("Obsidian/Goals/") and n.endswith(".md") and "Index" not in n
    ]
    basenames = {n.split("/")[-1].removesuffix(".md") for n in goal_files}
    assert "重复名称" in basenames
    assert "重复名称-2" in basenames

    goals_index = _read_md(zf, "Obsidian/Goals/Goals Index.md")
    assert "[[Goals/重复名称]]" in goals_index
    assert "[[Goals/重复名称-2]]" in goals_index

    first_goal = _read_md(zf, "Obsidian/Goals/重复名称.md")
    second_goal = _read_md(zf, "Obsidian/Goals/重复名称-2.md")
    assert first_goal.startswith("---\n")
    assert second_goal.startswith("---\n")


def test_export_obsidian_duplicate_name_links_match_final_filename(client):
    goal = client.post(
        "/api/goals",
        json={"name": "同名目标", "type": "年度"},
    ).get_json()["data"]
    client.post(
        "/api/projects",
        json={"goal_id": goal["id"], "name": "同名项目"},
    )
    second_goal = client.post(
        "/api/goals",
        json={"name": "同名目标", "type": "季度"},
    ).get_json()["data"]
    client.post(
        "/api/projects",
        json={"goal_id": second_goal["id"], "name": "同名项目"},
    )

    response = client.get("/api/export/obsidian.zip")
    zf = _read_zip(response.data)

    first_project = _read_md(zf, "Obsidian/Projects/同名项目.md")
    second_project = _read_md(zf, "Obsidian/Projects/同名项目-2.md")

    assert "[[Goals/同名目标]]" in first_project
    assert "[[Goals/同名目标-2]]" in second_project


def test_export_obsidian_empty_title_and_illegal_chars_fallback(client):
    backup = {
        "meta": {
            "exported_at": "2026-06-18 00:00:00",
            "version": "1.0",
            "tables": list(database.IMPORT_TABLES),
        },
        "goals": [
            {"id": 1, "name": "", "type": "年度", "created_at": "2026-06-18 00:00:00"}
        ],
        "projects": [
            {
                "id": 1,
                "goal_id": 1,
                "name": "bad<>name",
                "created_at": "2026-06-18 00:00:00",
            }
        ],
        "tasks": [],
        "reviews": [],
        "assets": [],
        "capability_entries": [],
    }
    client.post("/api/import", json=backup)
    goal = {"id": 1}

    response = client.get("/api/export/obsidian.zip")
    zf = _read_zip(response.data)
    names = zf.namelist()

    goal_file = next(
        n
        for n in names
        if n.startswith("Obsidian/Goals/") and n.endswith(".md") and "Index" not in n
    )
    assert f"Untitled Goal {goal['id']}" in goal_file

    project_file = next(
        n
        for n in names
        if n.startswith("Obsidian/Projects/") and n.endswith(".md") and "Index" not in n
    )
    assert "bad-name.md" in project_file

    goal_md = _read_md(zf, goal_file)
    assert f"Untitled Goal {goal['id']}" in goal_md


def test_export_obsidian_frontmatter_export_version(client):
    client.post("/api/goals", json={"name": "版本目标", "type": "年度"})

    response = client.get("/api/export/obsidian.zip")
    zf = _read_zip(response.data)

    for path in zf.namelist():
        if not path.endswith(".md") or "Index" in path or path.endswith("README.md"):
            continue
        if path == "Obsidian/00-Index.md":
            continue
        content = _read_md(zf, path)
        _assert_export_version(content)


def test_sanitize_filename_removes_illegal_chars():
    assert obsidian_export.sanitize_filename('bad<>name', fallback="x") == "bad-name"
    assert obsidian_export.sanitize_filename("", fallback="untitled") == "untitled"
    assert obsidian_export.sanitize_filename("  hello   world  ") == "hello world"
    assert obsidian_export.sanitize_filename("中文标题") == "中文标题"


def test_untitled_fallback_includes_entity_id():
    assert obsidian_export._untitled_fallback("goal", 42) == "Untitled Goal 42"
    assert obsidian_export._untitled_fallback("task", 7) == "Untitled Task 7"