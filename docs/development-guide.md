# 开发指南

> 本文提供环境与命令说明。开发门禁、范围控制和完成定义见 [项目开发规范](standards/README.md)。

## 环境要求

- Python 3.11+（CI 使用 3.11）
- pip

## 快速开始

```bash
cd personal-system-v2
pip install -r requirements.txt
cp .env.example .env   # 可选：配置 DEEPSEEK_API_KEY
python app.py
```

浏览器访问 http://127.0.0.1:5000

当前远程部署方向是阿里云 ECS + 正常域名 + 公网 HTTPS + Nginx + loopback Gunicorn；部署阶段边界见 [Phase 5 数据库切换与回滚 Runbook](phase-5-database-cutover-runbook.md)。[home-server.md](home-server.md) 只保留历史 Home Server/Tailscale 资料。

## 环境变量（.env）

| 变量 | 说明 |
|------|------|
| DEEPSEEK_API_KEY | AI 功能必填；未配置时 CRUD 仍可用 |
| DEEPSEEK_BASE_URL | 默认 DeepSeek API 地址 |
| DEEPSEEK_MODEL | 锁定模型后 AI 管理页不可改 |
| DEEPSEEK_TIMEOUT | 请求超时秒数 |
| YD_OS_DB_PATH | 本地开发/测试可显式指向临时库；生产禁止写入 runtime env，由 launcher 从已验证 descriptor 注入绝对路径 |
| SECRET_KEY | session 签名密钥；加固运行要求至少 32 字节且通过弱值/熵校验 |
| PERSONAL_OS_ENV | 本机开发精确设 `development`，生产/远程精确设 `production`；缺失/未知值拒绝运行 |
| PERSONAL_OS_REMOTE | 远程可达安全信号；不承担鉴权或放宽监听地址 |
| PERSONAL_OS_BIND_HOST | 默认 127.0.0.1；加固运行只允许 loopback |
| PERSONAL_OS_TRUSTED_HOSTS | 加固运行必填；逗号分隔的精确公网 DNS 名/IP，不接受通配符、URL 或端口 |
| PERSONAL_OS_TRUSTED_PROXY | 加固运行必填；当前拓扑只接受一个精确 loopback IP |
| PERSONAL_OS_PROXY_TOKEN | 加固运行必填；反代与应用共享的独立强随机凭据，必须与 `SECRET_KEY` 不同 |
| PERSONAL_OS_BG | 仅控制正常本地开发的后台/debug 行为，不能覆盖生产安全判断 |

只有显式 `PERSONAL_OS_ENV=development` 且 loopback、非远程时才允许临时密钥和本地 debug。远程/加固运行必须精确声明 `PERSONAL_OS_ENV=production` 与 `PERSONAL_OS_REMOTE=1`；环境缺失/未知或非 loopback 绑定都会拒绝启动。

配置职责不能混用：项目 `.env` / `.env.example` 只服务本地开发；`deploy/launcher.env.example` 只承载批准的 app version 与 commit；`deploy/runtime.env.example` 承载生产安全运行变量，但不得包含 `YD_OS_DB_PATH` 或 Gunicorn 覆盖项。生产 DB 路径由 release descriptor 绑定并由 `production_launcher.py` 注入。

## v2.2 Phase 4.1 生产运行时门禁

正式启动只能从 active release launcher 进入，不能用 Flask 开发服务器、直接运行 `production.py`，也不能由 systemd 独立指定 code/config/DB：

```bash
python production_launcher.py \
  --active-pointer /var/lib/psy/releases/active-release.json \
  --descriptor-root /var/lib/psy/releases \
  --release-root /opt/psy/releases \
  --config-root /etc/psy/releases \
  --database-root /var/lib/psy/databases \
  --expected-app-version v2.2.0 \
  --expected-git-commit 40位小写提交哈希 \
  --check
```

