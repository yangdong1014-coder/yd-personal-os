# 开发规范

## 开发前门禁

任何修改前 MUST：

1. 检查当前 branch、HEAD 与 `git status`。
2. 确认正式 baseline，以及本地与远端基线是否一致。
3. 阅读本次涉及的现有模块和相邻实现。
4. 找到已有 service、database、API、UI、CSS、测试与 error handling 模式。
5. 判断本次任务涉及哪些 standards。
6. 写清范围、禁止范围、验收标准和是否涉及数据、AI、发布。

原则：**先理解现有系统，再写新代码。**

## 工作方式

Feature、UX、Hotfix 或其他明显修改 SHOULD 使用独立 branch，按以下顺序推进：

```text
现状检查 → 新建分支 → 本地开发 → 本地验证 → Git 提交
```

正式应用发布另按 [RELEASE.md](RELEASE.md) 执行。

禁止：

- 在生产服务器开发或持续 debug。
- 在 `main` 上做实验或未经验证的大改。
- 未确认现有架构就创造第二套模式。
- 顺手重构无关模块或扩大任务范围。
- 擅自升级依赖。
- 提交 `.env`、临时文件、数据库、日志、备份、密钥或 token。

执行 agent 的 push 与生产权限仍以仓库根目录 `CLAUDE.md` 和用户当次明确授权为准。

## 架构原则

PSY 新模块必须做到：**代码上独立，数据上可连接，产品上属于 PSY。**

MUST 优先复用：

- 现有 service 与业务错误处理；
- `database.py` 的连接、CRUD 和幂等 migration 模式；
- 现有 API 响应与校验模式；
- 页面结构、CSS variables 和组件；
- pytest 临时数据库与 mock 方式。

不要为了一个模块建立第二套数据库层、AI 调用层、设计系统或测试框架。

## 修改范围

- Scope MUST 清晰，采用满足目标的最小修改。
- 禁止触碰无关代码或顺手“优化整个项目”。
- 发现额外问题时记录在报告中，不得自动扩大 scope。
- 用户交互不得直接照搬数据库字段；具体规则见 [UI 规范](UI.md#数据模型与交互模型)。

具体启动、环境与测试命令见 [开发指南](../development-guide.md)。
