(function () {
  const listEl = document.getElementById("opportunities-list");
  const createBtn = document.getElementById("create-opportunity-btn");
  const statuses = window.OPPORTUNITY_STATUSES || [];
  const expandedOpportunityLinks = new Set();
  const linksCache = new Map();
  let currentItems = [];
  const scoreFields = [
    ["importance_score", "重要性"],
    ["feedback_speed_score", "反馈速度"],
    ["revenue_score", "收入/成本"],
    ["asset_score", "资产化"],
    ["leverage_score", "杠杆"],
  ];

  if (!listEl) return;

  function advice(score) {
    if (score >= 20) return "优先推进";
    if (score >= 15) return "小范围验证";
    if (score >= 10) return "谨慎投入";
    return "暂停或删除";
  }

  function options(values, selected) {
    return values.map((v) => `<option value="${escapeAttr(v)}"${v === selected ? " selected" : ""}>${escapeHtml(v)}</option>`).join("");
  }

  function scoreInputs(item = {}) {
    return scoreFields.map(([key, label]) => `
      <label class="value-score-field">
        <span class="form-label">${label}</span>
        <input class="input value-score-input" type="number" min="0" max="5" id="op-${key}" value="${Number(item[key] || 0)}">
      </label>
    `).join("");
  }

  function formHtml(item = {}) {
    return `
      <div class="stacked-form value-form-grid">
        <div class="form-row">
          <label class="form-label">机会名称</label>
          <input id="op-name" class="input full-width" value="${escapeAttr(item.name || "")}" required>
        </div>
        <div class="form-row">
          <label class="form-label">状态</label>
          <select id="op-status" class="select full-width">${options(statuses, item.status || "待审计")}</select>
        </div>
        <div class="form-row"><label class="form-label">来源</label><input id="op-source" class="input full-width" value="${escapeAttr(item.source || "")}"></div>
        <div class="form-row"><label class="form-label">目标用户/对象</label><input id="op-target_user" class="input full-width" value="${escapeAttr(item.target_user || "")}"></div>
        <div class="form-row form-row-wide"><label class="form-label">机会描述</label><textarea id="op-description" class="textarea" rows="3">${escapeHtml(item.description || "")}</textarea></div>
        <div class="form-row form-row-wide"><label class="form-label">相关上下文</label><textarea id="op-related_context" class="textarea" rows="2">${escapeHtml(item.related_context || "")}</textarea></div>
        <div class="form-row"><label class="form-label">影响收入</label><textarea id="op-affects_revenue" class="textarea" rows="2">${escapeHtml(item.affects_revenue || "")}</textarea></div>
        <div class="form-row"><label class="form-label">影响成本</label><textarea id="op-affects_cost" class="textarea" rows="2">${escapeHtml(item.affects_cost || "")}</textarea></div>
        <div class="form-row"><label class="form-label">影响效率</label><textarea id="op-affects_efficiency" class="textarea" rows="2">${escapeHtml(item.affects_efficiency || "")}</textarea></div>
        <div class="form-row"><label class="form-label">影响体验</label><textarea id="op-affects_experience" class="textarea" rows="2">${escapeHtml(item.affects_experience || "")}</textarea></div>
        <div class="form-row"><label class="form-label">产品化可能</label><textarea id="op-productization_potential" class="textarea" rows="2">${escapeHtml(item.productization_potential || "")}</textarea></div>
        <div class="form-row"><label class="form-label">交易可能</label><textarea id="op-transaction_potential" class="textarea" rows="2">${escapeHtml(item.transaction_potential || "")}</textarea></div>
        <div class="form-row"><label class="form-label">7天MVP</label><textarea id="op-seven_day_mvp" class="textarea" rows="2">${escapeHtml(item.seven_day_mvp || "")}</textarea></div>
        <div class="form-row"><label class="form-label">案例资产可能</label><textarea id="op-case_asset_potential" class="textarea" rows="2">${escapeHtml(item.case_asset_potential || "")}</textarea></div>
        <div class="form-row"><label class="form-label">杠杆可能</label><textarea id="op-leverage_potential" class="textarea" rows="2">${escapeHtml(item.leverage_potential || "")}</textarea></div>
        <div class="form-row"><label class="form-label">下一步</label><textarea id="op-next_action" class="textarea" rows="2">${escapeHtml(item.next_action || "")}</textarea></div>
        <div class="form-row form-row-wide">
          <span class="form-label">五维评分</span>
          <div class="value-score-grid">${scoreInputs(item)}</div>
        </div>
      </div>
    `;
  }

  function readForm() {
    const payload = {
      name: document.getElementById("op-name").value.trim(),
      status: document.getElementById("op-status").value,
    };
    [
      "source", "target_user", "description", "related_context",
      "affects_revenue", "affects_cost", "affects_efficiency", "affects_experience",
      "productization_potential", "transaction_potential", "seven_day_mvp",
      "case_asset_potential", "leverage_potential", "next_action",
    ].forEach((key) => {
      payload[key] = document.getElementById(`op-${key}`).value.trim();
    });
    scoreFields.forEach(([key]) => {
      payload[key] = Number(document.getElementById(`op-${key}`).value || 0);
    });
    return payload;
  }

  function openEditor(item = null) {
    showAIModal({
      title: item ? `编辑机会 - ${item.name}` : "审计一个机会",
      bodyHtml: formHtml(item || {}),
      confirmLabel: item ? "保存机会" : "创建机会",
      onConfirm: async () => {
        const payload = readForm();
        if (item) {
          await apiRequest(`/api/opportunities/${item.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        } else {
          await apiRequest("/api/opportunities", { method: "POST", body: JSON.stringify(payload) });
        }
        showToast("机会已保存", "success");
        await load();
      },
    });
  }

  async function createExperiment(item) {
    const opportunityId = Number(item?.id);
    if (!Number.isFinite(opportunityId) || opportunityId <= 0) {
      showToast("缺少机会 ID，无法从机会创建实验", "error");
      return;
    }
    showAIModal({
      title: `从机会创建实验 - ${item.name}`,
      bodyHtml: `
        <div class="stacked-form value-form-grid">
          <input type="hidden" id="op-exp-opportunity-id" value="${opportunityId}">
          <div class="form-row">
            <label class="form-label">关联机会</label>
            <input class="input full-width" value="${escapeAttr(item.name || "")}" disabled>
          </div>
          <div class="form-row">
            <label class="form-label">实验名称</label>
            <input id="op-exp-name" class="input full-width" value="${escapeAttr(`${item.name} MVP实验`)}" required>
          </div>
          <div class="form-row form-row-wide">
            <label class="form-label">假设</label>
            <textarea id="op-exp-hypothesis" class="textarea" rows="2">${escapeHtml(item.description || item.next_action || "")}</textarea>
          </div>
          <div class="form-row">
            <label class="form-label">最小验证动作</label>
            <textarea id="op-exp-minimum-action" class="textarea" rows="2">${escapeHtml(item.seven_day_mvp || "")}</textarea>
          </div>
          <div class="form-row">
            <label class="form-label">测试对象</label>
            <input id="op-exp-test-target" class="input full-width" value="${escapeAttr(item.target_user || "")}">
          </div>
          <div class="form-row">
            <label class="form-label">成功标准</label>
            <textarea id="op-exp-success" class="textarea" rows="2">获得明确真实反馈或可观察结果</textarea>
          </div>
          <div class="form-row">
            <label class="form-label">失败标准</label>
            <textarea id="op-exp-failure" class="textarea" rows="2">7天内无真实反馈、无人使用或价值无法说明</textarea>
          </div>
        </div>
      `,
      confirmLabel: "创建实验",
      onConfirm: async () => {
        const linkedOpportunityId = Number(document.getElementById("op-exp-opportunity-id").value);
        const name = document.getElementById("op-exp-name").value.trim();
        if (!Number.isFinite(linkedOpportunityId) || linkedOpportunityId <= 0) {
          throw new Error("缺少机会 ID，无法从机会创建实验");
        }
        if (!name) {
          throw new Error("实验名称不能为空");
        }
        await apiRequest("/api/experiments", {
          method: "POST",
          body: JSON.stringify({
            opportunity_id: linkedOpportunityId,
            source_opportunity_id: linkedOpportunityId,
            require_opportunity: true,
            name,
            hypothesis: document.getElementById("op-exp-hypothesis").value.trim(),
            minimum_action: document.getElementById("op-exp-minimum-action").value.trim(),
            test_target: document.getElementById("op-exp-test-target").value.trim(),
            success_criteria: document.getElementById("op-exp-success").value.trim(),
            failure_criteria: document.getElementById("op-exp-failure").value.trim(),
            status: "设计中",
          }),
        });
        showToast("已从机会创建实验", "success");
        await load();
      },
    });
  }

  function disciplineForStatus(status) {
    if (status === "值得测试") {
      return { className: "value-success", text: "建议进入 7 天 MVP 验证。" };
    }
    if (status === "暂停" || status === "观察") {
      return { className: "value-pause", text: "暂停观察：等待更强反馈或更低成本测试方式。" };
    }
    if (status === "删除" || status === "停止") {
      return { className: "value-stop", text: "已停止：不再投入新资源，除非出现新证据。" };
    }
    if (status === "已转项目" || status === "已转化") {
      return { className: "value-success", text: "已转化：应沉淀为实验、案例或资产。" };
    }
    return null;
  }

  function renderDiscipline(status) {
    const discipline = disciplineForStatus(status);
    if (!discipline) return "";
    return `<div class="value-discipline ${discipline.className}">${escapeHtml(discipline.text)}</div>`;
  }

  function latestItem(items = []) {
    return items[0] || null;
  }

  function renderLatestLink(label, item, titleKey, metaParts = []) {
    if (!item) return "";
    const meta = metaParts.filter(Boolean).join(" · ");
    return `
      <div class="opportunity-link-latest">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(item[titleKey] || item.title || item.name || `#${item.id}`)}</strong>
        ${meta ? `<small>${escapeHtml(meta)}</small>` : ""}
      </div>
    `;
  }

  function renderLinks(links) {
    const counts = links.counts || {};
    const experiment = latestItem(links.experiments || []);
    const feedback = latestItem(links.feedback || []);
    const asset = latestItem(links.assets || []);
    const hasDownstream = Number(counts.experiments || 0) + Number(counts.feedback || 0) + Number(counts.assets || 0) > 0;
    if (!hasDownstream) {
      return `
        <div class="opportunity-link-expanded">
          <p class="form-hint">暂无下游链路，建议先创建实验验证该机会。</p>
        </div>
      `;
    }
    return `
      <div class="opportunity-link-expanded">
        <div class="value-link-counts">
          <span>实验 ${counts.experiments || 0}</span>
          <span>反馈 ${counts.feedback || 0}</span>
          <span>资产 ${counts.assets || 0}</span>
        </div>
        <div class="opportunity-link-latest-grid">
          ${renderLatestLink("最近实验", experiment, "name", [experiment?.status, experiment?.experiment_type])}
          ${renderLatestLink("最近反馈", feedback, "title", [feedback?.level, feedback?.source])}
          ${renderLatestLink("最近资产", asset, "title", [asset?.asset_level, asset?.asset_type])}
        </div>
        <div class="opportunity-link-jumps">
          <a href="/experiments">去实验页</a>
          <a href="/feedback">去反馈页</a>
          <a href="/assets">去资产页</a>
        </div>
      </div>
    `;
  }

  function hasContent(value) {
    return String(value || "").trim().length > 0;
  }

  function renderKernelTags(item) {
    const tags = [];
    if (item.target_user) tags.push([item.target_user, "muted"]);
    if (hasContent(item.seven_day_mvp)) tags.push(["有 7 天 MVP", "positive"]);
    if (hasContent(item.next_action)) tags.push(["有下一步", "muted"]);
    if (
      hasContent(item.affects_revenue) ||
      hasContent(item.affects_cost) ||
      hasContent(item.affects_efficiency) ||
      hasContent(item.affects_experience)
    ) {
      tags.push(["价值变化明确", "positive"]);
    }
    tags.push([renderMvpLayerLabel(item), "muted"]);
    if (!["已转项目", "已转化", "删除", "停止", "已归档"].includes(item.status || "")) {
      tags.push(["待实验验证", "warning"]);
    }
    const visible = tags.slice(0, 4);
    const hidden = tags.length - visible.length;
    return [
      ...visible.map(([label, tone]) => `<span class="kernel-tag kernel-tag--${tone}">${escapeHtml(label)}</span>`),
      hidden > 0 ? `<span class="kernel-tag kernel-tag--muted">+${hidden}</span>` : "",
    ].join("");
  }

  function renderMvpLayerLabel(item) {
    let label = "想法 MVP";
    if (hasContent(item.case_asset_potential)) {
      label = "资产 MVP 候选";
    } else if (hasContent(item.transaction_potential)) {
      label = "交易 MVP 候选";
    } else if (hasContent(item.target_user) && hasContent(item.next_action)) {
      label = "表达 MVP";
    }
    return label;
  }

  async function renderLinkPanel(el, item) {
    const panel = el.querySelector(".value-link-panel");
    const summary = el.querySelector(".value-link-summary");
    const button = el.querySelector(".btn-links");
    button.setAttribute("aria-expanded", "true");
    button.textContent = "收起链路";
    panel.hidden = false;
    if (linksCache.has(item.id)) {
      const links = linksCache.get(item.id);
      summary.textContent = `关联链路：实验 ${links.counts?.experiments || 0} · 反馈 ${links.counts?.feedback || 0} · 资产 ${links.counts?.assets || 0}`;
      panel.innerHTML = renderLinks(links);
      return;
    }
    panel.innerHTML = `<p class="form-hint">链路加载中...</p>`;
    try {
      const links = await apiRequest(`/api/opportunities/${item.id}/links`);
      linksCache.set(item.id, links);
      summary.textContent = `关联链路：实验 ${links.counts?.experiments || 0} · 反馈 ${links.counts?.feedback || 0} · 资产 ${links.counts?.assets || 0}`;
      panel.innerHTML = renderLinks(links);
    } catch (err) {
      panel.innerHTML = `<p class="form-hint">链路加载失败</p>`;
    }
  }

  function collapseLinkPanel(el, item) {
    const panel = el.querySelector(".value-link-panel");
    const button = el.querySelector(".btn-links");
    expandedOpportunityLinks.delete(item.id);
    button.setAttribute("aria-expanded", "false");
    button.textContent = "查看链路";
    panel.hidden = true;
    panel.innerHTML = "";
  }

  async function toggleLinks(el, item) {
    if (expandedOpportunityLinks.has(item.id)) {
      collapseLinkPanel(el, item);
      return;
    }
    expandedOpportunityLinks.add(item.id);
    await renderLinkPanel(el, item);
  }

  const AI_ACTIONS = {
    advance: { label: "AI推进", endpoint: "/api/ai/opportunity-advance" },
    redTeam: { label: "AI审查", endpoint: "/api/ai/opportunity-red-team" },
    audit: { label: "AI审计", endpoint: "/api/ai/opportunity-audit" },
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
          <a class="btn btn-sm btn-ghost" href="/experiments">去创建实验</a>
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
    const total = Number(item.total_score || 0);
    return `
      <article class="entity-card value-card" data-id="${item.id}">
        <div class="value-card-head">
          <div class="value-card-title-group">
            <div class="opportunity-card-title-row">
              <h3 class="entity-title opportunity-card-title">${escapeHtml(item.name)}</h3>
              <span class="opportunity-card-source-meta">${escapeHtml(item.source || "未记录来源")}</span>
            </div>
          </div>
          <div class="opportunity-card-badges">
            <span class="opportunity-status-badge">${escapeHtml(item.status || "待审计")}</span>
            <span class="value-score-badge">${total}</span>
            <div class="opportunity-card-tools">
              ${renderAiTools()}
            </div>
          </div>
        </div>
        <p class="value-card-summary">${formatText(item.description || item.related_context || "暂无描述")}</p>
        <div class="kernel-tag-row">
          <span class="kernel-tag kernel-tag--positive">${escapeHtml(advice(total))}</span>
          ${renderKernelTags(item)}
        </div>
        <div class="value-link-strip">
          <span class="value-link-summary">${expandedOpportunityLinks.has(item.id) && linksCache.has(item.id)
            ? `关联链路：实验 ${linksCache.get(item.id).counts?.experiments || 0} · 反馈 ${linksCache.get(item.id).counts?.feedback || 0} · 资产 ${linksCache.get(item.id).counts?.assets || 0}`
            : "关联链路：待查看"}</span>
          <button type="button" class="btn btn-sm btn-ghost btn-links" aria-expanded="${expandedOpportunityLinks.has(item.id) ? "true" : "false"}">${expandedOpportunityLinks.has(item.id) ? "收起链路" : "查看链路"}</button>
        </div>
        <div class="value-link-panel" hidden></div>
        <div class="entity-actions">
          <button type="button" class="btn btn-sm btn-ghost btn-create-exp">创建实验</button>
          <button type="button" class="btn btn-sm btn-ghost btn-edit">编辑</button>
          <button type="button" class="btn btn-sm btn-ghost btn-delete">删除</button>
        </div>
      </article>
    `;
  }

  async function load() {
    currentItems = await apiRequest("/api/opportunities");
    if (!currentItems.length) {
      listEl.innerHTML = `<div class="empty-state"><strong>暂无机会</strong>点击右上角开始审计第一个机会</div>`;
      return;
    }
    listEl.innerHTML = currentItems.map(card).join("");
    listEl.querySelectorAll(".value-card").forEach((el) => {
      const item = currentItems.find((row) => row.id === Number(el.dataset.id));
      if (item && expandedOpportunityLinks.has(item.id)) renderLinkPanel(el, item);
    });
  }

  listEl.addEventListener("click", async (event) => {
    const cardEl = event.target.closest(".value-card");
    if (!cardEl) return;
    const item = currentItems.find((row) => row.id === Number(cardEl.dataset.id));
    if (!item) return;
    if (event.target.closest(".btn-links")) {
      await toggleLinks(cardEl, item);
      return;
    }
    const aiButton = event.target.closest(".btn-ai-value");
    if (aiButton) {
      await runAiAction(item, aiButton.dataset.aiAction, aiButton);
      return;
    }
    if (event.target.closest(".btn-edit")) {
      openEditor(item);
      return;
    }
    if (event.target.closest(".btn-create-exp")) {
      createExperiment(item);
      return;
    }
    if (event.target.closest(".btn-delete")) {
      if (!confirm(`确定删除机会「${item.name}」？`)) return;
      await apiRequest(`/api/opportunities/${item.id}`, { method: "DELETE" });
      expandedOpportunityLinks.delete(item.id);
      linksCache.delete(item.id);
      showToast("机会已删除", "success");
      await load();
    }
  });

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
