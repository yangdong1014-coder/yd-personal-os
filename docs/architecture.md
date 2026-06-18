# 系统架构

## 概览

```
浏览器 (HTML/CSS/JS)
        ↓ HTTP
Flask (app.py) — 路由、模板、API
        ↓
database.py — SQLite CRUD、导入导出
ai_service.py — DeepSeek（可选）
inbox_service.py — 智能归档解析与确认入库
prompts/loader.py — 场景提示词加载
changelog.py — 版本日志
```

本地优先：数据默认存于 `data/yd_os.db`，不依赖云端。

## 后端（Flask）

- 入口：`personal-system-v2/app.py`
- 页面路由：首页、目标、任务、复盘、资产、能力、智能归档、AI 管理、版本日志
- JSON API：CRUD、导入/导出、AI 代理、changelog
- 全局注入：`current_version`（来自 changelog）、`ai_enabled`

## 数据库（SQLite）

- 路径：`data/yd_os.db`（可通过 `YD_OS_DB_PATH` 覆盖）
- 连接启用 `PRAGMA foreign_keys = ON`
- 初始化：`database.init_db()`

## 前端

- 原生 HTML 模板 + `static/css/main.css`
- 按页加载 `static/js/*.js`，共用 `api.js`、`toast.js`、`main.js`
- 侧边栏：导航、JSON 备份导出、导入恢复、Obsidian zip 导出

## 提示词（Prompt Loader）

- 目录：`personal-system-v2/prompts/<module>/<scene>.system.txt`
- `prompts/loader.py`：读取、保存、scene 名校验、路径安全
- AI 管理页在线编辑，下次 AI 调用生效

## 版本机制（Changelog）

- 数据源：`personal-system-v2/changelog.json`
- `current` 为当前正式版号
- 页面徽章与 `/api/changelog` 均读取该字段
- README 不写死版本号，以 changelog 为准

## 测试与 CI

- 测试框架：pytest（`personal-system-v2/tests/`）
- 配置：`pytest.ini`（`pythonpath = .`）
- Fixture 使用临时数据库，不碰生产 `yd_os.db`
- CI：`.github/workflows/test.yml`，push/PR 到 `main` 时 Python 3.11 跑 pytest

## v1.10 新增：知识库导出

- `obsidian_export.py`：将核心数据生成 Obsidian 友好 Markdown 并打包 zip
- API：`GET /api/export/obsidian.zip`
- 仅一向导出，不写用户本地 vault

## v1.11 新增：智能归档 Inbox

```
用户输入原文 → POST /api/inbox/analyze → AI 结构化建议
        ↓
inbox_entries（原文）+ inbox_suggestions（候选）
        ↓ 用户预览勾选
POST /api/inbox/commit → 写入 goals/projects/tasks/reviews/assets/capability_entries
```

- 解析层：`inbox_service.py` + `prompts/inbox/analyze.*`
- 原则：AI 解析 → 人工确认 → 入库；不静默创建虚假目标/项目
- 可独立入库：goal、asset、review、capability_entry
- 外键约束：project 需有效 `goal_id`；task 需有效 `project_id`（均为数字 ID）
- AI 若返回项目名称而非 ID，commit 前校验跳过并返回明确 errors
- 批量归档支持部分成功：有效建议写入，无效建议保留 pending 并列出 errors
- 拒绝：`POST /api/inbox/suggestions/<id>/reject`