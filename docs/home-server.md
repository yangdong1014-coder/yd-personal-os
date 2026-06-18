# 家庭服务器模式（v1.13+）

## 定位

将家里常开的 Windows 电脑作为 PSY-1 **家庭服务器**，供手机在外通过 **Tailscale** 安全访问。本版本只做远程访问 MVP，不包含完整移动端。

```
手机（Tailscale）→ tailnet → 家里电脑 PSY-1（127.0.0.1:5000）
```

## 安全原则

| 原则 | 说明 |
|------|------|
| 默认监听 | `127.0.0.1:5000`，不默认暴露公网 |
| 禁止默认 `0.0.0.0` | 不允许未配置时监听所有网卡 |
| 不推荐端口转发 | 不要将路由器 5000 端口映射到公网 |
| 推荐远程方式 | **Tailscale** 组网 + 访问令牌 |
| 显式开启远程 | 设置 `PERSONAL_OS_REMOTE=1` 后才要求 token |
| 显式改绑定 | `PERSONAL_OS_BIND_HOST` 仅在 `REMOTE=1` 时允许非 localhost |

## 环境变量

在 `personal-system-v2/.env` 中配置：

```env
PERSONAL_OS_REMOTE=1
PERSONAL_OS_ACCESS_TOKEN=你的长随机令牌
```

可选：

```env
# 仅在 REMOTE=1 时生效；默认 127.0.0.1
# PERSONAL_OS_BIND_HOST=100.x.x.x
```

生成 token 示例（PowerShell）：

```powershell
[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
```

## Tailscale 推荐配置

### 1. 安装与登录

1. 在家里电脑安装 [Tailscale](https://tailscale.com/download)。
2. 在手机安装 Tailscale 客户端。
3. 使用**同一账号**登录。

### 2. 启动 PSY-1

- 桌面快捷方式（后台无黑框）
- 或 `scripts/install-startup.vbs` 开机自启

### 3. 暴露服务（推荐 Tailscale Serve）

Flask 保持 `127.0.0.1:5000`，用 Serve 转发到 tailnet：

```powershell
tailscale serve --bg 5000
```

手机浏览器访问（示例）：

```
http://你的机器名.tailnet-name.ts.net:端口/?token=你的令牌
```

或 Tailscale IP（若使用 `PERSONAL_OS_BIND_HOST` 绑定 tailnet IP）：

```
http://100.x.x.x:5000/?token=你的令牌
```

### 4. 不建议的做法

- ❌ 路由器端口转发 5000 到公网
- ❌ 未设 token 就开启 `PERSONAL_OS_REMOTE=1`
- ❌ 将 token 分享给不可信的人

## 访问鉴权

| 访问来源 | 是否需要 token |
|----------|----------------|
| 本机 `127.0.0.1` | 否（保持原有体验） |
| Tailscale / 局域网远程 | 是 |

令牌传递方式：

1. URL：`/?token=xxx`（首次推荐）
2. 请求头：`X-Personal-OS-Token: xxx`（API）
3. Cookie：首次 URL 验证成功后自动写入（页面跳转用）
4. localStorage：前端 API 自动携带

## Windows 常开设置

1. **电源**：控制面板 → 电源选项 → 关闭「睡眠」；笔记本合盖可选「不采取任何操作」。
2. **网络**：保持 Wi-Fi/有线不断线；路由器勿频繁断网。
3. **开机自启**：`scripts/install-startup.vbs`。
4. **后台运行**：使用桌面快捷方式（`start-server.vbs`）。

## 启动 / 停止 / 健康检查

| 操作 | 命令 |
|------|------|
| 启动 | 桌面「个人能力操作系统」或 `scripts/start-server.vbs` |
| 停止 | `scripts/stop-server.bat` |
| 健康检查 | `scripts/check-health.bat` 或 `GET /api/health` |
| 数据库备份 | `python scripts/backup-db.py` |

## 数据库备份与恢复

### 自动备份脚本

```bash
python scripts/backup-db.py
python scripts/backup-db.py --keep 30
```

备份位置：`personal-system-v2/backups/yd_os_YYYYMMDD_HHMMSS.db`  
默认保留最近 **30** 份；`backups/` 已加入 `.gitignore`。

### 手动恢复

1. `scripts/stop-server.bat` 停止服务。
2. 复制备份文件覆盖 `personal-system-v2/data/yd_os.db`。
3. 重新启动 PSY-1。

也可用 JSON 全量备份（侧边栏「导出备份」）通过导入恢复。

## 验收清单

- [ ] 桌面快捷方式启动正常
- [ ] `/api/health` 返回 `status: up`
- [ ] 本机 `http://127.0.0.1:5000` 无需 token
- [ ] `PERSONAL_OS_REMOTE=1` 时，远程无 token 返回 403
- [ ] 带正确 token 可访问页面与 API
- [ ] 手机 Tailscale 访问成功
- [ ] `backup-db.py` 生成备份且原库不变