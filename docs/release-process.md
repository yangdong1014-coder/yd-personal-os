# 版本发布流程

> 本文提供发布操作说明。正式发布门禁、tag 不可变规则与最终一致性要求见 [发布规范](standards/RELEASE.md)。

## 版本真源

- **唯一正式版号**：`personal-system-v2/changelog.json` → `current`
- 页面版本徽章、`/api/changelog`、版本日志页均读取该字段
- README **不写死**具体版本，避免与 changelog 漂移

## 发布前检查

```bash
cd personal-system-v2
pytest
cd ..
git status          # 工作区干净
git pull --ff-only  # 与 origin/main 同步
```

确认 `changelog.json` 已更新目标版本条目，且 `current` 指向新版本。`-shadow` candidate 只用于 Phase 5A 构建识别，不得创建正式 tag 或 GitHub Release，也不得描述为 Phase 5B 已完成。

## v2.2 Phase 5 部署门禁

Phase 4 commit、tag 或 CI 通过不等于允许切换真实数据库。v2.2 必须按以下顺序推进：

```text
Phase 5A 独立 ECS shadow
→ 公网 HTTPS / 正常域名 / 真实浏览器验收
→ 人工批准
→ Phase 5B 停写、备份、迁移与正式切换
```

Phase 5A 使用独立 code/config/descriptor/pointer、批准的独立数据库副本、独立 Gunicorn 端口、shadow systemd unit 与 Nginx 路由；不得停止现有生产、替换正式 active pointer、读取或迁移真实 `personal-system-v2/data/yd_os.db`。未获得明确人工批准时，流程必须停留在 Phase 5A。

## Production 站点级配置持久化

Production 的站点级公开配置使用稳定文件 `/etc/psy/site_config.json`，不得写入不可变 physical release。文件由 root 管理，建议权限为 `root:psy 0640`；现有 `psy-v22.service` 已将 `/etc/psy` 作为运行期只读路径。当前支持的 JSON 结构为：

```json
{
  "icp_filing_number": "<approved-filing-number>"
}
```

仅在 `PERSONAL_OS_ENV=production` 时加载该文件，优先级为 `Production 持久配置 > release 内 site_config.json 默认值`。文件缺失、JSON malformed 或不是对象时保持可选配置行为：回退到 release 默认值，不阻止应用启动；默认备案号为空时不显示。

创建 release artifact、解包并晋升新的 physical release、激活 descriptor/pointer 或回滚时，都不得创建、覆盖或删除 `/etc/psy/site_config.json`。release artifact 内的 `personal-system-v2/site_config.json` 必须继续保持非 Production 默认值；真实备案号只迁移一次到上述稳定文件，后续 release 复用同一外置配置。

## 发布步骤

1. **开发与测试**：功能完成 → pytest 全绿
2. **更新 changelog**：在 `entries` 顶部新增版本条目，更新 `current`
3. **提交**：语义化 commit（如 `feat:` / `chore:` / `fix:`）
4. **打 annotated tag**（正式发布必需）：
   ```bash
    git tag -a vX.Y.Z -m "vX.Y.Z short description"
   ```
5. **推送**：
   ```bash
    git push origin main
    git push origin vX.Y.Z
   ```
6. **验证 CI**：GitHub Actions `Test` workflow 绿灯
7. **创建 GitHub Release**：绑定已经存在的 tag，不重新创建或移动 tag
8. **生产收口**：先按上述门禁完成 Phase 5A；仅在人工批准后按 Runbook 执行 Phase 5B，随后健康检查、smoke test 并核对 commit 一致性

## 标签策略

| 类型 | 示例 | 说明 |
|------|------|------|
| 功能版 | v1.10 | 新能力发布点 |
| 补丁版 | v1.9.1 / v1.10.1 | 收口、修复、工程化；流程与功能版相同 |

标签只打在已验证的 commit 上；不可变与版本一致性规则见 [发布规范](standards/RELEASE.md)。

## 回滚与热修

- v2.2 多用户 schema 切换、SQLite 备份验证、code/DB 原子配对和完整 v2.1.4 回滚必须遵循 [Phase 5 数据库切换与回滚 Runbook](phase-5-database-cutover-runbook.md)。JSON 导出不能替代正式 SQLite backup/restore。
- 数据库升级回滚必须同时恢复匹配的旧 code、旧 DB 和旧配置，不能只回滚代码。
- 代码：`git revert` 或修复后新版本（如 v1.10.1）
- **禁止**对 `main` 使用 `git push --force`（除非团队明确约定）

## 远程仓库

- 当前：`https://github.com/yangdong1014-coder/yd-personal-os.git`
- CI：`.github/workflows/test.yml`
