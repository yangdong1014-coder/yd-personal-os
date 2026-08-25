# Phase 5A ECS Shadow Deployment Runbook（待批准执行）

> 本文是 Phase 5A.1 生成的未来 ECS 操作 SOP，不是执行记录。本地实现阶段不得 SSH、修改 ECS、安装 unit/Nginx/证书、改 DNS 或接触正式数据库。真正执行前必须获得新的人工批准；Phase 5A 验收后必须再次停止，Phase 5B 不在本文范围内。

## 固定边界与待填参数

Shadow 与当前正式 `/opt/psy1`、正式 unit、正式端口 `127.0.0.1:5000`、正式 Nginx/Tailscale 配置及正式数据库完全分离。运行用户固定为 `psy:psy`，应用 HTTP host 固定为 `127.0.0.1`。端口没有 shadow 默认值；本次候选值是经现场复验后才可批准的 `5100`。

执行工单必须先填写并双人复核下列值，不能原样执行占位符：

```bash
INSTANCE="<short-shadow-id>"
RELEASE_ID="<unique-release-id>"
GIT_COMMIT="<approved-40-char-lowercase-commit>"
APP_VERSION="v2.2.0-shadow"
SHADOW_PORT="5100"
SHADOW_SERVER_NAME="<dedicated-shadow-fqdn>"
ECS_BIND_ADDRESS="<reviewed-private-eth0-ip>"
ACME_ROOT="<dedicated-acme-webroot>"
SHADOW_CERTIFICATE_PATH="<absolute-shadow-fullchain-path>"
SHADOW_CERTIFICATE_KEY_PATH="<absolute-shadow-private-key-path>"
SHADOW_PROXY_AUTH_SNIPPET="<absolute-shadow-proxy-auth-snippet-path>"
SHADOW_NGINX_OUTPUT="<absolute-new-shadow-nginx-config-path>"
SHADOW_TOOL="<absolute-verified-bundle-path>/personal-system-v2/shadow_deployment.py"
SHADOW_ADMIN_USERNAME="<shadow-admin>"
SHADOW_ADMIN_EMAIL="<shadow-admin-email>"
```

`INSTANCE` 与 `RELEASE_ID` 必须先由代码验证并严格匹配 `^[a-z0-9][a-z0-9-]{0,63}$`。slash、whitespace/newline、semicolon、wildcard、`..`、leading `-` 和 shell metacharacter 都必须在任何目录、unit、descriptor 或模板渲染前被拒绝。不得只依赖人工目检。

`ECS_BIND_ADDRESS` 是部署时参数，不是产品默认值。Phase 5A.0 曾观察到 `eth0=172.25.103.111`，执行窗口仍须重新核对；公网 `8.137.186.60` 仅是待确认的 EIP/NAT 事实，不能作为 Nginx 本机 listen 地址，必须先由人工确认映射链、DNS 和安全组。

建议路径契约：

| 资源 | Shadow 路径/名称 | 权限真源 |
|---|---|---|
| immutable release repo / app code | `/opt/psy/releases/shadow-${INSTANCE}/repo/` / `repo/personal-system-v2/` | `root:root`, directories `0755`, files non-writable |
| venv | `/opt/psy/venvs/shadow-${INSTANCE}` | 独立、root 管理、运行期只读 |
| runtime/launcher config | `/etc/psy/releases/shadow-${INSTANCE}/` | directory `root:psy 0750`, files `root:psy 0640` |
| descriptor/pointer | `/var/lib/psy/releases/shadow/${INSTANCE}/` | `root:root`, service 只读 |
| approved source copy | `/var/lib/psy/databases/shadow/${INSTANCE}/source/` | `root:root 0700`, runtime 不可见 |
| migration artifact | `/var/lib/psy/databases/shadow/${INSTANCE}/migration/` | `root:root 0700`, runtime 不可见 |
| immutable manifest/checksum | `/var/lib/psy/databases/shadow/${INSTANCE}/manifests/` | parent `root:psy 0750`, files `root:root 0644` |
| runtime DB | `/var/lib/psy/databases/shadow/${INSTANCE}/staged/yd_os-v22-shadow.db` | parent `psy:psy 0700`, DB `psy:psy 0600` |
| service | `psy-v22-shadow@${INSTANCE}.service` | 只 start，不 enable |
| upstream | `psy_v22_shadow` | 只代理到 `127.0.0.1:${SHADOW_PORT}` |

