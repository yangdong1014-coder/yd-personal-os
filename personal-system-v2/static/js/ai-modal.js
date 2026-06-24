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
      showToast(err.message || "操作失败", "error");
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
            ${buildTaskContextLine(t.project_name, t.goal_name)}
            <span class="form-hint muted-relation">状态 · ${escapeHtml(t.status)}</span>
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

function buildAssetClassifyHtml(draft, assetTypes, capabilityModules) {
  const typeOptions = assetTypes
    .map(
      (t) =>
        `<option value="${escapeHtml(t)}"${t === draft.asset_type ? " selected" : ""}>${escapeHtml(t)}</option>`
    )
    .join("");
  const tagOptions = capabilityModules
    .map((m) => {
      const checked = (draft.capability_tags || []).includes(m) ? " checked" : "";
      return `
        <label class="tag-option">
          <input type="checkbox" class="classify-tag" value="${escapeHtml(m)}"${checked}>
          <span>${escapeHtml(m)}</span>
        </label>
      `;
    })
    .join("");

  return `
    <div class="stacked-form">
      ${draft.reason ? `<p class="form-hint">${escapeHtml(draft.reason)}</p>` : ""}
      <div class="form-row">
        <label class="form-label">资产类型</label>
        <select id="classify-type" class="select">${typeOptions}</select>
      </div>
      <div class="form-row">
        <span class="form-label">关联能力模块</span>
        <div class="tag-picker">${tagOptions}</div>
      </div>
    </div>
  `;
}

function readAssetClassifyForm() {
  return {
    asset_type: document.getElementById("classify-type").value,
    capability_tags: Array.from(
      document.querySelectorAll(".classify-tag:checked")
    ).map((el) => el.value),
  };
}

function buildAssetEditHtml(draft, fieldSchemas = {}) {
  const assetType = draft.asset_type || "本质洞察";
  const schema = fieldSchemas[assetType] || [];
  const fields = draft.fields || {};
  const fieldHtml = schema
    .map((field) => {
      const value = escapeHtml(fields[field.key] || "");
      return `
        <div class="form-row">
          <label class="form-label">${escapeHtml(field.label)}</label>
          <textarea class="textarea draft-field" data-key="${escapeAttr(field.key)}" rows="3">${value}</textarea>
        </div>`;
    })
    .join("");

  return `
    <div class="stacked-form">
      <div class="form-row">
        <label class="form-label">标题</label>
        <input type="text" id="draft-title" class="input full-width" value="${escapeAttr(draft.title || "")}">
      </div>
      <div class="form-row">
        <label class="form-label">资产类型</label>
        <input type="text" id="draft-asset-type" class="input full-width" value="${escapeAttr(assetType)}" readonly>
      </div>
      ${fieldHtml || `
        <div class="form-row">
          <label class="form-label">触发情境</label>
          <textarea id="draft-trigger" class="textarea" rows="2">${escapeHtml(draft.trigger_context || "")}</textarea>
        </div>
        <div class="form-row">
          <label class="form-label">核心内容</label>
          <textarea id="draft-content" class="textarea" rows="8">${escapeHtml(draft.core_content || "")}</textarea>
        </div>`}
    </div>
  `;
}

function readAssetEditForm(fieldSchemas = {}) {
  const title = document.getElementById("draft-title")?.value.trim() || "";
  const assetType = document.getElementById("draft-asset-type")?.value.trim() || "";
  const fieldInputs = document.querySelectorAll(".draft-field");
  if (fieldInputs.length) {
    const fields = {};
    fieldInputs.forEach((el) => {
      fields[el.dataset.key] = el.value.trim();
    });
    return { title, asset_type: assetType, fields };
  }
  return {
    title,
    asset_type: assetType,
    trigger_context: document.getElementById("draft-trigger")?.value.trim() || "",
    core_content: document.getElementById("draft-content")?.value.trim() || "",
  };
}

function buildCapabilityAttributeHtml(draft, levelTypes) {
  const levelOptions = levelTypes
    .map(
      (l) =>
        `<option value="${escapeHtml(l)}"${l === draft.level_type ? " selected" : ""}>${escapeHtml(l)}</option>`
    )
    .join("");

  return `
    <div class="stacked-form">
      ${draft.reason ? `<p class="form-hint">${escapeHtml(draft.reason)}</p>` : ""}
      <div class="form-row">
        <label class="form-label">进展内容</label>
        <textarea id="attr-content" class="textarea" rows="4">${escapeHtml(draft.content || "")}</textarea>
      </div>
      <div class="form-row">
        <label class="form-label">层级判断</label>
        <select id="attr-level" class="select">${levelOptions}</select>
      </div>
      <div class="form-row">
        <label class="form-label">来源项目</label>
        <input type="text" id="attr-project" class="input full-width" value="${escapeAttr(draft.source_project || "")}">
      </div>
    </div>
  `;
}

