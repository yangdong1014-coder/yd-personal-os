# 战略定位模块 · Bug修复规格 v1.19.1

> 基于真实使用后发现的问题。目标：修复三个使用痛点，不新增功能。
> 版本：v1.19.0 → v1.19.1（bug修复小版本）
> 受 CLAUDE.md 全部约束。手测用临时库，不碰生产库，不 push，完成后截图汇报。

---

## 0 · 最重要的设计变更（先理解再动手）

**目标变更模块整体降级为「意图记录」**

原 commit-3 规格中「confirm 后真实写 goals 表」的设计，现在取消。
理由：真实使用后发现「记录意图 + 手动去目标模块改」比「自动执行」更可控、更符合使用习惯。

新定义：
```
positioning_goal_action 表 = 纯记录表
- 只记录「我打算对哪个目标做什么变更、理由是什么」
- 支持增 / 改 / 删这些记录本身
- 绝不联动 goals 表（不 INSERT / UPDATE / DELETE goals 表的任何数据）
- status 字段（pending/confirmed/rejected）改为纯标签，仅供人工备注用，不触发任何副作用
- 「确认」「拒绝」按钮如果已存在，改为只更新 status 标签，不写 goals 表
- 底部那行「确认后真实改写目标系统」的说明文字，删掉或改为「记录意图，手动前往目标模块执行」
```

---

## 1 · Bug ① 校准轨迹支持修改与删除

**问题**：校准记录只能新建，没有编辑/删除入口，填错了无法修改。

**修复要求**：

每条校准记录展示时，加两个操作入口（右侧或悬停显示）：
- **编辑**：点击后展开与新建校准相同的表单（字段预填当前值），提交后 `PUT /api/positioning/calibrations/<id>` 更新记录。
- **删除**：点击后二次确认弹窗（「确认删除这条校准记录？」），确认后 `DELETE /api/positioning/calibrations/<id>` 删除，同时级联删除该校准关联的所有 `positioning_goal_action` 记录（外键 CASCADE 已设置，数据库层自动处理）。

**新增 API**：
```
PUT    /api/positioning/calibrations/<id>    更新校准记录
DELETE /api/positioning/calibrations/<id>    删除校准记录（级联删 actions）
```

---

## 2 · Bug ② 目标变更关联真实目标，改为下拉选择

**问题**：「目标 ID」是手填数字输入框，用户不知道填哪个 ID，体验极差。

**修复要求**：

- 页面初始化时，从 `GET /api/goals`（或既有的目标列表接口）拉取当前所有目标，缓存到 JS 变量。
- 「目标 ID」输入框改为 `<select>` 下拉框，选项格式：`目标名称（#ID · 类型）`，例如「完成独立咨询转型（#3 · 当前主线）」。
- 选中后自动填入目标 ID（隐藏字段），「目标类型」联动自动填入（可覆盖）。
- 当变更类型为「新建目标」时，目标下拉框隐藏（新建不需要关联既有目标），显示「新目标名称」文本输入框。
- 目标列表只拉 `status='active'` 的（已淘汰的不显示）。

**不新增 API**：复用既有目标列表接口即可。

---

## 3 · Bug ③ 目标变更记录支持修改与删除（纯记录，不联动目标表）

**问题**：变更建议添加后无法编辑或删除；且现有设计暗示会「确认后改写目标系统」，与实际使用需求不符。

**修复要求**：

每条 `positioning_goal_action` 记录，加编辑和删除操作：
- **编辑**：点击后展开编辑表单（变更类型、关联目标下拉、目标类型、变更理由），提交后 `PUT /api/positioning/actions/<id>` 更新。
- **删除**：二次确认后 `DELETE /api/positioning/actions/<id>` 删除这条记录（只删这条记录，绝不影响 goals 表）。
- **status 标签**：「待确认/已确认/已拒绝」改为纯手动标签，点击可切换，`PATCH /api/positioning/actions/<id>/status`，只更新 status 字段，不触发任何 goals 表操作。
- **删除底部说明文字**「确认后真实改写目标系统（既有六模块）→ 运转结果反哺下次校准」，改为「记录意图，请手动前往目标模块执行对应变更」。

**新增 API**：
```
PUT   /api/positioning/actions/<id>           更新变更记录
DELETE /api/positioning/actions/<id>          删除变更记录（只删记录，不动 goals）
PATCH  /api/positioning/actions/<id>/status   切换 status 标签
```

---

## 4 · 执行约束

```
✗ goals 表在本次修复中绝对不可写（不 INSERT / UPDATE / DELETE）
✗ 只改 positioning 相关文件（app.py 路由、positioning_service.py、database.py、positioning.html、positioning.js）
✗ 不动既有六模块
✗ 手测用 YD_OS_DB_PATH 临时库，不碰 data/yd_os.db
✗ 改完本地截图汇报，不 push，等杨栋验收
```

---

## 5 · 验收标准

```
[ ] 校准记录可编辑（表单预填）、可删除（二次确认）
[ ] 目标变更手填区：目标选择改为下拉框，显示目标名+ID+类型
[ ] 新建目标类型时下拉隐藏，显示新目标名称输入框
[ ] 变更记录可编辑、可删除（只删记录，goals 表不受影响）
[ ] status 可手动切换标签，不触发任何 goals 表操作
[ ] 底部说明文字已改为「记录意图，请手动前往目标模块执行」
[ ] pytest 全绿
[ ] 既有六模块未受影响
```

---

## 6 · 版本收尾（完成后）

```
changelog.json → v1.19.1（bug修复）
git commit，不 push，等杨栋验收后手动 push 和云端部署
```

---

*positioning bugfix v1.19.1 · 受 CLAUDE.md 约束 · goals 表本次绝对不可写*