数据流只能是：

```text
separately approved source copy (immutable)
→ offline migration
→ verified staged migration artifact (immutable)
→ one-time runtime copy (writable only by psy)
→ descriptor-bound runtime DB
```

manifest 与 `.manifest.json.sha256` 记录 staged artifact 的身份，放在 runtime 用户不可写的独立 parent；runtime DB 开始写入后不再声称其 hash 与初始 manifest 持续相同。launcher 每次仍复验 manifest/checksum、v2.2 schema/integrity/FK、唯一启用 admin、明确批准路径和 release context，且不会调用 `init_db()` 或 fallback 到 `data/yd_os.db`。

## 21 步执行与验收

以下所有命令都只允许在新的 Phase 5A ECS 执行批准后运行，并须保存脱敏输出。任何一步失败都停止 shadow 推进，不得修改正式服务来绕过。

### 1. 创建独立 release layout

先从已校验、尚未安装到 identity 派生目标路径的 release bundle 执行 validator；只有返回 `0` 才能确认目标不存在并由 root 创建上表目录：

```bash
/usr/bin/python3 "${SHADOW_TOOL}" validate-identity \
  --instance "${INSTANCE}" \
  --release-id "${RELEASE_ID}"
```

禁止复用 `/opt/psy1`、正式 pointer、正式配置、正式 venv 或正式数据库目录。记录 `readlink -f` 结果，确认每个 shadow 目标都在批准根内。

### 2. 核验 runtime user/group

只复用 Phase 5A.0 已确认的 `psy:psy`，不得新建或改变正式账号：

```bash
id psy
getent passwd psy
getent group psy
```

### 3. 安装不可变 code release

将批准 commit 的独立、已校验 repository release bundle 安装到 `/opt/psy/releases/shadow-${INSTANCE}/repo`，应用 code root 固定为其下的 `personal-system-v2/`。同时将该 bundle 的 `shadow_deployment.py` 安装为 root-owned、不可写的 `/usr/local/libexec/psy-shadow-deployment.py`，供 unit 在任何应用进程前复验 instance/release id。核对 `git_commit`/bundle checksum，移除 `.git`、所有 `.env`、`personal-system-v2/data`、cache 和 venv；release tree 全部 root-owned，group/world 不可写。不得在 ECS checkout/pull 一个可漂移工作树后直接运行。

```bash
install -o root -g root -m 0755 \
  "/opt/psy/releases/shadow-${INSTANCE}/repo/personal-system-v2/shadow_deployment.py" \
  /usr/local/libexec/psy-shadow-deployment.py
```

### 4. 创建独立 venv

使用 ECS 已核验的 Python 创建 `/opt/psy/venvs/shadow-${INSTANCE}`，从批准 release 的 `personal-system-v2/requirements.lock` 以 `--require-hashes` 安装全部锁定依赖（不得使用 `--no-deps`）。

锁文件生成基线：
- 环境：Ubuntu 22.04 LTS (`x86_64`)
- Python：`Python 3.10.12`
- pip：`pip 26.2.1`
- pip-tools：`pip-tools 7.6.1`
- 生成命令：在 Scratch 隔离目录中执行相对路径 `pip-compile --generate-hashes --output-file=requirements.lock requirements.txt`

安装与验收命令（以 `shadow-01` 为例）：

```bash
"/opt/psy/venvs/shadow-${INSTANCE}/bin/python" -m pip install \
  --require-hashes \
  -r "/opt/psy/releases/shadow-${INSTANCE}/repo/personal-system-v2/requirements.lock"

"/opt/psy/venvs/shadow-${INSTANCE}/bin/python" --version
"/opt/psy/venvs/shadow-${INSTANCE}/bin/python" -m pip check
"/opt/psy/venvs/shadow-${INSTANCE}/bin/python" -m gunicorn --version

# group/world writable 权限审计（严禁包含 group/world 写权限）
find "/opt/psy/venvs/shadow-${INSTANCE}" -perm -0002 -o -perm -0020
```

