# PSY 项目开发规范

本目录把 PSY v2.1.2 至 v2.1.4 已验证的工程经验转成项目门禁，适用于 Codex、其他 AI coding agent 与人工开发，也适用于 Feature、UX、Hotfix、Release 和 Documentation。

> 先继承，再创造；
>
> 先本地验证，再生产发布；
>
> 可量化的问题不用感觉验收；
>
> 正式版本必须可追溯、可回滚。

## 使用方式

执行顺序：**任务分类 → 阅读对应规范 → 开发或修改 → DoD 验收 → 最终报告列出 Standards Applied。**

| 变更范围 | 必读规范 |
|---|---|
| 任意开发或修复 | [DEVELOPMENT.md](DEVELOPMENT.md) |
| 页面、样式、响应式 | [UI.md](UI.md) |
| 数据、schema、migration | [DATABASE.md](DATABASE.md) |
| AI、Prompt、结构化输出 | [AI.md](AI.md) |
| 版本、tag、生产部署 | [RELEASE.md](RELEASE.md) |
| Documentation 或宣布完成 | [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) |

常用组合：UI Hotfix = DEVELOPMENT + UI + DoD；数据库修改 = DEVELOPMENT + DATABASE + DoD；AI Feature 再按是否涉及页面、落库和正式发布追加 UI、DATABASE、RELEASE。

## Rule Precedence

文档冲突时按以下顺序执行：

1. [系统搭建说明书](../系统搭建说明书_1.1.md)中的核心产品原则与不可破坏的系统边界。
2. 仓库根目录 `CLAUDE.md` 中的 Agent 执行权限与安全约束；其内容不得覆盖系统宪法。
3. 本目录中与当前任务适用的专项工程规范。
4. [架构](../architecture.md)、[开发指南](../development-guide.md)、[版本发布流程](../release-process.md)、部署文档和历史模块规格等实现或操作参考。

`AGENTS.md` 只负责入口与任务路由，不另建一套规则。文件名、命令、路径和运行机制 MUST 以当前仓库验证为准；历史路线图或示例不得覆盖当前实现。仍无法消解冲突时，停止并报告。
