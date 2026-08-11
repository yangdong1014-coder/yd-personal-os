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

家庭服务器远程访问配置见 [home-server.md](home-server.md)。

## 环境变量（.env）

| 变量 | 说明 |
|------|------|
| DEEPSEEK_API_KEY | AI 功能必填；未配置时 CRUD 仍可用 |
| DEEPSEEK_BASE_URL | 默认 DeepSeek API 地址 |
| DEEPSEEK_MODEL | 锁定模型后 AI 管理页不可改 |
| DEEPSEEK_TIMEOUT | 请求超时秒数 |
| YD_OS_DB_PATH | 覆盖 SQLite 路径（测试常用） |
| SECRET_KEY | session 签名密钥；生产、远程或非 loopback 运行必填，至少 32 字节强随机值 |
| PERSONAL_OS_ENV | 本机开发必须显式设 `development`；缺失/未知值与 `production` 均进入加固模式 |
| PERSONAL_OS_REMOTE | 远程部署安全信号；也用于许可显式非 localhost 绑定，不承担鉴权 |
| PERSONAL_OS_BIND_HOST | 显式绑定地址，默认 127.0.0.1 |
| PERSONAL_OS_BG | 仅控制正常本地开发的后台/debug 行为，不能覆盖生产安全判断 |

只有显式 `PERSONAL_OS_ENV=development` 且 loopback、非远程时才允许临时密钥和本地 debug。其他环境值、缺失环境值、`PERSONAL_OS_REMOTE=1` 或非 loopback 绑定都会进入同一安全校验。反向代理后端即使绑定 loopback，也必须显式设置远程或生产信号。

## 管理员初始化

首次使用前先配置持久 `SECRET_KEY` 并初始化唯一 bootstrap 管理员：

```bash
cd personal-system-v2
python -m flask --app app bootstrap-admin
```

命令在终端隐藏输入并二次确认密码，不接受前端或管理 API 创建管理员。初始化后通过 `/login` 登录；所有来源（包括 `127.0.0.1`）都必须认证。

## 运行测试

```bash
cd personal-system-v2
pytest
pytest -v tests/test_obsidian_export.py   # 单文件
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
2. **导入**：合并模式，失败会 `rolled_back: true`，不会部分写入
3. **提示词路径**：scene 仅允许 `[a-z0-9-]+`，防止路径穿越
4. **版本号**：只改 `changelog.json`，勿在 README 写死版本
5. **Obsidian**：v1.10 仅 zip 下载，不写入用户 vault

## 调试

- Flask 默认 `debug=True`，仅本地使用
- 修改 `prompts/` 后无需重启即可被 loader 读取（下次 AI 调用）