function readCapabilityAttributeForm() {
  return {
    content: document.getElementById("attr-content").value.trim(),
    level_type: document.getElementById("attr-level").value,
    source_project: document.getElementById("attr-project").value.trim(),
  };
}

function formatMultiline(text) {
  return escapeHtml(text || "").replace(/\n/g, "<br>");
}

function buildWeeklyReviewHtml(draft) {
  return `
    <div class="stacked-form">
      <p class="form-hint">聚合 ${draft.source_count || 0} 条日复盘 → 每周复盘草稿</p>
      <div class="form-row">
        <label class="form-label">复盘日期</label>
        <input type="date" id="weekly-date" class="input" value="${escapeAttr(draft.review_date || "")}">
      </div>
      <div class="form-row">
        <label class="form-label">本周做了什么</label>
        <textarea id="weekly-what-done" class="textarea" rows="4">${escapeHtml(draft.what_done || "")}</textarea>
      </div>
      <div class="form-row">
        <label class="form-label">卡住了什么</label>
        <textarea id="weekly-stuck" class="textarea" rows="3">${escapeHtml(draft.stuck || "")}</textarea>
      </div>
      <div class="form-row">
        <label class="form-label">下一步调整</label>
        <textarea id="weekly-next" class="textarea" rows="3">${escapeHtml(draft.next_adjust || "")}</textarea>
      </div>
      <div class="form-row">
        <label class="form-label">可沉淀内容</label>
        <textarea id="weekly-depositable" class="textarea" rows="3">${escapeHtml(draft.depositable || "")}</textarea>
      </div>
    </div>
  `;
}

function readWeeklyReviewForm() {
  return {
    review_date: document.getElementById("weekly-date").value,
    type: "每周",
    what_done: document.getElementById("weekly-what-done").value.trim(),
    stuck: document.getElementById("weekly-stuck").value.trim(),
    next_adjust: document.getElementById("weekly-next").value.trim(),
    depositable: document.getElementById("weekly-depositable").value.trim(),
  };
}

function buildDispatchActionsHtml(data) {
  const markHtml = (data.mark_today || [])
    .map(
      (item) => `
    <label class="project-draft-item">
      <input type="checkbox" class="dispatch-mark-check" data-task-id="${item.task_id}" checked>
      <div class="project-draft-fields">
        <strong class="recommend-name">标记今日推进 · ${escapeHtml(item.name)}</strong>
        ${buildTaskContextLine(item.project_name, item.goal_name)}
        ${item.reason ? `<span class="form-hint">${escapeHtml(item.reason)}</span>` : ""}
      </div>
    </label>
  `
    )
    .join("");

  const newHtml = (data.new_tasks || [])
    .map(
      (item) => `
    <label class="project-draft-item">
      <input type="checkbox" class="dispatch-new-check" data-project-id="${item.project_id}" checked>
      <div class="project-draft-fields">
        <input type="text" class="input full-width dispatch-new-name" data-project-id="${item.project_id}" value="${escapeAttr(item.name)}">
        ${buildTaskContextLine(item.project_name, item.goal_name)}
        ${item.reason ? `<span class="form-hint">${escapeHtml(item.reason)}</span>` : ""}
      </div>
    </label>
  `
    )
    .join("");

  return `
    <div class="stacked-form project-draft-list">
      ${markHtml ? `<h4 class="ai-briefing-subtitle">标记今日推进</h4>${markHtml}` : ""}
      ${newHtml ? `<h4 class="ai-briefing-subtitle">新建任务</h4>${newHtml}` : ""}
    </div>
  `;
}

function readSelectedDispatchActions() {
  const markToday = [];
  document.querySelectorAll(".dispatch-mark-check:checked").forEach((el) => {
    const id = parseInt(el.dataset.taskId, 10);
    if (id) markToday.push(id);
  });

  const newTasks = [];
  document.querySelectorAll(".dispatch-new-check:checked").forEach((el) => {
    const projectId = parseInt(el.dataset.projectId, 10);
    const input = document.querySelector(
      `.dispatch-new-name[data-project-id="${projectId}"]`
    );
    const name = input?.value.trim();
    if (projectId && name) {
      newTasks.push({ project_id: projectId, name });
    }
  });

  return { markToday, newTasks };
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