# 家庭服务器模式

## 当前边界

v2.2 Phase 3 已在本地开发完成账户、所有权 schema、Repository/Service/AI 隔离和普通用户业务入口。正式生产仍为 v2.1.4；本阶段不得部署或迁移生产数据库，本文的远程拓扑仍只是后续发布建议。

远程拓扑仍建议为：

```text
手机（Tailscale）→ 受控 HTTPS → 家里电脑 PSY（127.0.0.1:5000）
```

## 安全原则

| 原则 | 说明 |
|------|------|
| 默认监听 | `127.0.0.1:5000`，不默认暴露公网 |
| 单一认证 | 本机与远程都使用用户 session，不存在本机免验或共享凭据旁路 |
| HTTPS | 远程输入密码和发送 session cookie 时必须使用受控 HTTPS |
| 持久密钥 | 生产、远程或非 loopback 运行必须设置至少 32 字节强随机 `SECRET_KEY` |
| 显式绑定 | `PERSONAL_OS_BIND_HOST` 非 localhost 时必须同时设置 `PERSONAL_OS_REMOTE=1` |
| 运行加固 | 上述任一暴露信号都会强制 Secure cookie、`debug=False` 与关闭 reloader |
| 数据边界 | 16 张业务表按 `user_id` 隔离；admin 与 user 都只能访问自己的私人业务数据 |

`PERSONAL_OS_REMOTE` 标记远程可达运行并许可显式非 localhost 绑定，不参与身份认证。通过反向代理远程访问时，即使 Flask 仍绑定 loopback，也必须设置该信号或生产信号。旧共享访问凭据及其 URL、Header、Cookie、localStorage 路径已从 Phase 1 代码删除。

## 本地开发配置

所有开发、手测先使用临时数据库，禁止指向 `data/yd_os.db`：

```powershell
$env:YD_OS_DB_PATH = Join-Path $env:TEMP "psy-v22-auth-dev.db"
$env:PERSONAL_OS_ENV = "development"
$env:SECRET_KEY = "请替换为至少32字节的本地随机值"
python -m flask --app app bootstrap-admin
python app.py
```

`bootstrap-admin` 在终端隐藏输入并二次确认密码；管理员不能通过前端或管理 API 创建。不要把密钥、密码或临时数据库提交到 Git。

受控远程配置在后续正式发布前另行验收。目标配置至少包括：

```env
PERSONAL_OS_ENV=production
PERSONAL_OS_REMOTE=1
SECRET_KEY=至少32字节强随机值
```

只有确需 Flask 直接绑定非 localhost 时才增加：

```env
PERSONAL_OS_BIND_HOST=受控内网地址
```

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

`GET /api/health`、静态资源与 service worker 保持公开；公开不代表它们能读取业务数据。

## PWA 缓存边界

- service worker 只缓存 CSS、JavaScript、manifest 与图标等静态资源。
- `/login` 和所有业务 HTML navigation 不进入 Cache Storage。
- `/api/*` 与所有非 GET 请求不缓存。
- 激活新版 worker 时删除全部旧版本 Cache Storage；退出响应清理 cache 与 storage。
- bfcache 恢复认证页面时先隐藏内容并重新校验 session；失败或离线时不显示旧私人内容。
- 即使离线，也不以旧业务 HTML 作为 fallback。

## Windows 常开设置

1. 电源设置关闭自动睡眠；笔记本按实际需要设置合盖行为。
2. 保持网络连接稳定，不做公网 5000 端口转发。
3. 可用 `scripts/install-startup.vbs` 配置开机自启。
4. 后台运行使用 `scripts/start-server.vbs`。

## 启动、停止与备份

| 操作 | 命令 |
|------|------|
| 启动 | 桌面「个人能力操作系统」或 `scripts/start-server.vbs` |
| 停止 | `scripts/stop-server.bat` |
| 健康检查 | `scripts/check-health.bat` 或 `GET /api/health` |
| 数据库备份 | `python scripts/backup-db.py` |

备份位置为 `personal-system-v2/backups/yd_os_YYYYMMDD_HHMMSS.db`，默认保留最近 30 份。生产备份、migration 与恢复必须另按数据库和发布规范执行，本阶段不操作生产。

## Phase 1 本地验收清单

- [ ] 使用临时 `YD_OS_DB_PATH`，没有读取或写入真实数据库
- [ ] bootstrap 管理员在并发下也只能原子初始化一次，密码不回显
- [ ] 本机与模拟远程地址未登录均无法访问业务数据
- [ ] 普通用户只能访问认证/改密表面，所有业务页面与 API 都由后端拒绝
- [ ] 登录、全会话退出、禁用、重置与首次改密行为符合上表
- [ ] service worker 升级会清旧 cache，不缓存登录后 HTML，也不提供旧页面离线 fallback
- [ ] `backup-db.py` 的既有回归测试仍通过
- [ ] 正式生产 v2.1.4 未被修改或部署