descriptor 选择 code tree、入口、外置 runtime config 与 staged DB；launcher 校验 pointer/descriptor/code/config/manifest 后，才从 descriptor 注入绝对 `YD_OS_DB_PATH`，先运行所选入口的只读 preflight，再以固定命令 `python -m gunicorn --config <selected>/gunicorn.conf.py 'production:create_production_app()'` 替换自身。这个零参数 Gunicorn 工厂不会暴露可关闭 release context 门禁的参数。runtime config 必须显式提供 `PERSONAL_OS_ENV=production`、`PERSONAL_OS_REMOTE=1`、强随机 `SECRET_KEY`、精确 `PERSONAL_OS_TRUSTED_HOSTS`、唯一 loopback `PERSONAL_OS_TRUSTED_PROXY` 与独立强随机 `PERSONAL_OS_PROXY_TOKEN`；禁止配置 `YD_OS_DB_PATH` 或 Gunicorn 覆盖参数。可用 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 分别生成密钥，不得把生成值写入 Git。

门禁顺序为：launcher 解析 active release → selected `production.py --check` → Gunicorn preload → `production:create_production_app()` 同进程复验 release context/config/DB → 导入应用 → loopback 监听。生产入口不会调用 `init_db()`，schema/migration 仍必须在线下 staged 流程完成。每个加固请求只信任一个精确代理跳数，要求代理覆盖而非追加三项转发头并覆盖注入代理 token；应用在 ProxyFix 前校验 peer、头和 token，随后要求外部协议为 HTTPS、Host 在精确白名单内。`GET /api/health` 可由同机探针直连，响应仅包含 `status=up`。

当前限制：登录预算是单个 Gunicorn worker 内、按来源指纹的 10 次失败/60 秒滑动窗口；成功只退回当前尝试，不清既有失败。一个来源在账户成功登录或 worker 重启前最多给同一规范账户贡献一次失败计数，5 个不同来源仍可触发 15 分钟锁定。为使边界精确，`gunicorn.conf.py` 强制 1 worker + 4 threads；扩为多 worker/多实例前必须采用共享限流存储。worker 重启会丢失来源贡献守卫但保留数据库失败计数，属于 MVP 已知边界；Step 4.3 必须核对真实 systemd 未覆盖 worker 数。MFA/OAuth/外部身份平台不在 Phase 4.1 范围。

Phase 5 尚未实施。Phase 5A 必须先在 ECS 使用独立目录、独立配置/descriptor/pointer、批准的独立数据库副本、独立 Gunicorn 端口、shadow systemd unit 与 Nginx HTTPS 路由完成真实浏览器验收；它不得改正式 pointer 或真实生产库。只有验收通过并获得人工批准，才进入 Phase 5B 正式切换。

## 管理员初始化

首次使用前先配置持久 `SECRET_KEY` 并初始化唯一 bootstrap 管理员：

```bash
cd personal-system-v2
python -m flask --app app bootstrap-admin
```

命令在终端隐藏输入并二次确认密码，不接受前端或管理 API 创建管理员。初始化后通过 `/login` 登录；所有来源（包括 `127.0.0.1`）都必须认证。

## v2.2 离线 staged migration

Phase 2 代码不会在 `init_db()` 中自动绑定 legacy 数据。检测到 v2.1.4 业务表缺少 `user_id` 时，应用会 fail closed；只能对数据库副本或发布阶段明确指定的只读源执行：

```bash
cd personal-system-v2
python scripts/migrate-v2.2-multiuser.py \
  path/to/legacy-v2.1.4.db \
  path/to/staged-v2.2.db \
  --admin-username admin \
  --admin-email admin@example.com

python scripts/verify-v2.2-migration.py \
  path/to/legacy-v2.1.4.db \
  path/to/staged-v2.2.db
```

迁移密码只通过隐藏终端输入，不接受命令行参数。工具以 SQLite `mode=ro` 打开源库；目标必须不存在，且不得与源路径相同。它先写目标目录内的临时 DB，复制 16 表并执行 row count、`user_id`、双向 EXCEPT、主键、`sqlite_sequence`、integrity、FK、硬/软关联验证，全部成功后才原子生成 staged 文件。

开发与测试 MUST 使用 fixture、临时库或数据库副本。不要把 `data/yd_os.db` 作为命令参数；Phase 2 不执行生产切换，staged DB 也不得提交 Git。迁移 admin 只承接 legacy 原有训练路径，不额外 seed，以保证旧表 row count 完全相等；之后新建的账户会在各自事务中获得独立默认训练路径。

