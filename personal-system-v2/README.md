# 个人能力操作系统 v2

本地优先的个人操作系统。Flask + SQLite + 原生 HTML/CSS/JS，可选接入 DeepSeek API。

**当前版本：v1.9**

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

## 数据导出与导入

导航栏右侧「导出备份」按钮，或请求 `GET /api/export`，下载 JSON 备份。

「导入恢复」按钮采用**先预览、后导入**流程：

1. 选择 JSON 备份文件
2. 调用 `POST /api/import/preview` 进行 dry-run（不写库）
3. 预览面板展示预计新增、更新、跳过、失败数量
4. 确认后调用 `POST /api/import` 执行合并导入

合并导入规则：

- 按 `id` 判断：不存在则插入，存在且内容相同则跳过，存在且内容不同则更新
- **不会自动清空**现有数据；误导入错误备份可能覆盖同 id 记录
- **建议导入前先导出当前备份**
- 导入失败时事务回滚，不破坏已有数据
- 预览返回 `{ will_import, will_update, will_skip, will_fail, errors }`
- 导入返回 `{ imported, skipped, failed, errors }`，并在结果面板中展示

## 操作反馈（Toast）

全局轻量 toast 替代 `alert`，用于保存成功、删除失败、AI 错误、导入结果等提示。危险操作（删除、导入确认）仍使用 `confirm` 二次确认。

## 数据删除

各列表页提供删除按钮，操作前需确认，**不可撤销**：

| 对象 | 级联行为 |
|------|----------|
| 目标 (goal) | 级联删除其下所有项目与任务 |
| 项目 (project) | 级联删除其下所有任务 |
| 复盘 (review) | 关联资产的 `source_review_id` 置为 NULL，资产本身保留 |
| 任务 / 资产 / 能力记录 | 无子表级联 |

外键约束由 `PRAGMA foreign_keys = ON` 保障，不会产生孤儿数据。

## 测试

```bash
cd personal-system-v2
pip install -r requirements.txt
pytest
```

- 测试使用**临时 SQLite 数据库**，不依赖生产 `data/yd_os.db`
- pytest fixture 会覆盖 `database.DB_PATH`；也可通过环境变量 `YD_OS_DB_PATH` 指定数据库路径
- 覆盖首页/changelog、列表、删除（含级联）、导入（去重/回滚）等基础回归

## 版本记录

- 页面 `/changelog` 展示历史版本
- `changelog.json` 中 `current` 字段为当前正式版号
- 页面版本徽章统一读取 `changelog.current`

版本线：v1.0（数据导出）→ v1.1–v1.4（AI Phase 1–4）→ v1.5（提示词管理）→ v1.6（模型选择）→ v1.7（提示词 AI 生成）→ v1.8（布局与体验升级）→ v1.8.1（数据能力闭环收口）→ **v1.9**（toast 与导入体验优化）

## 项目文档

| 文档 | 说明 |
|------|------|
| [系统搭建说明书 1.1](../docs/系统搭建说明书_1.1.md) | 系统宪法、架构原则与模块规范（最高约束文件） |

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