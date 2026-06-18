document.addEventListener("DOMContentLoaded", () => {
  const listEl = document.getElementById("inbox-history-list");
  const detailEl = document.getElementById("inbox-history-detail");
  if (!listEl || !detailEl) return;

  const STATUS_LABELS = {
    draft: "草稿",
    analyzed: "已解析",
    committed: "已归档",
    archived: "已封存",
    failed: "解析失败",
  };

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadDetail(entryId) {
    const data = await apiRequest(`/api/inbox/${entryId}`);
    const entry = data.entry;
    const suggestions = data.suggestions || [];
    detailEl.innerHTML = `
      <div class="inbox-history-entry">
        <p class="form-hint"><strong>时间：</strong>${escapeHtml(entry.created_at)} · <strong>状态：</strong>${escapeHtml(STATUS_LABELS[entry.status] || entry.status)}</p>
        <h3 class="entity-title">原文</h3>
        <pre class="inbox-payload-pre">${escapeHtml(entry.raw_text)}</pre>
        <h3 class="entity-title">建议（${suggestions.length}）</h3>
        <ul class="inbox-history-suggestions">
          ${suggestions
            .map(
              (item) =>
                `<li><span class="tag">${escapeHtml(item.target_type)}</span> ${escapeHtml(item.title)} · ${escapeHtml(item.status)} · 置信度 ${(Number(item.confidence) * 100).toFixed(0)}%</li>`
            )
            .join("")}
        </ul>
      </div>`;
  }

  async function loadHistory() {
    try {
      const entries = await apiRequest("/api/inbox");
      if (!entries.length) {
        listEl.innerHTML = `<div class="empty-state"><strong>暂无记录</strong></div>`;
        return;
      }
      listEl.innerHTML = entries
        .map(
          (entry) => `
          <button type="button" class="inbox-history-item entity-card" data-id="${entry.id}">
            <div class="entity-header">
              <strong>#${entry.id}</strong>
              <span class="tag">${escapeHtml(STATUS_LABELS[entry.status] || entry.status)}</span>
            </div>
            <p class="inbox-summary">${escapeHtml(entry.raw_text_summary)}</p>
            <p class="form-hint">${escapeHtml(entry.created_at)} · 建议 ${entry.suggestion_count} · 已入库 ${entry.committed_count} · 待处理 ${entry.pending_count} · 已拒绝 ${entry.rejected_count}</p>
          </button>`
        )
        .join("");

      listEl.querySelectorAll(".inbox-history-item").forEach((btn) => {
        btn.addEventListener("click", async () => {
          listEl.querySelectorAll(".inbox-history-item").forEach((el) => el.classList.remove("is-active"));
          btn.classList.add("is-active");
          try {
            await loadDetail(Number(btn.dataset.id));
          } catch (error) {
            showToast(error.message || "加载详情失败", "error");
          }
        });
      });
    } catch (error) {
      listEl.innerHTML = `<div class="empty-state">加载失败：${escapeHtml(error.message)}</div>`;
    }
  }

  loadHistory();
});