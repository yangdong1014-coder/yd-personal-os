# 战略定位页 · 编辑/填写态对齐修复（补丁规格）

> 承接 positioning-layout-spec-v2.md。上一次重构后，结构对了，但「编辑锚」和「新建校准」两个填写态布局混乱、输入框大小不一、不对齐。
> 本补丁只修这两个填写态的对齐，其余保持 v2 已实现的样子。
> 核心方法：直接采用下方 CSS 网格规则，不要自行设计网格。颜色一律换成项目主题变量，下方代码里的 hex 仅示意结构，严禁照抄颜色。

---

## 1 · 问题（要修的）

```
✗ 锚区编辑态：五个字段空框平铺，北极星缩在右半边、中间大块空白
✗ 校准填写态：五个框大小不一、横竖不对齐、参差不齐
✗ 整体回到「一屏全是乱排空框」的填表混乱
```

## 2 · 锚区编辑态 → 改成「北极星置顶块 + 一行一项对齐列表」

**北极星单独置顶**：一个带边框的强调块，输入框做宽、字号大，提示文字在下方。
**其余四字段**：每个一行，标签统一右对齐固定宽，输入框占满剩余宽度，四行整齐竖排。

直接采用这套结构与 CSS（颜色换主题变量）：

```html
<div class="anchor-edit">
  <div class="ns-block">
    <div class="ns-label">北极星指标 · 全页基准</div>
    <input class="ns-input" />
    <div class="ns-hint">北极星 = 当前阶段唯一最重要的、可衡量的成功标准</div>
  </div>
  <div class="anchor-rows">
    <div class="row"><span class="row-label">第一性原理</span><input /></div>
    <div class="row"><span class="row-label">身份内核</span><input /></div>
    <div class="row"><span class="row-label">飞轮定义</span><input /></div>
    <div class="row"><span class="row-label">当前阶段</span><input /></div>
  </div>
</div>
```

```css
.ns-block{
  background: var(--surface-2);
  border: 1px solid var(--border-accent);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 16px;
}
.ns-label{
  font-size: 11px; letter-spacing: 2px;
  color: var(--text-accent);
  margin-bottom: 8px;
}
.ns-input{
  width: 100%; box-sizing: border-box;
  padding: 12px 14px; font-size: 18px; font-weight: 500;
}
.ns-hint{ font-size: 11px; color: var(--text-muted); margin-top: 8px; }

.anchor-rows{ display: flex; flex-direction: column; gap: 11px; }
.anchor-rows .row{
  display: grid;
  grid-template-columns: 96px 1fr;   /* 标签列固定，输入列占满 */
  align-items: center;
  gap: 14px;
}
.anchor-rows .row-label{
  font-size: 12px; color: var(--text-secondary);
  text-align: right;                  /* 标签统一右对齐 */
}
.anchor-rows .row input{ width: 100%; box-sizing: border-box; }
```

## 3 · 校准填写态 → 真正的等宽 2×2 网格

四个思考字段两列等宽、四框等高对齐；结论字段单独通栏；日期/周期一行两列。

直接采用这套 CSS（颜色换主题变量）：

```html
<div class="cal-form">
  <div class="cal-meta">
    <div class="field"><label>校准日期</label><input type="date" /></div>
    <div class="field"><label>校准周期</label><select>…</select></div>
  </div>
  <div class="cal-grid">
    <div class="field"><label>当前主要矛盾</label><textarea></textarea></div>
    <div class="field"><label>目标对齐审查</label><textarea></textarea></div>
    <div class="field"><label>在做但不该做的</label><textarea></textarea></div>
    <div class="field"><label>该做但没做的</label><textarea></textarea></div>
  </div>
  <div class="field cal-conclusion"><label>本期校准结论</label><textarea></textarea></div>
  <div class="cal-actions"><button>提交校准</button><button>取消</button></div>
</div>
```

```css
.cal-meta{
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
  margin-bottom: 12px;
}
.cal-grid{
  display: grid; grid-template-columns: 1fr 1fr;  /* 两列等宽 */
  gap: 12px; margin-bottom: 12px;
}
.cal-grid .field textarea{
  width: 100%; box-sizing: border-box;
  height: 64px; resize: vertical;     /* 四框统一起始高度 */
}
.cal-conclusion{ margin-bottom: 14px; }
.cal-conclusion textarea{
  width: 100%; box-sizing: border-box; height: 56px; resize: vertical;
}
.field label{
  display: block; font-size: 11px;
  color: var(--text-secondary); margin-bottom: 5px;
}
.cal-actions{ display: flex; justify-content: flex-end; gap: 10px; }
```

## 4 · 死命令

```
✓ 上面 CSS 的网格结构（grid-template-columns、gap、固定标签列、等高 textarea）照抄，
  这是为了强制对齐，不要自行改成其它排法。
✗ 所有颜色换成项目既有主题变量，绝不硬编码 hex（上面 hex 仅示意，严禁照抄颜色）。
✗ 只改这两个填写态的 html 结构 + css，不动功能、API、数据、六模块。
✗ 不动 v2 已实现的：态势面板默认态、流向箭头、图标、北极星提示逻辑。
✗ 手测用 YD_OS_DB_PATH 临时库；改完截图，停下给杨栋看，不 push。
```

## 5 · 验收

```
[ ] 锚区编辑：北极星单独置顶强调块，输入框宽、字大、提示在下
[ ] 锚区四字段：标签右对齐固定列宽，输入框占满，四行整齐竖排
[ ] 校准填写：四个思考框两列等宽、等高、横竖对齐，无参差、无大块空白
[ ] 结论字段单独通栏；日期/周期一行两列
[ ] 全程主题变量，切深/浅主题均正常
[ ] 功能、API、六模块未受影响
```

---

*编辑/填写态对齐修复 · 承接 positioning-layout-spec-v2.md*
*整齐感靠 CSS grid 规则锁定，不靠现场发挥*
