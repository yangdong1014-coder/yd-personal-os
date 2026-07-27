# Definition of Done

`tests passed` 只是一个门禁，不等于工作完成。先按变更类型选择适用项；没有涉及的项应标记为不适用并说明理由。

## Feature / UX

- Scope 清晰，无无关修改或临时文件，diff 可解释。
- 新行为有测试，缺陷有 regression；运行时修改的适用测试与完整 pytest 全部通过。
- 真实浏览器完成核心流程，不能只验证 HTTP 200。
- UI 修改满足 [UI.md](UI.md) 的设计、布局、截图与响应式验收。
- 数据或 schema 修改满足 [DATABASE.md](DATABASE.md) 的兼容、备份与完整性验收。
- 合并或发布边界 working tree clean。

## 正式发布

正式应用 Release 只有在满足 [RELEASE.md](RELEASE.md) 的版本、生产验证和最终一致性门禁后才算完成。本地实现完成与正式发布完成不得混称。

## Hotfix

Hotfix 必须有 regression；正式发布时遵循 [RELEASE.md](RELEASE.md)。可以根据风险缩减与缺陷无关的测试，但必须说明理由。

## Documentation-only

纯文档修改 MUST：

- 运行 `git diff --check`；
- 检查 Markdown 内部链接；
- 确认文档与当前代码、脚本和发布机制一致；
- 确认 diff 只含预期文档；
- 明确未改运行时代码、UI、数据库、Prompt、依赖、版本与生产配置。

纯文档修改不机械要求完整 pytest、浏览器验收、数据库检查或 [RELEASE.md](RELEASE.md) 的应用发布链路，除非文档本身参与运行。Documentation/governance commit 可以进入 `main` 而不改变正式应用版本或生产代码。

## 完成报告

每次最终交付报告 MUST 包含：

```markdown
## Standards Applied

- docs/standards/DEVELOPMENT.md
- docs/standards/DEFINITION_OF_DONE.md
```

只列本次真正适用的文件。适用规范未执行时必须说明原因，禁止静默跳过。
