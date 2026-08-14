# 个人能力操作系统 v2

低成本、低维护的个人操作系统。Flask + SQLite + 原生 HTML/CSS/JS，可选接入 DeepSeek API；当前正式部署方向是复用阿里云 ECS，通过正常域名与公网 HTTPS 从任意联网设备访问。

**当前版本以 `changelog.json` 的 `current` 字段与页面版本徽章为准**（无需在 README 手动维护具体版号）。

## 主要模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 首页 | `/` | 指挥部总览、AI 今日简报、AI 行动分发 |
| 推演 | `/deliberations` | 独立判断、AI 对抗、最终决策、现实反馈与原则沉淀 |
| 目标 | `/goals` | 目标管理、项目拆解、AI 拆解项目 |
| 任务 | `/tasks` | 任务管理、今日推进、AI 拆任务/今日推荐 |
| 复盘 | `/reviews` | 日复盘/周复盘、AI 补全、周聚合、AI 提炼资产 |
| 资产 | `/assets` | 可复用资产库（多类型 + 动态字段）、AI 优化/归类/类型转换 |
| 能力 | `/capabilities` | 八能力模块记录、AI 归因/诊断 |
| AI管理 | `/prompts` | 模型切换、提示词编辑、AI 生成初版 |
| 版本日志 | `/changelog` | 各版本更新记录 |

## 启动

```bash
cd personal-system-v2
pip install -r requirements.txt
cp .env.example .env   # 编辑 .env，填入 DEEPSEEK_API_KEY
python app.py
```

浏览器访问 http://127.0.0.1:5000

本机开发的 `.env` 必须显式设置 `PERSONAL_OS_ENV=development`。缺失或未知环境值不能隐式退化为 debug；远程/加固运行还必须精确声明 `PERSONAL_OS_ENV=production`，否则拒绝启动。

### v2.2 Phase 4.1 生产入口（仅本地完成，尚未部署）

```text
联网设备 → 正常域名 / 公网 HTTPS → Nginx → loopback Gunicorn → Flask → SQLite
```

生产或远程运行禁止使用 `python app.py` 或直接调用 Gunicorn。必须由 active release launcher 以批准的版本、commit 和路径根进入；只读诊断示例见 `docs/development-guide.md`。

`production_launcher.py` 是正式稳定入口：它只从 active release pointer 解析 descriptor 绑定的 code/config/DB，校验 hash/manifest 后运行所选 `production.py --check`，再无 shell 地 exec 固定 Gunicorn 命令。`production.py` 不创建或迁移数据库；Gunicorn 通过零参数 `production:create_production_app()` 在同一进程、监听前复验 release context、当前 v2.2 schema、integrity、外键和唯一启用管理员，失败即退出。`gunicorn.conf.py` 将 MVP 固定为 loopback、1 worker、gthread/4 threads 与 preload；应用只接受精确一跳代理覆盖提供的 `X-Forwarded-For`、`X-Forwarded-Proto=https`、白名单 `X-Forwarded-Host` 和独立强随机 `X-PSY-Proxy-Token`。除本机最小健康检查外，直连应用或伪造/多跳转发头都会拒绝。

本步骤只建立本地生产运行时门禁，尚未执行真实 Nginx/systemd/ECS、数据库切换、发布或部署。Phase 5A 必须先做独立 ECS shadow 并完成公网 HTTPS 与真实浏览器验收，获得人工批准后才可进入 Phase 5B 正式切换。MFA 不在当前 P0 范围。

首次使用前设置持久 `SECRET_KEY`，并通过本地交互式命令初始化唯一管理员：

```bash
python -m flask --app app bootstrap-admin
```

密码采用隐藏输入且不会回显。初始化后访问 `/login`；本机与远程请求都必须登录。

### 桌面快捷方式（Windows）

**创建 / 重建快捷方式**（升级后若仍出现黑框，请重新执行一次）：

```
双击 scripts/create-desktop-shortcut.vbs
```

或在项目根目录执行：

```bash
python scripts/create_desktop_shortcut.py
```

桌面会出现「个人能力操作系统」快捷方式，指向 `scripts/start-server.vbs`。

**启动行为**：

| 方式 | 说明 |
|------|------|
| 桌面快捷方式 | 后台无黑框启动，自动打开浏览器；关闭任何窗口**不会**停止服务 |
| `scripts/start-server.bat` | 开发调试模式，有黑框；**关闭黑框即停止服务** |
| 开机自启 | 运行 `scripts/install-startup.vbs`，同样使用后台模式 |

