# Step 4.3 本地受限验收证据说明

日期：2026-08-13

这是 Phase 4.3 的本地受限验收记录，不是 Phase 5 ECS 公网 HTTPS 最终验收或生产关账记录。

本目录只保存使用临时数据库和本地 disposable reverse-proxy harness 产生的浏览器截图。没有读取或修改真实 `data/yd_os.db`，也没有操作 ECS、真实 Nginx/systemd、Tailscale、DNS 或正式证书。

## 已验证

- admin 创建、禁用、启用、重置普通用户；普通用户不能进入 admin 页面。
- user A / user B 分别创建并刷新 goal、project、task，数据互不可见，admin 业务空间不显示 A/B 私人数据。
- logout 后旧 session/API 失效；Back 与断网场景未恢复私人 HTML；恢复联网后认证状态正确。
- 功能流程期间 Console 无 CSP violation；HTTPS 客户端验证 nonce CSP、HSTS、private/API `no-store`、Cookie flags 与旧 Cookie 失效。
- 当时对 390、768、1024、1440 四个视口的 DOM 测量均无横向溢出，导航、表单和按钮可用；这不表示每个页面和视口均形成了有效截图，截图有效性以本记录的截图索引为准。

## 证据限制

- 当前 Windows 主机没有可用 WSL distribution、容器 runtime、Gunicorn 或 Nginx，所以这里的 harness 不是 Linux/Gunicorn/Nginx 生产链路证据。
- 临时自签名证书没有进入浏览器信任链。浏览器功能流程使用 HTTP 测试 origin，由 harness 内部构造受信代理边界；HTTPS、HSTS、Cookie、nonce CSP 和请求限制另由本地 TLS 客户端验证。这不能替代可信 HTTPS 浏览器验收。
- 截图后端在部分视口切换后曾沿用旧的 390px 宽度，并产生错误尺寸或无效截图；这些错误抓取现已清理，不作为正式 evidence。窄屏有效截图可能因垂直滚动条使内容位图宽度比请求视口少约 10px。
- 当前保留截图页面上的版本标记仍为 `v2.1.4`，因此不能作为 v2.2 build identity 的强证明。Phase 5 正式取证时必须确保页面版本和构建身份与实际部署一致。
- 当前截图主要证明本地受限环境下的页面布局、登录流程和隔离行为，不能证明 ECS、公网 HTTPS、真实域名或真实 Secure Cookie 链路已经最终通过。Phase 5 必须在真实浏览器中重新完成验收，并重跑 Cookie/Network/CSP/PWA 与所需断点取证。

## 截图索引

- `admin-users-{1440,1024,768,390}.png`：均为当前有效的本地布局 evidence。
- `login-768.png`：有效本地 evidence。原 `login-390.png` 无效并已清理；390 登录页视口在本地 Phase 4.3 未形成有效截图，待 Phase 5 公网 HTTPS 环境重新验证和取证。1024/1440 同样尚无有效本地截图。
- `user-tasks-{768,390}.png`：有效本地 evidence。原 `user-tasks-1024.png` 无效并已清理；1024 任务页视口在本地 Phase 4.3 未形成有效截图，待 Phase 5 公网 HTTPS 环境重新验证和取证。1440 同样尚无有效本地截图。
- 本地取证中曾产生 `invalid-capture-*` 错误截图，现已清理；这些错误抓取不属于正式 evidence。

截图不包含密码、临时密码或 session token。
