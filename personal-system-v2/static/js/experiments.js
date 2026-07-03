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
        <span>来源机会：${escapeHtml(links.opportunity?.name || "无")}</span>
        <span>反馈 ${links.counts?.feedback || 0}</span>
        <span>案例资产 ${links.counts?.assets || 0}</span>
      </div>
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
      const links = await apiRequest(`/api/experiments/${item.id}/links`);
      summary.textContent = `来源机会：${links.opportunity?.name || "无"} · 反馈 ${links.counts?.feedback || 0} · 案例资产 ${links.counts?.assets || 0}`;
      panel.innerHTML = renderLinks(links);
    } catch (err) {
      panel.innerHTML = `<p class="form-hint">链路加载失败</p>`;
    }
  }

  function card(item) {
    return `
      <article class="entity-card value-card" data-id="${item.id}">
        <div class="value-card-head">
          <div>
            <h3 class="entity-title">${escapeHtml(item.name)}</h3>
            <p class="entity-meta">${escapeHtml(item.status)} · ${escapeHtml(item.experiment_type)}${item.opportunity_name ? ` · ${escapeHtml(item.opportunity_name)}` : ""}</p>
          </div>
        </div>
        <p class="value-card-summary">${formatText(item.hypothesis || item.minimum_action || "暂无实验假设")}</p>
        <div class="value-card-meta">
          <span class="tag">来源机会：${escapeHtml(item.opportunity_name || "无")}</span>
          ${item.success_criteria ? `<span class="tag">成功标准</span>` : ""}
          ${item.real_feedback ? `<span class="tag">已有反馈</span>` : ""}
          ${item.data_result ? `<span class="tag">有结果数据</span>` : ""}
        </div>
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