不得引用正式 venv。

### 5. 安装 shadow runtime.env

从 `personal-system-v2/deploy/shadow-runtime.env.example` 生成 `/etc/psy/releases/shadow-${INSTANCE}/runtime.env`。必须是 `root:psy 0640`，且只允许 launcher allowlist 中的键。使用独立强随机 `SECRET_KEY` 和 `PERSONAL_OS_PROXY_TOKEN`；`PERSONAL_OS_TRUSTED_HOSTS` 必须是唯一 shadow FQDN。禁止 `YD_OS_DB_PATH`、host override、Gunicorn 参数和正式 `.env`。

### 6. 安装 shadow launcher.env

从 `shadow-launcher.env.example` 生成同目录 `launcher.env`，写入五项精确批准值：candidate version、符合 allowlist 的 release id、40 字符 commit、runtime DB 绝对路径和端口。`5100` 只是当前候选；现场端口复验后才可写入。文件为 `root:psy 0640`。

### 7. 接收 approved DB copy

取得 source copy 是独立的、需另行批准的运维动作；本文不授权从正式数据库复制。执行本 runbook 时，批准副本及外部保存的 source identity/hash 必须已经由负责人交付到 shadow `source/`，且路径不得包含 `/opt/psy1` 或仓库 `personal-system-v2/data/yd_os.db`。先验证目标是非 symlink regular file、`root:root 0400`，再核对交付 hash；不查询私人行数据。

### 8. 固化 source checksum

对“已批准副本”计算 SHA-256、size 和 mtime，和工单中的外部值比较；输出只记录路径身份和摘要，不记录内容：

```bash
sha256sum "/var/lib/psy/databases/shadow/${INSTANCE}/source/<approved-copy>.db"
stat --format='%n %s %y %U:%G %a' "/var/lib/psy/databases/shadow/${INSTANCE}/source/<approved-copy>.db"
```

### 9. 执行离线 migration

目标必须是 migration parent 中一个不存在的新文件；迁移器从 source copy 以 SQLite read-only URI 打开源库，并通过隐藏提示读取/确认 bootstrap admin 密码：

```bash
"/opt/psy/venvs/shadow-${INSTANCE}/bin/python" \
  "/opt/psy/releases/shadow-${INSTANCE}/repo/personal-system-v2/scripts/migrate-v2.2-multiuser.py" \
  "/var/lib/psy/databases/shadow/${INSTANCE}/source/<approved-copy>.db" \
  "/var/lib/psy/databases/shadow/${INSTANCE}/migration/yd_os-v22-shadow.db" \
  --admin-username "${SHADOW_ADMIN_USERNAME}" \
  --admin-email "${SHADOW_ADMIN_EMAIL}"
```

### 10. 复验 staged DB

运行独立 verifier，并再次核对 source hash 未变化：

```bash
"/opt/psy/venvs/shadow-${INSTANCE}/bin/python" \
  "/opt/psy/releases/shadow-${INSTANCE}/repo/personal-system-v2/scripts/verify-v2.2-migration.py" \
  "/var/lib/psy/databases/shadow/${INSTANCE}/source/<approved-copy>.db" \
  "/var/lib/psy/databases/shadow/${INSTANCE}/migration/yd_os-v22-shadow.db"
```

必须通过 schema、16 表双向数据、ID、sequence、integrity、FK、软/硬关联和 admin ownership 检查。

### 11. 生成 immutable manifest/checksum 和 runtime DB

先对 migration artifact 生成 manifest 到独立 `manifests/`，再一次性复制为尚不存在的 runtime DB。三者 basename 必须一致；复制后用 manifest 复验 runtime DB。不得覆盖任一已有目标：

