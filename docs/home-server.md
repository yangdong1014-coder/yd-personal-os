# 历史方案：家庭服务器与 Tailscale

> **历史定位**：本文保留 Windows Home Server、Tailscale 与 Phase 4.3 本地受限验收的历史背景和仍有价值的安全原则。它不是 PSY v2.2 当前部署 runbook，也不再把家庭电脑、VPN、本地 CA 或本地 TLS 模拟环境作为主方向。

## 当前方向与历史边界

当前正式方向是复用阿里云 ECS，以正常域名经公网 HTTPS 访问；Nginx 反向代理到 loopback Gunicorn，Flask 使用账号密码登录并读写 SQLite。Phase 5A 先做不触碰现有生产 pointer 与真实数据库的影子部署，验收并获得人工批准后才可能进入 Phase 5B 正式切换。

本文历史方案曾采用：

```text
手机（Tailscale）→ 受控 HTTPS → 家里电脑 PSY（127.0.0.1:5000）
```

该拓扑不再是当前推荐方案。下文凡涉及 Windows 常开、Tailscale、本地证书或桌面脚本，均按历史资料理解；生产契约和 Phase 5 执行顺序以 [架构说明](architecture.md) 与 [Phase 5 Runbook](phase-5-database-cutover-runbook.md) 为准。

## 安全原则

| 原则 | 说明 |
|------|------|
| 默认监听 | `127.0.0.1:5000`，不默认暴露公网 |
| 单一认证 | 本机与远程都使用用户 session，不存在本机免验或共享凭据旁路 |
| HTTPS | 远程输入密码和发送 session cookie 时必须使用受控 HTTPS |
| 持久密钥 | 加固运行必须设置至少 32 字节并通过弱值/熵校验的强随机 `SECRET_KEY` |
| 显式绑定 | 加固运行只允许 `127.0.0.1:5000`，不能把应用服务器直接暴露公网 |
| 代理信任 | 只接受一个精确 loopback peer、一个转发跳数、HTTPS 与精确公网 Host |
| 代理凭据 | Nginx 覆盖注入独立强随机 `X-PSY-Proxy-Token`；应用在 ProxyFix 前校验并移除，直连上游不能只靠伪造转发头冒充代理 |
| 运行加固 | Secure/HttpOnly/SameSite cookie、固定 session、debug/reloader fail closed |
| 数据边界 | 16 张业务表按 `user_id` 隔离；admin 与 user 都只能访问自己的私人业务数据 |

`PERSONAL_OS_REMOTE` 标记远程可达运行，不参与身份认证。生产同时要求 `PERSONAL_OS_ENV=production`，并只能经精确信任的 HTTPS 反向代理访问。旧共享访问凭据及其 URL、Header、Cookie、localStorage 路径已从 Phase 1 代码删除。

## 历史本地开发与模拟配置

所有开发、手测先使用临时数据库，禁止指向真实 `personal-system-v2/data/yd_os.db`：

```powershell
$env:YD_OS_DB_PATH = Join-Path $env:TEMP "psy-v22-auth-dev.db"
$env:PERSONAL_OS_ENV = "development"
$env:SECRET_KEY = "请替换为至少32字节的本地随机值"
python -m flask --app app bootstrap-admin
python app.py
```

`bootstrap-admin` 在终端隐藏输入并二次确认密码；管理员不能通过前端或管理 API 创建。不要把密钥、密码或临时数据库提交到 Git。

Phase 4.1 当时记录的安全变量如下；这不是当前生产 runtime env，也不能用来直接启动生产。当前生产 runtime config 禁止包含 `YD_OS_DB_PATH`，数据库路径由 descriptor/launcher 注入：

```env
PERSONAL_OS_ENV=production
PERSONAL_OS_REMOTE=1
SECRET_KEY=至少32字节强随机值
PERSONAL_OS_TRUSTED_HOSTS=精确公网域名
PERSONAL_OS_TRUSTED_PROXY=127.0.0.1
PERSONAL_OS_PROXY_TOKEN=与SECRET_KEY不同的至少32字节强随机值
PERSONAL_OS_BIND_HOST=127.0.0.1
```

