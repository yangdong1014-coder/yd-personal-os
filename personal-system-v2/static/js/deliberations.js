(function () {
  const pageRoot = document.querySelector("[data-deliberation-page]");
  if (!pageRoot) return;

  const STATUS_META = {
    draft: { label: "思考中", tone: "draft", step: 2 },
    analyzed: { label: "已对抗", tone: "analyzed", step: 3 },
    decided: { label: "已决策", tone: "decided", step: 4 },
    reviewed: { label: "已复盘", tone: "reviewed", step: 5 },
  };
  const ANALYSIS_SECTIONS = [
    ["essence", "本质", "真正需要判断的矛盾、变量与约束"],
    ["counter_argument", "最强反方", "对当前判断最有力的攻击"],
    ["hidden_assumptions", "隐含假设", "尚未被意识到的前提"],
    ["missing_information", "缺失信息", "提高判断质量最需要补齐的事实"],
    ["validation", "最小验证", "尽快让现实给出反馈"],
  ];
  let relations = { projects: [], opportunities: [] };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[char]));
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, "&#096;");
  }

  function formatText(value) {
    return escapeHtml(value || "").replace(/\n/g, "<br>");
  }

  function summarize(value, maxLength = 130) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
  }

  function formatDate(value) {
    if (!value) return "—";
    const normalized = `${String(value).replace(" ", "T")}Z`;
    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function statusMeta(status) {
    return STATUS_META[status] || STATUS_META.draft;
  }

  async function loadRelations() {
    try {
      const [projects, opportunities] = await Promise.all([
        apiRequest("/api/projects"),
        apiRequest("/api/opportunities"),
      ]);
      relations = { projects: projects || [], opportunities: opportunities || [] };
    } catch (_error) {
      relations = { projects: [], opportunities: [] };
    }
    return relations;
  }

  function relationValue(item) {
    return item.related_type && item.related_id
      ? `${item.related_type}:${item.related_id}`
      : "";
  }

  function relationLabel(item) {
    if (!item.related_type || !item.related_id) return "未关联";
    const collection = item.related_type === "project"
      ? relations.projects
      : relations.opportunities;
    const match = collection.find((row) => row.id === Number(item.related_id));
    const typeLabel = item.related_type === "project" ? "项目" : "机会";
    return match ? `${typeLabel} · ${match.name}` : `${typeLabel} #${item.related_id}`;
  }

  function relationOptions(selected = "") {
    const projectOptions = relations.projects
      .map((item) => {
        const value = `project:${item.id}`;
        return `<option value="${value}"${value === selected ? " selected" : ""}>项目 · ${escapeHtml(item.name)}</option>`;
      })
      .join("");
    const opportunityOptions = relations.opportunities
      .map((item) => {
        const value = `opportunity:${item.id}`;
        return `<option value="${value}"${value === selected ? " selected" : ""}>机会 · ${escapeHtml(item.name)}</option>`;
      })
      .join("");
    return `
      <option value="">不关联</option>
      ${projectOptions ? `<optgroup label="项目">${projectOptions}</optgroup>` : ""}
      ${opportunityOptions ? `<optgroup label="机会">${opportunityOptions}</optgroup>` : ""}
    `;
  }

  function parseRelation(value) {
    if (!value) return { related_type: "", related_id: null };
    const [relatedType, rawId] = value.split(":");
    return {
      related_type: relatedType,
      related_id: Number(rawId) || null,
    };
  }

  function setBusy(button, busy, busyLabel) {
    if (!button) return;
    if (busy) {
      button.dataset.originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = busyLabel;
    } else {
      button.disabled = false;
      button.textContent = button.dataset.originalLabel || button.textContent;
    }
  }

  async function initList() {
    const listEl = document.getElementById("deliberations-list");
    const countEl = document.getElementById("delib-list-count");
    try {
      const items = await apiRequest("/api/deliberations");
      countEl.textContent = `${items.length} 次推演`;
      if (!items.length) {
        listEl.innerHTML = `
          <div class="empty-state delib-empty-state">
            <strong>还没有推演</strong>
            从一个真实、正在影响行动的问题开始。
            <a href="/deliberations/new" class="btn btn-sm">开始第一次推演</a>
          </div>
        `;
        return;
      }
      listEl.innerHTML = items.map((item) => {
        const meta = statusMeta(item.status);
        return `
          <article class="delib-list-card" data-id="${item.id}">
            <a href="/deliberations/${item.id}" class="delib-card-main">
              <div class="delib-card-topline">
                <span class="delib-status delib-status--${meta.tone}">${meta.label}</span>
                <span class="delib-card-time">${formatDate(item.created_at)}</span>
              </div>
              <h3>${escapeHtml(item.title)}</h3>
              <p>${escapeHtml(summarize(item.problem))}</p>
              <div class="delib-card-foot">
                <span>${item.reviewed ? "已用现实结果复盘" : "闭环尚未完成"}</span>
                <span aria-hidden="true">打开推演 →</span>
              </div>
            </a>
            <button type="button" class="delib-card-delete" aria-label="删除推演">×</button>
          </article>
        `;
      }).join("");
      listEl.querySelectorAll(".delib-card-delete").forEach((button) => {
        button.addEventListener("click", async () => {
          const card = button.closest(".delib-list-card");
          const item = items.find((row) => row.id === Number(card.dataset.id));
          if (!confirm(`确定删除推演「${item.title}」？此操作不可撤销。`)) return;
          try {
            await apiRequest(`/api/deliberations/${item.id}`, { method: "DELETE" });
            showToast("推演已删除", "success");
            await initList();
          } catch (error) {
            showToast(error.message, "error");
          }
        });
      });
    } catch (error) {
      countEl.textContent = "读取失败";
      listEl.innerHTML = `<div class="empty-state"><strong>无法读取推演</strong>${escapeHtml(error.message)}</div>`;
    }
  }

  function readInitialForm(prefix = "delib") {
    const relation = parseRelation(document.getElementById(`${prefix}-related`).value);
    const titleInput = document.getElementById(`${prefix}-title`);
    return {
      title: titleInput ? titleInput.value.trim() : "",
      problem: document.getElementById(`${prefix}-problem`).value.trim(),
      context: document.getElementById(`${prefix}-context`).value.trim(),
      initial_judgment: document.getElementById(`${prefix}-initial-judgment`).value.trim(),
      reasoning: document.getElementById(`${prefix}-reasoning`).value.trim(),
      assumptions: document.getElementById(`${prefix}-assumptions`).value.trim(),
      ...relation,
    };
  }

  async function initNew() {
    await loadRelations();
    const relationSelect = document.getElementById("delib-related");
    relationSelect.innerHTML = relationOptions();
    const form = document.getElementById("deliberation-new-form");
    const button = document.getElementById("delib-create-btn");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      setBusy(button, true, "正在保存…");
      try {
        const created = await apiRequest("/api/deliberations", {
          method: "POST",
          body: JSON.stringify(readInitialForm()),
        });
        if (window.DELIBERATION_AI_ENABLED) {
          setBusy(button, true, "AI 正在对抗…");
          try {
            await apiRequest(`/api/deliberations/${created.id}/analyze`, {
              method: "POST",
              body: "{}",
            });
            window.location.href = `/deliberations/${created.id}`;
            return;
          } catch (_error) {
            window.location.href = `/deliberations/${created.id}?analysis=retry`;
            return;
          }
        }
        window.location.href = `/deliberations/${created.id}?saved=1`;
      } catch (error) {
        showToast(error.message, "error");
        setBusy(button, false);
      }
    });
  }

  function progressHtml(item) {
    const currentStep = statusMeta(item.status).step;
    const steps = ["我的起点", "AI 审计", "决策与行动", "现实复盘"];
    return `
      <ol class="delib-progress" aria-label="推演进度">
        ${steps.map((label, index) => {
          const step = index + 1;
          const state = step < currentStep ? "complete" : step === currentStep ? "current" : "future";
          return `
            <li class="delib-progress-step is-${state}">
              <span>${String(step).padStart(2, "0")}</span>
              <strong>${label}</strong>
            </li>
          `;
        }).join("")}
      </ol>
    `;
  }

  function readOnlyBlock(label, value, className = "") {
    return `
      <div class="delib-read-block${className ? ` ${className}` : ""}">
        <span>${label}</span>
        <p>${formatText(value || "—")}</p>
      </div>
    `;
  }

  function draftEditorHtml(item) {
    return `
      <form id="delib-draft-form" class="delib-stage-form delib-draft-editor">
        <div class="form-row">
          <label class="delib-thinking-label" for="detail-problem">你现在真正需要判断什么？</label>
          <textarea id="detail-problem" class="textarea delib-question-input" rows="4" required>${escapeHtml(item.problem)}</textarea>
        </div>
        <div class="form-row delib-secondary-field">
          <label class="form-label" for="detail-context">背景 <span class="delib-optional">可选</span></label>
          <textarea id="detail-context" class="textarea" rows="2">${escapeHtml(item.context || "")}</textarea>
        </div>
        <div class="form-row">
          <label class="delib-thinking-label" for="detail-initial-judgment">你现在倾向怎么判断？</label>
          <textarea id="detail-initial-judgment" class="textarea" rows="4" required>${escapeHtml(item.initial_judgment)}</textarea>
        </div>
        <div class="form-row">
          <label class="delib-thinking-label delib-thinking-label--secondary" for="detail-reasoning">为什么？ <span class="delib-optional">可选</span></label>
          <textarea id="detail-reasoning" class="textarea" rows="3">${escapeHtml(item.reasoning)}</textarea>
        </div>
        <div class="form-row">
          <label class="delib-thinking-label" for="detail-assumptions">这个判断成立，需要哪些事情是真的？ <span class="delib-optional">可选</span></label>
          <p class="form-hint delib-field-intro">找出 1–3 个一旦不成立，你的判断就可能改变的假设。</p>
          <textarea id="detail-assumptions" class="textarea" rows="3">${escapeHtml(item.assumptions)}</textarea>
        </div>
        <details class="delib-more-info">
          <summary>更多信息</summary>
          <div class="delib-more-info-fields">
            <div class="form-row">
              <label class="form-label" for="detail-title">推演标题</label>
              <input id="detail-title" class="input full-width" maxlength="120" value="${escapeAttr(item.title)}">
            </div>
            <div class="form-row">
              <label class="form-label" for="detail-related">关联项目或机会 <span class="delib-optional">可选</span></label>
              <select id="detail-related" class="select full-width">${relationOptions(relationValue(item))}</select>
            </div>
          </div>
        </details>
        <div class="delib-form-actions">
          <button type="submit" class="btn" id="delib-save-draft">保存修改</button>
        </div>
      </form>
    `;
  }

  function initialStageHtml(item) {
    if (item.status === "draft") return draftEditorHtml(item);
    return `
      <div class="delib-question-card">
        <span class="delib-context-label">问题</span>
        <p class="delib-question-text">${formatText(item.problem)}</p>
        ${item.context ? `<p class="delib-context-text">${formatText(item.context)}</p>` : ""}
        <span class="delib-relation-chip">${escapeHtml(relationLabel(item))}</span>
      </div>
      <div class="delib-judgment-grid">
        ${readOnlyBlock("当时，我这样判断", item.initial_judgment, "delib-read-block--primary")}
        ${readOnlyBlock("为什么", item.reasoning)}
        ${readOnlyBlock("成立所需的关键假设", item.assumptions)}
      </div>
    `;
  }

  function analysisStageHtml(item) {
    const analysis = item.ai_analysis || {};
    if (!analysis.essence) {
      return `
        <div class="delib-ai-pending">
          <div>
            <span class="section-kicker">轮到 AI 挑战</span>
            <h3>让最强反方进入房间</h3>
            <p>AI 将检查本质、逻辑漏洞、隐含假设和最低成本验证方法，但不会替你做最终决定。</p>
          </div>
          <button type="button" id="delib-analyze-btn" class="btn delib-primary-action"
                  ${window.DELIBERATION_AI_ENABLED ? "" : "disabled"}>
            ${window.DELIBERATION_AI_ENABLED ? "开始 AI 对抗" : "AI 未配置"}
          </button>
        </div>
      `;
    }
    return `
      <section class="section-card delib-analysis-report">
        <div class="section-header-row delib-analysis-report-head">
          <div>
            <h2>思考审计</h2>
            <p class="form-hint section-hint">用反方、假设与事实缺口检查我的判断</p>
          </div>
        </div>
        <div class="delib-analysis-sections">
        ${ANALYSIS_SECTIONS.map(([key, title, note], index) => `
          <section class="delib-analysis-section${key === "validation" ? " delib-analysis-section--validation" : ""}">
            <div class="delib-analysis-head">
              <span>${String(index + 1).padStart(2, "0")}</span>
              <div>
                <h3>${title}</h3>
                <p>${note}</p>
              </div>
            </div>
            <div class="delib-analysis-content">${formatText(analysis[key])}</div>
          </section>
        `).join("")}
        </div>
      </section>
    `;
  }

  function decisionStageHtml(item) {
    if (!item.ai_analysis?.essence) {
      return `<div class="delib-locked-stage">完成 AI 对抗后，才能重新做最终判断。</div>`;
    }
    if (item.status === "reviewed") {
      return `
        <div class="delib-judgment-grid">
          ${readOnlyBlock("现在，我这样判断", item.final_judgment, "delib-read-block--primary")}
          ${readOnlyBlock("所以我决定", item.decision)}
          ${readOnlyBlock("为什么", item.decision_reasoning)}
          ${readOnlyBlock("下一步最小动作", item.next_action, "delib-read-block--action")}
        </div>
      `;
    }
    return `
      <form id="delib-decision-form" class="delib-stage-form">
        <div class="form-row">
          <label class="delib-thinking-label" for="final-judgment">现在，你怎么判断？</label>
          <textarea id="final-judgment" class="textarea" rows="4" required>${escapeHtml(item.final_judgment || "")}</textarea>
        </div>
        <div class="form-row">
          <label class="delib-thinking-label" for="decision">所以你决定做什么？</label>
          <textarea id="decision" class="textarea" rows="3" required>${escapeHtml(item.decision || "")}</textarea>
        </div>
        <div class="form-row">
          <label class="delib-thinking-label delib-thinking-label--secondary" for="decision-reasoning">为什么？</label>
          <textarea id="decision-reasoning" class="textarea" rows="3" required>${escapeHtml(item.decision_reasoning || "")}</textarea>
        </div>
        <div class="form-row delib-next-action-field">
          <label class="delib-thinking-label" for="next-action">下一步最小动作</label>
          <textarea id="next-action" class="textarea" rows="3" required>${escapeHtml(item.next_action || "")}</textarea>
          <p class="form-hint">用最低成本验证这次判断。</p>
        </div>
        <div class="delib-form-actions">
          <button type="submit" class="btn" id="delib-save-decision">保存最终判断</button>
        </div>
      </form>
    `;
  }

  function reviewStageHtml(item) {
    if (!["decided", "reviewed"].includes(item.status)) {
      return `<div class="delib-locked-stage">完成最终判断并行动后，再回来记录现实反馈。</div>`;
    }
    if (item.status === "reviewed") {
      return `
        <div class="delib-review-grid">
          ${readOnlyBlock("后来发生了什么", item.actual_result, "delib-read-block--primary")}
          ${readOnlyBlock("哪里判断对了", item.judgment_accuracy)}
          ${readOnlyBlock("哪里判断错了", item.judgment_error)}
          ${readOnlyBlock("真正关键的变量", item.key_variable)}
          ${readOnlyBlock("如果重新来一次", item.lesson)}
        </div>
        <div class="delib-principle">
          <span>留下一条原则</span>
          <blockquote>${formatText(item.principle)}</blockquote>
        </div>
      `;
    }
    return `
      <form id="delib-review-form" class="delib-stage-form">
        <div class="form-row">
          <label class="delib-thinking-label" for="actual-result">后来发生了什么？</label>
          <textarea id="actual-result" class="textarea" rows="4" required>${escapeHtml(item.actual_result || "")}</textarea>
        </div>
        <div class="delib-two-column">
          <div class="form-row">
            <label class="delib-thinking-label delib-thinking-label--secondary" for="judgment-accuracy">回头看，哪里判断对了？</label>
            <textarea id="judgment-accuracy" class="textarea" rows="4" required>${escapeHtml(item.judgment_accuracy || "")}</textarea>
          </div>
          <div class="form-row">
            <label class="delib-thinking-label delib-thinking-label--secondary" for="judgment-error">哪里判断错了？</label>
            <textarea id="judgment-error" class="textarea" rows="4" required>${escapeHtml(item.judgment_error || "")}</textarea>
          </div>
        </div>
        <div class="form-row">
          <label class="delib-thinking-label" for="key-variable">真正关键的变量是什么？</label>
          <textarea id="key-variable" class="textarea" rows="3" required>${escapeHtml(item.key_variable || "")}</textarea>
        </div>
        <div class="form-row">
          <label class="delib-thinking-label" for="lesson">如果重新来一次？</label>
          <textarea id="lesson" class="textarea" rows="3" required>${escapeHtml(item.lesson || "")}</textarea>
        </div>
        <div class="form-row delib-principle-field">
          <label class="delib-thinking-label" for="principle">留下一条原则</label>
          <textarea id="principle" class="textarea" rows="3" required>${escapeHtml(item.principle || "")}</textarea>
        </div>
        <div class="delib-form-actions">
          <button type="submit" class="btn" id="delib-save-review">完成现实复盘</button>
        </div>
      </form>
    `;
  }

  function timelineStage(number, eyebrow, title, body, state = "") {
    return `
      <section class="delib-timeline-stage ${state}">
        <div class="delib-timeline-marker"><span>${number}</span></div>
        <div class="delib-timeline-body">
          <div class="delib-stage-heading">
            <span class="section-kicker">${eyebrow}</span>
            <h2>${title}</h2>
          </div>
          ${body}
        </div>
      </section>
    `;
  }

  function renderDetail(item) {
    const meta = statusMeta(item.status);
    pageRoot.innerHTML = `
      <header class="page-header delib-detail-header">
        <div class="page-header-row">
          <div>
            <h1 class="page-title">${escapeHtml(item.title)}</h1>
            <p class="page-subtitle">创建于 ${formatDate(item.created_at)} · 最近更新 ${formatDate(item.updated_at)}</p>
          </div>
          <div class="header-actions delib-detail-actions">
            <span class="delib-status delib-status--${meta.tone}">${meta.label}</span>
            <a href="/deliberations" class="btn btn-sm btn-ghost">返回推演</a>
            <button type="button" id="delib-delete-btn" class="btn btn-sm btn-ghost">删除</button>
          </div>
        </div>
      </header>

      ${progressHtml(item)}

      <div class="delib-timeline">
        ${timelineStage("01", "问题 → 当时的判断", "我当时是怎么想的", initialStageHtml(item), "is-initial")}
        ${timelineStage("02", "AI 对抗", "一份思考审计", analysisStageHtml(item), item.ai_analysis?.essence ? "is-complete" : "is-current")}
        ${timelineStage("03", "最终决策 → 行动", "现在，我怎么判断", decisionStageHtml(item), item.status === "analyzed" ? "is-current" : "")}
        ${timelineStage("04", "结果 → 原则", "现实后来给了什么反馈", reviewStageHtml(item), item.status === "decided" ? "is-current" : item.status === "reviewed" ? "is-complete" : "")}
      </div>
    `;
    wireDetailEvents(item);
  }

  function wireDetailEvents(item) {
    document.getElementById("delib-delete-btn")?.addEventListener("click", async () => {
      if (!confirm(`确定删除推演「${item.title}」？此操作不可撤销。`)) return;
      try {
        await apiRequest(`/api/deliberations/${item.id}`, { method: "DELETE" });
        showToast("推演已删除", "success");
        window.location.href = "/deliberations";
      } catch (error) {
        showToast(error.message, "error");
      }
    });

    document.getElementById("delib-draft-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = document.getElementById("delib-save-draft");
      setBusy(button, true, "保存中…");
      try {
        const updated = await apiRequest(`/api/deliberations/${item.id}`, {
          method: "PATCH",
          body: JSON.stringify(readInitialForm("detail")),
        });
        showToast("初始判断已保存", "success");
        renderDetail(updated);
      } catch (error) {
        showToast(error.message, "error");
        setBusy(button, false);
      }
    });

    document.getElementById("delib-analyze-btn")?.addEventListener("click", async () => {
      const button = document.getElementById("delib-analyze-btn");
      setBusy(button, true, "AI 正在对抗…");
      try {
        const updated = await apiRequest(`/api/deliberations/${item.id}/analyze`, {
          method: "POST",
          body: "{}",
        });
        showToast("AI 对抗已完成", "success");
        renderDetail(updated);
      } catch (error) {
        showToast(error.message, "error");
        setBusy(button, false);
      }
    });

    document.getElementById("delib-decision-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = document.getElementById("delib-save-decision");
      setBusy(button, true, "保存中…");
      try {
        const updated = await apiRequest(`/api/deliberations/${item.id}/decision`, {
          method: "PATCH",
          body: JSON.stringify({
            final_judgment: document.getElementById("final-judgment").value.trim(),
            decision: document.getElementById("decision").value.trim(),
            decision_reasoning: document.getElementById("decision-reasoning").value.trim(),
            next_action: document.getElementById("next-action").value.trim(),
          }),
        });
        showToast("最终判断已保存", "success");
        renderDetail(updated);
      } catch (error) {
        showToast(error.message, "error");
        setBusy(button, false);
      }
    });

    document.getElementById("delib-review-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = document.getElementById("delib-save-review");
      setBusy(button, true, "保存中…");
      try {
        const updated = await apiRequest(`/api/deliberations/${item.id}/review`, {
          method: "PATCH",
          body: JSON.stringify({
            actual_result: document.getElementById("actual-result").value.trim(),
            judgment_accuracy: document.getElementById("judgment-accuracy").value.trim(),
            judgment_error: document.getElementById("judgment-error").value.trim(),
            key_variable: document.getElementById("key-variable").value.trim(),
            lesson: document.getElementById("lesson").value.trim(),
            principle: document.getElementById("principle").value.trim(),
          }),
        });
        showToast("现实反馈已沉淀", "success");
        renderDetail(updated);
      } catch (error) {
        showToast(error.message, "error");
        setBusy(button, false);
      }
    });
  }

  async function initDetail() {
    const id = Number(pageRoot.dataset.deliberationId);
    try {
      const [, item] = await Promise.all([
        loadRelations(),
        apiRequest(`/api/deliberations/${id}`),
      ]);
      renderDetail(item);
      const params = new URLSearchParams(window.location.search);
      if (params.get("analysis") === "retry") {
        showToast("推演已保存，但 AI 对抗未完成。请检查配置后重试。", "error", 6500);
      } else if (params.get("saved") === "1") {
        showToast("推演已保存，配置 AI 后可继续对抗。", "success");
      }
    } catch (error) {
      pageRoot.innerHTML = `
        <div class="empty-state delib-empty-state">
          <strong>无法打开这次推演</strong>
          ${escapeHtml(error.message)}
          <a href="/deliberations" class="btn btn-sm">返回推演列表</a>
        </div>
      `;
    }
  }

  const page = pageRoot.dataset.deliberationPage;
  if (page === "list") initList();
  if (page === "new") initNew();
  if (page === "detail") initDetail();
})();
