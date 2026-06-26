document.addEventListener("DOMContentLoaded", () => {
  const anchorDisplay = document.getElementById("anchor-display");
  const anchorForm = document.getElementById("anchor-form");
  const anchorEditBtn = document.getElementById("anchor-edit-btn");
  const anchorCancelBtn = document.getElementById("anchor-cancel-btn");
  const anchorEmptyGuide = document.getElementById("anchor-empty-guide");
  const anchorSection = document.getElementById("positioning-anchor-section");
  const calibrationForm = document.getElementById("calibration-form");
  const calibrationFormPanel = document.getElementById("calibration-form-panel");
  const newCalibrationBtn = document.getElementById("new-calibration-btn");
  const calibrationCancelBtn = document.getElementById("calibration-cancel-btn");
  const historyListEl = document.getElementById("calibration-history-list");
  const actionsListEl = document.getElementById("positioning-actions-list");
  const actionsContextHint = document.getElementById("actions-context-hint");
  const handfillForm = document.getElementById("action-handfill-form");
  const handfillDetails = document.getElementById("action-handfill-details");
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

  function hasText(value) {
    return Boolean((value || "").trim());
  }

  function displayValue(value, fallback = "—") {
    const text = (value || "").trim();
    return text ? escapeHtml(text) : fallback;
  }

  function todayInputValue() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${now.getFullYear()}-${month}-${day}`;
  }

  function isAnchorEmpty(anchor) {
    const data = anchor || {};
    return ![
      data.first_principle,
      data.identity_core,
      data.flywheel_def,
      data.current_stage,
      data.north_star,
    ].some(hasText);
  }

  function setAnchorDisplay(anchor) {
    const data = anchor || {};
    const empty = isAnchorEmpty(data);

    if (anchorSection) {
      anchorSection.classList.toggle("is-anchor-empty", empty);
    }
    if (anchorEmptyGuide) {
      anchorEmptyGuide.hidden = !empty;
    }

    if (displayFields.first_principle) {
      displayFields.first_principle.innerHTML = displayValue(data.first_principle);
    }
    if (displayFields.identity_core) {
      displayFields.identity_core.innerHTML = displayValue(data.identity_core);
    }
    if (displayFields.flywheel_def) {
      displayFields.flywheel_def.innerHTML = displayValue(data.flywheel_def);
    }
    if (displayFields.current_stage) {
      displayFields.current_stage.innerHTML = displayValue(data.current_stage);
    }
    if (displayFields.north_star) {
      const northStarText = hasText(data.north_star)
        ? escapeHtml(data.north_star)
        : "尚未设定北极星";
      displayFields.north_star.innerHTML = northStarText;
      displayFields.north_star.classList.toggle(
        "is-placeholder",
        !hasText(data.north_star)
      );
    }

    if (anchorUpdatedAtEl) {
      anchorUpdatedAtEl.textContent = data.updated_at
        ? `最近更新：${data.updated_at}`
        : "";
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
    if (anchorEmptyGuide) anchorEmptyGuide.hidden = show || !anchorSection?.classList.contains("is-anchor-empty");
  }

  function showCalibrationForm(show) {
    if (!calibrationFormPanel) return;
    calibrationFormPanel.hidden = !show;
    if (newCalibrationBtn) {
      newCalibrationBtn.textContent = show ? "收起表单" : "+ 新建校准";
    }
  }

  function statusLabel(status) {
    const labels = {
      pending: "待确认",
      confirmed: "已确认",
      rejected: "已拒绝",
    };
    return labels[status] || status;
  }

  function actionTargetLabel(action) {
    const payload = action.payload || {};
    if (hasText(payload.name)) return payload.name;
    if (action.target_goal_id) return `目标 #${action.target_goal_id}`;
    return "";
  }

  function setHandfillVisible(visible) {
    if (handfillDetails) handfillDetails.hidden = !visible;
  }

  function renderActions(actions) {
    if (!activeCalibrationId) {
      actionsListEl.innerHTML =
        '<p class="positioning-inline-empty">先选择校准轨迹中的记录</p>';
      setHandfillVisible(false);
      return;
    }

    setHandfillVisible(true);

    if (!actions || !actions.length) {
      actionsListEl.innerHTML =
        '<p class="positioning-inline-empty">本条校准暂无变更建议</p>';
      return;
    }

    actionsListEl.innerHTML = actions
      .map((action) => {
        const statusClass =
          action.status === "pending"
            ? "is-pending"
            : action.status === "confirmed"
              ? "is-confirmed"
              : "is-rejected";
        const targetLabel = actionTargetLabel(action);
        const targetHtml = targetLabel
          ? `<span class="positioning-action-target">${escapeHtml(targetLabel)}</span>`
          : "";
        const badgeClass =
          action.status === "pending"
            ? "positioning-action-badge is-pending"
            : "positioning-action-badge";
        return `
          <article class="positioning-action-item ${statusClass}">
            <div class="positioning-action-head">
              <div class="positioning-action-head-main">
                <span class="positioning-action-type">${escapeHtml(action.action_type)}</span>
                ${targetHtml}
              </div>
              <span class="${badgeClass}">${escapeHtml(statusLabel(action.status))}</span>
            </div>
            <p class="positioning-action-reason">${escapeHtml(action.reason)}</p>
          </article>`;
      })
      .join("");
  }

  function summarizeLine(text, fallback) {
    const value = (text || "").trim();
    return value || fallback;
  }

  function renderHistory() {
    if (!calibrations.length) {
      historyListEl.innerHTML =
        '<p class="positioning-inline-empty">尚无校准记录</p>';
      return;
    }

    historyListEl.innerHTML = calibrations
      .map((item, index) => {
        const active = item.id === activeCalibrationId ? " is-active" : "";
        const latest = index === 0 ? " is-latest" : "";
        const contradiction = summarizeLine(
          item.primary_contradiction,
          "未记录主要矛盾"
        );
        const conclusion = summarizeLine(item.conclusion, "未记录结论");
        return `
          <button
            type="button"
            class="positioning-timeline-item${active}${latest}"
            data-calibration-id="${item.id}"
          >
            <span class="positioning-timeline-rail" aria-hidden="true"></span>
            <span class="positioning-timeline-body">
              <span class="positioning-timeline-meta">
                <span class="positioning-history-date">${escapeHtml(item.calibrated_at)}</span>
                <span class="positioning-history-cycle">${escapeHtml(item.cycle)}</span>
              </span>
              <span class="positioning-timeline-contradiction">${escapeHtml(contradiction)}</span>
              <span class="positioning-timeline-conclusion">${escapeHtml(conclusion)}</span>
            </span>
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
      actionsContextHint.textContent = `当前选中：${date} 校准 · 目标变更确认区只读展示 pending · 确认 / 拒绝将在下一版本开放`;
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
          "选择校准轨迹中的记录后，目标变更确认区只读展示 pending 建议。确认 / 拒绝将在下一版本开放。";
      }
      setHandfillVisible(false);
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

  newCalibrationBtn?.addEventListener("click", () => {
    const willShow = calibrationFormPanel?.hidden !== false;
    showCalibrationForm(willShow);
  });

  calibrationCancelBtn?.addEventListener("click", () => {
    showCalibrationForm(false);
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
      showCalibrationForm(false);
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
  showCalibrationForm(false);

  Promise.all([loadAnchor(), loadCalibrations()]).catch((error) => {
    showToast(error.message || "加载定位页失败", "error");
  });
});