Phase 4.2 的备份、staged manifest、原子 code/DB pointer 与完整 v2.1.4 回滚工具只允许对 fixture/临时库演练；正式命令顺序和路径门禁见 [Phase 5 数据库切换与回滚 Runbook](phase-5-database-cutover-runbook.md)。

## v2.2 Phase 3 多用户运行期

- 业务路由只能把 `current_user.id` 传入 Service / Repository；不要读取请求体中的 `user_id`。
- 新增或修改业务 Repository API 时，`user_id` 必须显式且无默认值；get/update/delete 使用 `id AND user_id`，JOIN 同时约束两侧 owner。
- 新增 count、recent、search、summary、ranking、dashboard、normalization 或 aggregation helper 时，必须加入三账户不同标记/数量的负向隔离测试。
- AI、Inbox、Deliberation、Positioning 与 Obsidian Service 不得通过裸 ID 全局加载对象；最终 provider context 必须用三账户唯一标记测试无串线。
- JSON Export 只导出当前用户 16 张业务表且不包含 `users`/认证信息/行级 `user_id`。Import preview 与实际导入必须共用映射逻辑；输入 owner 被忽略，跨 owner ID 冲突只能 remap，不能 UPDATE 冲突记录。
- 普通用户完成首次改密后可以使用业务功能；`must_change_password` 和 `admin_required` 门禁继续生效。

## 运行测试

```bash
cd personal-system-v2
pytest
pytest -v tests/test_obsidian_export.py   # 单文件
pytest -v tests/test_phase_2_schema.py tests/test_phase_2_migration.py
pytest -v tests/test_phase_3_repository_isolation.py tests/test_phase_3_import_export_isolation.py
pytest -v tests/test_phase_3_service_ai_isolation.py tests/test_phase_3_business_access.py
pytest -v tests/test_phase_4_2_release_safety.py
```

- 使用临时数据库，**不要**指向生产 `data/yd_os.db`
- 无需 `DEEPSEEK_API_KEY`
- fixture 通过真实 `/login` + CSRF 建立管理员 session，不关闭认证或 CSRF

### AI mock 测试（智能归档等）

不调用真实 DeepSeek 时，在测试中 `monkeypatch` AI 入口：

```python
import ai_service

def test_inbox_analyze(client, monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "analyze_inbox_text",
        lambda text: {"items": [...]},
    )
    response = client.post("/api/inbox/analyze", json={"text": "测试"})
```

参考：`tests/test_inbox.py`

### 智能归档手动验证注意点

- goal/asset/review/capability_entry 可直接入库；project 需 `goal_id`，task 需 `project_id`
- AI 常返回项目名称字符串而非数字 ID，此时 UI 会展示校验 errors，建议先手动建目标/项目
- 真实 AI 验证前建议 `GET /api/export` 备份生产库；`data/backup_*.json` 已 gitignore
- 验证产生的 inbox 记录、测试资产等如无保留价值，应在各模块手动删除；**不要**提交 `data/yd_os.db`

## 目录约定

| 路径 | 职责 |
|------|------|
| `app.py` | 路由 |
| `database.py` | 数据层 |
| `obsidian_export.py` | Obsidian Markdown zip |
| `inbox_service.py` | 智能归档解析与确认入库 |
| `prompts/` | AI 提示词文件 |
| `tests/` | pytest |
| `data/` | 运行时 DB（git 忽略） |

## 常见风险

1. **外键**：删除 goal/project 会级联；测试库也需 `foreign_keys=ON`（已默认）
2. **导入**：当前用户合并模式；跨 owner 主键冲突会重映射，失败会 `rolled_back: true`，不会部分写入
3. **提示词路径**：scene 仅允许 `[a-z0-9-]+`，防止路径穿越
4. **版本号**：只改 `changelog.json`，勿在 README 写死版本
5. **Obsidian**：v1.10 仅 zip 下载，不写入用户 vault

## 调试

- Flask 默认 `debug=True`，仅本地使用
- 修改 `prompts/` 后无需重启即可被 loader 读取（下次 AI 调用）