```bash
"/opt/psy/venvs/shadow-${INSTANCE}/bin/python" \
  "/opt/psy/releases/shadow-${INSTANCE}/repo/scripts/manifest-db.py" \
  --database "/var/lib/psy/databases/shadow/${INSTANCE}/migration/yd_os-v22-shadow.db" \
  --manifest "/var/lib/psy/databases/shadow/${INSTANCE}/manifests/yd_os-v22-shadow.db.manifest.json" \
  --schema-profile v22 \
  --artifact-kind migration-staged \
  --source "/var/lib/psy/databases/shadow/${INSTANCE}/source/<approved-copy>.db" \
  --source-schema-profile legacy_v214 \
  --git-commit "${GIT_COMMIT}" \
  --app-version "${APP_VERSION}"

"/opt/psy/venvs/shadow-${INSTANCE}/bin/python" \
  "/opt/psy/releases/shadow-${INSTANCE}/repo/scripts/backup-db.py" restore \
  --database "/var/lib/psy/databases/shadow/${INSTANCE}/migration/yd_os-v22-shadow.db" \
  --manifest "/var/lib/psy/databases/shadow/${INSTANCE}/manifests/yd_os-v22-shadow.db.manifest.json" \
  --restore "/var/lib/psy/databases/shadow/${INSTANCE}/staged/yd_os-v22-shadow.db" \
  --schema-profile v22

chown psy:psy "/var/lib/psy/databases/shadow/${INSTANCE}/staged/yd_os-v22-shadow.db"
chmod 0600 "/var/lib/psy/databases/shadow/${INSTANCE}/staged/yd_os-v22-shadow.db"
```

随后建立 shadow descriptor，并在服务尚未启动时创建独立 pointer；两条命令只能引用本 runbook 的 shadow code/config/runtime DB/manifest 路径和 `v2.2.0-shadow`：

```bash
"/opt/psy/venvs/shadow-${INSTANCE}/bin/python" \
  "/opt/psy/releases/shadow-${INSTANCE}/repo/scripts/switch-release.py" describe \
  --descriptor "/var/lib/psy/releases/shadow/${INSTANCE}/${RELEASE_ID}.json" \
  --release-id "${RELEASE_ID}" \
  --app-version "${APP_VERSION}" \
  --git-commit "${GIT_COMMIT}" \
  --code-root "/opt/psy/releases/shadow-${INSTANCE}/repo/personal-system-v2" \
  --entrypoint "/opt/psy/releases/shadow-${INSTANCE}/repo/personal-system-v2/production.py" \
  --config "/etc/psy/releases/shadow-${INSTANCE}/runtime.env" \
  --database "/var/lib/psy/databases/shadow/${INSTANCE}/staged/yd_os-v22-shadow.db" \
  --manifest "/var/lib/psy/databases/shadow/${INSTANCE}/manifests/yd_os-v22-shadow.db.manifest.json" \
  --schema-profile v22

"/opt/psy/venvs/shadow-${INSTANCE}/bin/python" \
  "/opt/psy/releases/shadow-${INSTANCE}/repo/scripts/switch-release.py" activate \
  --descriptor "/var/lib/psy/releases/shadow/${INSTANCE}/${RELEASE_ID}.json" \
  --active-pointer "/var/lib/psy/releases/shadow/${INSTANCE}/active-release.json" \
  --expected-app-version "${APP_VERSION}" \
  --expected-git-commit "${GIT_COMMIT}" \
  --service-stopped-confirmed
```

### 12. 核验 Linux 权限链

逐级执行 `namei -l`/`stat`，证明：code、venv、config、descriptor、pointer、manifest/checksum 对 `psy` 不可写；source/migration 为 root-only；只有 `staged/` 及 runtime DB 由 `psy` 写。显式负向检查：

```bash
sudo -u psy test -r "/etc/psy/releases/shadow-${INSTANCE}/runtime.env"
sudo -u psy test ! -w "/etc/psy/releases/shadow-${INSTANCE}/runtime.env"
sudo -u psy test ! -w "/var/lib/psy/databases/shadow/${INSTANCE}/manifests/yd_os-v22-shadow.db.manifest.json"
sudo -u psy test -w "/var/lib/psy/databases/shadow/${INSTANCE}/staged/yd_os-v22-shadow.db"
```

### 13. 端口和 launcher preflight

用 `ss -ltnp` 同时确认 5000 仍由正式链占用/保持原状、批准 shadow 端口空闲，且附近候选没有冲突。随后以 unit 中完全相同的参数执行 launcher：

