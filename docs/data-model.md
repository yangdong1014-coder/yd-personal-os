# 数据模型

SQLite 表结构及关系说明（`database.py` / `init_db`）。

## 实体关系

```
goals (1) ──< projects (N) ──< tasks (N)

reviews (1) ──< assets (N, optional source_review_id)

capability_entries — 独立表，无外键

inbox_entries (1) ──< inbox_suggestions (N)
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

### inbox_entries

| 字段 | 说明 |
|------|------|
| id | 主键 |
| raw_text | 用户原始输入 |
| source_type | 来源类型（如 manual） |
| status | draft / analyzed / committed / archived / failed |
| created_at | 创建时间 |

### inbox_suggestions

| 字段 | 说明 |
|------|------|
| id | 主键 |
| inbox_entry_id | → inbox_entries.id，`ON DELETE CASCADE` |
| target_type | goal / project / task / review / asset / capability_entry / uncertain / ignored |
| title | 建议标题 |
| content | 建议正文 |
| confidence | 置信度 0-1 |
| reason | 归档理由 |
| suggested_payload | JSON 字符串，建议写入字段 |
| status | pending / accepted / rejected / committed |
| created_at | 创建时间 |

#### 智能归档入库边界

| target_type | 入库条件 |
|-------------|----------|
| goal / asset / review / capability_entry | 字段满足即可独立写入 |
| project | `suggested_payload.goal_id` 必须为已存在目标的数字 ID |
| task | `suggested_payload.project_id` 必须为已存在项目的数字 ID |

- 校验失败时该 suggestion 保持 `pending`，`commit` 响应 `errors` 列出原因
- 系统不会为通过校验而自动创建占位 goal/project

#### suggested_payload 关联字段（v1.11.1）

| 字段 | 说明 |
|------|------|
| local_ref | 同批临时引用（如 `project_ai_retouche`），project 创建后映射为真实 id |
| parent_ref | task 指向同批 project 的 local_ref，commit 时解析为 project_id |
| goal_id / project_id | 数字 ID；可由用户在卡片选择或 `override_payload` 补充 |

`override_payload` 仅允许覆盖 `goal_id`、`project_id`，后端仍做最终校验。

## 外键与级联

| 删除对象 | 行为 |
|----------|------|
| goal | 级联删除 projects、tasks |
| project | 级联删除 tasks |
| review | 关联 assets 的 `source_review_id` 置 NULL |
| inbox_entry | 级联删除 inbox_suggestions |

`PRAGMA foreign_keys = ON` 在每次 `get_connection()` 时启用。

## 备份与导入

- JSON 全量导出：`GET /api/export`
- 合并导入：`POST /api/import`（按 id 插入/更新/跳过，失败回滚）
- Obsidian 导出：`GET /api/export/obsidian.zip`（Markdown，非数据库回写）