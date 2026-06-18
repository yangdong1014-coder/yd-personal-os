# 版本发布流程

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

确认 `changelog.json` 已更新目标版本条目，且 `current` 指向新版本。

## 发布步骤

1. **开发与测试**：功能完成 → pytest 全绿
2. **更新 changelog**：在 `entries` 顶部新增版本条目，更新 `current`
3. **提交**：语义化 commit（如 `feat:` / `chore:` / `fix:`）
4. **打标签**（可选但推荐）：
   ```bash
   git tag -a v1.x.x -m "v1.x.x short description"
   ```
5. **推送**：
   ```bash
   git push origin main
   git push origin --tags
   ```
6. **验证 CI**：GitHub Actions `Test` workflow 绿灯

## 标签策略

| 类型 | 示例 | 说明 |
|------|------|------|
| 功能版 | v1.10 | 新能力发布点 |
| 补丁版 | v1.9.1 / v1.10.1 | 收口、修复、工程化；流程与功能版相同 |

标签打在**已验证**的 commit 上，不打在未测通的状态。

## 回滚与热修

- 数据：用 JSON 备份 `GET /api/export` 恢复
- 代码：`git revert` 或修复后新版本（如 v1.10.1）
- **禁止**对 `main` 使用 `git push --force`（除非团队明确约定）

## 远程仓库

- 当前：`https://github.com/yangdong1014-coder/yd-personal-os.git`
- CI：`.github/workflows/test.yml`