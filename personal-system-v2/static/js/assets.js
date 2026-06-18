document.addEventListener("DOMContentLoaded", () => {
  const assetForm = document.getElementById("asset-form");
  const assetsList = document.getElementById("assets-list");
  const assetsCount = document.getElementById("assets-count");
  const typeFilter = document.getElementById("type-filter");
  const tagFilter = document.getElementById("tag-filter");
  const prefillHint = document.getElementById("asset-prefill-hint");
  const sourceReviewInput = document.getElementById("asset-source-review");
  const assetTypeSelect = document.getElementById("asset-type");
  const dynamicFieldsEl = document.getElementById("asset-dynamic-fields");
  const maturitySelect = document.getElementById("asset-maturity");

  const assetTypes = window.ASSET_TYPES || [];
  const fieldSchemas = window.ASSET_FIELD_SCHEMAS || {};
  const maturityLevels = window.MATURITY_LEVELS || [];

  if (!assetForm || !assetsList) return;

  let activeType = "";
  let activeTag = "";

  const MATURITY_CLASS = {
    草稿: "maturity-draft",
    可用: "maturity-ready",
    稳定: "maturity-stable",
    标准化: "maturity-standard",
  };

  function getSelectedTags() {
    return Array.from(
      document.querySelectorAll("#capability-picker input:checked")
    ).map((el) => el.value);
  }

  function setSelectedTags(tags) {
    document.querySelectorAll("#capability-picker input").forEach((el) => {
      el.checked = tags.includes(el.value);
    });
  }

  function renderDynamicFields(assetType, values = {}) {
    if (!dynamicFieldsEl) return;
    const schema = fieldSchemas[assetType] || [];
    dynamicFieldsEl.innerHTML = schema
      .map((field) => {
        const value = escapeAttr(values[field.key] || "");
        const rows = field.input === "textarea" ? 3 : 1;
        if (field.input === "textarea") {
          return `
            <div class="form-row asset-field-row" data-field-key="${escapeAttr(field.key)}">
              <label class="form-label">${escapeHtml(field.label)}</label>
              <textarea class="textarea asset-field-input" data-key="${escapeAttr(field.key)}" rows="${rows}">${value}</textarea>
            </div>`;
        }
        return `
          <div class="form-row asset-field-row" data-field-key="${escapeAttr(field.key)}">
            <label class="form-label">${escapeHtml(field.label)}</label>
            <input type="text" class="input full-width asset-field-input" data-key="${escapeAttr(field.key)}" value="${value}">
          </div>`;
      })
      .join("");
  }

  function readDynamicFields() {
    const fields = {};
    document.querySelectorAll(".asset-field-input").forEach((el) => {
      fields[el.dataset.key] = el.value.trim();
    });
    return fields;
  }

  function setDynamicFieldValues(values = {}) {
    document.querySelectorAll(".asset-field-input").forEach((el) => {
      el.value = values[el.dataset.key] || "";
    });
  }

  async function patchAsset(asset, data) {
    await apiRequest(`/api/assets/${asset.id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
    await loadAssets();
  }

  function buildPatchFromModal(asset, data) {
    const payload = {
      title: data.title ?? asset.title,
      asset_type: data.asset_type ?? asset.asset_type,
      capability_tags: data.capability_tags ?? asset.capability_tags,
      maturity: data.maturity ?? asset.maturity,
      summary: data.summary ?? asset.summary,
      reusable_scenario: data.reusable_scenario ?? asset.reusable_scenario,
    };
    if (data.fields) {
      payload.fields = data.fields;
    } else if (data.trigger_context !== undefined || data.core_content !== undefined) {
      payload.trigger_context = data.trigger_context ?? asset.trigger_context;
      payload.core_content = data.core_content ?? asset.core_content;
    }
    return payload;
  }

  async function handleAIOptimize(asset, button) {
    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "优化中…";
    try {
      const result = await apiRequest("/api/ai/optimize-asset", {
        method: "POST",
        body: JSON.stringify({ asset_id: asset.id }),
      });
      showAIModal({
        title: "AI 优化结果",
        bodyHtml: buildAssetEditHtml(result, fieldSchemas),
        onConfirm: async () => {
          const data = readAssetEditForm(fieldSchemas);
          if (!data.title) throw new Error("标题不能为空");
          await patchAsset(asset, buildPatchFromModal(asset, data));
        },
      });
    } catch (err) {
      showToast(err.message || "AI 优化失败", "error");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  async function handleAIClassify(asset, button) {
    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "归类中…";
    try {
      const result = await apiRequest("/api/ai/classify-asset", {
        method: "POST",
        body: JSON.stringify({ asset_id: asset.id }),
      });
      showAIModal({
        title: "AI 归类建议",
        bodyHtml: buildAssetClassifyHtml(result, assetTypes, window.CAPABILITY_MODULES || []),
        confirmLabel: "确认更新",
        onConfirm: async () => {
          const data = readAssetClassifyForm();
          await patchAsset(asset, data);
        },
      });
    } catch (err) {
      showToast(err.message || "AI 归类失败", "error");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  async function handleAITemplate(asset, targetType, button) {
    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "生成中…";
    try {
      const result = await apiRequest("/api/ai/template-asset", {
        method: "POST",
        body: JSON.stringify({ asset_id: asset.id, target_type: targetType }),
      });
      showAIModal({
        title: `AI 转换 · ${targetType}`,
        bodyHtml: buildAssetEditHtml(result, fieldSchemas),
        confirmLabel: "确认更新",
        onConfirm: async () => {
          const data = readAssetEditForm(fieldSchemas);
          if (!data.title) throw new Error("标题不能为空");
          await patchAsset(asset, {
            ...buildPatchFromModal(asset, data),
            asset_type: result.asset_type,
          });
        },
      });
    } catch (err) {
      showToast(err.message || "AI 转换失败", "error");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  async function handleReuse(asset, button) {
    button.disabled = true;
    try {
      await apiRequest(`/api/assets/${asset.id}/reuse`, { method: "POST", body: "{}" });
      showToast("已记录复用", "success");
      await loadAssets();
    } catch (err) {
      showToast(err.message || "记录失败", "error");
      button.disabled = false;
    }
  }

  function renderFieldPreview(asset) {
    const fields = asset.fields || {};
    const entries = Object.entries(fields).filter(([, v]) => (v || "").trim());
    if (!entries.length) {
      return `<p class="asset-preview-text">${formatText(asset.summary || asset.core_content)}</p>`;
    }
    const top = entries.slice(0, 2);
    return `
      <dl class="asset-field-preview">
        ${top
          .map(
            ([key, value]) =>
              `<div><dt>${escapeHtml(key)}</dt><dd>${formatText(value)}</dd></div>`
          )
          .join("")}
      </dl>`;
  }

  async function loadAssets() {
    const params = new URLSearchParams();
    if (activeTag) params.set("tag", activeTag);
    if (activeType) params.set("asset_type", activeType);
    const query = params.toString();
    const url = query ? `/api/assets?${query}` : "/api/assets";
    const assets = await apiRequest(url);

    if (assetsCount) {
      assetsCount.textContent = assets.length ? `${assets.length} 条` : "";
    }

    assetsList.innerHTML = "";
    if (assets.length === 0) {
      assetsList.innerHTML = `
        <div class="empty-state assets-empty-state">
          <strong>${activeType || activeTag ? "暂无匹配资产" : "添加第一条可复用资产"}</strong>
          ${activeType || activeTag ? "调整筛选条件或新建资产" : "填写左侧表单，或从复盘 / 智能归档生成"}
        </div>`;
      return;
    }

    assets.forEach((asset) => {
      const card = document.createElement("article");
      card.className = `asset-card asset-card--${slugifyType(asset.asset_type)}`;
      const tagsHtml = (asset.capability_tags || [])
        .map((t) => `<span class="tag tag-cap">${escapeHtml(t)}</span>`)
        .join("");
      const maturityClass = MATURITY_CLASS[asset.maturity] || "maturity-draft";

      card.innerHTML = `
        <div class="asset-card-top">
          <div class="asset-card-intro">
            <div class="asset-card-tags-row">
              <span class="tag tag-type">${escapeHtml(asset.asset_type)}</span>
              <span class="tag asset-maturity ${maturityClass}">${escapeHtml(asset.maturity || "草稿")}</span>
              ${tagsHtml}
            </div>
            <h3 class="entity-title">${escapeHtml(asset.title)}</h3>
            <p class="asset-summary">${formatText(asset.summary || "")}</p>
          </div>
          <div class="card-actions asset-card-actions">
            <button type="button" class="btn btn-sm btn-ghost btn-reuse" title="记录一次复用">+复用</button>
            <button type="button" class="btn btn-sm btn-ghost btn-delete-asset">删除</button>
          </div>
        </div>
        ${renderFieldPreview(asset)}
        <div class="asset-card-meta-grid">
          <div><span class="meta-label">复用场景</span><span class="meta-value">${formatInline(asset.reusable_scenario)}</span></div>
          <div><span class="meta-label">复用次数</span><span class="meta-value mono">${asset.reuse_count || 0}</span></div>
          <div><span class="meta-label">创建</span><span class="meta-value mono">${escapeHtml(formatDate(asset.created_at))}</span></div>
          <div><span class="meta-label">更新</span><span class="meta-value mono">${escapeHtml(formatDate(asset.updated_at || asset.created_at))}</span></div>
        </div>
        <div class="asset-ai-actions">
          <button type="button" class="btn btn-sm btn-ai btn-optimize">AI优化</button>
          <button type="button" class="btn btn-sm btn-ai btn-classify">AI归类</button>
          <button type="button" class="btn btn-sm btn-ai btn-sop">转SOP</button>
          <button type="button" class="btn btn-sm btn-ai btn-model">转模型</button>
          <button type="button" class="btn btn-sm btn-ai btn-method">转方法论</button>
          <button type="button" class="btn btn-sm btn-ai btn-prompt">转提示词</button>
        </div>`;

      card.querySelector(".btn-delete-asset").addEventListener("click", async () => {
        if (!window.confirm(`确定删除资产「${asset.title}」？此操作不可撤销。`)) return;
        try {
          await apiRequest(`/api/assets/${asset.id}`, { method: "DELETE" });
          showToast("资产已删除", "success");
          await loadAssets();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
      card.querySelector(".btn-reuse").addEventListener("click", (e) => {
        handleReuse(asset, e.currentTarget);
      });
      card.querySelector(".btn-optimize").addEventListener("click", (e) => {
        handleAIOptimize(asset, e.currentTarget);
      });
      card.querySelector(".btn-classify").addEventListener("click", (e) => {
        handleAIClassify(asset, e.currentTarget);
      });
      card.querySelector(".btn-sop").addEventListener("click", (e) => {
        handleAITemplate(asset, "SOP", e.currentTarget);
      });
      card.querySelector(".btn-model").addEventListener("click", (e) => {
        handleAITemplate(asset, "模型", e.currentTarget);
      });
      card.querySelector(".btn-method").addEventListener("click", (e) => {
        handleAITemplate(asset, "方法论", e.currentTarget);
      });
      card.querySelector(".btn-prompt").addEventListener("click", (e) => {
        handleAITemplate(asset, "提示词", e.currentTarget);
      });

      assetsList.appendChild(card);
    });
  }

  async function applyPrefillFromReview(reviewId) {
    const review = await apiRequest(`/api/reviews/${reviewId}`);
    document.getElementById("asset-title").value = `${review.type}复盘 · ${review.review_date}`;
    assetTypeSelect.value = "本质洞察";
    renderDynamicFields("本质洞察", {
      现象: [review.what_done, review.stuck].filter(Boolean).join("\n"),
      底层本质: review.depositable || "",
    });
    sourceReviewInput.value = review.id;
    prefillHint.hidden = false;
    assetForm.scrollIntoView({ behavior: "smooth" });
  }

  assetTypeSelect.addEventListener("change", () => {
    renderDynamicFields(assetTypeSelect.value);
  });

  assetForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const sourceId = sourceReviewInput.value
      ? parseInt(sourceReviewInput.value, 10)
      : null;
    const payload = {
      title: document.getElementById("asset-title").value,
      asset_type: assetTypeSelect.value,
      maturity: maturitySelect.value,
      fields: readDynamicFields(),
      capability_tags: getSelectedTags(),
      source_review_id: sourceId,
    };
    try {
      await apiRequest("/api/assets", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      assetForm.reset();
      sourceReviewInput.value = "";
      prefillHint.hidden = true;
      assetTypeSelect.value = "本质洞察";
      maturitySelect.value = "草稿";
      renderDynamicFields("本质洞察");
      showToast("资产已保存", "success");
      await loadAssets();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  function bindFilterBar(container, attr, setter) {
    if (!container) return;
    container.addEventListener("click", async (e) => {
      const chip = e.target.closest(".filter-chip");
      if (!chip) return;
      container.querySelectorAll(".filter-chip").forEach((el) => {
        el.classList.remove("active");
      });
      chip.classList.add("active");
      setter(chip.dataset[attr] || "");
      await loadAssets();
    });
  }

  bindFilterBar(typeFilter, "type", (value) => {
    activeType = value;
  });
  bindFilterBar(tagFilter, "tag", (value) => {
    activeTag = value;
  });

  renderDynamicFields(assetTypeSelect.value);

  const params = new URLSearchParams(window.location.search);
  const fromReview = params.get("from_review");
  const init = fromReview
    ? applyPrefillFromReview(fromReview).then(loadAssets)
    : loadAssets();
  init.catch((err) => console.error(err));
});

function slugifyType(type) {
  return String(type || "generic")
    .replace(/\s+/g, "-")
    .replace(/[^\w\u4e00-\u9fff-]/g, "");
}

function formatDate(value) {
  if (!value) return "—";
  return String(value).replace("T", " ").slice(0, 16);
}

function formatInline(text) {
  if (!text || !String(text).trim()) {
    return '<span class="muted-text">—</span>';
  }
  const short = String(text).length > 80 ? `${String(text).slice(0, 80)}…` : text;
  return escapeHtml(short);
}

function formatText(text) {
  if (!text || !String(text).trim()) {
    return '<span class="muted-text">—</span>';
  }
  return escapeHtml(String(text)).replace(/\n/g, "<br>");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function escapeAttr(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}