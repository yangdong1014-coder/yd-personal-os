# Phase 5 ECS Shadow、正式切换与回滚 Runbook（待执行）

> 本文把 Phase 5 分成必须顺序执行的 Phase 5A ECS Shadow Deployment 与 Phase 5B Approved Production Cutover。它是待执行 SOP，不是已执行记录；Phase 4 只完成代码、测试和模板准备。未经每一阶段的单独授权，不得据此操作 ECS、systemd、Nginx 或真实数据库。

## 阶段门禁

~~~text
Phase 5A：独立 ECS shadow
→ 公网 HTTPS / 正常域名 / 真实浏览器验收
→ 保存 evidence
→ 人工明确批准
→ Phase 5B：停写、备份、迁移、正式切换与回滚窗口
~~~

- Phase 5A 完成后必须停止。不得因为 shadow 通过而自动进入 Phase 5B。
- 只有发布负责人对 Phase 5A evidence、目标 commit/version、维护窗口、真实源库绝对路径和回滚负责人作出明确批准，才能开始 Phase 5B。
- Phase 5A 与 Phase 5B 的命令、目录、systemd unit、Nginx 配置和数据库路径必须分开记录，不能复用一个含义不明的 “production” 临时目录。
- 本文中的尖括号占位符必须在对应阶段由人工替换并复核；不得原样执行。

## 已实现的正式启动链与路径契约

现有 production launcher、release switch、systemd unit 与部署模板约定：

| 职责 | 根路径 |
|---|---|
| 不可变 code release | /opt/psy/releases/ |
| 稳定 launcher | /opt/psy/launcher/ |
| launcher 批准版本/commit | /etc/psy/launcher.env |
| 版本化 runtime config 与配置批准元数据 | /etc/psy/releases/ |
| launcher-consumed descriptor、active pointer 与 release 状态 | /var/lib/psy/releases/ |
| SQLite、backup、staged、shadow 与 restore artifact | /var/lib/psy/databases/ |

正式 systemd unit 明确传入 descriptor-root=/var/lib/psy/releases 与 config-root=/etc/psy/releases。因此 launcher 实际读取的 descriptor 和 active pointer 必须位于 /var/lib/psy/releases；/etc/psy/releases 保存 descriptor 绑定的外置 runtime config，而不是可自由选择数据库路径的通用 env。具体部署前必须再次以当次批准 commit 中的 unit 和 launcher 为准。

正式权限契约：

- `/var/lib/psy/releases` 推荐 `root:root` + `0755`：`psy` 可 traverse/read，但不得 create、rename、delete 或 write。
- active pointer 与 release descriptor 均为 `root:root` + `0644`：由 root 受控创建或切换，`psy` 可读但不可写，且没有 group/world write 位。
- descriptor-bound runtime config 含 `SECRET_KEY`、proxy token 与可选 API key，必须为 `root:psy` + `0640`，不得使用 `0644`。
- `/etc/psy/releases` 必须允许 `psy` traverse/read 但不得允许其写入；可使用 `root:root` + `0755`、`root:psy` + `0750` 或等价 ACL。

Windows 本地回归只能可移植地验证 mode-setting 调用；真实 Linux 上由 root 创建 descriptor/激活 pointer、再由 `psy` 读取且无法写入或替换的完整链路，以及 runtime config 的 group 可读性，仍须在 Phase 5 ECS 窗口实测并留存证据。

正式链路是：

~~~text
systemd
→ /opt/psy/launcher/production_launcher.py
→ /var/lib/psy/releases/active-release.json
→ descriptor 绑定 code/config/DB/manifest
→ selected production.py --check
→ production:create_production_app()
→ Gunicorn
~~~

runtime config 禁止包含 YD_OS_DB_PATH；launcher 在校验 descriptor 与 manifest 后注入该值。PERSONAL_OS_PROXY_TOKEN 只保护 Nginx→Flask 的内部代理信任边界，不是用户登录凭据。

