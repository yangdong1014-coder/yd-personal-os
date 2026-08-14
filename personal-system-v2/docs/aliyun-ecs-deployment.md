# PSY-1 Aliyun ECS Deployment MVP

> **历史归档，不是 v2.2 部署手册。** 本文只记录 2026-06-19 的 v1.14.0 状态。Gunicorn 继续作为 v2.2 正式 WSGI Server，但本文中的旧启动参数、Tailscale HTTP Serve 和共享 access token 均不构成 v2.2 Phase 4 安全契约。v2.2 的候选启动链和配置仅见 `deploy/psy-v22.service`、`deploy/nginx-psy-v22.conf` 与 `production_launcher.py`，仍须 Phase 5 单独审批和真实 Ubuntu smoke；禁止据此文执行 v2.2 部署。当前任务也未操作 ECS、Tailscale、Nginx、systemd 或真实数据库。

Date: 2026-06-19
Version: v1.14.0

## Deployment Result

PSY-1 has been deployed successfully on Aliyun ECS as a private cloud personal system.

## Environment

- Server: Aliyun ECS, Chengdu
- OS: Ubuntu 22.04
- Runtime: Python 3.10 + venv
- App Server: gunicorn
- Service Manager: systemd
- Access Method: Tailscale HTTP Serve
- App Bind: 127.0.0.1:5000
- Health Check: /api/health
- AI Provider: DeepSeek

## Runtime Commands

Check service:

    systemctl status psy1 --no-pager

Restart service:

    systemctl restart psy1

Check local health:

    curl -i http://127.0.0.1:5000/api/health

Check Tailscale Serve:

    tailscale serve status

Start Tailscale HTTP Serve:

    tailscale serve --bg --http=80 5000

## DeepSeek Troubleshooting

If AI calls fail, first check DNS:

    getent hosts api.deepseek.com
    getent hosts www.baidu.com
    curl -I https://www.baidu.com

If DNS cannot resolve common domains, fix server DNS before changing API keys or model settings.

Direct DeepSeek test:

    curl -sS -o /tmp/ds_chat.json -w "\nHTTP_STATUS:%{http_code}\n" \
      https://api.deepseek.com/chat/completions \
      -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"只回复：ok"}],"stream":false}'

Expected result:

    HTTP_STATUS:200

## Security Notes

Never commit:

- .env
- .env backups
- DeepSeek API keys
- historical shared access credentials
- yd_os.db
- database backups
- .venv/

## Current Status

- ECS deployment: done
- systemd service: running
- Tailscale HTTP access: working
- Historical shared-token login: retired in v2.2
- DeepSeek API call: working
- Real database migration: pending
- Automatic backup: pending
- v2.2 backup/cutover/rollback 工具已仅在临时数据库验证；正式操作必须使用 [`../../docs/phase-5-database-cutover-runbook.md`](../../docs/phase-5-database-cutover-runbook.md)，本文旧部署命令不得替代该门禁
- Domain and ICP filing plan: pending

## Next Steps

- Rotate exposed DeepSeek API Key
- Remove any remaining historical shared access credentials
- Migrate real yd_os.db
- Add automatic database backup
- Evaluate domain, ICP filing, and public personal website access