后台启动时设置 `PERSONAL_OS_BG=1`，Flask 关闭 debug 与热重载；服务仅监听 `127.0.0.1:5000`。

**停止服务**：

```
双击 scripts/stop-server.bat
```

停止后 `http://127.0.0.1:5000` 不可访问。需要再次使用时，重新点击桌面快捷方式即可。

**健康检查**：`scripts/check-health.bat` 或访问 `GET /api/health`。

### 历史方案：家庭服务器与 Tailscale（v1.13+）

旧版本曾把家里常开电脑作为服务器并通过 Tailscale 访问。该路线只保留为历史资料，不是 v2.2 当前部署方案，也不再要求 VPN、本地 CA 或本地 TLS 模拟环境。

历史细节见 [docs/home-server.md](../docs/home-server.md)。当前执行方向以 [架构说明](../docs/architecture.md) 与 [Phase 5 Runbook](../docs/phase-5-database-cutover-runbook.md) 为准。

旧共享 token 的 URL、Header、Cookie 与 localStorage 路径已移除；无论本机或远程都只接受账号密码建立的用户 session。`PERSONAL_OS_REMOTE` 是远程可达的显式安全信号，不是第二套鉴权。`PERSONAL_OS_PROXY_TOKEN` 只保护 Nginx→Flask 的内部代理信任边界，也不是用户登录凭据。

**数据库备份**：

```bash
python ../scripts/backup-db.py --help
```

数据库备份命令不再含指向真实数据库的默认路径。生产备份、manifest 验证、staged migration、release pointer 与完整回滚顺序见 [`docs/phase-5-database-cutover-runbook.md`](../docs/phase-5-database-cutover-runbook.md)；Phase 4.2 只在 fixture/临时数据库演练，不执行真实切换。

备份目录必须通过 `--backup-dir` 显式指定且预先存在；工具不自动裁剪历史备份。

**v2.2 Phase 2 staged migration（仅本地开发/发布准备，不切生产）**：

```bash
python scripts/migrate-v2.2-multiuser.py LEGACY.db STAGED.db \
  --admin-username admin --admin-email admin@example.com
python scripts/verify-v2.2-migration.py LEGACY.db STAGED.db
```

