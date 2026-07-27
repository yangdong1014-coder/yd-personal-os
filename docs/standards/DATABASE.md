# 数据库规范

PSY 已承载真实生产数据。数据库安全 MUST 高于开发速度。

## 基本规则

- 开发和测试 MUST 使用临时 SQLite；禁止读取、写入或初始化真实 `data/yd_os.db`。
- Schema 修改 SHOULD additive，并与现有 `init_db()` 幂等模式一致。
- 禁止随意删除字段或表、清空或重建生产库、直接操作唯一生产库。
- 禁止在生产环境试验 migration。
- 数据库、备份与导出数据禁止提交到 Git。

## Migration 流程

涉及 schema 时 MUST 按顺序执行：

```text
确认数据库位置 → 本地备份 → 本地 migration → 数据兼容检查
→ regression → 完整测试 → 生产备份
→ production migration → integrity verification
```

## 生产操作前

MUST 记录并确认：

- 实际数据库绝对路径正确；
- 新备份已存在且文件大小大于 0；
- 备份文件名含时间；
- 旧备份未被覆盖；
- 当前代码与目标 migration 对应。

条件允许时 SHOULD 记录备份 SHA-256、数据库 hash 与关键表发布前 row count。使用现有 `scripts/backup-db.py` 时还要确认其保留数量符合本次恢复要求。

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

任何校验失败都 MUST 停止后续发布，保留现场并优先从已验证备份恢复。现有表关系见 [数据模型](../data-model.md)，备份操作见 [家庭服务器模式](../home-server.md#数据库备份与恢复)。

## 无 schema 修改

仅涉及 UI、UX、CSS、Documentation 或非数据逻辑时，禁止为了“流程完整”机械执行 migration 或数据库校验。先确认 diff 确实没有 schema 与数据路径变化。