## Phase 5A：ECS Shadow Deployment

### 目标与禁止事项

Phase 5A 的目标是在同一 ECS 上并行证明 v2.2 的公网可用性与安全边界，不改变现有生产：

- 不停止或重启现有生产服务；
- 不替换 /var/lib/psy/releases/active-release.json；
- 不读取、复制、修改或迁移仓库真实路径 personal-system-v2/data/yd_os.db；
- 不对当前生产 SQLite 文件运行 migration；
- 不复用正式 descriptor/pointer、正式 Gunicorn 监听端口或正式 Nginx upstream；
- 不把 shadow 结果写成正式切换已经完成。

### 独立资源

Phase 5A 设计和执行时至少建立以下独立边界：

| 资源 | Shadow 约束 |
|---|---|
| code | /opt/psy/releases/rel-v220-shadow-<approved-commit>/ 下的批准 commit，只读且不可变 |
| runtime config | /etc/psy/releases/<instance>/runtime.env，不含 YD_OS_DB_PATH |
| descriptor/pointer state | /var/lib/psy/releases/<instance>/<release-id>.json 与独立 shadow pointer；不得指向正式 active-release.json |
| database | /var/lib/psy/databases/<instance>/ 下的批准独立副本、staged DB 与 manifest |
| Gunicorn | 独立 loopback 端口，不与正式 upstream 共用 |
| systemd | 独立 shadow unit，不替换或重启正式 unit |
| Nginx | 独立 upstream 与受控 shadow server_name/URL，使用真实 HTTPS |

shadow 数据库只能来自发布负责人预先批准、置于独立路径并具有来源身份记录的副本。副本必须记录 source identity、SHA-256、manifest、schema profile、app version 和 git commit；任何 migration 都只从该只读副本生成一个不存在的新 staged 文件。如何取得副本属于单独获批的运维动作，本文不授权从真实库复制。

### 当前端口与执行前置项

Phase 5A.1 在本地代码中保留正式默认 `127.0.0.1:5000`，并增加由 launcher 严格批准、Gunicorn 单一消费的非特权 loopback port；当前 shadow 候选为 5100。该能力、独立 unit/Nginx 模板和权限契约尚未在 ECS 安装或运行，不构成 Phase 5A 部署通过。实际命令、路径与 21 步验收以 [Phase 5A Shadow Deployment Runbook](phase-5a-shadow-deployment-runbook.md) 为准，必须另获执行批准。

### Phase 5A 执行与验收清单

1. 获得 Phase 5A 单独执行批准，记录 shadow release id、commit/version、域名、端口方案、资源路径和负责人。
2. 只从已批准的部署清单记录正式服务、正式 pointer 与真实数据库路径并列入禁止目标；不得为此读取、stat、hash、复制、停止或迁移真实数据库。
3. 准备独立 code、runtime config、descriptor/pointer state、数据库副本/manifest、shadow unit、loopback 端口与 Nginx upstream/server_name。
4. 在监听前完成 launcher/release context、code/config hash、DB manifest、schema、integrity、foreign key 与唯一启用 admin 预检。
5. 启动独立 shadow unit，确认正式 unit、正式端口和正式 active pointer 未变化。
6. 通过公网正常域名和可信 HTTPS 从真实浏览器验收：
   - 任意联网设备可像普通网页直接打开；未登录只能看到登录页；
   - 账号密码登录、首次改密、退出、禁用/重置与旧 session 撤销符合预期；
   - admin 与普通用户权限正确，个人业务数据 owner scope 不串线；
   - Secure/HttpOnly/SameSite Cookie、HTTPS-only、CSP/HSTS、安全头、Host/代理信任和 CSRF 正确；
   - logout 后 Back、bfcache、offline 与 service worker 不恢复私人页面；
   - Console/Network 无 CSP violation、mixed content、私密响应缓存或意外敏感字段；
   - login、代表性 user 页面和 admin-users 在 390/768/1024/1440 目标视口重新取证；
   - 页面版本/构建身份与 shadow 的批准 app version、git commit 一致。
