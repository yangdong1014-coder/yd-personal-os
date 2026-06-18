# Obsidian 联动策略

## v1.10 范围：一向导出

从 yd-personal-os **导出** Markdown zip，由用户**手动解压**到 Obsidian vault。系统不直接写入用户本地目录。

```
yd-personal-os (SQLite)
        ↓ GET /api/export/obsidian.zip
   Markdown + YAML frontmatter
        ↓ 用户手动解压
   Obsidian vault（用户管理）
```

## v1.10.1 增强：索引、命名、链接稳定性

在 v1.10 一向导出基础上，v1.10.1 聚焦导出包可读性与长期沉淀：

| 增强项 | 说明 |
|--------|------|
| README.md | zip 内说明来源、时间、范围、用法与限制 |
| 00-Index.md | MOC 总入口，链接各模块 Index |
| 各模块 Index | 列出目录下所有条目的 `[[内部链接]]` |
| 命名一致性 | 文件名与正文链接共用同一套映射；重复名自动 `-2`/`-3` |
| 兜底命名 | 空标题 → `Untitled <Type> <id>`；非法字符清理 |
| frontmatter | 增加 `export_version` 与可选关联字段 |

**仍不做**：双向同步、自动写入 vault、覆盖用户文件、自动删除旧文件。

## 明确不做（v1.10 / v1.10.1）

| 能力 | 状态 |
|------|------|
| 双向同步 | ❌ 不做 |
| 自动写入 vault | ❌ 不做（无 vault 路径配置） |
| 覆盖用户手写笔记 | ❌ 不做 |
| 自动删除 Obsidian 文件 | ❌ 不做 |
| 冲突合并 | ❌ 不做 |

## 导出结构

```
Obsidian/
  README.md
  00-Index.md
  Goals/
    Goals Index.md
    <name>.md
  Projects/
    Projects Index.md
    <name>.md
  Tasks/
    Tasks Index.md
    <name>.md
  Reviews/
    Reviews Index.md
    <date-type>.md
  Assets/
    Assets Index.md
    <title>.md
  Capabilities/
    Capabilities Index.md
    <module-date>.md
```

- 每实体文件含 YAML frontmatter：`id`, `type`, `created_at`, `source: yd-personal-os`, `export_version`
- 存在时补充：`status`, `related_goal_id`, `related_project_id`, `source_review_id`, `capability`
- 正文保留字段，并用 `[[Folder/name]]` 表达关联（链接指向最终文件名，含后缀）

## 使用方式

1. 侧边栏点击「导出 Obsidian」
2. 下载 zip
3. 解压到 vault 子目录（建议单独文件夹如 `YD-OS-Export/`）
4. 从 `00-Index.md` 或各模块 Index 开始浏览

## 与 JSON 备份的区别

| 方式 | 用途 |
|------|------|
| JSON (`/api/export`) | 完整备份、导入恢复 |
| Obsidian zip | 阅读、沉淀、知识库编排 |

JSON 可回写系统；Obsidian 导出**不可**自动回写（后续版本再评估）。

## 后续规划（v1.11+）

- 增量导出（仅变更）
- 回链与双向索引（仍只读或半自动）
- 可选 vault 路径配置（需安全审查）
- 与宪法「资产沉淀」流程对齐

**增量同步前置条件**：必须先定义冲突策略（同名覆盖 vs 旁路）与覆盖策略（是否删除 Obsidian 中已移除的条目），v1.10.1 未解决这些问题。