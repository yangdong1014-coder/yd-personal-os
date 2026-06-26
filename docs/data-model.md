# 数据模型

SQLite 表结构及关系说明（`database.py` / `init_db`）。

## 实体关系

```
positioning_anchor — 定位锚（低频，单行有效）

positioning_calibration (1) ──< positioning_goal_action (N)

goals (1) ──< projects (N) ──< tasks (N)
         ↑ positioning_goal_action.target_goal_id（软引用，无强制 FK）

reviews (1) ──< assets (N, optional source_review_id)

capability_entries — 独立表，无外键

inbox_entries (1) ──< inbox_suggestions (N)
```

战略定位层位于目标系统之上：校准产生目标变更建议（`positioning_goal_action`），人工确认后才写入 `goals`（与 inbox 建议→确认范式一致）。

## 表说明

### goals

| 字段 | 说明 |
|------|------|
| id | 主键 |
| name | 目标名称 |
| type | 年度 / 季度 / 月度 / 当前主线 |
| status | v1.19+：`active`（默认）/ `已淘汰`；淘汰为归档，不硬删 |
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

### assets（可复用资产库，v1.12+）

v1.12 起，资产从「知识卡片列表」升级为**可复用资产库**：按类型承载不同动态字段，支持成熟度、复用场景与复用次数统计。

| 字段 | 说明 |
|------|------|
| id | 主键 |
| title | 资产标题 |
| asset_type | 资产类型，见下方枚举 |
| capability_tags | 关联能力模块标签（JSON 数组）；API 字段名 `capability_tags`，概念上亦称 ability_tags |
| summary | 简要说明，列表卡片展示用；可由 fields 自动提取 |
| fields | **JSON 对象**，承载不同资产类型的动态字段（如 SOP 的执行步骤、本质洞察的底层本质等） |
| reusable_scenario | 复用场景描述 |
| maturity | 成熟度：`草稿` / `可用` / `稳定` / `标准化` |
| reuse_count | 复用次数，通过 `POST /api/assets/<id>/reuse` 递增 |
| source_type | 来源类型（如 `review`、空字符串表示手动创建） |
| source_review_id | → reviews.id，`ON DELETE SET NULL`；API 响应中同步暴露为 `source_id` |
| created_at | 创建时间 |
| updated_at | 更新时间 |

**兼容字段（v1.12 保留，由 fields 同步生成）**：

| 字段 | 说明 |
|------|------|
| trigger_context | 旧版触发情境；迁移后由 fields 回填，导入导出仍兼容 |
| core_content | 旧版核心内容；迁移后由 fields 回填，导入导出仍兼容 |

#### 资产类型（asset_type）

`SOP` · `本质洞察` · `方法论` · `模型` · `模板` · `提示词` · `案例复盘` · `清单` · `原则规则` · `工具组件` · `通用资产`

类型与动态字段定义见 `personal-system-v2/asset_schemas.py`（`TYPE_FIELD_DEFS` / `GENERIC_FIELD_DEFS`）。

#### 成熟度（maturity）

`草稿` · `可用` · `稳定` · `标准化`

#### 旧数据迁移（`_migrate_assets_table`）

`init_db()` 启动时自动执行，**幂等**（重复执行不重复污染 fields、不重置 reuse_count / created_at）：

| 旧 asset_type | 迁移规则 |
|---------------|----------|
| SOP / 提示词 / 案例复盘 / 方法论 | 直接映射为新类型 |
| 工作流 | 映射为 `SOP` |
| 知识卡片 | 按标题与内容关键词推断为 `本质洞察` 或 `方法论` |
| 其他 / 无法判断 | 归为 `通用资产` |

- 旧 `trigger_context` / `core_content` 自动写入对应 `fields`
- 自动补全 `summary`、`reusable_scenario`、`maturity`、`updated_at`、`source_type`
- 逻辑实现：`database._migrate_assets_table()` + `asset_schemas.build_fields_from_legacy()`

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

### positioning_anchor（v1.19+）

定位锚：战略不动点，低频修订。实现上保留最新一行（`upsert` 覆盖更新）。

| 字段 | 说明 |
|------|------|
| id | 主键 |
| first_principle | 第一性原理 |
| identity_core | 身份内核 |
| flywheel_def | 飞轮定义 |
| current_stage | 当前战略阶段 |
| north_star | 北极星指标 |
| updated_at | 更新时间 |

### positioning_calibration（v1.19+）

周期性或触发式校准记录。

| 字段 | 说明 |
|------|------|
| id | 主键 |
| calibrated_at | 校准日期 |
| cycle | 月度 / 季度 / 触发式 |
| primary_contradiction | 当前主要矛盾 |
| doing_but_shouldnt | 在做但不该做的 |
| should_but_not_doing | 该做但没做的 |
| alignment_review | 目标对齐审查 |
| conclusion | 本期校准结论 |
| created_at | 创建时间 |

### positioning_goal_action（v1.19+）

校准触发的目标变更建议，pending 中间态。

| 字段 | 说明 |
|------|------|
| id | 主键 |
| calibration_id | → positioning_calibration.id，`ON DELETE CASCADE` |
| action_type | 新建目标 / 淘汰目标 / 降级目标 / 升级为主线 |
| target_goal_id | 涉及的既有目标 id（新建类为空；软引用，不强制 FK） |
| payload | JSON：新建字段或降级目标类型等 |
| reason | 变更理由（关联定位锚） |
| status | pending / confirmed / rejected |
| created_at | 创建时间 |

#### 目标变更 confirm 规则（设计）

| action_type | 写入 goals 的行为 |
|-------------|-------------------|
| 新建目标 | INSERT，type 取自 payload |
| 淘汰目标 | UPDATE status = `已淘汰` |
| 降级目标 | UPDATE type，级别由 payload.type 指定 |
| 升级为主线 | UPDATE type = `当前主线`，并降级其它主线 |

confirm/reject API 在 v1.19.0 页面阶段为只读展示；真实写 goals 在后续小版本接入。

## 外键与级联

| 删除对象 | 行为 |
|----------|------|
| goal | 级联删除 projects、tasks |
| project | 级联删除 tasks |
| review | 关联 assets 的 `source_review_id` 置 NULL |
| inbox_entry | 级联删除 inbox_suggestions |
| positioning_calibration | 级联删除 positioning_goal_action |

`PRAGMA foreign_keys = ON` 在每次 `get_connection()` 时启用。

## 备份与导入

- JSON 全量导出：`GET /api/export`（assets 含 summary、fields、maturity、reuse_count 等 v1.12 字段）
- 合并导入：`POST /api/import`（按 id 插入/更新/跳过，失败回滚）
- Obsidian 导出：`GET /api/export/obsidian.zip`（Markdown，非数据库回写；资产含类型、成熟度、复用次数、fields 结构化章节，见 [obsidian-sync-plan.md](obsidian-sync-plan.md)）