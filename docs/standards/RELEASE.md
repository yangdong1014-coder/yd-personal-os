# 发布规范

本文件定义正式发布门禁；具体 Git 命令见 [版本发布流程](../release-process.md)，服务器操作见现有部署文档。执行 agent 未获明确授权时不得 push 或操作生产。

## 适用边界

本文件的完整版本、tag、GitHub Release、生产部署与 commit 一致性链路，仅适用于正式应用 Release。

Documentation-only / governance commit 满足 [Documentation DoD](DEFINITION_OF_DONE.md#documentation-only) 后可以进入 `main`，不触发应用版本 bump、tag、GitHub Release 或生产部署。此时 `main` 可以仅比生产多文档提交；下述生产一致性等式不适用。

## 正式发布链路

MUST 按以下顺序收口：

```text
本地开发 → 自动测试 → 浏览器验证 → changelog/版本记录
→ main → push → annotated tag → GitHub Release → production
→ restart → smoke test → 日志检查 → 数据检查 → 最终一致性确认
```

Changelog、页面版本与必要的 PWA cache 版本 MUST 进入被 tag 的 release commit，不能在 tag 之后补写。当前 PWA cache 标识位于 `personal-system-v2/static/service-worker.js` 的 `CACHE_NAME`，正式版本需要变更时必须同步对应测试。合并、push、tag 或部署前工作区 MUST clean，目标 commit 必须明确。

## Tag 与版本不可变

正式 tag 一旦发布，禁止 move、overwrite 或重新指向其他 commit，也禁止用同一版本号部署新代码。

v2.1.3 已发布后，Deliberation Layout Hotfix 必须成为 v2.1.4；不能修改代码后仍称 v2.1.3。Hotfix 也是正式代码变化，不能跳过 version、changelog、annotated tag、GitHub Release 和生产验证。

原则：**正式 Release 发布后，任何后续正式代码变化都产生新版本。**

## Changelog

版本真源是 `personal-system-v2/changelog.json` 的 `current`。正式版本 MUST 在 `entries` 中记录真实的 `version`、`date`、`title`、`type` 与 `items`；GitHub Release Notes 使用本次适用的 Added、Improved 或 Fixed 分类。禁止伪造历史或记录未发生的变化。

## 一致性门禁

发布结束 MUST 证明：

```text
local main
= origin/main
= GitHub main
= release tag target
= production HEAD
```

必须记录最终 commit SHA、tag 与 GitHub Release URL。任一项不一致，发布未完成。

## Production

### v2.2 release 权限契约

- `/var/lib/psy/releases` 推荐 `root:root` + `0755`：`psy` 可 traverse/read，但不得 create、rename、delete 或 write。
- active pointer 与 release descriptor 必须为 `root:root` + `0644`：`psy` 可读但不可写，且不得包含 group/world write 位。
- descriptor-bound runtime config 含 `SECRET_KEY`、proxy token 与可选 API key，必须为 `root:psy` + `0640`，不得使用 `0644`；`/etc/psy/releases` 必须允许 `psy` traverse/read 但不得允许其写入，可使用 `root:root` + `0755`、`root:psy` + `0750` 或等价 ACL。

部署前 MUST：

- 检查生产 branch、HEAD 与 `git status`；
- 确认工作区 clean；
- 记录旧正式 commit；
- 数据变更已满足 [DATABASE.md](DATABASE.md) 的备份与验证要求；
- 确认本次是否真的有 schema 或依赖变化。

禁止：

- 用 `git reset --hard` 作为默认部署方式；
- 未确认代码与配置就 restart；
- 测试失败仍继续发布；
- 在生产持续 debug。

部署后 MUST 检查 service、HTTP health、鉴权、关键页面 smoke、Tailscale（如适用）和新增日志错误。异常时优先恢复已验证的稳定 tag/commit，再分析原因。
