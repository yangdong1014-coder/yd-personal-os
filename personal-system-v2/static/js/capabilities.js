document.addEventListener("DOMContentLoaded", () => {
  const panels = document.querySelectorAll(".module-panel");
  const diagnoseBtn = document.getElementById("ai-diagnose-btn");
  const overviewEl = document.getElementById("capability-overview");
  const overviewMetaEl = document.getElementById("capability-overview-meta");
  const detailPanel = document.getElementById("capability-detail");
  const detailTitle = document.getElementById("capability-detail-title");
  const detailSubtitle = document.getElementById("capability-detail-subtitle");
  const detailStatus = document.getElementById("capability-detail-status");
  const detailBody = document.getElementById("capability-detail-body");
  const practiceRegion = document.getElementById("capability-practice-region");
  const trainingTitle = document.getElementById("capability-training-title");
  const levelTypes = window.LEVEL_TYPES || [];

  if (!panels.length) return;

  let capabilitySummary = null;
  let practicePathsByModule = {};
  let selectedPracticeStepIds = {};
  let practiceEditModule = "";
  let practiceEditDraft = [];
  let activeModule = panels[0]?.dataset.module || "";
  const today = new Date().toISOString().slice(0, 10);
  panels.forEach((panel) => {
    const dateInput = panel.querySelector(".entry-date");
    if (dateInput) dateInput.value = today;
  });
  syncTrainingPanel(activeModule);

  async function loadProjects() {
    const projects = await apiRequest("/api/projects");
    panels.forEach((panel) => {
      const select = panel.querySelector(".entry-project");
      if (!select) return;
      const current = select.value;
      select.innerHTML = '<option value="">无</option>';
      projects.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = `${p.goal_name} / ${p.name}`;
        opt.textContent = opt.value;
        select.appendChild(opt);
      });
      if (current) select.value = current;
    });
  }

  function statusClass(status) {
    if (status === "有优势") return "capability-status--strong";
    if (status === "积累中") return "capability-status--growing";
    return "capability-status--weak";
  }

  function formatDate(value) {
    if (!value) return "暂无";
    return String(value).slice(0, 10);
  }

  function metricHtml(label, value) {
    return `
      <span class="capability-card-metric">
        <strong>${escapeHtml(value)}</strong>
        <span>${escapeHtml(label)}</span>
      </span>`;
  }

  function renderCapabilityOverview(summary) {
    if (!overviewEl) return;
    const modules = summary.modules || [];
    const overview = summary.overview || {};
    if (overviewMetaEl) {
      overviewMetaEl.textContent = `${overview.tagged_assets || 0}/${overview.total_assets || 0} 个资产已关联能力`;
    }
    if (!modules.length) {
      overviewEl.innerHTML = `
        <div class="empty-state">
          <strong>暂无能力数据</strong>
          资产库与训练记录为空
        </div>`;
      return;
    }

    overviewEl.innerHTML = modules
      .map((item, index) => {
        const active = item.module === activeModule ? " active" : "";
        return `
          <button type="button" class="capability-overview-card ${statusClass(item.status)}${active}" data-module="${escapeAttr(item.module)}">
            <span class="capability-card-topline">
              <span><span class="module-num">${String(index + 1).padStart(2, "0")}</span>${escapeHtml(item.module)}</span>
              <span class="capability-status-badge ${statusClass(item.status)}">${escapeHtml(item.status)}</span>
            </span>
            <span class="capability-card-layer">${escapeHtml(item.layer)}</span>
            <span class="capability-card-metrics">
              ${metricHtml("关联资产", item.asset_count)}
              ${metricHtml("可用/成熟", item.usable_asset_count)}
              ${metricHtml("复用", item.reuse_total)}
            </span>
            <span class="capability-card-footer">最近资产 ${escapeHtml(formatDate(item.recent_asset_updated_at))}</span>
          </button>`;
      })
      .join("");

    overviewEl.querySelectorAll(".capability-overview-card").forEach((card) => {
      card.addEventListener("click", () => {
        selectCapabilityModule(card.dataset.module);
      });
    });

    const fallbackModule = modules[0]?.module || "";
    const preferred =
      activeModule && modules.some((item) => item.module === activeModule)
        ? activeModule
        : fallbackModule;
    if (preferred) selectCapabilityModule(preferred);
  }

  function selectCapabilityModule(module) {
    if (!capabilitySummary || !module) return;
    if (practiceEditModule && practiceEditModule !== module) {
      practiceEditModule = "";
      practiceEditDraft = [];
    }
    activeModule = module;
    document.querySelectorAll(".capability-overview-card").forEach((card) => {
      card.classList.toggle("active", card.dataset.module === module);
    });
    const item = (capabilitySummary.modules || []).find((m) => m.module === module);
    renderCapabilityDetail(item);
    renderCurrentPracticePath(module);
    syncTrainingPanel(module);
    loadEntriesForModule(module).catch((err) => console.error(err));
    if (!Object.prototype.hasOwnProperty.call(practicePathsByModule, module)) {
      loadPracticePath(module)
        .then(() => renderCurrentPracticePath(module))
        .catch((err) => console.error(err));
    }
  }

  function currentSummaryItem(module = activeModule) {
    return (capabilitySummary?.modules || []).find((item) => item.module === module);
  }

  function renderCurrentCapabilityDetail(module = activeModule) {
    const item = currentSummaryItem(module);
    if (item) renderCapabilityDetail(item);
  }

  function renderCurrentPracticePath(module = activeModule) {
    renderPracticePath(module);
  }

  function syncTrainingPanel(module) {
    panels.forEach((panel) => {
      const isActive = panel.dataset.module === module;
      panel.hidden = !isActive;
      panel.classList.toggle("module-panel-active", isActive);
    });
    if (trainingTitle) {
      trainingTitle.textContent = module ? `${module}训练记录` : "训练记录";
    }
  }

  function renderCapabilityDetail(item) {
    if (!item || !detailPanel || !detailBody) return;
    detailPanel.hidden = false;
    detailTitle.textContent = item.module;
    detailSubtitle.textContent = `${item.layer} · 建议沉淀 ${item.recommended_asset_type}`;
    detailStatus.textContent = item.status;
    detailStatus.className = `capability-status-badge ${statusClass(item.status)}`;

    detailBody.innerHTML = `
      <div class="capability-detail-stats">
        ${detailStatHtml("关联资产", item.asset_count)}
        ${detailStatHtml("可用/成熟", item.usable_asset_count)}
        ${detailStatHtml("成熟", item.mature_asset_count)}
        ${detailStatHtml("复用次数", item.reuse_total)}
        ${detailStatHtml("训练记录", item.entry_count)}
        ${detailStatHtml("最近资产", formatDate(item.recent_asset_updated_at))}
      </div>
      <div class="capability-detail-grid">
        ${distributionHtml("资产类型分布", item.asset_type_distribution)}
        ${distributionHtml("成熟度分布", item.maturity_distribution)}
        ${assetListHtml("最近沉淀资产", item.recent_assets, "暂无关联资产")}
        ${assetListHtml("高复用资产", item.high_reuse_assets, "暂无复用记录")}
        <section class="capability-next-panel">
          <h3>下一步进阶建议</h3>
          <p>${escapeHtml(item.next_action)}</p>
          <span class="tag">建议资产：${escapeHtml(item.recommended_asset_type)}</span>
        </section>
      </div>`;
  }

  function renderPracticePath(module) {
    if (!practiceRegion) return;
    practiceRegion.innerHTML = practicePathHtml(module);
    bindPracticePathEvents(module);
  }

  function detailStatHtml(label, value) {
    return `
      <span class="capability-detail-stat">
        <strong>${escapeHtml(value)}</strong>
        <span>${escapeHtml(label)}</span>
      </span>`;
  }

  function distributionHtml(title, rows = []) {
    const visibleRows = rows.filter((row) => row.count > 0 || title === "成熟度分布");
    const max = Math.max(...visibleRows.map((row) => row.count), 1);
    const body = visibleRows.length
      ? visibleRows
          .map((row) => {
            const width = Math.max(4, Math.round((row.count / max) * 100));
            return `
              <div class="capability-distribution-row">
                <span>${escapeHtml(row.name)}</span>
                <span class="capability-distribution-bar"><i style="width:${width}%"></i></span>
                <strong>${escapeHtml(row.count)}</strong>
              </div>`;
          })
          .join("")
      : '<p class="history-empty">暂无数据</p>';
    return `
      <section class="capability-analysis-panel">
        <h3>${escapeHtml(title)}</h3>
        <div class="capability-distribution">${body}</div>
      </section>`;
  }

  function assetListHtml(title, assets = [], emptyText) {
    const body = assets.length
      ? assets
          .map(
            (asset) => `
              <article class="capability-mini-item">
                <div>
                  <strong>${escapeHtml(asset.title)}</strong>
                  <span>${escapeHtml(asset.asset_type)} · ${escapeHtml(asset.maturity_label)} · 复用 ${escapeHtml(asset.reuse_count)}</span>
                </div>
                <time>${escapeHtml(formatDate(asset.updated_at))}</time>
              </article>`
          )
          .join("")
      : `<p class="history-empty">${escapeHtml(emptyText)}</p>`;
    return `
      <section class="capability-analysis-panel">
        <h3>${escapeHtml(title)}</h3>
        <div class="capability-mini-list">${body}</div>
      </section>`;
  }

  function practiceStepsForModule(module) {
    return practicePathsByModule[module] || [];
  }

  function selectedPracticeStep(module) {
    const steps = practiceStepsForModule(module);
    if (!steps.length) return null;
    const selectedId = selectedPracticeStepIds[module];
    return steps.find((step) => step.id === selectedId) || steps[0];
  }

  function practicePathHtml(module) {
    if (practiceEditModule === module) {
      return practiceEditHtml(module);
    }
    const steps = practiceStepsForModule(module);
    const selected = selectedPracticeStep(module);
    return `
      <section class="capability-practice-panel">
        <div class="capability-practice-head">
          <div>
            <h3>推荐练习方式 / 训练路径</h3>
          </div>
          <button type="button" class="btn btn-sm btn-ghost" id="practice-edit-btn">编辑训练路径</button>
        </div>
        ${
          steps.length
            ? `<div class="practice-step-grid">
                ${steps
                  .map((step) => practiceStepCardHtml(step, selected?.id === step.id))
                  .join("")}
              </div>
              <div class="practice-step-detail">
                <span class="module-num">${String(selected.step_order).padStart(2, "0")}</span>
                <div>
                  <h4>${escapeHtml(selected.title)}</h4>
                  <p>${formatText(selected.detail || selected.description)}</p>
                </div>
              </div>`
            : `<div class="empty-state"><strong>暂无训练路径</strong>可以编辑并新增第一步</div>`
        }
      </section>`;
  }

  function practiceStepCardHtml(step, active) {
    return `
      <button type="button" class="practice-step-card${active ? " active" : ""}" data-step-id="${escapeAttr(step.id)}">
        <span class="practice-step-order">${String(step.step_order).padStart(2, "0")}</span>
        <strong>${escapeHtml(step.title)}</strong>
        <span>${escapeHtml(step.description || "暂无简短说明")}</span>
      </button>`;
  }

  function practiceEditHtml(module) {
    const draft = practiceEditDraft.length ? practiceEditDraft : practiceStepsForModule(module);
    const stepsHtml = draft.length
      ? draft
          .map((step, index) => {
            const key = practiceDraftKey(step, index);
            return `
              <article class="practice-edit-step" data-step-id="${escapeAttr(step.id || "")}" data-step-key="${escapeAttr(key)}" data-client-id="${escapeAttr(step.client_id || "")}">
                <div class="practice-edit-step-head">
                  <span class="practice-step-order">${String(index + 1).padStart(2, "0")}</span>
                  <button type="button" class="btn btn-sm btn-ghost practice-delete-draft" data-step-key="${escapeAttr(key)}">删除</button>
                </div>
                <div class="form-row">
                  <label class="form-label">步骤名称</label>
                  <input type="text" class="input full-width practice-edit-title" value="${escapeAttr(step.title || "")}">
                </div>
                <div class="form-row">
                  <label class="form-label">简短说明</label>
                  <textarea class="textarea practice-edit-description" rows="2">${escapeHtml(step.description || "")}</textarea>
                </div>
                <div class="form-row">
                  <label class="form-label">详细说明</label>
                  <textarea class="textarea practice-edit-detail" rows="4">${escapeHtml(step.detail || "")}</textarea>
                </div>
              </article>`;
          })
          .join("")
      : '<p class="history-empty">暂无步骤</p>';
    return `
      <section class="capability-practice-panel capability-practice-panel-edit">
        <div class="capability-practice-head">
          <div>
            <h3>编辑训练路径</h3>
            <p class="form-hint">${escapeHtml(module)}</p>
          </div>
          <div class="practice-edit-actions">
            <button type="button" class="btn btn-sm btn-ghost" id="practice-add-step">新增步骤</button>
            <button type="button" class="btn btn-sm btn-ghost" id="practice-cancel-edit">取消</button>
            <button type="button" class="btn btn-sm" id="practice-save-edit">保存</button>
          </div>
        </div>
        <div class="practice-edit-list">${stepsHtml}</div>
      </section>`;
  }

  function practiceDraftKey(step, index = 0) {
    if (step.id) return `id-${step.id}`;
    return step.client_id || `new-${index}`;
  }

  function readPracticeEditDraft() {
    return Array.from(document.querySelectorAll(".practice-edit-step")).map(
      (item, index) => {
        const id = parseInt(item.dataset.stepId, 10);
        return {
          id: Number.isFinite(id) && id > 0 ? id : null,
          client_id: item.dataset.clientId || item.dataset.stepKey || "",
          step_order: index + 1,
          title: item.querySelector(".practice-edit-title")?.value.trim() || "",
          description:
            item.querySelector(".practice-edit-description")?.value.trim() || "",
          detail: item.querySelector(".practice-edit-detail")?.value.trim() || "",
        };
      }
    );
  }

  function bindPracticePathEvents(module) {
    const root = practiceRegion || detailBody;
    root.querySelectorAll(".practice-step-card").forEach((card) => {
      card.addEventListener("click", () => {
        const stepId = parseInt(card.dataset.stepId, 10);
        if (stepId) selectedPracticeStepIds[module] = stepId;
        renderCurrentPracticePath(module);
      });
    });

    root.querySelector("#practice-edit-btn")?.addEventListener("click", () => {
      practiceEditModule = module;
      practiceEditDraft = practiceStepsForModule(module).map((step) => ({ ...step }));
      renderCurrentPracticePath(module);
    });

    root.querySelector("#practice-cancel-edit")?.addEventListener("click", () => {
      practiceEditModule = "";
      practiceEditDraft = [];
      renderCurrentPracticePath(module);
    });

    root.querySelector("#practice-add-step")?.addEventListener("click", () => {
      practiceEditDraft = readPracticeEditDraft();
      practiceEditDraft.push({
        id: null,
        client_id: `new-${Date.now()}`,
        step_order: practiceEditDraft.length + 1,
        title: "",
        description: "",
        detail: "",
      });
      renderCurrentPracticePath(module);
    });

    root.querySelectorAll(".practice-delete-draft").forEach((button) => {
      button.addEventListener("click", () => {
        if (!window.confirm("确定删除这个训练步骤？保存后将不可恢复。")) {
          return;
        }
        const key = button.dataset.stepKey;
        practiceEditDraft = readPracticeEditDraft().filter(
          (step, index) => practiceDraftKey(step, index) !== key
        );
        renderCurrentPracticePath(module);
      });
    });

    root.querySelector("#practice-save-edit")?.addEventListener("click", async () => {
      await savePracticePath(module);
    });
  }

  async function savePracticePath(module) {
    const draft = readPracticeEditDraft();
    if (draft.some((step) => !step.title)) {
      showToast("步骤名称不能为空", "error");
      return;
    }

    const original = practiceStepsForModule(module);
    const draftIds = new Set(draft.map((step) => step.id).filter(Boolean));
    try {
      for (const step of original) {
        if (!draftIds.has(step.id)) {
          await apiRequest(`/api/capabilities/practice-steps/${step.id}`, {
            method: "DELETE",
          });
        }
      }

      for (const [index, step] of draft.entries()) {
        const payload = {
          title: step.title,
          description: step.description,
          detail: step.detail,
          step_order: index + 1,
        };
        if (step.id) {
          await apiRequest(`/api/capabilities/practice-steps/${step.id}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
          });
        } else {
          await apiRequest(
            `/api/capabilities/${encodeURIComponent(module)}/practice-steps`,
            {
              method: "POST",
              body: JSON.stringify(payload),
            }
          );
        }
      }

      practiceEditModule = "";
      practiceEditDraft = [];
      await loadPracticePath(module);
      await loadCapabilitySummary();
      renderCurrentPracticePath(module);
      showToast("训练路径已保存", "success");
    } catch (err) {
      showToast(err.message || "训练路径保存失败", "error");
    }
  }

  async function loadCapabilitySummary() {
    capabilitySummary = await apiRequest("/api/capabilities/summary");
    renderCapabilityOverview(capabilitySummary);
    return capabilitySummary;
  }

  async function loadPracticePaths() {
    practicePathsByModule = await apiRequest("/api/capabilities/practice-paths");
    return practicePathsByModule;
  }

  async function loadPracticePath(module) {
    practicePathsByModule[module] = await apiRequest(
      `/api/capabilities/${encodeURIComponent(module)}/practice-path`
    );
    return practicePathsByModule[module];
  }

  async function refreshCapabilityData() {
    await loadCapabilitySummary();
    await loadEntriesForModule(activeModule);
  }

  async function loadEntriesForModule(module = activeModule) {
    if (!module) return [];
    const entries = await apiRequest(
      `/api/capability-entries?module=${encodeURIComponent(module)}`
    );
    const panel = Array.from(panels).find((item) => item.dataset.module === module);
    const list = panel?.querySelector(".history-list");
    if (list) renderHistory(list, entries);
    return entries;
  }

  function renderHistory(container, entries) {
    container.innerHTML = "";

    if (!entries.length) {
      container.innerHTML = '<p class="history-empty">暂无记录</p>';
      return;
    }

    entries.forEach((entry) => {
      const item = document.createElement("article");
      item.className = "history-item";
      item.innerHTML = `
        <div class="history-item-head">
          <span class="history-date">${escapeHtml(entry.entry_date)}</span>
          <span class="tag">${escapeHtml(entry.level_type)}</span>
          <button type="button" class="btn btn-sm btn-ghost btn-delete-entry">删除</button>
        </div>
        <p class="history-content">${formatText(entry.content)}</p>
        ${
          entry.source_project
            ? `<p class="history-meta">来源：${escapeHtml(entry.source_project)}</p>`
            : ""
        }
      `;

      item.querySelector(".btn-delete-entry").addEventListener("click", async () => {
        if (
          !window.confirm(
            `确定删除 ${entry.entry_date} 的能力记录？此操作不可撤销。`
          )
        ) {
          return;
        }
        try {
          await apiRequest(`/api/capability-entries/${entry.id}`, {
            method: "DELETE",
          });
          showToast("能力记录已删除", "success");
          await refreshCapabilityData();
        } catch (err) {
          showToast(err.message, "error");
        }
      });

      container.appendChild(item);
    });
  }

  async function handleAIDiagnose(button) {
    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "诊断中…";

    try {
      const result = await apiRequest("/api/ai/diagnose-capabilities", {
        method: "POST",
        body: JSON.stringify({}),
      });

      showAIViewModal({
        title: "AI 能力诊断",
        bodyHtml: buildAIDiagnoseHtml(result),
      });
    } catch (err) {
      showToast(err.message || "AI 诊断失败", "error");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  async function handleAIAttribute(panel, button) {
    const module = panel.dataset.module;
    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "归因中…";

    try {
      const draft = await apiRequest("/api/ai/attribute-capability", {
        method: "POST",
        body: JSON.stringify({ module }),
      });

      showAIModal({
        title: `AI 进展归因 · ${module}`,
        bodyHtml: buildCapabilityAttributeHtml(draft, levelTypes),
        confirmLabel: "确认保存",
        onConfirm: async () => {
          const data = readCapabilityAttributeForm();
          if (!data.content) {
            throw new Error("进展内容不能为空");
          }
          await apiRequest("/api/capability-entries", {
            method: "POST",
            body: JSON.stringify({
              module,
              entry_date: panel.querySelector(".entry-date").value || today,
              content: data.content,
              source_project: data.source_project,
              level_type: data.level_type,
            }),
          });
          panel.querySelector(".entry-content").value = "";
          await refreshCapabilityData();
        },
      });
    } catch (err) {
      showToast(err.message || "AI 归因失败", "error");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  if (diagnoseBtn) {
    diagnoseBtn.addEventListener("click", () => handleAIDiagnose(diagnoseBtn));
  }

  panels.forEach((panel) => {
    const form = panel.querySelector(".entry-form");
    const attrBtn = panel.querySelector(".btn-attribute");

    if (attrBtn) {
      attrBtn.addEventListener("click", () => handleAIAttribute(panel, attrBtn));
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const module = panel.dataset.module;

      const payload = {
        module,
        entry_date: panel.querySelector(".entry-date").value,
        content: panel.querySelector(".entry-content").value,
        source_project: panel.querySelector(".entry-project").value,
        level_type: panel.querySelector(".entry-level").value,
      };

      try {
        await apiRequest("/api/capability-entries", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        panel.querySelector(".entry-content").value = "";
        showToast("能力记录已保存", "success");
        await refreshCapabilityData();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });

  Promise.all([
    loadProjects(),
    loadPracticePaths().then(() => loadCapabilitySummary()),
  ]).catch((err) => console.error(err));
});

function buildAIDiagnoseHtml(result) {
  const focusModules = Array.isArray(result.focus_modules) ? result.focus_modules : [];
  return `
    <div class="ai-briefing capability-ai-briefing">
      <p class="ai-briefing-text">${formatMultiline(result.summary)}</p>
      ${aiListHtml("当前能力优势", result.strengths)}
      ${aiListHtml("当前能力短板", result.weaknesses)}
      ${aiListHtml("记录多但资产少", result.record_asset_gaps)}
      ${aiListHtml("资产多但复用少", result.low_reuse_modules)}
      ${aiListHtml("失衡提示", result.imbalances)}
      ${aiListHtml("建议沉淀资产", result.suggested_asset_types)}
      ${
        focusModules.length
          ? `<p class="ai-briefing-focus"><strong>优先训练：</strong>${escapeHtml(focusModules.join("、"))}</p>`
          : ""
      }
      ${
        result.focus_module
          ? `<p class="ai-briefing-focus"><strong>关注模块：</strong>${escapeHtml(result.focus_module)}${result.focus_action ? ` — ${escapeHtml(result.focus_action)}` : ""}</p>`
          : ""
      }
    </div>`;
}

function aiListHtml(title, items) {
  if (!Array.isArray(items) || !items.length) return "";
  return `
    <h4 class="ai-briefing-subtitle">${escapeHtml(title)}</h4>
    <ul class="ai-briefing-list">
      ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
    </ul>`;
}

function formatText(text) {
  return escapeHtml(text || "").replace(/\n/g, "<br>");
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
