# 开发指南

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

## 环境变量（.env）

| 变量 | 说明 |
|------|------|
| DEEPSEEK_API_KEY | AI 功能必填；未配置时 CRUD 仍可用 |
| DEEPSEEK_BASE_URL | 默认 DeepSeek API 地址 |
| DEEPSEEK_MODEL | 锁定模型后 AI 管理页不可改 |
| DEEPSEEK_TIMEOUT | 请求超时秒数 |
| YD_OS_DB_PATH | 覆盖 SQLite 路径（测试常用） |

## 运行测试

```bash
cd personal-system-v2
pytest
pytest -v tests/test_obsidian_export.py   # 单文件
```

- 使用临时数据库，**不要**指向生产 `data/yd_os.db`
- 无需 `DEEPSEEK_API_KEY`

## 目录约定

| 路径 | 职责 |
|------|------|
| `app.py` | 路由 |
| `database.py` | 数据层 |
| `obsidian_export.py` | Obsidian Markdown zip |
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