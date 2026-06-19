# PSY-1 Aliyun ECS Deployment MVP

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
- PERSONAL_OS_ACCESS_TOKEN
- yd_os.db
- database backups
- .venv/

## Current Status

- ECS deployment: done
- systemd service: running
- Tailscale HTTP access: working
- Token login: working
- DeepSeek API call: working
- Real database migration: pending
- Automatic backup: pending
- Domain and ICP filing plan: pending

## Next Steps

- Rotate exposed DeepSeek API Key
- Rotate PERSONAL_OS_ACCESS_TOKEN
- Migrate real yd_os.db
- Add automatic database backup
- Evaluate domain, ICP filing, and public personal website access