7. 保存 unit 状态、监听端口、Nginx/证书、health、浏览器、版本身份和数据库 manifest evidence；不得记录密码、session、secret、token 或私人正文。
8. 验证正式 unit、正式 active pointer 和正式服务可用性未因 shadow 改变；根据命令记录确认没有任何 shadow 操作把真实数据库列为目标，不读取其内容或元数据。
9. 停在人工批准门禁，记录 Phase 5A 通过/失败及遗留项。

任何 Phase 5A 项失败都只停止 shadow 推进并保留证据，不触发 Phase 5B，也不通过修改正式生产来绕过问题。

## Phase 5B：Approved Production Cutover

只有 Phase 5A 全部验收、evidence 已复核且获得明确人工批准，以下内容才成为可执行候选。Phase 5B 会触及正式服务与正式数据库，必须在新的获批执行任务中逐条确认；Phase 4 不执行。

### 安全不变量

- 所有数据库、备份目录、manifest、release descriptor 路径都使用已核对的绝对路径；命令没有指向仓库 `data/yd_os.db` 的默认值。
- v2.1.4 源库只允许 SQLite backup API 读取；正式窗口仍先停业务写入/停服务，再备份。
- backup、manifest、checksum、staged DB、restore DB 和 release descriptor 都只创建新文件，拒绝覆盖既有文件。
- v2.2 staged migration 不原地修改 legacy DB；源库 hash、size、mtime 任一变化即失败。
- code tree、入口、配置与 DB 以一个不可变 release descriptor 配对；active release pointer 是唯一可变选择器。
- 服务停止后才允许用 `os.replace(temp_pointer, active_pointer)` 原子切换。中断发生在替换前则仍选旧 release，替换后则选完整新 release，不存在半写 pointer。
- 启动器必须先解析 active pointer、核对 descriptor/code/manifest，再将 descriptor 中的绝对数据库路径传给 `YD_OS_DB_PATH`。随后 `production.py --check` 和 Gunicorn preload 在监听前再次检查 v2.2 schema、完整性、外键和唯一启用 admin。
- 任一验证失败都保持服务停止，禁止继续下一步；不能靠应用自动创建空数据库补救。

## Phase 5B 工具契约（仅人工批准后）

以下示例全部属于 Phase 5B。路径位于已实现的受控根目录内，但带尖括号的名称仍是占位符；Phase 5B 必须替换为服务器上已人工核对的版本化绝对路径：

```bash
# 一致快照 + manifest + manifest checksum；使用 SQLite backup API
python scripts/backup-db.py create \
  --source /var/lib/psy/databases/production/<approved-v214-source>.db \
  --backup-dir /var/lib/psy/databases/backups/<phase5b-release-id> \
  --schema-profile legacy_v214 \
  --git-commit <v2.1.4-40-char-commit> \
  --app-version v2.1.4

# 独立复验（可在复制到恢复介质后再次运行）
python scripts/backup-db.py verify \
  --database /var/lib/psy/databases/backups/<phase5b-release-id>/<backup>.sqlite3 \
  --manifest /var/lib/psy/databases/backups/<phase5b-release-id>/<backup>.manifest.json \
  --schema-profile legacy_v214

# 恢复演练/回滚只能恢复到一个不存在的新路径
python scripts/backup-db.py restore \
  --database /var/lib/psy/databases/backups/<phase5b-release-id>/<backup>.sqlite3 \
  --manifest /var/lib/psy/databases/backups/<phase5b-release-id>/<backup>.manifest.json \
  --restore /var/lib/psy/databases/rollback/<phase5b-release-id>/yd_os-v214-restored.db \
  --schema-profile legacy_v214
```

所有命令都从仓库根目录执行；因此迁移脚本路径包含 `personal-system-v2/`，而备份/切换工具位于根目录 `scripts/`。

