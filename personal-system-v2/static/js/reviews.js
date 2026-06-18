document.addEventListener("DOMContentLoaded", () => {
  const reviewForm = document.getElementById("review-form");
  const reviewsList = document.getElementById("reviews-list");
  const dateInput = document.getElementById("review-date");
  const capabilityModules = window.CAPABILITY_MODULES || [];

  if (!reviewForm || !reviewsList) return;

  const completeBtn = document.getElementById("ai-complete-btn");
  const weeklyBtn = document.getElementById("ai-weekly-btn");
  const selectedDailyIds = new Set();

  if (dateInput) {
    dateInput.value = new Date().toISOString().slice(0, 10);
  }

  async function handleAIComplete(button) {
    const whatDone = document.getElementById("review-what-done").value.trim();
    if (!whatDone) {
      alert("请先填写「今天做了什么」");
      return;
    }

    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "补全中…";

    try {
      const draft = await apiRequest("/api/ai/complete-review", {
        method: "POST",
        body: JSON.stringify({
          what_done: whatDone,
          type: document.getElementById("review-type").value,
        }),
      });

      showAIModal({
        title: "AI 复盘补全",
        bodyHtml: buildReviewCompleteHtml(draft),
        confirmLabel: "填入表单",
        loadingLabel: "填入中…",
        onConfirm: async () => {
          const data = readReviewCompleteForm();
          document.getElementById("review-stuck").value = data.stuck;
          document.getElementById("review-next").value = data.next_adjust;
          document.getElementById("review-depositable").value = data.depositable;
        },
      });
    } catch (err) {
      alert(err.message || "AI 补全失败");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  function updateWeeklyButton() {
    if (!weeklyBtn) return;
    weeklyBtn.disabled = selectedDailyIds.size < 2;
  }

  async function handleAIWeekly(button) {
    if (selectedDailyIds.size < 2) {
      alert("请至少勾选两条「每日」复盘");
      return;
    }

    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "聚合中…";

    try {
      const draft = await apiRequest("/api/ai/aggregate-weekly-reviews", {
        method: "POST",
        body: JSON.stringify({ review_ids: Array.from(selectedDailyIds) }),
      });

      showAIModal({
        title: "AI 周复盘草稿",
        bodyHtml: buildWeeklyReviewHtml(draft),
        confirmLabel: "保存周复盘",
        loadingLabel: "保存中…",
        onConfirm: async () => {
          const data = readWeeklyReviewForm();
          if (!data.what_done) {
            throw new Error("本周推进内容不能为空");
          }
          await apiRequest("/api/reviews", {
            method: "POST",
            body: JSON.stringify(data),
          });
          selectedDailyIds.clear();
          await loadReviews();
        },
      });
    } catch (err) {
      alert(err.message || "AI 周复盘聚合失败");
    } finally {
      button.textContent = prevText;
      updateWeeklyButton();
    }
  }

  function renderEmpty() {
    reviewsList.innerHTML = `
      <div class="empty-state">
        <strong>添加第一条复盘</strong>
        填写上方表单后即时保存
      </div>
    `;
  }

  async function handleAIRefine(review, button) {
    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "提炼中…";

    try {
      const draft = await apiRequest("/api/ai/refine-review", {
        method: "POST",
        body: JSON.stringify({ review_id: review.id }),
      });

      showAIModal({
        title: "AI 知识卡片草稿",
        bodyHtml: buildDraftFormHtml(draft, capabilityModules),
        onConfirm: async () => {
          const data = readDraftForm();
          if (!data.title || !data.core_content) {
            throw new Error("标题和核心内容不能为空");
          }
          await apiRequest("/api/assets", {
            method: "POST",
            body: JSON.stringify({
              title: data.title,
              trigger_context: data.trigger_context,
              core_content: data.core_content,
              asset_type: "知识卡片",
              capability_tags: data.capability_tags,
              source_review_id: review.id,
            }),
          });
          alert("已保存到资产模块，可前往「资产」页查看");
        },
      });
    } catch (err) {
      alert(err.message || "AI 提炼失败");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  async function loadReviews() {
    const reviews = await apiRequest("/api/reviews");
    reviewsList.innerHTML = "";

    if (reviews.length === 0) {
      selectedDailyIds.clear();
      updateWeeklyButton();
      renderEmpty();
      return;
    }

    reviews.forEach((review) => {
      const card = document.createElement("article");
      card.className = "review-card";

      const hasDepositable = Boolean((review.depositable || "").trim());
      const assetUrl = `/assets?from_review=${review.id}`;
      const isDaily = review.type === "每日";
      const checked = selectedDailyIds.has(review.id) ? " checked" : "";

      card.innerHTML = `
        <div class="entity-header">
          <div class="review-title-row">
            ${
              isDaily
                ? `<label class="review-select"><input type="checkbox" class="daily-review-check" data-review-id="${review.id}"${checked}><span class="sr-only">选择</span></label>`
                : ""
            }
            <div>
              <h3 class="entity-title">${escapeHtml(review.review_date)}</h3>
              <span class="tag">${escapeHtml(review.type)}</span>
            </div>
          </div>
          <div class="card-actions">
            <button type="button" class="btn btn-sm btn-ai">AI提炼</button>
            ${
              hasDepositable
                ? `<a href="${assetUrl}" class="btn btn-sm btn-ghost">生成卡片</a>`
                : ""
            }
          </div>
        </div>
        <dl class="review-fields">
          <div><dt>今天做了什么</dt><dd>${formatText(review.what_done)}</dd></div>
          <div><dt>卡住了什么</dt><dd>${formatText(review.stuck)}</dd></div>
          <div><dt>下一步调整</dt><dd>${formatText(review.next_adjust)}</dd></div>
          <div><dt>可沉淀内容</dt><dd>${formatText(review.depositable)}</dd></div>
        </dl>
      `;

      card.querySelector(".btn-ai").addEventListener("click", (e) => {
        handleAIRefine(review, e.currentTarget);
      });

      const dailyCheck = card.querySelector(".daily-review-check");
      if (dailyCheck) {
        dailyCheck.addEventListener("change", () => {
          if (dailyCheck.checked) {
            selectedDailyIds.add(review.id);
          } else {
            selectedDailyIds.delete(review.id);
          }
          updateWeeklyButton();
        });
      }

      reviewsList.appendChild(card);
    });

    updateWeeklyButton();
  }

  if (completeBtn) {
    completeBtn.addEventListener("click", () => handleAIComplete(completeBtn));
  }

  if (weeklyBtn) {
    weeklyBtn.addEventListener("click", () => handleAIWeekly(weeklyBtn));
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