源库只读、目标必须是不存在的新文件；16 张业务表的 ID、字段、时间、JSON、外键与 `sqlite_sequence` 均逐表校验。普通 `init_db()` 遇到 legacy schema 会停止，不会自动绑定管理员。完整安全流程见 [开发指南](../docs/development-guide.md#v22-离线-staged-migration)。

## 配置职责与环境变量

项目根目录 `.env`（参考 `.env.example`）只用于本机开发。生产必须按职责分离：

- `deploy/launcher.env.example`：只承载获批准的 app version 与 git commit 元数据；
- `deploy/runtime.env.example`：承载生产安全变量，禁止包含 `YD_OS_DB_PATH` 或 Gunicorn 覆盖项；
- release descriptor：绑定 code/config/DB/manifest，`production_launcher.py` 校验后注入生产 `YD_OS_DB_PATH`；
- `deploy/psy-v22.service`：调用 launcher，不能绕过它直接运行 `production.py` 或 Gunicorn。

下表是变量职责总览，不表示所有变量都应写入项目 `.env`：

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | 是（AI 功能） | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | 否 | API 地址，默认 `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | 否 | 锁定模型；设置后 AI管理页不可改 |
| `DEEPSEEK_TIMEOUT` | 否 | 超时秒数，默认 60 |
| `SECRET_KEY` | 加固运行必填 | Flask session 签名密钥，至少 32 字节并通过弱值/熵校验 |
| `PERSONAL_OS_ENV` | 是 | 本机开发精确设 `development`，生产/远程精确设 `production`；缺失/未知值拒绝运行 |
| `PERSONAL_OS_REMOTE` | 远程运行必填 | 远程可达安全信号，不承担鉴权或放宽监听地址 |
| `PERSONAL_OS_BIND_HOST` | 否 | 默认 `127.0.0.1`；加固运行禁止非 loopback 绑定 |
| `YD_OS_DB_PATH` | launcher 注入 | 本地开发/测试可指向临时库；生产禁止写入 runtime env，由 descriptor 绑定 |
| `PERSONAL_OS_TRUSTED_HOSTS` | 生产必填 | 逗号分隔的精确公网 DNS 名/IP；禁止通配符、URL 与端口 |
| `PERSONAL_OS_TRUSTED_PROXY` | 生产必填 | 直接连接应用的唯一精确 loopback 代理 IP |
| `PERSONAL_OS_PROXY_TOKEN` | 生产必填 | Nginx→Flask 内部强随机 token，必须与 `SECRET_KEY` 不同；不是用户认证凭据 |
| `PERSONAL_OS_BG` | 否 | 仅关闭正常本地开发的 debug/reloader，不能降低生产安全配置 |

未配置 `DEEPSEEK_API_KEY` 时，CRUD 功能正常，AI 按钮不可用。

> **安全提示**：远程使用必须设置生产/远程信号、强 `SECRET_KEY`、精确 Host/代理信任并使用 HTTPS；不要将 5000 端口直接暴露。Phase 3 已完成 owner-scoped Repository/Service/AI 隔离并开放普通用户个人空间；Phase 4.1 的代码仍未部署，正式生产状态不因本地实现而改变。

## 数据文件

| 路径 | 说明 |
|------|------|
| `data/yd_os.db` | 既有真实数据库路径（git 忽略）；开发、测试和 shadow 禁止访问，v2.2 生产使用 descriptor 绑定的外置数据库路径 |
| `data/settings.json` | AI 模型选择（git 忽略） |
| `prompts/` | AI 场景提示词（可经 AI管理页编辑） |
| `changelog.json` | 版本日志数据源 |

## 数据导出与导入

导航栏右侧「导出备份」按钮，或请求 `GET /api/export`，下载 JSON 备份。

「导出 Obsidian」按钮或 `GET /api/export/obsidian.zip`，下载 Obsidian 友好 Markdown zip（一向导出，需手动解压到 vault，不自动写入本地目录）。详见 [obsidian-sync-plan.md](../docs/obsidian-sync-plan.md)。

### 智能归档 Inbox（v1.11）

导航「智能归档」或访问 `/inbox`：粘贴一段非结构化文字，AI 解析为归档建议（目标、项目、任务、复盘、知识卡片、能力记录等），**预览确认后**才批量入库。

- `POST /api/inbox/analyze` — AI 解析，保存原文与建议项
- `GET /api/inbox/<id>` — 查看某次输入及建议
- `POST /api/inbox/commit` — 勾选建议后批量写入对应模块
- `POST /api/inbox/suggestions/<id>/reject` — 拒绝单条建议

**数据安全**：遵循「AI 解析 → 人工确认 → 入库」；AI 不会静默写入数据库；低置信度（&lt;60%）建议默认不勾选；已入库建议不会重复创建。

**已知边界**：

| 类型 | 入库要求 |
|------|----------|
| goal / asset / review / capability_entry | 可独立入库 |
| project | 需要有效 `goal_id`（已存在目标的数字 ID） |
| task | 需要有效 `project_id`（已存在项目的数字 ID） |

- AI 可能返回项目名称而非数字 ID，系统会**跳过该建议**并在页面展示原因，不会静默创建虚假目标或项目。
- 批量归档支持**部分成功**：可入库项正常写入，无效项返回 errors，不再因一条失败导致全部回滚。
- 任务型内容建议先手动创建目标/项目，或分步归档（先 goal → 再 project → 再 task）。
- v1.11.1+：同批 project/task 可通过 `local_ref` / `parent_ref` 链式入库；卡片上可选择已有目标/项目；`POST /api/inbox/commit` 支持 `override_payload` 补充 `goal_id` / `project_id`。
- 归档历史：`GET /api/inbox` 或页面 `/inbox/history` 查看最近 20 条输入与解析状态。

Obsidian zip 结构（v1.12.0+）：

| 文件 | 说明 |
|------|------|
| `Obsidian/README.md` | 导出来源、时间、数据范围、使用方式与一向导出限制 |
| `Obsidian/00-Index.md` | MOC 总索引，链接各模块 Index |
| `Obsidian/<模块>/<模块> Index.md` | 各目录条目列表（Goals / Projects / Tasks / Reviews / Assets / Capabilities） |
| `Obsidian/<模块>/<名称>.md` | 实体 Markdown，含 YAML frontmatter 与 `[[内部链接]]` |

frontmatter 至少含 `id`、`type`、`source`、`created_at`、`export_version`；存在时补充 `status`、`related_goal_id`、`related_project_id`、`source_review_id`、`capability` 等。

**一向导出限制**：不会自动同步回系统、不会自动删除 Obsidian 旧文件；重复名称自动加后缀；手动改名可能导致链接断开。

「导入恢复」按钮采用**先预览、后导入**流程：

1. 选择 JSON 备份文件
2. 调用 `POST /api/import/preview` 进行 dry-run（不写库）
3. 预览面板展示预计新增、更新、跳过、失败数量
4. 确认后调用 `POST /api/import` 执行合并导入

合并导入规则：

- 按 `id` 判断：不存在则插入，存在且内容相同则跳过，存在且内容不同则更新
- **不会自动清空**现有数据；误导入错误备份可能覆盖同 id 记录
- **建议导入前先导出当前备份**
- 导入失败时事务回滚，不破坏已有数据
- 失败响应含 `rolled_back: true` 表示数据库未被修改；此时 `created` / `updated` / `imported` 均为 0
- 预览返回 `{ will_import, will_update, will_skip, will_fail, errors }`
- 成功导入返回 `{ created, updated, skipped, failed, errors, imported }`（`imported = created + updated`），并在结果面板中展示
- 失败导入返回 `{ created: 0, updated: 0, skipped: 0, failed, errors, imported: 0, rolled_back: true, message }`

## 操作反馈（Toast）

全局轻量 toast 替代 `alert`，用于保存成功、删除失败、AI 错误、导入结果等提示。危险操作（删除、导入确认）仍使用 `confirm` 二次确认。最多同时显示 3 条 toast，超出时自动移除最旧的一条。

## 数据删除

各列表页提供删除按钮，操作前需确认，**不可撤销**：

| 对象 | 级联行为 |
|------|----------|
| 目标 (goal) | 级联删除其下所有项目与任务 |
| 项目 (project) | 级联删除其下所有任务 |
| 复盘 (review) | 关联资产的 `source_review_id` 置为 NULL，资产本身保留 |
| 任务 / 资产 / 能力记录 | 无子表级联 |

外键约束由 `PRAGMA foreign_keys = ON` 保障，不会产生孤儿数据。

## 测试与 CI

本地运行：

```bash
cd personal-system-v2
pip install -r requirements.txt
pytest
```

- 测试使用**临时 SQLite 数据库**，不依赖生产 `data/yd_os.db`，无需 `DEEPSEEK_API_KEY`
- pytest fixture 会覆盖 `database.DB_PATH`；也可通过环境变量 `YD_OS_DB_PATH` 指定数据库路径
- 覆盖首页/changelog、列表、删除（含级联）、导入（去重/回滚/计数拆分）等基础回归

GitHub Actions（`.github/workflows/test.yml`）在 push / PR 到 `main` 时自动执行 `pytest`（Python 3.11）。

## 版本记录

- 页面 `/changelog` 展示历史版本
- `changelog.json` 中 `current` 字段为当前正式版号
- 页面版本徽章统一读取 `changelog.current`

版本线：v1.0（数据导出）→ … → v1.11（智能归档 Inbox）→ **v1.11.1**（智能归档体验收口）

## Project Standards

开发、Hotfix 或发布前，请先阅读 [PSY 项目开发规范](../docs/standards/README.md)。

## 项目文档

完整导航见 [docs/README.md](../docs/README.md)。

| 文档 | 说明 |
|------|------|
| [docs/README.md](../docs/README.md) | 文档索引与阅读顺序 |
| [系统搭建说明书 1.1](../docs/系统搭建说明书_1.1.md) | **宪法文件**：最高约束与模块规范 |
| [architecture.md](../docs/architecture.md) | Flask / SQLite / 前端 / CI 架构 |
| [data-model.md](../docs/data-model.md) | 核心表结构与外键级联 |
| [release-process.md](../docs/release-process.md) | 版本发布与标签流程 |
| [development-guide.md](../docs/development-guide.md) | 本地开发与测试 |
| [obsidian-sync-plan.md](../docs/obsidian-sync-plan.md) | Obsidian 一向导出策略 |

## 目录结构

```
app.py              Flask 入口与 API 路由
database.py         SQLite 数据层
obsidian_export.py  Obsidian Markdown zip 导出
ai_service.py       DeepSeek AI 调用
deliberation_service.py 推演业务校验、AI 对抗与结构化结果落库
config.py           环境变量与模型配置
settings_store.py   AI 模型持久化
changelog.py        版本日志读取
prompt_specs.py     提示词生成场景元数据
prompts/            提示词文件与 loader
data/               运行时数据
static/             CSS / JS
templates/          页面模板
```

## 开发说明

- 默认 `debug=True`，仅用于本地开发
- 数据库连接已启用 `PRAGMA foreign_keys = ON`
- 提示词 `scene` 仅允许小写字母、数字与连字符（如 `decompose-tasks`）
