import io
import zipfile

import obsidian_export


def _read_zip(response_data):
    return zipfile.ZipFile(io.BytesIO(response_data), "r")


def test_export_obsidian_empty_database(client):
    response = client.get("/api/export/obsidian.zip")
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert "attachment" in response.headers.get("Content-Disposition", "")

    zf = _read_zip(response.data)
    names = zf.namelist()
    assert names == ["Obsidian/.gitkeep"] or any(
        n.startswith("Obsidian/") for n in names
    )


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

    for folder in (
        "Obsidian/Goals/",
        "Obsidian/Projects/",
        "Obsidian/Tasks/",
        "Obsidian/Reviews/",
        "Obsidian/Assets/",
        "Obsidian/Capabilities/",
    ):
        assert any(n.startswith(folder) and n.endswith(".md") for n in names)


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

    goal_file = next(n for n in zf.namelist() if n.startswith("Obsidian/Goals/"))
    goal_md = zf.read(goal_file).decode("utf-8")

    assert goal_md.startswith("---\n")
    assert "id:" in goal_md
    assert "type:" in goal_md
    assert "created_at:" in goal_md
    assert 'source: "yd-personal-os"' in goal_md or "source: yd-personal-os" in goal_md
    assert "[[Projects/" in goal_md


def test_sanitize_filename_removes_illegal_chars():
    assert obsidian_export.sanitize_filename('bad<>name', fallback="x") == "bad-name"
    assert obsidian_export.sanitize_filename("", fallback="untitled") == "untitled"
    assert obsidian_export.sanitize_filename("  hello   world  ") == "hello world"