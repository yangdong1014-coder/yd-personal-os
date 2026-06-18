function ensureAIModal() {
  let modal = document.getElementById("ai-modal");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.id = "ai-modal";
  modal.className = "ai-modal hidden";
  modal.innerHTML = `
    <div class="ai-modal-backdrop"></div>
    <div class="ai-modal-panel" role="dialog" aria-modal="true">
      <header class="ai-modal-header">
        <h3 id="ai-modal-title"></h3>
        <button type="button" class="ai-modal-close" aria-label="关闭">×</button>
      </header>
      <div id="ai-modal-body" class="ai-modal-body"></div>
      <footer class="ai-modal-footer">
        <button type="button" class="btn btn-ghost" id="ai-modal-cancel">取消</button>
        <button type="button" class="btn" id="ai-modal-confirm">确认保存</button>
      </footer>
    </div>
  `;
  document.body.appendChild(modal);

  modal.querySelector(".ai-modal-backdrop").addEventListener("click", () => {
    hideAIModal();
  });
  modal.querySelector(".ai-modal-close").addEventListener("click", () => {
    hideAIModal();
  });

  return modal;
}

function hideAIModal() {
  const modal = document.getElementById("ai-modal");
  if (modal) modal.classList.add("hidden");
}

function showAIModal({ title, bodyHtml, onConfirm }) {
  const modal = ensureAIModal();
  modal.querySelector("#ai-modal-title").textContent = title;
  modal.querySelector("#ai-modal-body").innerHTML = bodyHtml;

  const confirmBtn = modal.querySelector("#ai-modal-confirm");
  const cancelBtn = modal.querySelector("#ai-modal-cancel");

  const newConfirm = confirmBtn.cloneNode(true);
  const newCancel = cancelBtn.cloneNode(true);
  confirmBtn.replaceWith(newConfirm);
  cancelBtn.replaceWith(newCancel);

  newCancel.addEventListener("click", hideAIModal);
  newConfirm.addEventListener("click", async () => {
    newConfirm.disabled = true;
    newConfirm.textContent = "保存中…";
    try {
      await onConfirm();
      hideAIModal();
    } catch (err) {
      alert(err.message || "保存失败");
    } finally {
      newConfirm.disabled = false;
      newConfirm.textContent = "确认保存";
    }
  });

  modal.classList.remove("hidden");
}

function buildDraftFormHtml(draft, capabilityModules) {
  const tagOptions = capabilityModules
    .map((m) => {
      const checked = (draft.capability_tags || []).includes(m) ? " checked" : "";
      return `
        <label class="tag-option">
          <input type="checkbox" class="draft-tag" value="${escapeHtml(m)}"${checked}>
          <span>${escapeHtml(m)}</span>
        </label>
      `;
    })
    .join("");

  return `
    <div class="stacked-form">
      <div class="form-row">
        <label class="form-label">标题</label>
        <input type="text" id="draft-title" class="input full-width" value="${escapeAttr(draft.title || "")}">
      </div>
      <div class="form-row">
        <label class="form-label">触发情境</label>
        <textarea id="draft-trigger" class="textarea" rows="2">${escapeHtml(draft.trigger_context || "")}</textarea>
      </div>
      <div class="form-row">
        <label class="form-label">核心内容</label>
        <textarea id="draft-content" class="textarea" rows="6">${escapeHtml(draft.core_content || "")}</textarea>
      </div>
      <div class="form-row">
        <span class="form-label">关联能力模块</span>
        <div class="tag-picker">${tagOptions}</div>
      </div>
    </div>
  `;
}

function readDraftForm() {
  return {
    title: document.getElementById("draft-title").value.trim(),
    trigger_context: document.getElementById("draft-trigger").value.trim(),
    core_content: document.getElementById("draft-content").value.trim(),
    capability_tags: Array.from(document.querySelectorAll(".draft-tag:checked")).map(
      (el) => el.value
    ),
  };
}

function escapeAttr(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}