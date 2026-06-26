# 系统架构

## 概览

```
浏览器 (HTML/CSS/JS)
        ↓ HTTP
Flask (app.py) — 路由、模板、API
        ↓
database.py — SQLite CRUD、导入导出、资产迁移
asset_schemas.py — 资产类型与动态字段 schema
access_control.py — 家庭服务器远程 token 鉴权
ai_service.py — DeepSeek（可选）
inbox_service.py — 智能归档解析与确认入库
positioning_service.py — 战略定位锚/校准/目标变更建议
obsidian_export.py — Obsidian Markdown zip 导出
prompts/loader.py — 场景提示词加载
changelog.py — 版本日志
```

本地优先：数据默认存于 `data/yd_os.db`，不依赖云端。

## 后端（Flask）

- 入口：`personal-system-v2/app.py`
- 页面路由：首页、定位、目标、任务、复盘、资产、能力、智能归档、AI 管理、版本日志
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

## 个人 OS 闭环

```
战略定位（校准层）— 半自动增删改目标（建议 → 确认）
        ↓
目标 → 项目 → 任务 → 复盘 → 资产 → 能力
        ↑___________________________|
              运转数据反哺校准
```

资产系统处于复盘与能力之间：将执行与复盘中的经验沉淀为**可复用作战资产**，再通过能力标签关联到八能力模块。

## v1.19 新增：战略定位模块

**定位**：凌驾于目标之上的方向校准层，回答「此刻该往哪走、什么不该做」。默认态为态势面板（看战局），非空表单填写。

```
定位锚（positioning_anchor）
        ↓ 向下约束
校准轨迹（positioning_calibration）
        ↓ 产出建议
待确认目标变更（positioning_goal_action · pending）
        ↓ confirm（后续版本）
goals 表真实增删改（status 归档 / type 调整）
```

| 组件 | 职责 |
|------|------|
| `templates/positioning.html` + `static/js/positioning.js` | 三区页面：锚 / 轨迹 / pending |
| `positioning_service.py` | 业务封装，错误转 PositioningServiceError |
| `database.py` | 三表迁移、CRUD、goals.status 迁移 |
| `app.py` | `/positioning` 页面 + `/api/positioning/*` 路由 |

**API（v1.19.0）**：

- `GET/PUT /api/positioning/anchor`
- `GET/POST /api/positioning/calibrations`
- `GET /api/positioning/calibrations/<id>`
- `POST /api/positioning/calibrations/<id>/actions`（手填 pending）

**半自动范式**：复用 v1.11 inbox「AI/手填建议 → 人工确认 → 入库」；v1.19.0 仅 pending 只读展示，confirm/reject 与 AI suggest-actions 延后。

**导出**：JSON / Obsidian 含 positioning 数据 — 待后续版本补全（当前文档先行，实现见后续 commit）。

## v1.12 新增：可复用资产库

**定位**：从「知识卡片列表」升级为「可复用资产库」——沉淀可降低重复思考、沟通、试错与执行成本的内容。

**核心能力**：

| 能力 | 说明 |
|------|------|
| 多类型资产 | SOP、本质洞察、方法论、模型、提示词等 11 类 |
| 动态字段 | 按 `asset_type` 渲染不同表单字段，存入 `fields` JSON |
| 能力标签关联 | `capability_tags` 关联八能力模块 |
| 复用场景 | `reusable_scenario` 描述何时复用 |
| 成熟度管理 | 草稿 → 可用 → 稳定 → 标准化 |
| 复用次数 | `reuse_count` + `POST /api/assets/<id>/reuse` |
| AI 操作 | 优化、归类、转 SOP / 模型 / 方法论 / 提示词 |
| 筛选 | 资产类型 + 能力模块双层筛选 |
| 导出兼容 | JSON 备份与 Obsidian zip 均含 v1.12 资产字段 |

**模块分工**：

```
templates/assets.html + static/js/assets.js   # 表单、列表、筛选、AI 按钮
asset_schemas.py                              # 类型枚举、字段 schema、迁移辅助
database.py                                   # CRUD、_migrate_assets_table()、reuse 接口
ai_service.py                                 # optimize / classify / template 资产
obsidian_export.py                            # 资产 Markdown 可读化输出
```

### asset_schemas.py

集中管理资产体系的**类型枚举**、**动态字段结构**、**默认值**与**迁移辅助**：

- `ASSET_TYPES` / `MATURITY_LEVELS`：类型与成熟度枚举
- `TYPE_FIELD_DEFS` / `GENERIC_FIELD_DEFS`：各类型字段定义
- `get_frontend_schemas()`：供前端动态表单渲染
- `build_fields_from_legacy()` / `normalize_asset_type()`：旧知识卡片迁移
- `extract_summary()` / `extract_reusable_scenario()`：从 fields 派生展示字段

## v1.10 新增：知识库导出

- `obsidian_export.py`：将核心数据生成 Obsidian 友好 Markdown 并打包 zip
- API：`GET /api/export/obsidian.zip`
- 仅一向导出，不写用户本地 vault
- v1.12.0+：资产导出含 `asset_type`、`maturity`、`reuse_count`、`summary`、`reusable_scenario` 及 `fields` 结构化章节；frontmatter 补充 `asset_type`、`maturity`、`reuse_count`、`source_type`、`updated_at` 等

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
- v1.11.1 链式入库：同批 project 带 `local_ref`，task 带 `parent_ref`；commit 按 goal→project→task 顺序，task 自动挂到本批新建 project
- `override_payload`：前端可补充 `goal_id` / `project_id`，后端仅允许覆盖这两个关联字段
- 历史：`GET /api/inbox` 列表 + `/inbox/history` 详情
- 拒绝：`POST /api/inbox/suggestions/<id>/reject`

## v1.13 新增：家庭服务器远程访问 MVP

**定位**：家里电脑常开 + 手机通过 Tailscale 安全访问，为后续移动端快速记录打基础。

```
手机 (Tailscale) → tailnet → 家里电脑 PSY-1
                              ├── 127.0.0.1:5000 (默认)
                              ├── Tailscale Serve (推荐)
                              └── access_control token 鉴权
```

| 组件 | 职责 |
|------|------|
| `config.py` | `PERSONAL_OS_REMOTE` / `PERSONAL_OS_ACCESS_TOKEN` / `PERSONAL_OS_BIND_HOST` |
| `access_control.py` | 本机免验；远程校验 token（URL / Header / Cookie） |
| `static/js/access-token.js` | 解析 `?token=`，localStorage + API Header |
| `GET /api/health` | 健康检查（公开） |
| `scripts/backup-db.py` | SQLite 自动备份，保留 N 份 |
| `scripts/check-health.bat` | 本地健康探测 |

**安全默认值**：

- 监听 `127.0.0.1`，不默认 `0.0.0.0`
- 不推荐公网端口转发
- `PERSONAL_OS_BIND_HOST` 非 localhost 时必须 `PERSONAL_OS_REMOTE=1`

详见 [home-server.md](home-server.md)。