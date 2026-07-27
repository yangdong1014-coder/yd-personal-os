# UI 规范

## 继承现有设计系统

新增页面或明显 UI 修改前，MUST 先阅读至少 2–3 个成熟 PSY 页面作为基线，并优先复用：

- `.page-container`、`.page-header`、`.section-card`；
- button、input、textarea、select、badge；
- typography、spacing 与 CSS variables。

默认行为是继承现有 UI，不为单个模块重建视觉体系。颜色与交互基线见 [系统搭建说明书](../系统搭建说明书_1.1.md#陆--ui-设计规范)。

## 数据模型与交互模型

> 数据模型服务系统，交互模型服务人。

禁止因为数据库存在 `title`、`context`、`assumptions`、`related_type`、`related_id` 就把字段等权铺成表单。页面 MUST 围绕用户任务和思考顺序组织；字段映射、默认值和关联 ID 留在业务层。

Deliberation 已验证的交互顺序是：

```text
问题 → 当前判断 → 理由 → 关键假设 → AI 对抗
→ 最终判断 → 行动 → 反馈 → 原则
```

## Layout Grid

同一单列页面中的 Header、Form、Card、More Info 与 Action Wrapper MUST 共用标准内容容器的左右轴线。页面根容器、flow wrapper、form 和 section card MUST 为可用宽度的 `100%`；明确设计为多列 grid 的页面除外。

没有明确产品要求时，禁止在页面级 wrapper 或 form 上设置任意 `max-width`。

v2.1.4 的真实事故根因是：

```css
.delib-new-form {
  max-width: 920px;
}
```

当时桌面验收中，标准内容区约 1150px，Header 右边界约 1400px，而 Form/Card 约 1170px，形成约 250px 的无意义空白。当前代码的标准 token 为 `--content-max: 1180px`；这些历史测量值只用于说明事故，不得硬编码成新布局。

截图验收没有暴露真实父容器约束；最终通过逐级测量 ancestor 的 rect 与 computed style 才定位并删除旧规则。

## 阅读宽度与结构宽度

需要控制阅读宽度时，只能约束 card 内部的 `.card-inner`、`.form-content`、`.text-content`、`.reading-column` 或 textarea 内部阅读区。禁止缩窄 page root、主 form、section card、页面 flow 或 action wrapper。

原则：**页面结构宽度和内容阅读宽度是两个问题。**

## 数值验收

Alignment/Layout MUST 用真实浏览器 DOM 测量，不能只看截图：

```js
const measure = (element) => {
  const rect = element.getBoundingClientRect();
  const style = getComputedStyle(element);
  return {
    left: rect.left,
    right: rect.right,
    width: rect.width,
    cssWidth: style.width,
    maxWidth: style.maxWidth,
    margin: style.margin,
    marginLeft: style.marginLeft,
    marginRight: style.marginRight,
    display: style.display,
    gridTemplateColumns: style.gridTemplateColumns,
    flex: style.flex,
    flexBasis: style.flexBasis,
    overflow: style.overflow,
  };
};
```

同一视觉轴线的元素 MUST 满足：

```text
abs(element.left - header.left) <= 2px
abs(element.right - header.right) <= 2px
```

若不满足，从异常元素逐级检查 `parentElement`；第一个边界比 Header 提前结束的 ancestor 就是优先排查对象。必须定位其 `max-width`、width、margin、grid、flex 或 overflow 来源后再修改。

## 截图与响应式

- 数字验证对齐、等宽、overflow、grid/flex；截图验证层级、留白、密度、字体、节奏和阅读体验。二者不能互相替代。
- 新增或明显修改页面至少验证 `1440`、`1024`、`768`、`390` px。
- 每个宽度 MUST 确认无横向溢出、轴线错位或大块异常留白，导航、Card、表单和按钮可用。

## CSS 修复原则

发现旧规则造成问题时，MUST 修改或删除根因规则。禁止默认使用：

- `!important` 或不断增加 specificity；
- 在文件末尾叠加补丁覆盖；
- 未找到父容器就只给子元素 `width: 100%`；
- 只看截图、不检查 computed style。

原则：**修根因，不叠补丁。**
