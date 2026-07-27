# AI 功能规范

## 核心边界

AI 用于辅助判断、分析和结构化，不能替用户完成核心判断。需要用户承担责任的字段 MUST 由用户输入或确认；例如 Deliberation 的 initial judgment、final judgment 与 decision，AI 可以挑战但不能代填。

## 分层

AI 功能 SHOULD 保持：

```text
UI → business service → AI service → model/provider
```

- UI 只采集输入、展示结果和错误。
- 业务 service 负责上下文、状态、校验与持久化边界。
- AI service 负责统一 provider 调用和调用错误。
- Prompt MUST 独立放在 `prompts/<module>/`，通过现有 loader 加载。

禁止把 Prompt 直接写入 HTML、JavaScript、route 或 controller。更换模型/provider 不应迫使页面或业务规则重写。

## 输出进入系统前

AI 输出写入数据库前 MUST 依次完成：

1. schema/type validation；
2. normalization；
3. 必填字段、空值与业务状态校验；
4. 明确的 error handling。

缺字段、类型错误、不可解析或违反业务约束的结果禁止入库。错误必须可见，不得用空值或虚假关联静默兜底。

模型调用或校验失败时 MUST 保留用户原始输入和草稿状态，允许重试，不伪造成功结果。AI failure 不得破坏不依赖 AI 的主流程。

## 可替换性

- 模型/provider 的变化 SHOULD 收敛在 AI service。
- Prompt 可以独立修改和版本管理。
- 页面与业务状态不能依赖某个模型的偶然输出格式。

## 验证

- 自动测试 SHOULD mock AI 入口，不依赖真实 provider 或密钥。
- 至少覆盖合法结果、缺字段、错误类型与 provider failure。
- 真实 AI 验证只在明确需要且数据边界已确认时进行，不以生成生产脏数据作为发布门禁。

现有实现参考 `deliberation_service.py`、`ai_service.py` 与 `prompts/loader.py`。