```bash
sudo -u psy "/opt/psy/venvs/shadow-${INSTANCE}/bin/python" \
  "/opt/psy/releases/shadow-${INSTANCE}/repo/personal-system-v2/production_launcher.py" \
  --active-pointer "/var/lib/psy/releases/shadow/${INSTANCE}/active-release.json" \
  --descriptor-root "/var/lib/psy/releases/shadow/${INSTANCE}" \
  --release-root "/opt/psy/releases/shadow-${INSTANCE}/repo" \
  --config-root "/etc/psy/releases/shadow-${INSTANCE}" \
  --database-root "/var/lib/psy/databases/shadow/${INSTANCE}" \
  --expected-app-version "${APP_VERSION}" \
  --expected-git-commit "${GIT_COMMIT}" \
  --expected-database-path "/var/lib/psy/databases/shadow/${INSTANCE}/staged/yd_os-v22-shadow.db" \
  --bind-port "${SHADOW_PORT}" \
  --shadow-instance "${INSTANCE}" \
  --expected-release-id "${RELEASE_ID}" \
  --require-separated-database-artifacts \
  --check
```

报告必须显示 `127.0.0.1:${SHADOW_PORT}`、精确 instance/candidate version/release id/commit/runtime DB/manifest；任何 identity/path 缺失、相对、symlink、超出 shadow root、与批准 DB 不同或端口非法都必须失败。

### 14. 安装并启动独立 systemd unit

将 `psy-v22-shadow@.service` 安装为独立模板，先运行 `systemd-analyze verify`，再只执行：

```bash
/usr/bin/python3 /usr/local/libexec/psy-shadow-deployment.py validate-identity \
  --instance "${INSTANCE}" \
  --release-id "${RELEASE_ID}"
systemctl start "psy-v22-shadow@${INSTANCE}.service"
```

不得 `enable`，不得 start/stop/restart 正式 unit。unit 首个 validator `ExecStartPre` 必须在任何应用进程前验证未转义的原始 `%I` 与批准 release id；只有验证通过后，systemd 才可继续使用已转义的 `%i` 路径，launcher 还会复验同一 `%I` identity。这样 slash 等输入不能先被 systemd escape 成看似安全的 id。unit 的 `ConditionPathExists=/opt/psy1` 先在 host 侧确认正式目录确实存在；`ExecStartPre=/usr/bin/test ! -e /opt/psy1` 则必须在 shadow 的 `InaccessiblePaths` mount namespace 内成功。启动后再以 MainPID 的同一 mount namespace和 `psy` 身份实证：

```bash
MAINPID="$(systemctl show --property MainPID --value "psy-v22-shadow@${INSTANCE}.service")"
nsenter --target "${MAINPID}" --mount -- \
  setpriv --reuid=psy --regid=psy --clear-groups /usr/bin/test ! -e /opt/psy1
```

同样验证 source/migration 在该 namespace 不可见，manifest 不可写，只有 runtime DB parent 可写。保存 unit 状态和 journal 的脱敏证据。

### 15. localhost smoke test

确认只有 `127.0.0.1:${SHADOW_PORT}` 在监听，无 `0.0.0.0`、ECS IP 或 IPv6 HTTP bind。直连 `/api/health` 应返回最小 `status=up`；通过带精确可信头/token 的本机测试请求验证 candidate，再确认正式 5000 状态未变化。不得把 token 写进 shell history 或 evidence。

### 16. 实例化独立 Nginx 配置

禁止 `sed`/`envsubst` 或手工字符串替换。必须使用同一批准 bundle 中的最小 renderer；它先验证 instance/release id、合法 FQDN、canonical IPv4、非特权端口，以及 certificate/key/ACME/snippet/output 的安全绝对路径，再渲染 `nginx-psy-v22-shadow.conf.template`：

```bash
/usr/bin/python3 /usr/local/libexec/psy-shadow-deployment.py render-nginx \
  --instance "${INSTANCE}" \
  --release-id "${RELEASE_ID}" \
  --template "/opt/psy/releases/shadow-${INSTANCE}/repo/personal-system-v2/deploy/nginx-psy-v22-shadow.conf.template" \
  --output "${SHADOW_NGINX_OUTPUT}" \
  --server-name "${SHADOW_SERVER_NAME}" \
  --bind-address "${ECS_BIND_ADDRESS}" \
  --port "${SHADOW_PORT}" \
  --certificate "${SHADOW_CERTIFICATE_PATH}" \
  --certificate-key "${SHADOW_CERTIFICATE_KEY_PATH}" \
  --acme-root "${ACME_ROOT}" \
  --proxy-auth-snippet "${SHADOW_PROXY_AUTH_SNIPPET}"

if grep -Eq '__PSY_SHADOW_[A-Z0-9_]*__' "${SHADOW_NGINX_OUTPUT}"; then
  echo "unresolved shadow Nginx placeholder" >&2
  exit 1
fi
nginx -t
```

