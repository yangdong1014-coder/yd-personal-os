(function () {
  const listEl = document.getElementById("opportunities-list");
  const createBtn = document.getElementById("create-opportunity-btn");
  const statuses = window.OPPORTUNITY_STATUSES || [];
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

  function linkList(title, items, labelKey) {
    if (!items?.length) return `<div class="value-link-row"><strong>${title}</strong><span>暂无关联</span></div>`;
    return `
      <div class="value-link-row">
        <strong>${title}</strong>
        <ul>${items.map((row) => `<li>${escapeHtml(row[labelKey] || row.title || row.name || `#${row.id}`)}</li>`).join("")}</ul>
      </div>
    `;
  }

  function renderLinks(links) {
    return `
      <div class="value-link-counts">
        <span>实验 ${links.counts?.experiments || 0}</span>
        <span>反馈 ${links.counts?.feedback || 0}</span>
        <span>案例资产 ${links.counts?.assets || 0}</span>
      </div>
      ${linkList("实验", links.experiments || [], "name")}
      ${linkList("反馈", links.feedback || [], "title")}
      ${linkList("案例资产", links.assets || [], "title")}
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
      const links = await apiRequest(`/api/opportunities/${item.id}/links`);
      summary.textContent = `关联链路：实验 ${links.counts?.experiments || 0} · 反馈 ${links.counts?.feedback || 0} · 案例资产 ${links.counts?.assets || 0}`;
      panel.innerHTML = renderLinks(links);
    } catch (err) {
      panel.innerHTML = `<p class="form-hint">链路加载失败</p>`;
    }
  }

  function card(item) {
    const total = Number(item.total_score || 0);
    return `
      <article class="entity-card value-card" data-id="${item.id}">
        <div class="value-card-head">
          <div>
            <h3 class="entity-title">${escapeHtml(item.name)}</h3>
            <p class="entity-meta">${escapeHtml(item.status)} · ${escapeHtml(item.source || "未记录来源")}</p>
          </div>
          <span class="value-score-badge">${total}</span>
        </div>
        <p class="value-card-summary">${formatText(item.description || item.related_context || "暂无描述")}</p>
        <div class="value-card-meta">
          <span class="tag">${escapeHtml(advice(total))}</span>
          ${item.target_user ? `<span class="tag">${escapeHtml(item.target_user)}</span>` : ""}
        </div>
        <div class="value-link-strip">
          <span class="value-link-summary">关联链路：待查看</span>
          <button type="button" class="btn btn-sm btn-ghost btn-links" aria-expanded="false">查看链路</button>
        </div>
        <div class="value-link-panel" hidden></div>
        <div class="entity-actions">
          <button type="button" class="btn btn-sm btn-ghost btn-edit">编辑</button>
          <button type="button" class="btn btn-sm btn-ghost btn-create-exp">创建实验</button>
          <button type="button" class="btn btn-sm btn-ghost btn-delete">删除</button>
        </div>
      </article>
    `;
  }

  async function load() {
    const items = await apiRequest("/api/opportunities");
    if (!items.length) {
      listEl.innerHTML = `<div class="empty-state"><strong>暂无机会</strong>点击右上角开始审计第一个机会</div>`;
      return;
    }
    listEl.innerHTML = items.map(card).join("");
    listEl.querySelectorAll(".value-card").forEach((el) => {
      const item = items.find((row) => row.id === Number(el.dataset.id));
      el.querySelector(".btn-links").addEventListener("click", () => toggleLinks(el, item));
      el.querySelector(".btn-edit").addEventListener("click", () => openEditor(item));
      el.querySelector(".btn-create-exp").addEventListener("click", () => createExperiment(item));
      el.querySelector(".btn-delete").addEventListener("click", async () => {
        if (!confirm(`确定删除机会「${item.name}」？`)) return;
        await apiRequest(`/api/opportunities/${item.id}`, { method: "DELETE" });
        showToast("机会已删除", "success");
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
