(function () {
  const listEl = document.getElementById("feedback-list");
  const createBtn = document.getElementById("create-feedback-btn");
  const sources = window.FEEDBACK_SOURCES || [];
  const levels = window.FEEDBACK_LEVELS || [];
  const relatedTypes = window.FEEDBACK_RELATED_TYPES || [];

  if (!listEl) return;

  function options(values, selected) {
    return values.map((v) => `<option value="${escapeAttr(v)}"${v === selected ? " selected" : ""}>${escapeHtml(v)}</option>`).join("");
  }

  function relationOptions(selected) {
    return `<option value="">不关联</option>${relatedTypes.map((v) => `<option value="${escapeAttr(v)}"${v === selected ? " selected" : ""}>${escapeHtml(v)}</option>`).join("")}`;
  }

  function formHtml(item = {}) {
    return `
      <div class="stacked-form value-form-grid">
        <div class="form-row"><label class="form-label">反馈标题</label><input id="fb-title" class="input full-width" value="${escapeAttr(item.title || "")}" required></div>
        <div class="form-row"><label class="form-label">反馈来源</label><select id="fb-source" class="select full-width">${options(sources, item.source || "自我判断")}</select></div>
        <div class="form-row"><label class="form-label">反馈等级</label><select id="fb-level" class="select full-width">${options(levels, item.level || "L0 只是想法")}</select></div>
        <div class="form-row"><label class="form-label">关联类型</label><select id="fb-related_type" class="select full-width">${relationOptions(item.related_type || "")}</select></div>
        <div class="form-row"><label class="form-label">关联 ID</label><input id="fb-related_id" class="input full-width" type="number" min="1" value="${item.related_id || ""}"></div>
        <div class="form-row form-row-wide"><label class="form-label">反馈内容</label><textarea id="fb-content" class="textarea" rows="3">${escapeHtml(item.content || "")}</textarea></div>
        <div class="form-row form-row-wide"><label class="form-label">证据</label><textarea id="fb-evidence" class="textarea" rows="3">${escapeHtml(item.evidence || "")}</textarea></div>
        <div class="form-row form-row-wide"><label class="form-label">后续动作</label><textarea id="fb-next_action" class="textarea" rows="2">${escapeHtml(item.next_action || "")}</textarea></div>
      </div>
    `;
  }

  function readForm() {
    return {
      title: document.getElementById("fb-title").value.trim(),
      source: document.getElementById("fb-source").value,
      level: document.getElementById("fb-level").value,
      related_type: document.getElementById("fb-related_type").value,
      related_id: document.getElementById("fb-related_id").value || null,
      content: document.getElementById("fb-content").value.trim(),
      evidence: document.getElementById("fb-evidence").value.trim(),
      next_action: document.getElementById("fb-next_action").value.trim(),
    };
  }

  function openEditor(item = null) {
    showAIModal({
      title: item ? `编辑反馈 - ${item.title}` : "记录一个反馈",
      bodyHtml: formHtml(item || {}),
      confirmLabel: item ? "保存反馈" : "创建反馈",
      onConfirm: async () => {
        const payload = readForm();
        if (item) {
          await apiRequest(`/api/feedback/${item.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        } else {
          await apiRequest("/api/feedback", { method: "POST", body: JSON.stringify(payload) });
        }
        showToast("反馈已保存", "success");
        await load();
      },
    });
  }

  function card(item) {
    return `
      <article class="entity-card value-card" data-id="${item.id}">
        <div class="value-card-head">
          <div>
            <h3 class="entity-title">${escapeHtml(item.title)}</h3>
            <p class="entity-meta">${escapeHtml(item.source)} · ${escapeHtml(item.level)}</p>
          </div>
        </div>
        <p class="value-card-summary">${formatText(item.content || item.evidence || "暂无反馈内容")}</p>
        <div class="value-card-meta">
          ${item.related_type ? `<span class="tag">${escapeHtml(item.related_type)} #${escapeHtml(item.related_id || "")}</span>` : ""}
          ${item.evidence ? `<span class="tag">有证据</span>` : ""}
        </div>
        <div class="entity-actions">
          <button type="button" class="btn btn-sm btn-ghost btn-edit">编辑</button>
          <button type="button" class="btn btn-sm btn-ghost btn-delete">删除</button>
        </div>
      </article>
    `;
  }

  async function load() {
    const items = await apiRequest("/api/feedback");
    if (!items.length) {
      listEl.innerHTML = `<div class="empty-state"><strong>暂无反馈</strong>记录来自使用、业务、客户或数据的真实信号</div>`;
      return;
    }
    listEl.innerHTML = items.map(card).join("");
    listEl.querySelectorAll(".value-card").forEach((el) => {
      const item = items.find((row) => row.id === Number(el.dataset.id));
      el.querySelector(".btn-edit").addEventListener("click", () => openEditor(item));
      el.querySelector(".btn-delete").addEventListener("click", async () => {
        if (!confirm(`确定删除反馈「${item.title}」？`)) return;
        await apiRequest(`/api/feedback/${item.id}`, { method: "DELETE" });
        showToast("反馈已删除", "success");
        await load();
      });
    });
  }

  createBtn?.addEventListener("click", () => openEditor());
  load().catch((err) => showToast(err.message, "error"));
})();

function formatText(text) {
  return escapeHtml(text || "").replace(/\n/g, "<br>");
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[c]));
}

function escapeAttr(text) {
  return escapeHtml(text).replace(/`/g, "&#096;");
}