Manifest 只包含时间、应用版本/commit、路径、文件大小/hash、schema、表集合、row count、`sqlite_sequence`、integrity/FK 结果和 admin 数量。它不得包含 password/hash、`SECRET_KEY`、session、私人正文、JSON 正文或 AI prompt。`.manifest.json.sha256` 用于检测意外/单文件篡改；它不是数字签名，Phase 5 还必须依赖只读权限、受控备份目录和外部留存的 SHA-256 记录保护整套 artifact。

staged migration 与复验：

```bash
python personal-system-v2/scripts/migrate-v2.2-multiuser.py \
  /var/lib/psy/databases/production/<approved-v214-source>.db \
  /var/lib/psy/databases/staged/yd_os-v22-<release-id>.db \
  --admin-username <admin> \
  --admin-email <admin-email>

python personal-system-v2/scripts/verify-v2.2-migration.py \
  /var/lib/psy/databases/production/<approved-v214-source>.db \
  /var/lib/psy/databases/staged/yd_os-v22-<release-id>.db
```

迁移器继续隐藏并二次确认 bootstrap admin 密码。成功后先为 staged DB 生成 `migration-staged` manifest，然后才能建立 release descriptor：

```bash
python scripts/manifest-db.py \
  --database /var/lib/psy/databases/staged/yd_os-v22-<release-id>.db \
  --manifest /var/lib/psy/databases/staged/yd_os-v22-<release-id>.db.manifest.json \
  --schema-profile v22 \
  --artifact-kind migration-staged \
  --source /var/lib/psy/databases/production/<approved-v214-source>.db \
  --source-schema-profile legacy_v214 \
  --git-commit <v2.2-40-char-commit> \
  --app-version v2.2.0
```

release descriptor/pointer：

```bash
python scripts/switch-release.py describe \
  --descriptor /var/lib/psy/releases/<release-id>.json \
  --release-id <release-id> \
  --app-version v2.2.0 \
  --git-commit <v2.2-40-char-commit> \
  --code-root /opt/psy/releases/<release-id> \
  --entrypoint /opt/psy/releases/<release-id>/production.py \
  --config /etc/psy/releases/<release-id>/runtime.env \
  --database /var/lib/psy/databases/staged/yd_os-v22-<release-id>.db \
  --manifest /var/lib/psy/databases/staged/yd_os-v22-<release-id>.db.manifest.json \
  --schema-profile v22

# 只有 systemd 已确认 inactive 后才能给确认开关
python scripts/switch-release.py activate \
  --descriptor /var/lib/psy/releases/<release-id>.json \
  --active-pointer /var/lib/psy/releases/active-release.json \
  --expected-app-version v2.2.0 \
  --expected-git-commit <v2.2-40-char-commit> \
  --service-stopped-confirmed
```

`describe` 会拒绝 code version/commit 与 DB manifest 不一致的组合，并限制 `legacy_v214 ↔ v2.1.4`、`v22 ↔ v2.2.*`。它绑定完整 code tree hash（排除 `.git`、cache、venv、data、backups 等非 release 内容）、入口文件 hash 和对应配置文件 hash。`activate` 在原子替换前再次验证 code/config、manifest、DB hash、schema 和 row counts。正式 systemd 与 active-pointer resolver 已形成 Phase 4 模板和本地测试覆盖，但真实安装、Phase 5A shadow 端口实现与 Phase 5B 激活均尚未执行。

## Phase 5B 正式切换顺序（仅人工批准后）

