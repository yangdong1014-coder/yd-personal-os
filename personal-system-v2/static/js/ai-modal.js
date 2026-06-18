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

function showAIModal({
  title,
  bodyHtml,
  onConfirm,
  confirmLabel = "确认保存",
  loadingLabel = "保存中…",
}) {
  const modal = ensureAIModal();
  modal.querySelector("#ai-modal-title").textContent = title;
  modal.querySelector("#ai-modal-body").innerHTML = bodyHtml;

  const confirmBtn = modal.querySelector("#ai-modal-confirm");
  const cancelBtn = modal.querySelector("#ai-modal-cancel");
  confirmBtn.style.display = "";
  confirmBtn.textContent = confirmLabel;

  const newConfirm = confirmBtn.cloneNode(true);
  const newCancel = cancelBtn.cloneNode(true);
  confirmBtn.replaceWith(newConfirm);
  cancelBtn.replaceWith(newCancel);

  newCancel.addEventListener("click", hideAIModal);
  newConfirm.addEventListener("click", async () => {
    newConfirm.disabled = true;
    newConfirm.textContent = loadingLabel;
    try {
      await onConfirm();
      hideAIModal();
    } catch (err) {
      alert(err.message || "操作失败");
    } finally {
      newConfirm.disabled = false;
      newConfirm.textContent = confirmLabel;
    }
  });

  modal.classList.remove("hidden");
}

function showAIViewModal({ title, bodyHtml, closeLabel = "知道了" }) {
  const modal = ensureAIModal();
  modal.querySelector("#ai-modal-title").textContent = title;
  modal.querySelector("#ai-modal-body").innerHTML = bodyHtml;

  const confirmBtn = modal.querySelector("#ai-modal-confirm");
  const cancelBtn = modal.querySelector("#ai-modal-cancel");
  confirmBtn.style.display = "none";

  const newCancel = cancelBtn.cloneNode(true);
  cancelBtn.replaceWith(newCancel);
  newCancel.textContent = closeLabel;
  newCancel.addEventListener("click", hideAIModal);

  modal.classList.remove("hidden");
}

function buildProjectsDraftHtml(projects) {
  return `
    <div class="stacked-form project-draft-list">
      ${projects
        .map(
          (p, i) => `
        <label class="project-draft-item">
          <input type="checkbox" class="project-draft-check" data-idx="${i}" checked>
          <div class="project-draft-fields">
            <input type="text" class="input full-width project-draft-name" value="${escapeAttr(p.name)}">
            ${p.reason ? `<span class="form-hint">${escapeHtml(p.reason)}</span>` : ""}
          </div>
        </label>
      `
        )
        .join("")}
    </div>
  `;
}

function readSelectedProjectNames() {
  const names = [];
  document.querySelectorAll(".project-draft-item").forEach((item) => {
    const checked = item.querySelector(".project-draft-check");
    const input = item.querySelector(".project-draft-name");
    if (checked?.checked && input?.value.trim()) {
      names.push(input.value.trim());
    }
  });
  return names;
}

function buildTasksDraftHtml(tasks) {
  return `
    <div class="stacked-form project-draft-list">
      ${tasks
        .map(
          (t, i) => `
        <label class="project-draft-item">
          <input type="checkbox" class="task-draft-check" data-idx="${i}" checked>
          <div class="project-draft-fields">
            <input type="text" class="input full-width task-draft-name" value="${escapeAttr(t.name)}">
            ${
              t.priority || t.reason
                ? `<span class="form-hint">${escapeHtml(
                    [t.priority ? `优先级：${t.priority}` : "", t.reason || ""]
                      .filter(Boolean)
                      .join(" · ")
                  )}</span>`
                : ""
            }
          </div>
        </label>
      `
        )
        .join("")}
    </div>
  `;
}

function readSelectedTaskNames() {
  const names = [];
  document.querySelectorAll(".project-draft-item").forEach((item) => {
    const checked = item.querySelector(".task-draft-check");
    const input = item.querySelector(".task-draft-name");
    if (checked?.checked && input?.value.trim()) {
      names.push(input.value.trim());
    }
  });
  return names;
}

function buildTodayRecommendHtml(recommendations) {
  return `
    <div class="stacked-form project-draft-list">
      ${recommendations
        .map(
          (t) => `
        <label class="project-draft-item">
          <input type="checkbox" class="recommend-check" data-task-id="${t.task_id}" checked>
          <div class="project-draft-fields">
            <strong class="recommend-name">${escapeHtml(t.name)}</strong>
            <span class="form-hint">${escapeHtml(t.goal_name)} / ${escapeHtml(t.project_name)} · ${escapeHtml(t.status)}</span>
            ${t.reason ? `<span class="form-hint">${escapeHtml(t.reason)}</span>` : ""}
          </div>
        </label>
      `
        )
        .join("")}
    </div>
  `;
}

function readSelectedRecommendTaskIds() {
  const ids = [];
  document.querySelectorAll(".recommend-check:checked").forEach((el) => {
    const id = parseInt(el.dataset.taskId, 10);
    if (id) ids.push(id);
  });
  return ids;
}

function buildReviewCompleteHtml(draft) {
  return `
    <div class="stacked-form">
      <div class="form-row">
        <label class="form-label">卡住了什么</label>
        <textarea id="complete-stuck" class="textarea" rows="3">${escapeHtml(draft.stuck || "")}</textarea>
      </div>
      <div class="form-row">
        <label class="form-label">下一步调整</label>
        <textarea id="complete-next" class="textarea" rows="3">${escapeHtml(draft.next_adjust || "")}</textarea>
      </div>
      <div class="form-row">
        <label class="form-label">可沉淀内容</label>
        <textarea id="complete-depositable" class="textarea" rows="3">${escapeHtml(draft.depositable || "")}</textarea>
      </div>
    </div>
  `;
}

function readReviewCompleteForm() {
  return {
    stuck: document.getElementById("complete-stuck").value.trim(),
    next_adjust: document.getElementById("complete-next").value.trim(),
    depositable: document.getElementById("complete-depositable").value.trim(),
  };
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