Phase 4.3 已将 Step 4.2 的 active release pointer 接入稳定启动器；生产服务不得直接选择 code、config 或 DB：

```bash
python /opt/psy/launcher/production_launcher.py \
  --active-pointer /var/lib/psy/releases/active-release.json \
  --descriptor-root /var/lib/psy/releases \
  --release-root /opt/psy/releases \
  --config-root /etc/psy/releases \
  --database-root /var/lib/psy/databases \
  --expected-app-version "$PSY_APPROVED_APP_VERSION" \
  --expected-git-commit "$PSY_APPROVED_GIT_COMMIT" \
  --check
```

启动器只解析一个 active pointer，并将 descriptor 中经过 hash/manifest 校验的 code tree、入口、外置 runtime config 和可变运行 DB 作为一个单元传给 `production.py --check` 与 Gunicorn；它不会猜测或回退到 `data/yd_os.db`，也不会执行 shell。`gunicorn.conf.py` 强制 loopback、preload、1 worker + gthread/4 threads；零参数 `production:create_production_app()` 在同一进程、监听前重复解析并核对选择结果。

仓库中的 [`personal-system-v2/deploy/psy-v22.service`](../personal-system-v2/deploy/psy-v22.service) 与 [`personal-system-v2/deploy/nginx-psy-v22.conf`](../personal-system-v2/deploy/nginx-psy-v22.conf) 是待 Phase 5 审批的安全模板，不是已安装配置。本轮没有操作真实 systemd/Nginx/ECS，也没有执行真实数据库切换。

## 认证行为

| 场景 | 结果 |
|------|------|
| 未登录访问业务 HTML | 跳转 `/login` |
| 未登录访问 JSON API | `401` |
| 普通用户访问 admin API | `403 admin_required` |
| 普通用户首次改密后访问业务 HTML/API | 正常进入本人 owner-scoped 业务空间 |
| 用户被禁用 | 现有 session 下一请求立即失效 |
| 密码重置或 `auth_version` 变化 | 旧 session 下一请求失效 |
| 退出 | 递增 `auth_version`，撤销该账户全部现有 session |
| 首次临时密码登录 | 强制进入 `/change-password` |
| 浏览器写请求缺失 CSRF | `400` |

`GET /api/health`、静态资源与 service worker 保持公开；健康响应只包含 `{"ok":true,"data":{"status":"up"}}`，不返回版本、运行模式、数据库路径或账户信息。

## PWA 缓存边界

- service worker 只缓存 CSS、JavaScript、manifest 与图标等静态资源。
- `/login` 和所有业务 HTML navigation 不进入 Cache Storage。
- `/api/*` 与所有非 GET 请求不缓存。
- 激活新版 worker 时删除全部旧版本 Cache Storage；退出响应清理 cache 与 storage。
- bfcache 恢复认证页面时先隐藏内容并重新校验 session；失败或离线时不显示旧私人内容。
- 即使离线，也不以旧业务 HTML 作为 fallback。

## 历史 Windows 常开设置

1. 电源设置关闭自动睡眠；笔记本按实际需要设置合盖行为。
2. 保持网络连接稳定，不做公网 5000 端口转发。
3. 可用 `scripts/install-startup.vbs` 配置开机自启。
4. 后台运行使用 `scripts/start-server.vbs`。

## 历史启动/停止入口与现行备份参考

| 操作 | 命令 |
|------|------|
| 启动 | 桌面「个人能力操作系统」或 `scripts/start-server.vbs` |
| 停止 | `scripts/stop-server.bat` |
| 健康检查 | `scripts/check-health.bat` 或 `GET /api/health` |
| 数据库备份 | 按 [Phase 5 Runbook](phase-5-database-cutover-runbook.md) 显式传入绝对路径、schema、commit 与版本 |

