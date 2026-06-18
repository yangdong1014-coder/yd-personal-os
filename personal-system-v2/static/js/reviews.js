document.addEventListener("DOMContentLoaded", () => {
  const reviewForm = document.getElementById("review-form");
  const reviewsList = document.getElementById("reviews-list");
  const dateInput = document.getElementById("review-date");

  if (!reviewForm || !reviewsList) return;

  if (dateInput) {
    dateInput.value = new Date().toISOString().slice(0, 10);
  }

  function renderEmpty() {
    reviewsList.innerHTML = `
      <div class="empty-state">
        <strong>添加第一条复盘</strong>
        填写上方表单后即时保存
      </div>
    `;
  }

  async function loadReviews() {
    const reviews = await apiRequest("/api/reviews");
    reviewsList.innerHTML = "";

    if (reviews.length === 0) {
      renderEmpty();
      return;
    }

    reviews.forEach((review) => {
      const card = document.createElement("article");
      card.className = "review-card";

      const hasDepositable = Boolean((review.depositable || "").trim());
      const assetUrl = `/assets?from_review=${review.id}`;

      card.innerHTML = `
        <div class="entity-header">
          <div>
            <h3 class="entity-title">${escapeHtml(review.review_date)}</h3>
            <span class="tag">${escapeHtml(review.type)}</span>
          </div>
          ${
            hasDepositable
              ? `<a href="${assetUrl}" class="btn btn-sm">生成卡片</a>`
              : ""
          }
        </div>
        <dl class="review-fields">
          <div><dt>今天做了什么</dt><dd>${formatText(review.what_done)}</dd></div>
          <div><dt>卡住了什么</dt><dd>${formatText(review.stuck)}</dd></div>
          <div><dt>下一步调整</dt><dd>${formatText(review.next_adjust)}</dd></div>
          <div><dt>可沉淀内容</dt><dd>${formatText(review.depositable)}</dd></div>
        </dl>
      `;

      reviewsList.appendChild(card);
    });
  }

  reviewForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const payload = {
      review_date: document.getElementById("review-date").value,
      type: document.getElementById("review-type").value,
      what_done: document.getElementById("review-what-done").value,
      stuck: document.getElementById("review-stuck").value,
      next_adjust: document.getElementById("review-next").value,
      depositable: document.getElementById("review-depositable").value,
    };

    try {
      await apiRequest("/api/reviews", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      document.getElementById("review-what-done").value = "";
      document.getElementById("review-stuck").value = "";
      document.getElementById("review-next").value = "";
      document.getElementById("review-depositable").value = "";
      await loadReviews();
    } catch (err) {
      alert(err.message);
    }
  });

  loadReviews().catch((err) => console.error(err));
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