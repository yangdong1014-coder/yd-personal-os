# 项目文档导航

个人能力操作系统（yd-personal-os）文档体系。开发、发布与知识库联动均以本文档目录为入口。

## 文档索引

| 文档 | 用途 |
|------|------|
| [系统搭建说明书_1.1.md](系统搭建说明书_1.1.md) | **系统宪法**：最高约束文件，定义原则、架构与模块规范 |
| [architecture.md](architecture.md) | 技术架构：Flask、SQLite、前端、提示词、版本与 CI |
| [data-model.md](data-model.md) | 核心数据表、外键与级联关系 |
| [release-process.md](release-process.md) | 版本发布流程：changelog、标签、推送、Actions |
| [development-guide.md](development-guide.md) | 本地开发、测试与环境配置 |
| [obsidian-sync-plan.md](obsidian-sync-plan.md) | Obsidian 联动策略（v1.10 一向导出） |

## 阅读顺序建议

1. 新接手项目：宪法 → architecture → development-guide
2. 改数据或 API：data-model → development-guide
3. 发版：release-process
4. 对接 Obsidian：obsidian-sync-plan

## 与代码的关系

- 应用代码位于 `personal-system-v2/`
- 版本真源：`personal-system-v2/changelog.json` 的 `current` 字段
- 运行时数据：`personal-system-v2/data/`（git 忽略）