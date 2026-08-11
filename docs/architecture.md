# 系统架构

## 概览

```
浏览器 (HTML/CSS/JS)
        ↓ HTTP
Flask (app.py) — 路由、模板、API
        ↓
database.py — SQLite CRUD、v2.2 ownership schema 与启动门禁
v22_migration.py — v2.1.4 legacy → staged v2.2 离线复制与完整性验证
asset_schemas.py — 资产类型与动态字段 schema
auth_repository.py — users 与登录状态数据访问
auth_service.py — 密码哈希、登录、锁定、账户状态与 auth_version
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
- 页面路由：登录、修改密码、用户管理及既有业务页面
- JSON API：CRUD、导入/导出、AI 代理、changelog
- Flask-Login session：每个请求从 `users` 重载账户，并验证 `is_active` 与 `auth_version`
- Flask-WTF CSRF：覆盖登录、退出、改密、管理 API 与全部既有写请求
- 全局注入：`current_version`（来自 changelog）、`ai_enabled`、`current_user`

## 数据库（SQLite）

- 路径：`data/yd_os.db`（可通过 `YD_OS_DB_PATH` 覆盖）
- 连接启用 `PRAGMA foreign_keys = ON`
- 初始化：`database.init_db()`
- `users` 承载身份；16 张个人业务表均以 `user_id NOT NULL` 标记所有者
- `init_db()` 只创建/验证空库或当前 v2.2 schema；检测到 legacy 表会 fail closed
- legacy 数据只能经 `scripts/migrate-v2.2-multiuser.py` 复制到新的 staged DB

## 前端

- 原生 HTML 模板 + `static/css/main.css`
- 按页加载 `static/js/*.js`，共用 `api.js`、`toast.js`、`main.js`；写请求统一携带 CSRF header
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

## v2.2 Phase 1（已关账）：账户与认证骨架

**定位**：先建立“当前用户是谁”的身份层。Phase 1 当时业务表尚无 `user_id`；Phase 2 增加所有权 schema，Phase 3 已完成运行期查询隔离并开放普通用户业务入口。

```
浏览器 → Flask session + CSRF → 每请求加载 users
                               ├── is_active=false：立即失效
                               ├── auth_version 不匹配：旧 session 失效
                               └── role=user：改密后进入本人 owner-scoped 业务空间
```

| 组件 | 职责 |
|------|------|
| `database.py` | Phase 1 时幂等创建 `users`；当前 ownership schema 见下方 Phase 2 |
| `auth_repository.py` | 用户查询、登录状态、密码与状态更新；bootstrap 使用原子事务；无删除接口 |
| `auth_service.py` | 规范化、Werkzeug 哈希、失败锁定、临时密码与普通用户管理规则 |
| `app.py` | Flask-Login、Flask-WTF、页面/API 权限、bootstrap CLI |
| `templates/login.html` / `change_password.html` / `admin_users.html` | 认证与最小管理界面 |
| `static/service-worker.js` | 升级时删除所有旧 cache，只缓存静态资源，所有 HTML navigation 与 API 绕过缓存 |

旧 `access_control.py` 与 `access-token.js` 已从 Phase 1 代码删除；URL、Header、Cookie token 均不再构成认证路径。`PERSONAL_OS_REMOTE` 是远程部署安全信号和非 localhost 绑定许可，所有来源（包括本机）都必须登录。管理员只能通过本地交互式 `bootstrap-admin` 命令原子初始化；管理 API 只能创建 `user`。

Phase 1.1 曾在 Repository 隔离完成前以 `403 business_access_pending` 对普通用户 fail closed。Phase 3 关账后该临时业务门禁已移除；首次临时密码仍必须修改，普通用户访问管理端点仍返回 `403 admin_required`。退出会递增当前账户 `auth_version`，因此等价于撤销该账户全部现有 session。PWA 在 bfcache 恢复认证页面时会先隐藏文档并向服务器重新校验 session，失败或离线时不重新展示私人页面。

运行模式采用显式开发、默认加固：只有 `PERSONAL_OS_ENV=development`、loopback 且非远程时允许临时密钥与本地 debug；环境缺失/未知、production、remote 或非 loopback 任一情况都进入统一生产安全校验。

## v2.2 Phase 2（本地开发）：数据所有权 Schema + Migration

16 张个人业务表统一增加 `user_id INTEGER NOT NULL REFERENCES users(id)` 与前导索引。`project → goal`、`task → project`、`positioning_goal_action → calibration`、`inbox_suggestion → inbox_entry` 使用包含 `user_id` 的复合外键，直接阻断跨用户父子关联；可空 `SET NULL` 关系和已知多态关系由触发器校验 owner。所有业务行的 `user_id` 创建后不可修改。

`positioning_anchor` 使用 `UNIQUE(user_id)`，从“全库最新一行”升级为每用户一行。主线降级、训练路径排序和定位锚读写均按 owner 工作；`init_db()` 不再 seed、归一化或重写任何既有业务行。创建账户时只在同一用户、同一事务内 seed 默认 `capability_practice_steps`。

普通应用启动不会把 legacy 行绑定管理员。`v22_migration.py` 只读打开 v2.1.4 源库，在目标目录创建临时 staged DB，创建唯一 admin 后逐表原样复制 16 表并赋予该 admin；字段、ID、时间、JSON 与 `sqlite_sequence` 全部通过双向 EXCEPT、integrity/FK/孤儿检查后，才原子发布 staged 文件。源库与目标相同、目标已存在、源 schema 不匹配、单例冲突或任何验证失败都会停止。

Phase 2 的交付边界止于 schema 与 staged migration；运行期 owner scope 由下方 Phase 3 完成。

## v2.2 Phase 3（本地开发）：运行期多用户隔离

请求认证上下文中的 `current_user.id` 是业务 owner 的唯一来源。`app.py` 将其显式传入 Service 与 Repository；所有业务 Repository API 的 `user_id` 均为必填参数，无默认值。Create 强制写当前 owner，list/lookup/CRUD 使用 `user_id` 条件，跨 owner 的 get/update/delete 统一表现为 not found，admin 不绕过私人业务数据 owner。

Dashboard、价值链、能力汇总、recent/ranking/count、主线与训练路径 normalization 均从 owner-scoped 列表或 SQL 构建。所有硬关联、软关联、Inbox `suggested_payload` 引用和 Positioning 目标引用都校验同 owner；删除 goal 前会先清理其级联 projects 的同 owner 多态软引用，避免 feedback/deliberation 孤儿。

JSON Export 只输出当前用户的 16 张业务表，不输出 `users`、认证字段或内部 `user_id`。Import 忽略输入 owner，以当前用户强制落库；preview 与实际导入共用映射计划，主键命中其他用户时改用新 ID，并同步重映射父子、多态、Positioning 和 Inbox payload 引用，绝不更新冲突 owner 的记录。Obsidian、Inbox、Deliberation、Positioning 与全部读取业务数据的 AI context 同样显式接收 `user_id`。

普通用户在完成首次改密后使用与 admin 相同的 PSY 业务结构，但只看到自己的个人空间；新账户的业务数据为空，仅拥有本人的默认 capability practice steps。生产仍保持 v2.1.4，Phase 3 不包含生产 migration、发布或部署。

详见 [home-server.md](home-server.md) 与 [development-guide.md](development-guide.md)。
