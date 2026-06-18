document.addEventListener("DOMContentLoaded", () => {
  const assetForm = document.getElementById("asset-form");
  const assetsList = document.getElementById("assets-list");
  const tagFilter = document.getElementById("tag-filter");
  const prefillHint = document.getElementById("asset-prefill-hint");
  const sourceReviewInput = document.getElementById("asset-source-review");

  if (!assetForm || !assetsList) return;

  let activeTag = "";

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

  function renderEmpty() {
    assetsList.innerHTML = `
      <div class="empty-state">
        <strong>添加第一张知识卡片</strong>
        填写上方表单或从复盘生成
      </div>
    `;
  }

  async function loadAssets() {
    const url = activeTag
      ? `/api/assets?tag=${encodeURIComponent(activeTag)}`
      : "/api/assets";
    const assets = await apiRequest(url);
    assetsList.innerHTML = "";

    if (assets.length === 0) {
      assetsList.innerHTML = `
        <div class="empty-state">
          <strong>${activeTag ? "该标签下暂无卡片" : "添加第一张知识卡片"}</strong>
          ${activeTag ? "切换其他标签或新建卡片" : "填写上方表单或从复盘生成"}
        </div>
      `;
      return;
    }

    assets.forEach((asset) => {
      const card = document.createElement("article");
      card.className = "asset-card";

      const tagsHtml = (asset.capability_tags || [])
        .map((t) => `<span class="tag">${escapeHtml(t)}</span>`)
        .join(" ");

      card.innerHTML = `
        <div class="entity-header">
          <div>
            <h3 class="entity-title">${escapeHtml(asset.title)}</h3>
            <span class="tag tag-type">${escapeHtml(asset.asset_type)}</span>
            ${tagsHtml}
          </div>
        </div>
        <dl class="review-fields">
          <div><dt>触发情境</dt><dd>${formatText(asset.trigger_context)}</dd></div>
          <div><dt>核心内容</dt><dd>${formatText(asset.core_content)}</dd></div>
        </dl>
        <p class="asset-meta">${escapeHtml(asset.created_at)}</p>
      `;

      assetsList.appendChild(card);
    });
  }

  async function applyPrefillFromReview(reviewId) {
    const review = await apiRequest(`/api/reviews/${reviewId}`);
    const triggerParts = [];
    if (review.what_done) triggerParts.push(`做了什么：${review.what_done}`);
    if (review.stuck) triggerParts.push(`卡住了：${review.stuck}`);
    if (review.next_adjust) triggerParts.push(`下一步：${review.next_adjust}`);

    document.getElementById("asset-title").value =
      `${review.type}复盘 · ${review.review_date}`;
    document.getElementById("asset-trigger").value =
      triggerParts.join("\n") || `${review.review_date} ${review.type} 复盘`;
    document.getElementById("asset-content").value = review.depositable || "";
    document.getElementById("asset-type").value = "知识卡片";
    sourceReviewInput.value = review.id;
    prefillHint.style.display = "block";

    document.getElementById("asset-form").scrollIntoView({ behavior: "smooth" });
  }

  assetForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const sourceId = sourceReviewInput.value
      ? parseInt(sourceReviewInput.value, 10)
      : null;

    const payload = {
      title: document.getElementById("asset-title").value,
      trigger_context: document.getElementById("asset-trigger").value,
      core_content: document.getElementById("asset-content").value,
      asset_type: document.getElementById("asset-type").value,
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
      prefillHint.style.display = "none";
      document.getElementById("asset-type").value = "知识卡片";
      await loadAssets();
    } catch (err) {
      alert(err.message);
    }
  });

  if (tagFilter) {
    tagFilter.addEventListener("click", async (e) => {
      const chip = e.target.closest(".filter-chip");
      if (!chip) return;

      tagFilter.querySelectorAll(".filter-chip").forEach((el) => {
        el.classList.remove("active");
      });
      chip.classList.add("active");
      activeTag = chip.dataset.tag || "";
      await loadAssets();
    });
  }

  const params = new URLSearchParams(window.location.search);
  const fromReview = params.get("from_review");

  const init = fromReview
    ? applyPrefillFromReview(fromReview).then(loadAssets)
    : loadAssets();

  init.catch((err) => console.error(err));
});

function formatText(text) {
  if (!text || !text.trim()) {
    return '<span class="muted-text">—</span>';
  }
  return escapeHtml(text).replace(/\n/g, "<br>");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}