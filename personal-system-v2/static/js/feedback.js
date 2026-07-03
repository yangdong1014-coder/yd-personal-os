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

  function isStrongFeedback(item) {
    const level = item.level || "";
    return level.startsWith("L4") || level.startsWith("L5");
  }

  async function createCaseAsset(item) {
    const strongHint = isStrongFeedback(item) ? "这是强反馈，适合沉淀为案例资产。\n\n" : "";
    if (!confirm(`${strongHint}确定基于「${item.title}」生成案例资产？`)) return;
    const asset = await apiRequest(`/api/feedback/${item.id}/asset`, { method: "POST" });
    showToast("案例资产已生成", "success");
    showAIViewModal({
      title: "案例资产已生成",
      bodyHtml: `
        <div class="stacked-form">
          <p class="form-hint">已生成「${escapeHtml(asset.title)}」，可在资产中心继续补充可迁移场景和产品化下一步。</p>
          <a class="btn btn-primary" href="/assets">查看资产</a>
        </div>
      `,
      closeLabel: "知道了",
    });
    await load();
  }

  function relationLabel(item) {
    if (!item.related_type) return "无";
    const names = {
      opportunity: "机会",
      experiment: "实验",
      project: "项目",
      asset: "资产",
      review: "复盘",
    };
    return `${names[item.related_type] || item.related_type} #${item.related_id || ""}`.trim();
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
    const upstream = links.upstream || {};
    const upstreamItems = [
      upstream.opportunity ? `机会：${upstream.opportunity.name}` : "",
      upstream.experiment ? `实验：${upstream.experiment.name}` : "",
      upstream.project ? `项目：${upstream.project.name}` : "",
    ].filter(Boolean);
    return `
      <div class="value-link-counts">
        <span>关联对象：${escapeHtml(links.related?.name || links.related?.title || "无")}</span>
        <span>案例资产 ${links.counts?.assets || 0}</span>
      </div>
      ${upstreamItems.length ? `<div class="value-link-row"><strong>上游</strong><span>${escapeHtml(upstreamItems.join(" · "))}</span></div>` : ""}
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
      const links = await apiRequest(`/api/feedback/${item.id}/links`);
      summary.textContent = `关联对象：${links.related?.name || links.related?.title || relationLabel(item)} · 案例资产 ${links.counts?.assets || 0}`;
      panel.innerHTML = renderLinks(links);
    } catch (err) {
      panel.innerHTML = `<p class="form-hint">链路加载失败</p>`;
    }
  }

  function card(item) {
    const strongFeedback = isStrongFeedback(item);
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
          <span class="tag">关联对象：${escapeHtml(relationLabel(item))}</span>
          ${item.evidence ? `<span class="tag">有证据</span>` : ""}
          ${strongFeedback ? `<span class="tag">强反馈：适合沉淀为案例资产</span>` : ""}
        </div>
        <div class="value-link-strip">
          <span class="value-link-summary">已生成案例资产：待查看</span>
          <button type="button" class="btn btn-sm btn-ghost btn-links" aria-expanded="false">查看链路</button>
        </div>
        <div class="value-link-panel" hidden></div>
        <div class="entity-actions">
          <button type="button" class="btn btn-sm btn-primary btn-create-asset">生成案例资产</button>
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
      el.querySelector(".btn-links").addEventListener("click", () => {
        toggleLinks(el, item).catch((err) => showToast(err.message, "error"));
      });
      el.querySelector(".btn-create-asset").addEventListener("click", () => {
        createCaseAsset(item).catch((err) => showToast(err.message, "error"));
      });
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
