# 数据模型

SQLite 表结构及关系说明（`database.py` / `init_db`）。

## 实体关系

```
goals (1) ──< projects (N) ──< tasks (N)

reviews (1) ──< assets (N, optional source_review_id)

capability_entries — 独立表，无外键
```

## 表说明

### goals

| 字段 | 说明 |
|------|------|
| id | 主键 |
| name | 目标名称 |
| type | 年度 / 季度 / 月度 / 当前主线 |
| created_at | 创建时间 |

### projects

| 字段 | 说明 |
|------|------|
| id | 主键 |
| goal_id | → goals.id，`ON DELETE CASCADE` |
| name | 项目名称 |
| created_at | 创建时间 |

### tasks

| 字段 | 说明 |
|------|------|
| id | 主键 |
| project_id | → projects.id，`ON DELETE CASCADE` |
| name | 任务名称 |
| status | 待处理 / 进行中 / 完成 |
| today_progress | 是否今日推进 |
| today_progress_date | 今日推进日期 |
| created_at | 创建时间 |

### reviews

| 字段 | 说明 |
|------|------|
| id | 主键 |
| review_date | 复盘日期 |
| type | 每日 / 每周 / 项目 / 事件 |
| what_done, stuck, next_adjust, depositable | 复盘四段内容 |
| created_at | 创建时间 |

### assets

| 字段 | 说明 |
|------|------|
| id | 主键 |
| title, trigger_context, core_content | 卡片内容 |
| asset_type | 知识卡片 / SOP / 提示词等 |
| capability_tags | JSON 数组 |
| source_review_id | → reviews.id，`ON DELETE SET NULL` |
| created_at | 创建时间 |

### capability_entries

| 字段 | 说明 |
|------|------|
| id | 主键 |
| module | 八能力模块之一 |
| entry_date | 记录日期 |
| content | 进展内容 |
| source_project | 来源项目（文本） |
| level_type | 能力层 / 应用层 |
| created_at | 创建时间 |

## 外键与级联

| 删除对象 | 行为 |
|----------|------|
| goal | 级联删除 projects、tasks |
| project | 级联删除 tasks |
| review | 关联 assets 的 `source_review_id` 置 NULL |

`PRAGMA foreign_keys = ON` 在每次 `get_connection()` 时启用。

## 备份与导入

- JSON 全量导出：`GET /api/export`
- 合并导入：`POST /api/import`（按 id 插入/更新/跳过，失败回滚）
- Obsidian 导出：`GET /api/export/obsidian.zip`（Markdown，非数据库回写）