Renderer 必须拒绝 newline、semicolon、braces、whitespace/path traversal 等配置注入输入，且拒绝覆盖已有 output。只有确认渲染结果不存在任何 `__PSY_SHADOW_*__` placeholder 后才允许 `nginx -t`。结果必须保留独立 `psy_v22_shadow` upstream，不能含 `default_server`、wildcard listen、正式 upstream/server_name/token 或 Tailscale 配置。获批后只 reload Nginx，不改正式 server block。

### 17. 配置并核验 DNS

由域名负责人创建独立 shadow hostname。先确认阿里云 EIP/NAT/安全组把公网目标正确转发到当次复验的私网地址；`8.137.186.60` 未被确认前不能据此改 DNS。等待权威 DNS 和外部解析一致，不改变正式域名。

### 18. 获取并核验 HTTPS

仅对 shadow FQDN 申请独立证书，证书路径必须与渲染参数一致。验证 chain、SAN、有效期、TLS 1.2/1.3、HTTP→HTTPS 308、无 mixed content；Certbot 不得改写或接管正式 Nginx server。

### 19. 真实浏览器验收

从至少一台非 ECS 的普通联网设备验证：未登录登录页、账号密码登录、candidate build identity（`v2.2.0-shadow · ${RELEASE_ID}`）、创建/修改/刷新持久化临时验收数据、退出、退出后 protected route/Back/offline 不恢复私人页面。检查 Secure/HttpOnly/SameSite cookie、CSP/HSTS/Host/CSRF/代理信任、Console/Network、service worker/cache；页面文档和 `/api/` 响应不得进入 PWA cache。保存脱敏 evidence，不保存密码、token、session 或私人正文。

### 20. 验证 production non-impact

对照 Phase 5A.0 基线核对正式 unit 状态/MainPID、5000 listener、正式域名 health、正式 Nginx/Tailscale 配置 hash和正式 active pointer hash未改变。命令清单中不得出现正式 DB 路径；不读取、stat、hash、复制或迁移正式数据库。若任何正式状态发生变化，Phase 5A 立即失败并升级处理。

### 21. Shadow stop / rollback 与人工门禁

失败或验收完成后，按批准顺序停止 `psy-v22-shadow@${INSTANCE}`，撤下仅 shadow 的 Nginx server 并 reload，确认 shadow 端口关闭而正式 5000/服务未变化。保留不可变 evidence 与 artifact 供审查；不要自动删除。记录 Phase 5A 状态后停止，只有新的明确人工批准才能讨论 Phase 5B。

## Phase 5A evidence 清单

- 审批参数、bundle/hash、source-copy 外部 identity（无业务内容）
- `namei/stat` 权限链和 `psy` 正/负访问结果
- migration/verifier/manifest/descriptor/launcher 的脱敏报告
- systemd unit、MainPID mount namespace `/opt/psy1` 不可见证明、listener/journal
- 渲染后 Nginx `-t`、DNS、证书、HTTP→HTTPS、health
- 浏览器身份/登录/写入持久化/退出/cache/Console/Network 验收
- 正式 unit/5000/pointer/Nginx/域名 pre/post 不变证明
- 全部命令、操作者、时间、返回码，以及“正式数据库未触碰”声明

## 执行前仍需人工提供

独立 shadow FQDN、EIP/NAT/安全组确认、当次 ECS 私网 bind 地址、release/instance id、批准 commit 和 bundle/hash、端口最终批准、经批准 source copy 的交付路径与外部 checksum、shadow admin 身份、证书方式、执行/回滚负责人、窗口和 evidence 保存位置。任何 secret 只在执行环境安全生成/传递，不能发到工单、Git 或命令记录。
