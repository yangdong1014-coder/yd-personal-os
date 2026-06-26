document.addEventListener("DOMContentLoaded", () => {
  const anchorDisplay = document.getElementById("anchor-display");
  const anchorForm = document.getElementById("anchor-form");
  const anchorEditBtn = document.getElementById("anchor-edit-btn");
  const anchorCancelBtn = document.getElementById("anchor-cancel-btn");
  const calibrationForm = document.getElementById("calibration-form");
  const historyListEl = document.getElementById("calibration-history-list");
  const actionsListEl = document.getElementById("positioning-actions-list");
  const actionsContextHint = document.getElementById("actions-context-hint");
  const handfillForm = document.getElementById("action-handfill-form");
  const actionTypeSelect = document.getElementById("action-type");
  const actionTargetGoalField = document.getElementById("action-target-goal-field");
  const actionNewGoalNameField = document.getElementById("action-new-goal-name-field");
  const actionGoalTypeField = document.getElementById("action-goal-type-field");

  if (!anchorDisplay || !calibrationForm || !historyListEl || !actionsListEl) return;

  let activeCalibrationId = null;
  let calibrations = [];

  const displayFields = {
    first_principle: document.getElementById("anchor-display-first-principle"),
    identity_core: document.getElementById("anchor-display-identity-core"),
    flywheel_def: document.getElementById("anchor-display-flywheel-def"),
    current_stage: document.getElementById("anchor-display-current-stage"),
    north_star: document.getElementById("anchor-display-north-star"),
  };
  const formFields = {
    first_principle: document.getElementById("anchor-first-principle"),
    identity_core: document.getElementById("anchor-identity-core"),
    flywheel_def: document.getElementById("anchor-flywheel-def"),
    current_stage: document.getElementById("anchor-current-stage"),
    north_star: document.getElementById("anchor-north-star"),
  };
  const anchorUpdatedAtEl = document.getElementById("anchor-updated-at");

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function displayValue(value) {
    const text = (value || "").trim();
    return text ? escapeHtml(text) : "—";
  }

  function todayInputValue() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${now.getFullYear()}-${month}-${day}`;
  }

  function setAnchorDisplay(anchor) {
    const data = anchor || {};
    Object.keys(displayFields).forEach((key) => {
      if (displayFields[key]) {
        displayFields[key].innerHTML = displayValue(data[key]);
      }
    });
    if (anchorUpdatedAtEl) {
      anchorUpdatedAtEl.textContent = data.updated_at
        ? `最近更新：${data.updated_at}`
        : "尚未设置定位锚";
    }
  }

  function fillAnchorForm(anchor) {
    const data = anchor || {};
    Object.keys(formFields).forEach((key) => {
      if (formFields[key]) {
        formFields[key].value = data[key] || "";
      }
    });
  }

  function showAnchorForm(show) {
    if (!anchorForm || !anchorDisplay || !anchorEditBtn) return;
    anchorForm.hidden = !show;
    anchorDisplay.hidden = show;
    anchorEditBtn.hidden = show;
  }

  function statusLabel(status) {
    const labels = {
      pending: "待确认",
      confirmed: "已确认",
      rejected: "已拒绝",
    };
    return labels[status] || status;
  }

  function renderActions(actions) {
    const pending = (actions || []).filter((item) => item.status === "pending");
    if (!activeCalibrationId) {
      actionsListEl.innerHTML = `
        <div class="empty-state">
          <strong>暂无待确认变更</strong>
          先提交校准并在历史中选中一条记录
        </div>`;
      if (handfillForm) handfillForm.hidden = true;
      return;
    }

    if (handfillForm) handfillForm.hidden = false;

    if (!actions || !actions.length) {
      actionsListEl.innerHTML = `
        <div class="empty-state">
          <strong>本条校准尚无变更建议</strong>
          可手填 pending 建议，或使用后续 AI 生成（commit-3 前仅展示）
        </div>`;
      return;
    }

    actionsListEl.innerHTML = actions
      .map((action) => {
        const payloadText = JSON.stringify(action.payload || {}, null, 0);
        const statusClass =
          action.status === "pending"
            ? "is-pending"
            : action.status === "confirmed"
              ? "is-confirmed"
              : "is-rejected";
        return `
          <article class="positioning-action-item ${statusClass}">
            <div class="positioning-action-head">
              <span class="positioning-action-type">${escapeHtml(action.action_type)}</span>
              <span class="positioning-action-status">${escapeHtml(statusLabel(action.status))}</span>
            </div>
            <p class="positioning-action-reason">${escapeHtml(action.reason)}</p>
            <dl class="positioning-action-meta">
              ${action.target_goal_id ? `<div><dt>目标 ID</dt><dd>${action.target_goal_id}</dd></div>` : ""}
              <div><dt>payload</dt><dd><code>${escapeHtml(payloadText)}</code></dd></div>
            </dl>
          </article>`;
      })
      .join("");
  }

  function renderHistory() {
    if (!calibrations.length) {
      historyListEl.innerHTML = `
        <div class="empty-state">
          <strong>尚无校准记录</strong>
          完成第一次校准后显示在这里
        </div>`;
      return;
    }

    historyListEl.innerHTML = calibrations
      .map((item) => {
        const active = item.id === activeCalibrationId ? " is-active" : "";
        const summary = (item.conclusion || item.primary_contradiction || "未填写结论").trim();
        return `
          <button
            type="button"
            class="positioning-history-item${active}"
            data-calibration-id="${item.id}"
          >
            <span class="positioning-history-date">${escapeHtml(item.calibrated_at)}</span>
            <span class="positioning-history-cycle">${escapeHtml(item.cycle)}</span>
            <span class="positioning-history-summary">${escapeHtml(summary)}</span>
          </button>`;
      })
      .join("");

    historyListEl.querySelectorAll("[data-calibration-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = Number(button.dataset.calibrationId);
        selectCalibration(id);
      });
    });
  }

  async function selectCalibration(calibrationId) {
    activeCalibrationId = calibrationId;
    renderHistory();
    const detail = await apiRequest(`/api/positioning/calibrations/${calibrationId}`);
    if (actionsContextHint) {
      const date = detail.calibration?.calibrated_at || "";
      actionsContextHint.textContent = `当前选中：${date} 校准 · pending 建议只读展示 · 确认 / 拒绝将在下一版本开放`;
    }
    renderActions(detail.actions || []);
  }

  async function loadAnchor() {
    const anchor = await apiRequest("/api/positioning/anchor");
    setAnchorDisplay(anchor);
    fillAnchorForm(anchor);
  }

  async function loadCalibrations(selectLatest = false) {
    calibrations = await apiRequest("/api/positioning/calibrations");
    renderHistory();
    if (selectLatest && calibrations.length) {
      await selectCalibration(calibrations[0].id);
    } else if (
      activeCalibrationId &&
      calibrations.some((item) => item.id === activeCalibrationId)
    ) {
      await selectCalibration(activeCalibrationId);
    } else {
      activeCalibrationId = null;
      renderActions([]);
      if (actionsContextHint) {
        actionsContextHint.textContent =
          "选择下方校准历史后，此处只读展示 pending 建议。确认 / 拒绝将在下一版本开放。";
      }
      if (handfillForm) handfillForm.hidden = true;
    }
  }

  function updateHandfillFields() {
    const actionType = actionTypeSelect?.value || "";
    const isNewGoal = actionType === "新建目标";
    if (actionTargetGoalField) actionTargetGoalField.hidden = isNewGoal;
    if (actionNewGoalNameField) actionNewGoalNameField.hidden = !isNewGoal;
    if (actionGoalTypeField) {
      const showType =
        isNewGoal || actionType === "降级目标" || actionType === "升级为主线";
      actionGoalTypeField.hidden = !showType;
    }
  }

  anchorEditBtn?.addEventListener("click", () => {
    showAnchorForm(true);
  });

  anchorCancelBtn?.addEventListener("click", () => {
    showAnchorForm(false);
  });

  anchorForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const confirmed = window.confirm(
      "定位锚是战略不动点，修订属于重大动作。确认保存？"
    );
    if (!confirmed) return;

    const payload = {};
    Object.keys(formFields).forEach((key) => {
      payload[key] = formFields[key]?.value || "";
    });

    try {
      const anchor = await apiRequest("/api/positioning/anchor", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setAnchorDisplay(anchor);
      showAnchorForm(false);
      showToast("定位锚已保存");
    } catch (error) {
      showToast(error.message || "保存失败", "error");
    }
  });

  calibrationForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      calibrated_at: document.getElementById("calibration-date")?.value || "",
      cycle: document.getElementById("calibration-cycle")?.value || "触发式",
      primary_contradiction:
        document.getElementById("calibration-contradiction")?.value || "",
      doing_but_shouldnt:
        document.getElementById("calibration-doing-shouldnt")?.value || "",
      should_but_not_doing:
        document.getElementById("calibration-should-not-doing")?.value || "",
      alignment_review:
        document.getElementById("calibration-alignment-review")?.value || "",
      conclusion: document.getElementById("calibration-conclusion")?.value || "",
    };

    try {
      await apiRequest("/api/positioning/calibrations", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      calibrationForm.reset();
      const dateInput = document.getElementById("calibration-date");
      if (dateInput) dateInput.value = todayInputValue();
      await loadCalibrations(true);
      showToast("校准记录已保存");
    } catch (error) {
      showToast(error.message || "保存失败", "error");
    }
  });

  handfillForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!activeCalibrationId) {
      showToast("请先选择一条校准记录", "error");
      return;
    }

    const actionType = actionTypeSelect?.value || "";
    const payload = {
      action_type: actionType,
      reason: document.getElementById("action-reason")?.value || "",
      payload: {},
    };

    if (actionType === "新建目标") {
      payload.payload = {
        name: document.getElementById("action-new-goal-name")?.value || "",
        type: document.getElementById("action-goal-type")?.value || "",
      };
    } else {
      payload.target_goal_id = Number(
        document.getElementById("action-target-goal-id")?.value || 0
      );
      if (actionType === "降级目标" || actionType === "升级为主线") {
        payload.payload = {
          type: document.getElementById("action-goal-type")?.value || "",
        };
      }
    }

    try {
      await apiRequest(
        `/api/positioning/calibrations/${activeCalibrationId}/actions`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );
      handfillForm.reset();
      updateHandfillFields();
      await selectCalibration(activeCalibrationId);
      showToast("已添加 pending 建议");
    } catch (error) {
      showToast(error.message || "添加失败", "error");
    }
  });

  actionTypeSelect?.addEventListener("change", updateHandfillFields);

  const dateInput = document.getElementById("calibration-date");
  if (dateInput) dateInput.value = todayInputValue();
  updateHandfillFields();

  Promise.all([loadAnchor(), loadCalibrations()]).catch((error) => {
    showToast(error.message || "加载定位页失败", "error");
  });
});