1. Approval preflight：附上 Phase 5A evidence 与明确人工批准记录；核对批准的 commit/version、绝对路径、剩余空间、fixture 演练证据、回滚负责人和维护窗口；确认当前仍运行 v2.1.4 code + legacy DB。
2. 停止业务写入/停服务，并以 systemd 状态和端口检查确认没有进程持有写路径。
3. 对 legacy DB 运行 `backup-db.py create`，记录控制台 JSON 和外部 SHA-256。
4. 运行 `backup-db.py verify`，再恢复到一次性验证路径并复验；未完成 restore verification 不继续。
5. 从原 legacy DB 创建全新 staged v2.2 DB；目标已存在即停止，不能删除后重试掩盖来源不明的文件。
6. 运行 migration verifier，核对 16 表双向数据、ID、JSON/timestamp、sequence、admin ownership、integrity/FK/软硬关联。
7. 为 staged DB 生成并复验 manifest；建立 v2.2 code/DB descriptor。
8. 部署批准的版本化 v2.2 code，但服务保持停止；不要先改 active pointer。
9. 原子替换 active release pointer；重新 resolve，核对选中的 commit、version、DB path/hash。
10. 使用正式 systemd unit 的 launcher 参数先运行只读 `--check`，由 launcher 加载 descriptor 绑定的外置配置并调用 selected `production.py --check`；失败保持停止并回滚 pointer。
11. 使用 Gunicorn `preload_app=True` 启动；预检失败必须发生在监听前。
12. 完成 health、login/admin/user/owner-scope 核心 smoke 和 Step 4.3 浏览器清单。
13. 启用并验证获批的自动 SQLite backup 调度、不可覆盖 artifact、manifest/校验和、失败告警与一次恢复复验；在对应 Phase 5 实现和 evidence 完成前，不得声称自动备份已上线。
14. 业务验收通过后保持 rollback window；保留 legacy backup、manifest、checksum、v2.1.4 code/config/descriptor，不进行自动清理。

任一步失败：停止继续发布，保留现场证据，不在原文件上“修补”。

## 防止 code/DB 错配

| 风险 | 门禁 |
|---|---|
| code 已升级、DB 仍旧 | active pointer 一次选择 code+DB descriptor；v2.2 `production.py` 对 legacy/空/相对/错误路径 fail closed |
| DB 已升级、code 仍旧 | descriptor 只允许 `v22 ↔ v2.2.*`；v2.1.4 descriptor 只接受精确 legacy schema |
| staged 路径写错 | 所有路径必须绝对、存在、非空且 canonical；manifest filename/hash/schema/count 与 staged 文件逐项匹配 |
| staged 被验证后修改 | activate 前重算 code、manifest、DB hash；不一致拒绝切换 |
| 切换中断 | `os.replace` 前仍是旧 pointer；完成后是新 pointer；临时 pointer 不被启动器读取 |
| 错误路径创建空库 | backup/switch/preflight 都以只读 `mode=ro` 打开，缺失/空文件直接失败；不调用 `init_db` |

## 完整回滚

回滚不是只切代码。必须：

1. 停止 v2.2，并确认 inactive。
2. 复验 legacy backup + manifest；恢复到新的绝对路径，再核对 hash、16 表 row counts、integrity/FK 和关键读取。
3. 核对恢复库精确为 v2.1.4 schema：没有 `users`，16 表均没有 `user_id`。
4. 使用已留存的 v2.1.4 code entrypoint、commit、配置和 restored legacy DB 建立/复验 rollback descriptor。
5. 用同一个 `activate --service-stopped-confirmed` 原子选回 v2.1.4 descriptor。
6. 用 v2.1.4 模拟/正式入口做旧 schema 兼容预检，随后启动旧 Gunicorn。
7. 验证 health、关键 legacy 读取、计数、hash、integrity/FK；保留失败的 v2.2 artifact 供离线分析，禁止覆盖 backup。

Phase 4.2 临时演练已经覆盖“v2.1.4 fixture → verified backup → v2.2 → 模拟失败 → restored v2.1.4 code/DB/config descriptor → legacy schema/关键读取验证”。真实执行仍需 Phase 5 单独授权。

## 关账证据

每次正式窗口至少留存：批准 commit/version、停止/启动时间、绝对路径（可按运维规范脱敏）、backup/manifest SHA、16 表和 users counts、migration verifier JSON、release descriptor/pointer SHA、production preflight、smoke 结果、回滚窗口结束决定。日志不得留存密码、session、SECRET、私人正文或 prompt。
