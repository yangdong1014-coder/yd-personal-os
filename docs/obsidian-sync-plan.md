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

## 明确不做（v1.10）

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
  Goals/<name>.md
  Projects/<name>.md
  Tasks/<name>.md
  Reviews/<date-type>.md
  Assets/<title>.md
  Capabilities/<module-date>.md
```

- 每文件含 YAML frontmatter：`id`, `type`, `created_at`, `source: yd-personal-os`
- 正文保留字段，并用 `[[Folder/name]]` 表达关联

## 使用方式

1. 侧边栏点击「导出 Obsidian」
2. 下载 zip
3. 解压到 vault 子目录（建议单独文件夹如 `YD-OS-Export/`）
4. 在 Obsidian 中打开；内部链接需与解压路径一致

## 与 JSON 备份的区别

| 方式 | 用途 |
|------|------|
| JSON (`/api/export`) | 完整备份、导入恢复 |
| Obsidian zip | 阅读、沉淀、知识库编排 |

JSON 可回写系统；Obsidian 导出**不可**自动回写（后续版本再评估）。

## 后续规划（v1.11+）

- 导出索引页（MOC）
- 增量导出（仅变更）
- 回链与双向索引（仍只读或半自动）
- 可选 vault 路径配置（需安全审查）
- 与宪法「资产沉淀」流程对齐