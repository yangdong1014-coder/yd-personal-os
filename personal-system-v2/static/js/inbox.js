document.addEventListener("DOMContentLoaded", () => {
  const textInput = document.getElementById("inbox-text");
  const analyzeBtn = document.getElementById("inbox-analyze-btn");
  const clearBtn = document.getElementById("inbox-clear-btn");
  const suggestionsEl = document.getElementById("inbox-suggestions");
  const loadingEl = document.getElementById("inbox-loading");
  const bulkActions = document.getElementById("inbox-bulk-actions");
  const selectHighBtn = document.getElementById("inbox-select-high-btn");
  const deselectBtn = document.getElementById("inbox-deselect-btn");
  const commitBtn = document.getElementById("inbox-commit-btn");
  const commitResultEl = document.getElementById("inbox-commit-result");
  const resultHint = document.getElementById("inbox-result-hint");

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

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function summarize(text, maxLen = 160) {
    const value = (text || "").trim();
    if (value.length <= maxLen) return value;
    return `${value.slice(0, maxLen)}…`;
  }

  function defaultChecked(suggestion) {
    if (suggestion.status !== "pending") return false;
    if (suggestion.target_type === "uncertain" || suggestion.target_type === "ignored") {
      return false;
    }
    return Number(suggestion.confidence) >= CONFIDENCE_THRESHOLD;
  }

  function renderSuggestions() {
    if (!suggestions.length) {
      suggestionsEl.innerHTML = `
        <div class="empty-state">
          <strong>无归档建议</strong>
          AI 未从文本中识别出可归档内容
        </div>`;
      bulkActions.hidden = true;
      return;
    }

    const pending = suggestions.filter((s) => s.status === "pending");
    bulkActions.hidden = pending.length === 0;

    suggestionsEl.innerHTML = suggestions
      .map((suggestion) => {
        const checked = defaultChecked(suggestion);
        const disabled =
          suggestion.status !== "pending" ||
          suggestion.target_type === "uncertain" ||
          suggestion.target_type === "ignored";
        const payload = suggestion.suggested_payload || {};
        const payloadText = JSON.stringify(payload, null, 2);
        const statusTag =
          suggestion.status === "committed"
            ? '<span class="tag tag-success">已入库</span>'
            : suggestion.status === "rejected"
              ? '<span class="tag tag-muted">已拒绝</span>'
              : "";

        return `
          <article class="inbox-card entity-card" data-id="${suggestion.id}">
            <div class="inbox-card-head">
              <label class="inbox-card-check">
                <input
                  type="checkbox"
                  class="inbox-select"
                  data-id="${suggestion.id}"
                  ${checked && !disabled ? "checked" : ""}
                  ${disabled ? "disabled" : ""}
                >
              </label>
              <div class="inbox-card-meta">
                <span class="tag inbox-type-tag">${escapeHtml(TYPE_LABELS[suggestion.target_type] || suggestion.target_type)}</span>
                <span class="inbox-confidence">置信度 ${(Number(suggestion.confidence) * 100).toFixed(0)}%</span>
                ${statusTag}
              </div>
              ${suggestion.status === "pending" ? `<button type="button" class="btn btn-sm btn-ghost inbox-reject-btn" data-id="${suggestion.id}">拒绝</button>` : ""}
            </div>
            <h3 class="entity-title">${escapeHtml(suggestion.title)}</h3>
            <p class="inbox-summary">${escapeHtml(summarize(suggestion.content))}</p>
            <p class="form-hint"><strong>归档理由：</strong>${escapeHtml(suggestion.reason || "—")}</p>
            <details class="inbox-payload-details">
              <summary>建议字段</summary>
              <pre class="inbox-payload-pre">${escapeHtml(payloadText)}</pre>
            </details>
          </article>`;
      })
      .join("");

    suggestionsEl.querySelectorAll(".inbox-reject-btn").forEach((btn) => {
      btn.addEventListener("click", () => rejectSuggestion(Number(btn.dataset.id)));
    });
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

    try {
      const result = await apiRequest("/api/inbox/analyze", {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      currentEntryId = result.inbox_entry_id;
      suggestions = result.suggestions || [];
      renderSuggestions();
      resultHint.textContent = `已生成 ${suggestions.length} 条建议，低置信度（<60%）默认不勾选`;
      showToast("解析完成，请确认后归档", "success");
    } catch (error) {
      showToast(error.message || "解析失败", "error");
      resultHint.textContent = "解析失败，请重试";
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
  }

  function renderCommitResult(data) {
    const created = data.created || {};
    const errors = data.errors || [];
    const parts = Object.entries(created)
      .filter(([, count]) => count > 0)
      .map(([key, count]) => `${key}: ${count}`);
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
      showToast("请至少选择一条建议", "warning");
      return;
    }

    commitBtn.disabled = true;
    try {
      const result = await apiRequest("/api/inbox/commit", {
        method: "POST",
        body: JSON.stringify({ suggestion_ids: ids }),
      });
      if (currentEntryId) {
        const refreshed = await apiRequest(`/api/inbox/${currentEntryId}`);
        suggestions = refreshed.suggestions || [];
      }
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

  analyzeBtn.addEventListener("click", analyze);
  clearBtn.addEventListener("click", () => {
    textInput.value = "";
    suggestions = [];
    currentEntryId = null;
    commitResultEl.hidden = true;
    bulkActions.hidden = true;
    resultHint.textContent = "解析后在此预览，勾选需要归档的条目";
    suggestionsEl.innerHTML = `
      <div class="empty-state">
        <strong>等待输入</strong>
        在左侧输入文本后点击「AI 解析」
      </div>`;
  });
  selectHighBtn.addEventListener("click", () => setAllChecked(true, true));
  deselectBtn.addEventListener("click", () => setAllChecked(false));
  commitBtn.addEventListener("click", commitSelected);
});