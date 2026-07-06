(function () {
  const listEl = document.getElementById("experiments-list");
  const createBtn = document.getElementById("create-experiment-btn");
  const types = window.EXPERIMENT_TYPES || [];
  const statuses = window.EXPERIMENT_STATUSES || [];
  let opportunities = [];

  if (!listEl) return;

  function options(values, selected) {
    return values.map((v) => `<option value="${escapeAttr(v)}"${v === selected ? " selected" : ""}>${escapeHtml(v)}</option>`).join("");
  }

  function opportunityOptions(selected) {
    return `<option value="">不关联机会</option>${opportunities.map((item) => `<option value="${item.id}"${Number(selected) === item.id ? " selected" : ""}>${escapeHtml(item.name)}</option>`).join("")}`;
  }

  function formHtml(item = {}) {
    return `
      <div class="stacked-form value-form-grid">
        <div class="form-row"><label class="form-label">实验名称</label><input id="exp-name" class="input full-width" value="${escapeAttr(item.name || "")}" required></div>
        <div class="form-row"><label class="form-label">关联机会</label><select id="exp-opportunity_id" class="select full-width">${opportunityOptions(item.opportunity_id)}</select></div>
        <div class="form-row"><label class="form-label">实验类型</label><select id="exp-experiment_type" class="select full-width">${options(types, item.experiment_type || "结果型MVP")}</select></div>
        <div class="form-row"><label class="form-label">状态</label><select id="exp-status" class="select full-width">${options(statuses, item.status || "设计中")}</select></div>
        ${textArea("hypothesis", "假设", item)}
        ${textArea("minimum_action", "最小验证动作", item)}
        ${textArea("test_target", "测试对象/目标", item)}
        ${textArea("feedback_source", "反馈来源", item)}
        ${textArea("validation_period", "验证周期", item)}
        ${textArea("success_criteria", "成功标准", item)}
        ${textArea("failure_criteria", "失败标准", item)}
        ${textArea("progress", "进展", item)}
        ${textArea("real_feedback", "真实反馈", item)}
        ${textArea("data_result", "数据结果", item)}
        ${textArea("next_decision", "下一步：放大/调整/暂停/删除/转项目", item)}
        ${textArea("review_conclusion", "复盘结论", item)}
      </div>
    `;
  }

  function textArea(key, label, item) {
    return `<div class="form-row"><label class="form-label">${label}</label><textarea id="exp-${key}" class="textarea" rows="2">${escapeHtml(item[key] || "")}</textarea></div>`;
  }

  function readForm() {
    const payload = {
      name: document.getElementById("exp-name").value.trim(),
      opportunity_id: document.getElementById("exp-opportunity_id").value || null,
      experiment_type: document.getElementById("exp-experiment_type").value,
      status: document.getElementById("exp-status").value,
    };
    [
      "hypothesis", "minimum_action", "test_target", "feedback_source",
      "validation_period", "success_criteria", "failure_criteria", "progress",
      "real_feedback", "data_result", "next_decision", "review_conclusion",
    ].forEach((key) => {
      payload[key] = document.getElementById(`exp-${key}`).value.trim();
    });
    return payload;
  }

  function openEditor(item = null) {
    showAIModal({
      title: item ? `编辑实验 - ${item.name}` : "启动一个实验",
      bodyHtml: formHtml(item || {}),
      confirmLabel: item ? "保存实验" : "创建实验",
      onConfirm: async () => {
        const payload = readForm();
        if (item) {
          await apiRequest(`/api/experiments/${item.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        } else {
          await apiRequest("/api/experiments", { method: "POST", body: JSON.stringify(payload) });
        }
        showToast("实验已保存", "success");
        await load();
      },
    });
  }

  async function createFeedback(item) {
    await apiRequest("/api/feedback", {
      method: "POST",
      body: JSON.stringify({
        related_type: "experiment",
        related_id: item.id,
        title: `${item.name} 的真实反馈`,
        source: "使用者反馈",
        level: item.data_result ? "L4 产生可量化结果" : "L2 同事/使用者觉得有价值",
        content: item.real_feedback || item.review_conclusion || "",
        evidence: item.data_result || "",
        next_action: item.next_decision || "",
      }),
    });
    showToast("已生成反馈记录", "success");
  }

  function disciplineForExperiment(item) {
    const status = item.status || "";
    if (["停止", "已停止", "失败", "未验证", "已暂停"].includes(status)) {
      return { className: "value-stop", text: "实验已停止：请记录失败原因并沉淀复盘。" };
    }
    if (status === "进行中" && item.failure_criteria) {
      return { className: "value-warning", text: "请按失败标准判断是否继续投入。" };
    }
    if (["已完成", "成功", "已验证"].includes(status)) {
      return { className: "value-success", text: "实验已完成：建议沉淀反馈或案例资产。" };
    }
    return null;
  }

  function renderExperimentDiscipline(item) {
    const rows = [];
    if (item.success_criteria) rows.push(["成功标准", item.success_criteria]);
    if (item.failure_criteria) rows.push(["失败标准 / 停止条件", item.failure_criteria]);
    const discipline = disciplineForExperiment(item);
    if (!rows.length && !discipline) return "";
    return `
      <div class="value-discipline-stack">
        ${discipline ? `<div class="value-discipline ${discipline.className}">${escapeHtml(discipline.text)}</div>` : ""}
        ${rows.map(([label, value]) => `
          <div class="value-discipline value-warning">
            <strong>${escapeHtml(label)}：</strong>${formatText(value)}
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderLinks(links) {
    const feedback = (links.feedback || [])[0];
    const asset = (links.assets || [])[0];
    const feedbackCount = Number(links.counts?.feedback || 0);
    const assetCount = Number(links.counts?.assets || 0);
    if (!feedbackCount && !assetCount) {
      return `<p class="experiment-link-empty">暂无下游反馈或案例资产，建议先生成反馈验证实验结果。</p>`;
    }
    return `
      <div class="experiment-link-summary">
        ${feedback ? `
          <div class="experiment-link-summary-item">
            <span>最新反馈</span>
            <strong>${escapeHtml(feedback.title || `#${feedback.id}`)}</strong>
            <small>${escapeHtml([feedback.level, `反馈 ${feedbackCount}`].filter(Boolean).join(" · "))}</small>
          </div>
        ` : ""}
        ${asset ? `
          <div class="experiment-link-summary-item">
            <span>最新案例资产</span>
            <strong>${escapeHtml(asset.title || `#${asset.id}`)}</strong>
            <small>${escapeHtml([asset.asset_level, `资产 ${assetCount}`].filter(Boolean).join(" · "))}</small>
          </div>
        ` : ""}
      </div>
    `;
  }

  function hasContent(value) {
    return String(value || "").trim().length > 0;
  }

  function renderKernelTags(item) {
    const tags = [];
    if (hasContent(item.hypothesis)) tags.push(["有假设", "positive"]);
    if (hasContent(item.minimum_action)) tags.push(["有最小行动", "positive"]);
    if (hasContent(item.failure_criteria)) tags.push(["有失败标准", "warning"]);
    if (hasContent(item.success_criteria)) tags.push(["有成功标准", "muted"]);
    if (hasContent(item.next_decision)) tags.push(["有下一决策", "muted"]);
    return tags.map(([label, tone]) => `<span class="kernel-tag kernel-tag--${tone}">${label}</span>`).join("");
  }

  function mvpLayerLabel(item) {
    const type = item.experiment_type || "";
    let label = "表达 MVP";
    if (type === "交易型MVP") {
      label = "交易 MVP";
    } else if (type === "反证型MVP") {
      label = "想法 MVP";
    } else if (type === "功能型MVP") {
      label = "流程 MVP";
    } else if (type === "结果型MVP" && (hasContent(item.real_feedback) || hasContent(item.data_result))) {
      label = "流程 MVP";
    } else if (hasContent(item.minimum_action) && hasContent(item.failure_criteria)) {
      label = "流程 MVP";
    }
    return label;
  }

  function renderExperimentMetaTags(item) {
    return `
      <div class="experiment-meta-tags">
        ${item.real_feedback ? `<span class="kernel-tag kernel-tag--positive">已有反馈</span>` : ""}
        ${item.data_result ? `<span class="kernel-tag kernel-tag--positive">有结果数据</span>` : ""}
        ${renderKernelTags(item)}
      </div>
    `;
  }

  function renderExperimentTitleMeta(item) {
    return `
      <div class="experiment-title-meta">
        <span>${escapeHtml(item.status || "设计中")}</span>
        <span>${escapeHtml(item.experiment_type || "结果型MVP")}</span>
        <span>来源机会：${escapeHtml(item.opportunity_name || "无")}</span>
      </div>
    `;
  }

  async function toggleLinks(el, item) {
    const panel = el.querySelector(".value-link-panel");
    const summary = el.querySelector(".value-link-summary");
    const button = el.querySelector(".btn-links");
    const expanded = button.getAttribute("aria-expanded") === "true";
    if (expanded) {
      button.setAttribute("aria-expanded", "false");
      button.textContent = "查看链路";
      panel.hidden = true;
      return;
    }
    button.setAttribute("aria-expanded", "true");
    button.textContent = "收起链路";
    panel.hidden = false;
    panel.innerHTML = `<p class="form-hint">链路加载中…</p>`;
    try {
      const links = await apiRequest(`/api/experiments/${item.id}/links`);
      summary.textContent = `来源机会：${links.opportunity?.name || "无"} · 反馈 ${links.counts?.feedback || 0} · 案例资产 ${links.counts?.assets || 0}`;
      panel.innerHTML = renderLinks(links);
    } catch (err) {
      panel.innerHTML = `<p class="form-hint">链路加载失败</p>`;
    }
  }

  const AI_ACTIONS = {
    advance: { label: "AI推进", endpoint: "/api/ai/experiment-advance" },
    redTeam: { label: "AI审查", endpoint: "/api/ai/experiment-red-team" },
    audit: { label: "AI审计", endpoint: "/api/ai/experiment-audit" },
  };

  function renderAiTools() {
    return `
      <div class="value-ai-tool-row" aria-label="AI 工具">
        <span class="value-ai-tool-label">AI</span>
        <button type="button" class="btn btn-sm btn-ai btn-ai-value" data-ai-action="advance">AI推进</button>
        <button type="button" class="btn btn-sm btn-ai btn-ai-value" data-ai-action="redTeam">AI审查</button>
        <button type="button" class="btn btn-sm btn-ai btn-ai-value" data-ai-action="audit">AI审计</button>
      </div>
    `;
  }

  function renderAiResult(result) {
    const sections = (result.sections || [])
      .map((section) => `
        <section class="ai-result-section">
          <h4>${escapeHtml(section.title)}</h4>
          <ul>${(section.items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        </section>
      `)
      .join("");
    return `
      <div class="ai-result-panel">
        <p class="ai-result-summary">${formatText(result.summary || "")}</p>
        ${sections}
        <div class="ai-result-next">
          <strong>下一步</strong>
          <p>${formatText(result.next_action || result.recommendation || "")}</p>
        </div>
        ${result.recommendation ? `<p class="ai-result-recommendation">${formatText(result.recommendation)}</p>` : ""}
        <div class="ai-result-actions">
          <button type="button" class="btn btn-sm btn-ghost btn-copy-ai-result">复制建议</button>
        </div>
      </div>
    `;
  }

  function aiResultText(result) {
    const parts = [result.title, result.summary];
    (result.sections || []).forEach((section) => {
      parts.push(section.title);
      (section.items || []).forEach((item) => parts.push(`- ${item}`));
    });
    parts.push(`下一步：${result.next_action || result.recommendation || ""}`);
    return parts.filter(Boolean).join("\n");
  }

  async function runAiAction(item, actionKey, button) {
    const config = AI_ACTIONS[actionKey];
    if (!config) return;
    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "AI处理中…";
    try {
      const result = await apiRequest(config.endpoint, {
        method: "POST",
        body: JSON.stringify({ id: item.id }),
      });
      showAIViewModal({
        title: result.title || `${config.label}结果`,
        bodyHtml: renderAiResult(result),
      });
      setTimeout(() => {
        const copyBtn = document.querySelector(".btn-copy-ai-result");
        copyBtn?.addEventListener("click", async () => {
          await navigator.clipboard?.writeText(aiResultText(result));
          showToast("AI建议已复制", "success");
        });
      }, 0);
    } catch (err) {
      showToast(err.message || `${config.label}失败，请检查模型配置或稍后重试`, "error");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  function card(item) {
    return `
      <article class="entity-card value-card" data-id="${item.id}">
        <div class="value-card-head">
          <div class="experiment-title-wrap">
            <h3 class="entity-title">${escapeHtml(item.name)}</h3>
            ${renderExperimentTitleMeta(item)}
          </div>
          <div class="experiment-card-tools">
            ${renderAiTools()}
          </div>
        </div>
        <p class="value-card-summary">${formatText(item.hypothesis || item.minimum_action || "暂无实验假设")}</p>
        ${renderExperimentDiscipline(item)}
        ${renderExperimentMetaTags(item)}
        <div class="value-link-strip">
          <span class="value-link-summary">关联链路：待查看</span>
          <button type="button" class="btn btn-sm btn-ghost btn-links" aria-expanded="false">查看链路</button>
        </div>
        <div class="value-link-panel" hidden></div>
        <div class="entity-actions">
          <button type="button" class="btn btn-sm btn-ghost btn-edit">编辑</button>
          <button type="button" class="btn btn-sm btn-ghost btn-feedback">生成反馈</button>
          <button type="button" class="btn btn-sm btn-ghost btn-delete">删除</button>
        </div>
      </article>
    `;
  }

  async function load() {
    const [items, opps] = await Promise.all([
      apiRequest("/api/experiments"),
      apiRequest("/api/opportunities"),
    ]);
    opportunities = opps;
    if (!items.length) {
      listEl.innerHTML = `<div class="empty-state"><strong>暂无实验</strong>从机会创建实验，或直接启动一次 MVP</div>`;
      return;
    }
    listEl.innerHTML = items.map(card).join("");
    listEl.querySelectorAll(".value-card").forEach((el) => {
      const item = items.find((row) => row.id === Number(el.dataset.id));
      el.querySelector(".btn-links").addEventListener("click", () => toggleLinks(el, item));
      el.querySelectorAll(".btn-ai-value").forEach((button) => {
        button.addEventListener("click", () => runAiAction(item, button.dataset.aiAction, button));
      });
      el.querySelector(".btn-edit").addEventListener("click", () => openEditor(item));
      el.querySelector(".btn-feedback").addEventListener("click", () => createFeedback(item));
      el.querySelector(".btn-delete").addEventListener("click", async () => {
        if (!confirm(`确定删除实验「${item.name}」？`)) return;
        await apiRequest(`/api/experiments/${item.id}`, { method: "DELETE" });
        showToast("实验已删除", "success");
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
