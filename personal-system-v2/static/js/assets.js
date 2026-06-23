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

  function buildSelectOptions(options, selected) {
    return options
      .map(
        (value) =>
          `<option value="${escapeAttr(value)}"${value === selected ? " selected" : ""}>${escapeHtml(value)}</option>`
      )
      .join("");
  }

  function buildTagOptions(tags = []) {
    const selected = new Set(tags || []);
    return (window.CAPABILITY_MODULES || [])
      .map((module) => {
        const checked = selected.has(module) ? " checked" : "";
        return `
          <label class="tag-option">
            <input type="checkbox" class="asset-edit-tag" value="${escapeAttr(module)}"${checked}>
            <span>${escapeHtml(module)}</span>
          </label>`;
      })
      .join("");
  }

  function buildAssetEditFieldsHtml(assetType, values = {}) {
    const schema = fieldSchemas[assetType] || [];
    return schema
      .map((field) => {
        const value = escapeHtml(values[field.key] || "");
        return `
          <div class="form-row asset-edit-field-row">
            <label class="form-label">${escapeHtml(field.label)}</label>
            <textarea class="textarea asset-edit-field-input" data-key="${escapeAttr(field.key)}" rows="3">${value}</textarea>
          </div>`;
      })
      .join("");
  }

  function renderAssetEditFields(assetType, values = {}) {
    const fieldsEl = document.getElementById("asset-edit-dynamic-fields");
    if (!fieldsEl) return;
    fieldsEl.innerHTML = buildAssetEditFieldsHtml(assetType, values);
  }

  function readAssetEditFields() {
    const fields = {};
    document.querySelectorAll(".asset-edit-field-input").forEach((el) => {
      fields[el.dataset.key] = el.value.trim();
    });
    return fields;
  }

  function fieldsChanged(before = {}, after = {}) {
    const keys = new Set([...Object.keys(before || {}), ...Object.keys(after || {})]);
    for (const key of keys) {
      if (String(before[key] || "").trim() !== String(after[key] || "").trim()) {
        return true;
      }
    }
    return false;
  }

  function openAssetEditModal(asset) {
    showAIModal({
      title: `编辑资产 — ${asset.title}`,
      bodyHtml: `
        <div class="stacked-form">
          <div class="form-row">
            <label class="form-label">资产类型</label>
            <select id="asset-edit-type" class="select full-width">${buildSelectOptions(assetTypes, asset.asset_type)}</select>
          </div>
          <div class="form-row">
            <label class="form-label">标题</label>
            <input type="text" id="asset-edit-title" class="input full-width" value="${escapeAttr(asset.title)}" required>
          </div>
          <div class="form-row">
            <label class="form-label">成熟度</label>
            <select id="asset-edit-maturity" class="select full-width">${buildSelectOptions(maturityLevels, asset.maturity || "草稿")}</select>
          </div>
          <div id="asset-edit-dynamic-fields" class="asset-dynamic-fields">
            ${buildAssetEditFieldsHtml(asset.asset_type, asset.fields || {})}
          </div>
          <div class="form-row">
            <label class="form-label">复用场景</label>
            <textarea id="asset-edit-reusable" class="textarea" rows="3">${escapeHtml(asset.reusable_scenario || "")}</textarea>
          </div>
          <div class="form-row">
            <span class="form-label">关联能力模块</span>
            <div class="tag-picker">${buildTagOptions(asset.capability_tags || [])}</div>
          </div>
        </div>
      `,
      confirmLabel: "保存",
      loadingLabel: "保存中…",
      onConfirm: async () => {
        const title = document.getElementById("asset-edit-title").value.trim();
        const assetType = document.getElementById("asset-edit-type").value;
        const maturity = document.getElementById("asset-edit-maturity").value;
        const fields = readAssetEditFields();
        if (!title) {
          throw new Error("标题不能为空");
        }
        const payload = {
          title,
          asset_type: assetType,
          maturity,
          fields,
          reusable_scenario: document
            .getElementById("asset-edit-reusable")
            .value.trim(),
          capability_tags: Array.from(
            document.querySelectorAll(".asset-edit-tag:checked")
          ).map((el) => el.value),
        };
        if (assetType !== asset.asset_type || fieldsChanged(asset.fields, fields)) {
          payload.summary = "";
        }
        await patchAsset(asset, payload);
        showToast("资产已更新", "success");
      },
    });

    document.getElementById("asset-edit-type")?.addEventListener("change", (e) => {
      renderAssetEditFields(e.target.value, asset.fields || {});
    });
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

  function normalizeComparableText(text) {
    return String(text || "")
      .toLowerCase()
      .replace(/[\s　]+/g, "")
      .replace(/[，。！？、；：,.!?;:'"“”‘’（）()【】[\]{}<>《》—-]/g, "");
  }

  function isRepeatedContent(a, b) {
    const left = normalizeComparableText(a);
    const right = normalizeComparableText(b);
    if (!left || !right) return false;
    if (left === right) return true;
    const shorter = left.length <= right.length ? left : right;
    const longer = left.length > right.length ? left : right;
    return (
      shorter.length >= 24 &&
      longer.includes(shorter) &&
      (shorter.length / longer.length >= 0.5 || shorter.length >= 40)
    );
  }

  function getFieldPreviewEntries(asset) {
    const fields = asset.fields || {};
    const entries = [];
    Object.entries(fields).forEach(([key, value]) => {
      const text = (value || "").trim();
      if (!text) return;
      if (entries.some(([, existing]) => isRepeatedContent(existing, text))) {
        return;
      }
      entries.push([key, text]);
    });
    return entries;
  }

  function renderAssetSummary(asset, fieldEntries) {
    const summary = (asset.summary || "").trim();
    const fallback = !summary ? fieldEntries[0]?.[1] || "" : "";
    const text = summary || fallback;
    if (!text) return "";

    const repeatedWithFields =
      Boolean(summary) &&
      fieldEntries.some(([, value]) => isRepeatedContent(summary, value));
    const collapsedOnly = repeatedWithFields || Boolean(fallback);
    const className = collapsedOnly
      ? "asset-summary asset-summary-collapsed-only"
      : "asset-summary";
    return `<p class="${className}">${formatText(text)}</p>`;
  }

  function renderFieldPreview(asset, entries, hasSummary) {
    if (!entries.length) {
      const fallback = hasSummary ? "" : asset.summary || asset.core_content;
      return fallback
        ? `<p class="asset-preview-text">${formatText(fallback)}</p>`
        : "";
    }
    return `
      <dl class="asset-field-preview">
        ${entries
          .map(
            ([key, value]) =>
              `<div><dt>${escapeHtml(key)}</dt><dd>${formatText(value)}</dd></div>`
          )
        .join("")}
      </dl>`;
  }

  function assetUpdatedAt(asset) {
    return asset.updated_at || asset.created_at || "";
  }

  function groupAssetsByType(assets) {
    const groupsByType = new Map();
    assets.forEach((asset) => {
      const type = asset.asset_type || "通用资产";
      if (!groupsByType.has(type)) {
        groupsByType.set(type, {
          type,
          assets: [],
          latestUpdatedAt: "",
        });
      }
      const group = groupsByType.get(type);
      group.assets.push(asset);
      const updatedAt = assetUpdatedAt(asset);
      if (updatedAt > group.latestUpdatedAt) {
        group.latestUpdatedAt = updatedAt;
      }
    });

    const orderedTypes = [
      ...assetTypes,
      ...Array.from(groupsByType.keys()).filter((type) => !assetTypes.includes(type)),
    ];
    return orderedTypes
      .map((type) => groupsByType.get(type))
      .filter(Boolean);
  }

  function renderAssetArchiveItem(asset) {
    const tagsHtml = (asset.capability_tags || [])
      .map((tag) => `<span class="tag tag-cap">${escapeHtml(tag)}</span>`)
      .join("");
    const maturityClass = MATURITY_CLASS[asset.maturity] || "maturity-draft";
    const fieldPreviewEntries = getFieldPreviewEntries(asset);
    const summaryHtml = renderAssetSummary(asset, fieldPreviewEntries);

    return `
      <article class="asset-archive-item" data-asset-id="${asset.id}">
        <div class="asset-archive-item-head">
          <div class="asset-archive-item-main">
            <div class="asset-archive-item-title-row">
              <h3 class="asset-archive-item-title">${escapeHtml(asset.title)}</h3>
              <span class="tag asset-maturity ${maturityClass}">${escapeHtml(asset.maturity || "草稿")}</span>
            </div>
            ${tagsHtml ? `<div class="asset-card-tags-row asset-archive-tags">${tagsHtml}</div>` : ""}
            ${summaryHtml}
            <div class="asset-archive-item-meta">
              <span>复用 ${asset.reuse_count || 0}</span>
              <span>更新 ${escapeHtml(formatDate(assetUpdatedAt(asset)))}</span>
            </div>
          </div>
          <div class="asset-archive-item-actions">
            <button type="button" class="btn btn-sm btn-ghost btn-edit-asset">编辑</button>
            <button type="button" class="btn btn-sm btn-ghost btn-reuse" title="记录一次复用">+复用</button>
            <button type="button" class="btn btn-sm btn-ghost btn-toggle-asset" aria-expanded="false">展开</button>
          </div>
        </div>
        <div class="asset-card-details" hidden>
          ${renderFieldPreview(asset, fieldPreviewEntries, Boolean(summaryHtml))}
          <div class="asset-card-meta-grid asset-detail-meta-grid">
            <div><span class="meta-label">复用场景</span><span class="meta-value">${formatInline(asset.reusable_scenario)}</span></div>
          </div>
          <div class="asset-ai-actions">
            <button type="button" class="btn btn-sm btn-ai btn-optimize">AI优化</button>
            <button type="button" class="btn btn-sm btn-ai btn-classify">AI归类</button>
            <button type="button" class="btn btn-sm btn-ai btn-sop">转SOP</button>
            <button type="button" class="btn btn-sm btn-ai btn-model">转模型</button>
            <button type="button" class="btn btn-sm btn-ai btn-method">转方法论</button>
            <button type="button" class="btn btn-sm btn-ai btn-prompt">转提示词</button>
            <button type="button" class="btn btn-sm btn-ghost btn-delete-asset">删除</button>
          </div>
        </div>
      </article>`;
  }

  function bindAssetArchiveItem(itemEl, asset) {
    itemEl.querySelector(".btn-edit-asset").addEventListener("click", () => {
      openAssetEditModal(asset);
    });

    const toggleBtn = itemEl.querySelector(".btn-toggle-asset");
    const detailsEl = itemEl.querySelector(".asset-card-details");
    toggleBtn.addEventListener("click", () => {
      const expanded = toggleBtn.getAttribute("aria-expanded") === "true";
      toggleBtn.setAttribute("aria-expanded", String(!expanded));
      toggleBtn.textContent = expanded ? "展开" : "收起";
      itemEl.classList.toggle("asset-card-expanded", !expanded);
      detailsEl.hidden = expanded;
    });

    itemEl.querySelector(".btn-delete-asset").addEventListener("click", async () => {
      if (!window.confirm(`确定删除资产「${asset.title}」？此操作不可撤销。`)) return;
      try {
        await apiRequest(`/api/assets/${asset.id}`, { method: "DELETE" });
        showToast("资产已删除", "success");
        await loadAssets();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
    itemEl.querySelector(".btn-reuse").addEventListener("click", (e) => {
      handleReuse(asset, e.currentTarget);
    });
    itemEl.querySelector(".btn-optimize").addEventListener("click", (e) => {
      handleAIOptimize(asset, e.currentTarget);
    });
    itemEl.querySelector(".btn-classify").addEventListener("click", (e) => {
      handleAIClassify(asset, e.currentTarget);
    });
    itemEl.querySelector(".btn-sop").addEventListener("click", (e) => {
      handleAITemplate(asset, "SOP", e.currentTarget);
    });
    itemEl.querySelector(".btn-model").addEventListener("click", (e) => {
      handleAITemplate(asset, "模型", e.currentTarget);
    });
    itemEl.querySelector(".btn-method").addEventListener("click", (e) => {
      handleAITemplate(asset, "方法论", e.currentTarget);
    });
    itemEl.querySelector(".btn-prompt").addEventListener("click", (e) => {
      handleAITemplate(asset, "提示词", e.currentTarget);
    });
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

    const groups = groupAssetsByType(assets);
    groups.forEach((group) => {
      const groupEl = document.createElement("article");
      groupEl.className = `asset-archive-group asset-card--${slugifyType(group.type)}`;
      groupEl.innerHTML = `
        <div class="asset-archive-group-head">
          <div class="asset-archive-group-main">
            <h3 class="asset-archive-group-title">${escapeHtml(group.type)}</h3>
            <span class="asset-archive-group-count">${group.assets.length} 条</span>
          </div>
          <div class="asset-archive-group-meta">
            最近更新 ${escapeHtml(formatDate(group.latestUpdatedAt))}
          </div>
          <button type="button" class="btn btn-sm btn-ghost btn-toggle-asset-group" aria-expanded="false">展开</button>
        </div>
        <div class="asset-archive-items" hidden>
          ${group.assets.map((asset) => renderAssetArchiveItem(asset)).join("")}
        </div>`;

      const toggleGroupBtn = groupEl.querySelector(".btn-toggle-asset-group");
      const itemsEl = groupEl.querySelector(".asset-archive-items");
      toggleGroupBtn.addEventListener("click", () => {
        const expanded = toggleGroupBtn.getAttribute("aria-expanded") === "true";
        toggleGroupBtn.setAttribute("aria-expanded", String(!expanded));
        toggleGroupBtn.textContent = expanded ? "展开" : "收起";
        groupEl.classList.toggle("asset-archive-group-expanded", !expanded);
        itemsEl.hidden = expanded;
      });

      groupEl.querySelectorAll(".asset-archive-item").forEach((itemEl) => {
        const assetId = Number(itemEl.dataset.assetId);
        const asset = group.assets.find((entry) => entry.id === assetId);
        if (asset) bindAssetArchiveItem(itemEl, asset);
      });

      assetsList.appendChild(groupEl);
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
