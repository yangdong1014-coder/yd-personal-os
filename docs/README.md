# 项目文档导航

个人能力操作系统（yd-personal-os）文档体系。开发、发布与知识库联动均以本文档目录为入口。

## 文档索引

| 文档 | 用途 |
|------|------|
| [系统搭建说明书_1.1.md](系统搭建说明书_1.1.md) | **系统宪法**：最高约束文件，定义原则、架构与模块规范 |
| [standards/README.md](standards/README.md) | **项目开发规范**：开发、UI、数据库、AI、发布与完成定义 |
| [architecture.md](architecture.md) | 技术架构与当前 ECS 公网 HTTPS 生产拓扑 |
| [development-guide.md](development-guide.md) | 本地开发、测试与环境配置 |
| [data-model.md](data-model.md) | 核心数据表、外键与级联关系 |
| [release-process.md](release-process.md) | 版本发布流程：changelog、标签、推送、Actions |
| [phase-5-database-cutover-runbook.md](phase-5-database-cutover-runbook.md) | Phase 5A ECS 影子部署验收，以及获人工批准后的 Phase 5B 数据库切换/回滚 SOP（待执行） |
| [phase-5a-shadow-deployment-runbook.md](phase-5a-shadow-deployment-runbook.md) | Phase 5A 独立 shadow 的 21 步参数化部署、权限、HTTPS、浏览器与非影响验收 SOP（待批准执行） |
| [home-server.md](home-server.md) | **历史资料**：Windows Home Server、Tailscale 与本地受限验收记录；不是当前部署路线 |
| [aliyun-ecs-deployment.md](../personal-system-v2/docs/aliyun-ecs-deployment.md) | **历史资料**：旧版阿里云 ECS/Tailscale 部署说明；不是 v2.2 执行 runbook |
| [obsidian-sync-plan.md](obsidian-sync-plan.md) | Obsidian 联动策略（v1.10 一向导出） |

## 阅读顺序建议

1. 新接手项目：宪法 → standards → architecture → development-guide
2. 改数据或 API：standards → data-model → development-guide
3. v2.2 部署：architecture / development-guide → Phase 5A 独立影子部署 → 公网 HTTPS 与真实浏览器验收 → 人工批准 → Phase 5B 正式切换；不得从开发说明直接跳到真实数据库切换
4. 对接 Obsidian：obsidian-sync-plan

## 与代码的关系

- 应用代码位于 `personal-system-v2/`
- 版本真源：`personal-system-v2/changelog.json` 的 `current` 字段
- 运行时数据：`personal-system-v2/data/`（git 忽略）