旧 `copy2` 活跃 SQLite 主文件、默认真实 DB 路径与自动覆盖/裁剪策略已废止。正式工具使用 SQLite backup API，并生成包含 hash、size、schema、表集合、row counts、integrity/FK、commit/version 的 machine-readable manifest；每次恢复到新路径后必须复验。具体命令和完整 code+DB rollback 见 [Phase 5 数据库切换与回滚 Runbook](phase-5-database-cutover-runbook.md)。本阶段不操作生产。

## 历史 Phase 4.1 本地验收清单（记录性）

以下勾选模板保留当时的验收范围，不作为当前部署路线或 Phase 4 收口状态真源；公网环境相关项目统一进入 Phase 5A 重新验收。

- [ ] 使用临时 `YD_OS_DB_PATH`，没有读取或写入真实数据库
- [ ] bootstrap 管理员在并发下也只能原子初始化一次，密码不回显
- [ ] 本机与模拟远程地址未登录均无法访问业务数据
- [ ] 普通用户只访问本人 owner-scoped 业务空间，admin 不绕过私人数据边界
- [ ] 登录、全会话退出、禁用、重置与首次改密行为符合上表
- [ ] service worker 升级会清旧 cache，不缓存登录后 HTML，也不提供旧页面离线 fallback
- [ ] `backup-db.py` 使用显式绝对路径、SQLite backup API、不可覆盖 artifact 与 restore verification
- [ ] 弱密钥、未知 Host、伪造/多跳代理头、HTTP、超大请求与过量登录失败均 fail closed
- [ ] Cookie flags、CSP/HSTS/安全头、健康最小暴露和日志隐私已验证
- [ ] 未引入 MFA、OAuth 或外部身份平台；当前 P0 不扩展这些能力
- [ ] 正式生产 v2.1.4 未被修改或部署

## 历史 Phase 4.3 本地浏览器记录与 Phase 5A carry-over

Step 4.3 曾使用临时数据库和本地 reverse-proxy harness 验证功能流程与响应式布局。Windows/Linux runtime 差异、自签证书、本地 CA 和错误尺寸截图不再阻止 Phase 4 收口；未完成的公网 HTTPS、Secure Cookie、Console/Network 与截图项目必须在 Phase 5A ECS 真实域名环境重新验收。以下未勾选项表示 Phase 5A carry-over，不表示当前已经通过：

- [ ] login：验证 admin、普通用户、首次临时密码强制改密及错误凭据不枚举账户
- [ ] logout：验证私人页面/API 与复制的旧 session 失效，`Clear-Site-Data` 生效
- [x] back：退出后 Back 不恢复私人 HTML，最终回到 `/login`；bfcache/offline 的可信 HTTPS 复验仍随下项阻塞
- [ ] offline：reload/navigation/Back 不从 Cache Storage 或 bfcache 展示旧私人页面；恢复联网后认证状态正确
- [ ] CSP console：login 到 admin/user 核心流程无 CSP violation、脚本失败或 mixed content；nonce 一致
- [ ] Secure Cookie：本地 HTTPS origin 下验证 `Secure`/`HttpOnly`/`SameSite=Lax`，退出后失效；HTTP 不发送 session cookie
- [x] admin/user 核心流程：admin 创建/禁用/启用/重置临时用户；A/B 分别创建并刷新 goal/project/task，互不可见；admin 不读取 A/B 私人数据；普通用户 admin 页面被拒绝
- [x] 390/768/1024/1440：逐一检查 login、代表性 user 页和 admin users 页，DOM 测量无横向溢出且交互可用
- [ ] 响应式截图：本地有效 evidence 仅包括 admin-users 390/768/1024/1440、login 768、user-tasks 390/768；login 390 与 user-tasks 1024 的原截图无效且已清理，待 Phase 5A 公网 HTTPS 复验（login 1024/1440 与 user-tasks 1440 同样尚无有效本地截图）。这些本地 Phase 4.3 evidence 不是公网 HTTPS 最终验收；Console/Network/Cookie 证据同样随 TLS 浏览器项阻塞
