# 数据库规范

PSY 已承载真实生产数据。数据库安全 MUST 高于开发速度。

## 基本规则

- 真实数据库的仓库路径精确为 `personal-system-v2/data/yd_os.db`。开发、测试和 Phase 5A 影子部署 MUST 使用临时库或经批准的独立副本；禁止读取、写入、复制、初始化或迁移该真实路径。
- Schema 修改 SHOULD additive，并与现有 `init_db()` 幂等模式一致。
- 禁止随意删除字段或表、清空或重建生产库、直接操作唯一生产库。
- 禁止在生产环境试验 migration。
- 数据库、备份与导出数据禁止提交到 Git。

## Phase 5 影子与切换门禁

- Phase 5A shadow MUST 使用独立数据库绝对路径，并记录来源副本、hash、manifest、schema、app version 与 commit 身份；不得使用正式 active pointer 或正式数据库路径。
- 任何 shadow migration 只能针对批准的副本生成新的 staged 文件，源副本只读、目标必须不存在；禁止在真实库上运行 migration。
- Phase 5A 完成 ECS 公网 HTTPS 与真实浏览器验收后仍 MUST 停止，等待人工批准。
- 只有获得人工批准的 Phase 5B 才可进入停写、正式备份、migration、code/DB descriptor 激活与回滚窗口。

## Migration 流程

涉及 schema 时 MUST 按顺序执行：

```text
临时库/fixture migration → 数据兼容检查 → regression → 完整测试
→ Phase 5A：批准副本上的 staged migration + ECS HTTPS/浏览器验收
→ 人工批准
→ Phase 5B：停写 + 正式备份/恢复复验 + 新 staged migration
→ descriptor 激活 → integrity verification → rollback window
```

## 生产操作前

MUST 记录并确认：

- 实际数据库绝对路径正确；
- 新备份已存在且文件大小大于 0；
- 备份文件名含时间；
- 旧备份未被覆盖；
- 当前代码与目标 migration 对应。

条件允许时 SHOULD 记录备份 SHA-256、数据库 hash 与关键表发布前 row count。`scripts/backup-db.py` 必须显式接收源库和备份目录的绝对路径，使用 SQLite backup API 创建不可覆盖 artifact，并在完成后验证 manifest、恢复、integrity 与外键；历史备份保留/清理由发布负责人在 rollback window 结束后独立决定，工具不自动裁剪。

## 操作后验收

至少执行：

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

验收标准：

- `integrity_check` 仅返回 `ok`；
- `foreign_key_check` 返回 0 行；
- schema 与预期一致；
- 必要时比较 schema hash、database hash、关键表 row count 和 migration 前后数据变化。

任何校验失败都 MUST 停止后续发布，保留现场并优先从已验证备份恢复。现有表关系见 [数据模型](../data-model.md)；当前备份、影子验证、正式切换与回滚操作只以 [Phase 5 数据库切换与回滚 Runbook](../phase-5-database-cutover-runbook.md) 为执行入口。[家庭服务器模式](../home-server.md) 仅保留历史参考。

## 无 schema 修改

仅涉及 UI、UX、CSS、Documentation 或非数据逻辑时，禁止为了“流程完整”机械执行 migration 或数据库校验。先确认 diff 确实没有 schema 与数据路径变化。
