document.addEventListener("DOMContentLoaded", () => {
  const textInput = document.getElementById("inbox-text");
  const analyzeBtn = document.getElementById("inbox-analyze-btn");
  const clearBtn = document.getElementById("inbox-clear-btn");
  const suggestionsEl = document.getElementById("inbox-suggestions");
  const loadingEl = document.getElementById("inbox-loading");
  const bulkBar = document.getElementById("inbox-bulk-bar");
  const selectHighBtn = document.getElementById("inbox-select-high-btn");
  const deselectBtn = document.getElementById("inbox-deselect-btn");
  const commitBtn = document.getElementById("inbox-commit-btn");
  const commitResultEl = document.getElementById("inbox-commit-result");
  const resultHint = document.getElementById("inbox-result-hint");
  const statsEl = document.getElementById("inbox-stats");
  const charCountEl = document.getElementById("inbox-char-count");
  const selectedCountEl = document.getElementById("inbox-selected-count");
  const workflowSteps = document.querySelectorAll(".inbox-workflow-step");

  if (!textInput || !analyzeBtn || !suggestionsEl) return;

  const CONFIDENCE_THRESHOLD = 0.6;
  const TYPE_LABELS = {
    goal: "目标",
    project: "项目",
    task: "任务",
    review: "复盘",
    asset: "知识卡片",
    capability_entry: "能力记录",
    uncertain: "不确定",
    ignored: "忽略",
  };

  let currentEntryId = null;
  let suggestions = [];
  let goals = [];
  let projects = [];
  const overridePayloads = {};

  function updateCharCount() {
    if (!charCountEl) return;
    const len = textInput.value.length;
    charCountEl.textContent = `${len} 字`;
  }

  function updateWorkflow(activeStep) {
    const order = ["input", "analyze", "commit"];
    const activeIndex = order.indexOf(activeStep);
    workflowSteps.forEach((step) => {
      const stepName = step.dataset.step;
      const index = order.indexOf(stepName);
      step.classList.toggle("is-active", stepName === activeStep);
      step.classList.toggle("is-done", index >= 0 && index < activeIndex);
    });
  }

  function countSelected() {
    return suggestionsEl.querySelectorAll(".inbox-select:checked").length;
  }

  function updateSelectedCount() {
    if (!selectedCountEl) return;
    const count = countSelected();
    selectedCountEl.textContent = `已选 ${count} 条`;
    selectedCountEl.classList.toggle("has-selection", count > 0);
  }

  function updateStats() {
    if (!statsEl) return;
    if (!suggestions.length) {
      statsEl.hidden = true;
      statsEl.innerHTML = "";
      return;
    }
    const pending = suggestions.filter((s) => s.status === "pending");
    const committable = pending.filter((s) => isCommittable(s));
    const committed = suggestions.filter((s) => s.status === "committed").length;
    statsEl.hidden = false;
    statsEl.innerHTML = `
      <span class="inbox-stat-chip"><strong>${suggestions.length}</strong> 条建议</span>
      <span class="inbox-stat-chip"><strong>${pending.length}</strong> 待处理</span>
      <span class="inbox-stat-chip is-highlight"><strong>${committable.length}</strong> 可归档</span>
      ${committed ? `<span class="inbox-stat-chip"><strong>${committed}</strong> 已入库</span>` : ""}`;
  }

  function setBulkBarVisible(visible) {
    if (bulkBar) bulkBar.hidden = !visible;
  }

  async function loadRelations() {
    try {
      goals = await apiRequest("/api/goals");
      projects = await apiRequest("/api/projects");
    } catch (_error) {
      goals = [];
      projects = [];
    }
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function summarize(text, maxLen = 200) {
    const value = (text || "").trim();
    if (value.length <= maxLen) return value;
    return `${value.slice(0, maxLen)}…`;
  }

  function getEffectivePayload(suggestion) {
    const base = { ...(suggestion.suggested_payload || {}) };
    const override = overridePayloads[suggestion.id] || {};
    return { ...base, ...override };
  }

  function findBatchProjectByRef(ref) {
    return suggestions.find(
      (item) =>
        item.target_type === "project" &&
        (item.suggested_payload?.local_ref || "") === ref
    );
  }

  function hasValidGoalId(payload) {
    const id = Number(payload.goal_id);
    return Number.isInteger(id) && id > 0;
  }

  function hasValidProjectId(payload) {
    const id = Number(payload.project_id);
    return Number.isInteger(id) && id > 0;
  }

  function isCommittable(suggestion) {
    if (suggestion.status !== "pending") return false;
    if (suggestion.target_type === "uncertain" || suggestion.target_type === "ignored") {
      return false;
    }
    const payload = getEffectivePayload(suggestion);
    if (suggestion.target_type === "project") {
      return hasValidGoalId(payload);
    }
    if (suggestion.target_type === "task") {
      if (hasValidProjectId(payload)) return true;
      const parentRef = (payload.parent_ref || "").trim();
      if (!parentRef) return false;
      const batchProject = findBatchProjectByRef(parentRef);
      if (!batchProject || batchProject.status !== "pending") return false;
      return hasValidGoalId(getEffectivePayload(batchProject));
    }
    return true;
  }

  function defaultChecked(suggestion) {
    if (!isCommittable(suggestion)) return false;
    return Number(suggestion.confidence) >= CONFIDENCE_THRESHOLD;
  }

  function renderConfidenceBar(confidence) {
    const pct = Math.round(Number(confidence) * 100);
    return `
      <div class="inbox-confidence-wrap">
        <div class="inbox-confidence-bar" role="presentation">
          <div class="inbox-confidence-fill" style="width: ${pct}%"></div>
        </div>
        <span class="inbox-confidence">${pct}%</span>
      </div>`;
  }

  function renderGoalSelect(suggestion) {
    const payload = getEffectivePayload(suggestion);
    const selected = payload.goal_id || "";
    const options = ['<option value="">选择归属目标</option>']
      .concat(
        goals.map(
          (goal) =>
            `<option value="${goal.id}"${String(goal.id) === String(selected) ? " selected" : ""}>${escapeHtml(goal.name)}</option>`
        )
      )
      .join("");
    return `
      <div class="inbox-relation-row">
        <label class="form-label">选择归属目标</label>
        <select class="select inbox-goal-select" data-id="${suggestion.id}">${options}</select>
      </div>`;
  }

  function renderProjectSelect(suggestion) {
    const payload = getEffectivePayload(suggestion);
    const parentRef = (payload.parent_ref || "").trim();
    const batchProject = parentRef ? findBatchProjectByRef(parentRef) : null;
    if (batchProject) {
      return buildSourceRelationLine("将归属同批项目", batchProject.title);
    }
    const selected = payload.project_id || "";
    const options = ['<option value="">选择归属项目</option>']
      .concat(
        projects.map(
          (project) =>
            `<option value="${project.id}"${String(project.id) === String(selected) ? " selected" : ""}>${escapeHtml(project.name)}${project.goal_name ? `（${escapeHtml(project.goal_name)}）` : ""}</option>`
        )
      )
      .join("");
    return `
      <div class="inbox-relation-row">
        <label class="form-label">选择归属项目</label>
        <select class="select inbox-project-select" data-id="${suggestion.id}">${options}</select>
      </div>`;
  }

  function actionLabel(action) {
    const labels = {
      create: "新建资产",
      append: "追加已有资产",
      merge: "合并资产",
      stash: "暂存",
    };
    return labels[action] || "新建资产";
  }

  function normalizeList(value) {
    return Array.isArray(value) ? value.filter(Boolean) : [];
  }

  function renderAssetFieldPreview(fields = {}) {
    const entries = Object.entries(fields).filter(([, value]) => String(value || "").trim());
    if (!entries.length) {
      return '<p class="inbox-asset-empty">暂无结构化字段，确认后将按核心内容兼容入库</p>';
    }
    return `
      <dl class="inbox-asset-fields">
        ${entries
          .map(
            ([key, value]) => `
              <div class="inbox-asset-field">
                <dt>${escapeHtml(key)}</dt>
                <dd>${escapeHtml(summarize(value, 120))}</dd>
              </div>`
          )
          .join("")}
      </dl>`;
  }

  function renderAssetPlacementPreview(suggestion) {
    if (suggestion.target_type !== "asset") return "";
    const payload = getEffectivePayload(suggestion);
    const tags = normalizeList(payload.capability_tags);
    const unmatched = normalizeList(payload.unmatched_fragments);
    const title = payload.title || suggestion.title;
    const type = payload.asset_type || "通用资产";
    const reusable = payload.reusable_scenario || "";
    const summary = payload.summary || payload.core_content || suggestion.content || "";
    return `
      <section class="inbox-asset-placement" aria-label="资产落位预览">
        <div class="inbox-asset-placement-head">
          <span class="tag inbox-asset-action">${escapeHtml(actionLabel(payload.action || "create"))}</span>
          <span class="tag inbox-asset-type">${escapeHtml(type)}</span>
          ${payload.maturity ? `<span class="tag tag-muted">${escapeHtml(payload.maturity)}</span>` : ""}
        </div>
        <div class="inbox-asset-placement-title">${escapeHtml(title)}</div>
        ${summary ? `<p class="inbox-asset-summary">${escapeHtml(summarize(summary, 160))}</p>` : ""}
        ${
          tags.length
            ? `<div class="inbox-asset-tags">${tags
                .map((tag) => `<span class="tag tag-cap tag-cap-inline">${escapeHtml(tag)}</span>`)
                .join("")}</div>`
            : ""
        }
        ${reusable ? `<p class="inbox-asset-reuse"><strong>复用场景</strong>${escapeHtml(reusable)}</p>` : ""}
        <div class="inbox-asset-field-wrap">
          <h4>字段落位</h4>
          ${renderAssetFieldPreview(payload.fields || {})}
        </div>
        ${
          unmatched.length
            ? `<div class="inbox-asset-unmatched">
                <h4>未匹配片段</h4>
                <ul>${unmatched
                  .map((item) => `<li>${escapeHtml(summarize(item, 120))}</li>`)
                  .join("")}</ul>
              </div>`
            : ""
        }
      </section>`;
  }

  function renderRelationSummary(suggestion) {
    const payload = getEffectivePayload(suggestion);
    if (suggestion.target_type === "project") {
      const goalId = Number(payload.goal_id);
      const goal = goals.find((item) => item.id === goalId);
      if (goal) {
        return `<p class="task-context-line relation-line muted-relation item-context">${buildInlineGoalContext(goal.name)}</p>`;
      }
    }
    if (suggestion.target_type === "task") {
      const projectId = Number(payload.project_id);
      const project = projects.find((item) => item.id === projectId);
      if (project) return buildTaskContextLine(project.name, project.goal_name);
      const parentRef = (payload.parent_ref || "").trim();
      const batchProject = parentRef ? findBatchProjectByRef(parentRef) : null;
      if (batchProject) {
        return buildSourceRelationLine("归属项目", batchProject.title);
      }
    }
    return "";
  }

  function renderRelationControls(suggestion) {
    if (suggestion.status !== "pending") return "";
    const payload = getEffectivePayload(suggestion);
    if (suggestion.target_type === "project" && !hasValidGoalId(payload)) {
      return renderGoalSelect(suggestion);
    }
    if (suggestion.target_type === "task") {
      if (hasValidProjectId(payload)) return "";
      const parentRef = (payload.parent_ref || "").trim();
      if (parentRef && findBatchProjectByRef(parentRef)) {
        return renderProjectSelect(suggestion);
      }
      if (!hasValidProjectId(payload)) {
        return renderProjectSelect(suggestion);
      }
    }
    return "";
  }

  function bindSuggestionEvents() {
    suggestionsEl.querySelectorAll(".inbox-reject-btn").forEach((btn) => {
      btn.addEventListener("click", () => rejectSuggestion(Number(btn.dataset.id)));
    });

    suggestionsEl.querySelectorAll(".inbox-goal-select").forEach((select) => {
      select.addEventListener("change", () => {
        const id = Number(select.dataset.id);
        overridePayloads[id] = {
          ...(overridePayloads[id] || {}),
          goal_id: select.value ? Number(select.value) : undefined,
        };
        renderSuggestions();
      });
    });

    suggestionsEl.querySelectorAll(".inbox-project-select").forEach((select) => {
      select.addEventListener("change", () => {
        const id = Number(select.dataset.id);
        overridePayloads[id] = {
          ...(overridePayloads[id] || {}),
          project_id: select.value ? Number(select.value) : undefined,
        };
        renderSuggestions();
      });
    });

    suggestionsEl.querySelectorAll(".inbox-select").forEach((input) => {
      input.addEventListener("change", updateSelectedCount);
    });
  }

  function renderEmptyWaiting() {
    suggestionsEl.innerHTML = `
      <div class="empty-state inbox-empty-state">
        <div class="inbox-empty-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <strong>等待输入</strong>
        在左侧输入文本后点击「AI 解析」
      </div>`;
    setBulkBarVisible(false);
    updateStats();
    updateSelectedCount();
    updateWorkflow("input");
  }

  function renderSuggestions() {
    if (!suggestions.length) {
      suggestionsEl.innerHTML = `
        <div class="empty-state inbox-empty-state">
          <strong>无归档建议</strong>
          AI 未从文本中识别出可归档内容
        </div>`;
      setBulkBarVisible(false);
      updateStats();
      updateSelectedCount();
      updateWorkflow("analyze");
      return;
    }

    const pending = suggestions.filter((s) => s.status === "pending");
    setBulkBarVisible(pending.length > 0);
    updateWorkflow(pending.length > 0 ? "commit" : "analyze");

    suggestionsEl.innerHTML = suggestions
      .map((suggestion) => {
        const committable = isCommittable(suggestion);
        const checked = defaultChecked(suggestion);
        const disabled =
          suggestion.status !== "pending" ||
          suggestion.target_type === "uncertain" ||
          suggestion.target_type === "ignored" ||
          !committable;
        const payloadText = JSON.stringify(getEffectivePayload(suggestion), null, 2);
        const typeClass = `inbox-card--${suggestion.target_type}`;
        const statusTag =
          suggestion.status === "committed"
            ? '<span class="tag tag-success">已入库</span>'
            : suggestion.status === "rejected"
              ? '<span class="tag tag-muted">已拒绝</span>'
              : !committable && suggestion.status === "pending"
                ? '<span class="tag tag-muted">待补关联</span>'
                : "";

        return `
          <article class="inbox-card entity-card ${typeClass}" data-id="${suggestion.id}">
            <div class="inbox-card-head">
              <label class="inbox-card-check">
                <input
                  type="checkbox"
                  class="inbox-select"
                  data-id="${suggestion.id}"
                  aria-label="选择：${escapeHtml(suggestion.title)}"
                  ${checked && !disabled ? "checked" : ""}
                  ${disabled ? "disabled" : ""}
                >
              </label>
              <div class="inbox-card-body">
                <div class="inbox-card-meta">
                  <span class="tag inbox-type-tag">${escapeHtml(TYPE_LABELS[suggestion.target_type] || suggestion.target_type)}</span>
                  ${renderConfidenceBar(suggestion.confidence)}
                  ${statusTag}
                </div>
                <h3 class="entity-title">${escapeHtml(suggestion.title)}</h3>
                ${renderRelationSummary(suggestion)}
                <p class="inbox-summary">${escapeHtml(summarize(suggestion.content))}</p>
                <p class="inbox-reason"><strong>归档理由</strong> ${escapeHtml(suggestion.reason || "—")}</p>
                ${renderAssetPlacementPreview(suggestion)}
                ${renderRelationControls(suggestion)}
                <details class="inbox-payload-details">
                  <summary>查看建议字段</summary>
                  <pre class="inbox-payload-pre">${escapeHtml(payloadText)}</pre>
                </details>
              </div>
              ${suggestion.status === "pending"
                ? `<div class="inbox-card-actions"><button type="button" class="btn btn-sm btn-ghost inbox-reject-btn" data-id="${suggestion.id}">拒绝</button></div>`
                : ""}
            </div>
          </article>`;
      })
      .join("");

    bindSuggestionEvents();
    updateStats();
    updateSelectedCount();
  }

  async function analyze() {
    const text = textInput.value.trim();
    if (!text) {
      showToast("请输入需要解析的文本", "warning");
      return;
    }

    analyzeBtn.disabled = true;
    loadingEl.hidden = false;
    commitResultEl.hidden = true;
    resultHint.textContent = "AI 正在分析，请稍候…";
    updateWorkflow("analyze");
    Object.keys(overridePayloads).forEach((key) => delete overridePayloads[key]);

    try {
      await loadRelations();
      const result = await apiRequest("/api/inbox/analyze", {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      currentEntryId = result.inbox_entry_id;
      suggestions = result.suggestions || [];
      renderSuggestions();
      resultHint.textContent = `已生成 ${suggestions.length} 条建议 · 项目需选目标 · 任务可挂同批或已有项目`;
      showToast("解析完成，请确认后归档", "success");
    } catch (error) {
      showToast(error.message || "解析失败", "error");
      resultHint.textContent = "解析失败，请重试";
      updateWorkflow("input");
    } finally {
      analyzeBtn.disabled = false;
      loadingEl.hidden = true;
    }
  }

  async function rejectSuggestion(suggestionId) {
    try {
      const updated = await apiRequest(`/api/inbox/suggestions/${suggestionId}/reject`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      suggestions = suggestions.map((item) =>
        item.id === updated.id ? { ...item, ...updated } : item
      );
      renderSuggestions();
      showToast("已拒绝该建议", "info");
    } catch (error) {
      showToast(error.message || "拒绝失败", "error");
    }
  }

  function setAllChecked(checked, onlyHigh = false) {
    suggestionsEl.querySelectorAll(".inbox-select").forEach((input) => {
      if (input.disabled) return;
      const id = Number(input.dataset.id);
      const suggestion = suggestions.find((item) => item.id === id);
      if (!suggestion) return;
      if (onlyHigh && Number(suggestion.confidence) < CONFIDENCE_THRESHOLD) {
        input.checked = false;
        return;
      }
      input.checked = checked;
    });
    updateSelectedCount();
  }

  function buildOverridePayload() {
    return Object.entries(overridePayloads)
      .filter(([, value]) => value && (value.goal_id || value.project_id))
      .map(([id, value]) => {
        const item = { suggestion_id: Number(id) };
        if (value.goal_id) item.goal_id = value.goal_id;
        if (value.project_id) item.project_id = value.project_id;
        return item;
      });
  }

  function renderCommitResult(data) {
    const created = data.created || {};
    const errors = data.errors || [];
    const labelMap = {
      goals: "目标",
      projects: "项目",
      tasks: "任务",
      reviews: "复盘",
      assets: "知识卡片",
      capability_entries: "能力记录",
    };
    const parts = Object.entries(created)
      .filter(([, count]) => count > 0)
      .map(([key, count]) => `${labelMap[key] || key} ${count}`);
    const createdTotal = Object.values(created).reduce((sum, n) => sum + (n || 0), 0);
    const title = createdTotal > 0 ? "归档完成" : "未能入库";
    const errorHtml = errors.length
      ? `<ul class="import-error-list">${errors
          .map((err) => `<li>${escapeHtml(err)}</li>`)
          .join("")}</ul>`
      : "";
    commitResultEl.hidden = false;
    commitResultEl.innerHTML = `
      <p><strong>${title}</strong></p>
      <p class="form-hint">${parts.length ? parts.join(" · ") : "无新记录创建"}${data.skipped ? ` · 跳过 ${data.skipped} 条` : ""}</p>
      ${errorHtml}`;
  }

  async function commitSelected() {
    const ids = Array.from(suggestionsEl.querySelectorAll(".inbox-select:checked")).map(
      (input) => Number(input.dataset.id)
    );
    if (!ids.length) {
      showToast("请至少选择一条可提交的建议", "warning");
      return;
    }

    commitBtn.disabled = true;
    try {
      const result = await apiRequest("/api/inbox/commit", {
        method: "POST",
        body: JSON.stringify({
          suggestion_ids: ids,
          override_payload: buildOverridePayload(),
        }),
      });
      if (currentEntryId) {
        const refreshed = await apiRequest(`/api/inbox/${currentEntryId}`);
        suggestions = refreshed.suggestions || [];
      }
      await loadRelations();
      renderSuggestions();
      renderCommitResult(result);
      const createdTotal = Object.values(result.created || {}).reduce(
        (sum, n) => sum + (n || 0),
        0
      );
      if (createdTotal > 0) {
        const msg = result.errors?.length
          ? `已入库 ${createdTotal} 条，${result.errors.length} 条未通过校验`
          : "归档成功";
        showToast(msg, result.errors?.length ? "warning" : "success");
      } else if (result.errors?.length) {
        showToast("所选建议均未通过校验，请查看下方说明", "warning");
      } else {
        showToast("没有新记录入库", "info");
      }
    } catch (error) {
      showToast(error.message || "归档失败", "error");
    } finally {
      commitBtn.disabled = false;
    }
  }

  textInput.addEventListener("input", updateCharCount);
  updateCharCount();
  updateWorkflow("input");
  loadRelations();
  analyzeBtn.addEventListener("click", analyze);
  clearBtn.addEventListener("click", () => {
    textInput.value = "";
    updateCharCount();
    suggestions = [];
    currentEntryId = null;
    Object.keys(overridePayloads).forEach((key) => delete overridePayloads[key]);
    commitResultEl.hidden = true;
    resultHint.textContent = "解析后在此预览，勾选需要归档的条目";
    renderEmptyWaiting();
  });
  selectHighBtn.addEventListener("click", () => setAllChecked(true, true));
  deselectBtn.addEventListener("click", () => setAllChecked(false));
  commitBtn.addEventListener("click", commitSelected);
});
