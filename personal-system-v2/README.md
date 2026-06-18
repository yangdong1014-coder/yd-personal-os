# 个人能力操作系统 v2

本地优先的个人操作系统。Flask + SQLite + 原生 HTML/CSS/JS，可选接入 DeepSeek API。

**当前版本：v1.8**

## 主要模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 首页 | `/` | 指挥部总览、AI 今日简报、AI 行动分发 |
| 目标 | `/goals` | 目标管理、项目拆解、AI 拆解项目 |
| 任务 | `/tasks` | 任务管理、今日推进、AI 拆任务/今日推荐 |
| 复盘 | `/reviews` | 日复盘/周复盘、AI 补全、周聚合、AI 提炼资产 |
| 资产 | `/assets` | 知识卡片、AI 优化/归类/模板化 |
| 能力 | `/capabilities` | 八能力模块记录、AI 归因/诊断 |
| AI管理 | `/prompts` | 模型切换、提示词编辑、AI 生成初版 |
| 版本日志 | `/changelog` | 各版本更新记录 |

## 启动

```bash
cd personal-system-v2
pip install -r requirements.txt
cp .env.example .env   # 编辑 .env，填入 DEEPSEEK_API_KEY
python app.py
```

浏览器访问 http://127.0.0.1:5000

## 环境变量

在项目根目录创建 `.env`（参考 `.env.example`）：

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | 是（AI 功能） | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | 否 | API 地址，默认 `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | 否 | 锁定模型；设置后 AI管理页不可改 |
| `DEEPSEEK_TIMEOUT` | 否 | 超时秒数，默认 60 |

未配置 `DEEPSEEK_API_KEY` 时，CRUD 功能正常，AI 按钮不可用。

## 数据文件

| 路径 | 说明 |
|------|------|
| `data/yd_os.db` | SQLite 主数据库（git 忽略） |
| `data/settings.json` | AI 模型选择（git 忽略） |
| `prompts/` | AI 场景提示词（可经 AI管理页编辑） |
| `changelog.json` | 版本日志数据源 |

## 数据导出

导航栏右侧「导出备份」按钮，或请求 `GET /api/export`，下载 JSON 备份。

当前**无导入恢复接口**，备份仅用于归档与手动迁移。

## 版本记录

- 页面 `/changelog` 展示历史版本
- `changelog.json` 中 `current` 字段为当前正式版号
- 页面版本徽章统一读取 `changelog.current`

版本线：v1.0（数据导出）→ v1.1–v1.4（AI Phase 1–4）→ v1.5（提示词管理）→ v1.6（模型选择）→ v1.7（提示词 AI 生成）→ **v1.8**（布局与体验升级）

## 目录结构

```
app.py              Flask 入口与 API 路由
database.py         SQLite 数据层
ai_service.py       DeepSeek AI 调用
config.py           环境变量与模型配置
settings_store.py   AI 模型持久化
changelog.py        版本日志读取
prompt_specs.py     提示词生成场景元数据
prompts/            提示词文件与 loader
data/               运行时数据
static/             CSS / JS
templates/          页面模板
```

## 开发说明

- 默认 `debug=True`，仅用于本地开发
- 数据库连接已启用 `PRAGMA foreign_keys = ON`
- 提示词 `scene` 仅允许小写字母、数字与连字符（如 `decompose-tasks`）