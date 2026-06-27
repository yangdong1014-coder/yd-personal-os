document.addEventListener("DOMContentLoaded", () => {
  const anchorDisplay = document.getElementById("anchor-display");
  const anchorForm = document.getElementById("anchor-form");
  const anchorEditBtn = document.getElementById("anchor-edit-btn");
  const anchorCancelBtn = document.getElementById("anchor-cancel-btn");
  const anchorEmptyGuide = document.getElementById("anchor-empty-guide");
  const anchorSection = document.getElementById("positioning-anchor-section");
  const calibrationForm = document.getElementById("calibration-form");
  const calibrationFormPanel = document.getElementById("calibration-form-panel");
  const calibrationIdInput = document.getElementById("calibration-id");
  const calibrationSubmitBtn = document.getElementById("calibration-submit-btn");
  const newCalibrationBtn = document.getElementById("new-calibration-btn");
  const calibrationCancelBtn = document.getElementById("calibration-cancel-btn");
  const historyListEl = document.getElementById("calibration-history-list");
  const actionsListEl = document.getElementById("positioning-actions-list");
  const actionsContextHint = document.getElementById("actions-context-hint");
  const handfillForm = document.getElementById("action-handfill-form");
  const handfillDetails = document.getElementById("action-handfill-details");
  const handfillSummary = document.getElementById("action-handfill-summary");
  const handfillSubmitBtn = document.getElementById("action-handfill-submit");
  const handfillCancelBtn = document.getElementById("action-handfill-cancel");
  const actionTypeSelect = document.getElementById("action-type");
  const actionTargetGoalField = document.getElementById("action-target-goal-field");
  const actionTargetGoalSelect = document.getElementById("action-target-goal-select");
  const actionNewGoalNameField = document.getElementById("action-new-goal-name-field");
  const actionGoalTypeField = document.getElementById("action-goal-type-field");
  const actionGoalTypeSelect = document.getElementById("action-goal-type");

  if (!anchorDisplay || !calibrationForm || !historyListEl || !actionsListEl) return;

  let activeCalibrationId = null;
  let editingCalibrationId = null;
  let editingActionId = null;
  let calibrations = [];
  let activeGoals = [];
  let currentActions = [];

  const STATUS_ORDER = ["pending", "confirmed", "rejected"];

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
    if (anchorEmptyGuide) {
      anchorEmptyGuide.hidden = show || !anchorSection?.classList.contains("is-anchor-empty");
    }
  }

  function resetCalibrationForm() {
    calibrationForm.reset();
    if (calibrationIdInput) calibrationIdInput.value = "";
    editingCalibrationId = null;
    const dateInput = document.getElementById("calibration-date");
    if (dateInput) dateInput.value = todayInputValue();
    if (calibrationSubmitBtn) calibrationSubmitBtn.textContent = "提交校准";
  }

  function showCalibrationForm(show) {
    if (!calibrationFormPanel) return;
    calibrationFormPanel.hidden = !show;
    if (newCalibrationBtn) {
      newCalibrationBtn.textContent = show ? "收起表单" : "+ 新建校准";
    }
    if (!show) {
      resetCalibrationForm();
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

  function nextStatus(status) {
    const index = STATUS_ORDER.indexOf(status);
    if (index === -1) return STATUS_ORDER[0];
    return STATUS_ORDER[(index + 1) % STATUS_ORDER.length];
  }

  function goalOptionLabel(goal) {
    return `${goal.name}（#${goal.id} · ${goal.type}）`;
  }

  function populateGoalSelect(selectedId = "") {
    if (!actionTargetGoalSelect) return;
    const selected = String(selectedId || "");
    actionTargetGoalSelect.innerHTML =
      '<option value="">请选择目标</option>' +
      activeGoals
        .map(
          (goal) =>
            `<option value="${goal.id}"${String(goal.id) === selected ? " selected" : ""}>${escapeHtml(goalOptionLabel(goal))}</option>`
        )
        .join("");
  }

  function syncGoalTypeFromSelect() {
    if (!actionTargetGoalSelect || !actionGoalTypeSelect) return;
    const goalId = Number(actionTargetGoalSelect.value || 0);
    const goal = activeGoals.find((item) => item.id === goalId);
    if (goal) {
      actionGoalTypeSelect.value = goal.type;
    }
  }

  function actionTargetLabel(action) {
    const payload = action.payload || {};
    if (hasText(payload.name)) return payload.name;
    if (action.target_goal_id) {
      const goal = activeGoals.find((item) => item.id === action.target_goal_id);
      if (goal) return goalOptionLabel(goal);
      return `目标 #${action.target_goal_id}`;
    }
    return "";
  }

  function setHandfillVisible(visible) {
    if (handfillDetails) handfillDetails.hidden = !visible;
  }

  function resetActionForm() {
    handfillForm?.reset();
    editingActionId = null;
    if (handfillSubmitBtn) handfillSubmitBtn.textContent = "添加";
    if (handfillCancelBtn) handfillCancelBtn.hidden = true;
    if (handfillSummary) {
      handfillSummary.textContent = "手填变更意图（仅记录，不联动目标表）";
    }
    populateGoalSelect();
    updateHandfillFields();
  }

  function openActionHandfill(action = null) {
    if (!handfillDetails) return;
    handfillDetails.hidden = false;
    handfillDetails.open = true;
    if (action) {
      editingActionId = action.id;
      if (handfillSubmitBtn) handfillSubmitBtn.textContent = "保存修改";
      if (handfillCancelBtn) handfillCancelBtn.hidden = false;
      if (handfillSummary) handfillSummary.textContent = "编辑变更意图";
      if (actionTypeSelect) actionTypeSelect.value = action.action_type || "";
      if (document.getElementById("action-reason")) {
        document.getElementById("action-reason").value = action.reason || "";
      }
      const payload = action.payload || {};
      if (action.action_type === "新建目标") {
        if (document.getElementById("action-new-goal-name")) {
          document.getElementById("action-new-goal-name").value = payload.name || "";
        }
        if (actionGoalTypeSelect && payload.type) {
          actionGoalTypeSelect.value = payload.type;
        }
      } else {
        populateGoalSelect(action.target_goal_id || "");
        if (actionGoalTypeSelect && payload.type) {
          actionGoalTypeSelect.value = payload.type;
        } else {
          syncGoalTypeFromSelect();
        }
      }
      updateHandfillFields();
    } else {
      resetActionForm();
    }
  }

  function bindActionItemEvents() {
    actionsListEl.querySelectorAll("[data-action-edit]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        const actionId = Number(button.dataset.actionEdit);
        const action = currentActions.find((item) => item.id === actionId);
        if (action) openActionHandfill(action);
      });
    });

    actionsListEl.querySelectorAll("[data-action-delete]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        const actionId = Number(button.dataset.actionDelete);
        if (!window.confirm("确认删除这条变更意图记录？")) return;
        try {
          await apiRequest(`/api/positioning/actions/${actionId}`, {
            method: "DELETE",
          });
          if (editingActionId === actionId) resetActionForm();
          await selectCalibration(activeCalibrationId);
          showToast("变更意图已删除");
        } catch (error) {
          showToast(error.message || "删除失败", "error");
        }
      });
    });

    actionsListEl.querySelectorAll("[data-action-status]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        const actionId = Number(button.dataset.actionStatus);
        const action = currentActions.find((item) => item.id === actionId);
        if (!action) return;
        const newStatus = nextStatus(action.status);
        try {
          await apiRequest(`/api/positioning/actions/${actionId}/status`, {
            method: "PATCH",
            body: JSON.stringify({ status: newStatus }),
          });
          await selectCalibration(activeCalibrationId);
          showToast(`状态已标记为「${statusLabel(newStatus)}」`);
        } catch (error) {
          showToast(error.message || "更新状态失败", "error");
        }
      });
    });
  }

  function renderActions(actions) {
    currentActions = actions || [];

    if (!activeCalibrationId) {
      actionsListEl.innerHTML =
        '<p class="positioning-inline-empty">先选择校准轨迹中的记录</p>';
      setHandfillVisible(false);
      return;
    }

    setHandfillVisible(true);

    if (!currentActions.length) {
      actionsListEl.innerHTML =
        '<p class="positioning-inline-empty">本条校准暂无变更意图</p>';
      return;
    }

    actionsListEl.innerHTML = currentActions
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
            ? "positioning-action-badge is-pending is-clickable"
            : "positioning-action-badge is-clickable";
        return `
          <article class="positioning-action-item ${statusClass}">
            <div class="positioning-action-head">
              <div class="positioning-action-head-main">
                <span class="positioning-action-type">${escapeHtml(action.action_type)}</span>
                ${targetHtml}
              </div>
              <div class="positioning-action-toolbar">
                <button
                  type="button"
                  class="${badgeClass}"
                  data-action-status="${action.id}"
                  title="点击切换状态标签"
                >${escapeHtml(statusLabel(action.status))}</button>
                <button type="button" class="btn btn-sm btn-ghost" data-action-edit="${action.id}">编辑</button>
                <button type="button" class="btn btn-sm btn-ghost" data-action-delete="${action.id}">删除</button>
              </div>
            </div>
            <p class="positioning-action-reason">${escapeHtml(action.reason)}</p>
          </article>`;
      })
      .join("");

    bindActionItemEvents();
  }

  function summarizeLine(text, fallback) {
    const value = (text || "").trim();
    return value || fallback;
  }

  function fillCalibrationForm(item) {
    if (!item) return;
    if (calibrationIdInput) calibrationIdInput.value = String(item.id || "");
    const dateInput = document.getElementById("calibration-date");
    if (dateInput) dateInput.value = item.calibrated_at || "";
    const cycleInput = document.getElementById("calibration-cycle");
    if (cycleInput) cycleInput.value = item.cycle || "触发式";
    const contradictionInput = document.getElementById("calibration-contradiction");
    if (contradictionInput) contradictionInput.value = item.primary_contradiction || "";
    const alignmentInput = document.getElementById("calibration-alignment-review");
    if (alignmentInput) alignmentInput.value = item.alignment_review || "";
    const doingInput = document.getElementById("calibration-doing-shouldnt");
    if (doingInput) doingInput.value = item.doing_but_shouldnt || "";
    const shouldInput = document.getElementById("calibration-should-not-doing");
    if (shouldInput) shouldInput.value = item.should_but_not_doing || "";
    const conclusionInput = document.getElementById("calibration-conclusion");
    if (conclusionInput) conclusionInput.value = item.conclusion || "";
  }

  function openCalibrationEdit(item) {
    editingCalibrationId = item.id;
    fillCalibrationForm(item);
    if (calibrationSubmitBtn) calibrationSubmitBtn.textContent = "保存修改";
    showCalibrationForm(true);
  }

  function bindHistoryEvents() {
    historyListEl.querySelectorAll("[data-calibration-select]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = Number(button.dataset.calibrationSelect);
        selectCalibration(id);
      });
    });

    historyListEl.querySelectorAll("[data-calibration-edit]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        const id = Number(button.dataset.calibrationEdit);
        const item = calibrations.find((entry) => entry.id === id);
        if (item) openCalibrationEdit(item);
      });
    });

    historyListEl.querySelectorAll("[data-calibration-delete]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        const id = Number(button.dataset.calibrationDelete);
        if (!window.confirm("确认删除这条校准记录？")) return;
        try {
          await apiRequest(`/api/positioning/calibrations/${id}`, {
            method: "DELETE",
          });
          if (editingCalibrationId === id) resetCalibrationForm();
          if (activeCalibrationId === id) activeCalibrationId = null;
          await loadCalibrations();
          showToast("校准记录已删除");
        } catch (error) {
          showToast(error.message || "删除失败", "error");
        }
      });
    });
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
          <div class="positioning-timeline-item${active}${latest}">
            <span class="positioning-timeline-rail" aria-hidden="true"></span>
            <div class="positioning-timeline-body">
              <div class="positioning-timeline-meta">
                <button
                  type="button"
                  class="positioning-timeline-select"
                  data-calibration-select="${item.id}"
                >
                  <span class="positioning-history-date">${escapeHtml(item.calibrated_at)}</span>
                  <span class="positioning-history-cycle">${escapeHtml(item.cycle)}</span>
                </button>
                <span class="positioning-timeline-actions">
                  <button type="button" class="btn btn-sm btn-ghost" data-calibration-edit="${item.id}">编辑</button>
                  <button type="button" class="btn btn-sm btn-ghost" data-calibration-delete="${item.id}">删除</button>
                </span>
              </div>
              <button
                type="button"
                class="positioning-timeline-select positioning-timeline-select-body"
                data-calibration-select="${item.id}"
              >
                <span class="positioning-timeline-contradiction">${escapeHtml(contradiction)}</span>
                <span class="positioning-timeline-conclusion">${escapeHtml(conclusion)}</span>
              </button>
            </div>
          </div>`;
      })
      .join("");

    bindHistoryEvents();
  }

  async function selectCalibration(calibrationId) {
    activeCalibrationId = calibrationId;
    renderHistory();
    const detail = await apiRequest(`/api/positioning/calibrations/${calibrationId}`);
    if (actionsContextHint) {
      const date = detail.calibration?.calibrated_at || "";
      actionsContextHint.textContent = `当前选中：${date} 校准 · 在此记录目标变更意图，status 仅为人工备注标签`;
    }
    renderActions(detail.actions || []);
  }

  async function loadGoals() {
    const goals = await apiRequest("/api/goals");
    activeGoals = (goals || []).filter(
      (goal) => (goal.status || "active") === "active"
    );
    populateGoalSelect();
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
          "选择校准轨迹中的记录后，在此记录目标变更意图。status 仅为人工备注标签，不会改写目标模块。";
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

  function buildActionPayload() {
    const actionType = actionTypeSelect?.value || "";
    const payload = {
      action_type: actionType,
      reason: document.getElementById("action-reason")?.value || "",
      payload: {},
    };

    if (actionType === "新建目标") {
      payload.payload = {
        name: document.getElementById("action-new-goal-name")?.value || "",
        type: actionGoalTypeSelect?.value || "",
      };
    } else {
      payload.target_goal_id = Number(actionTargetGoalSelect?.value || 0);
      if (actionType === "降级目标" || actionType === "升级为主线") {
        payload.payload = {
          type: actionGoalTypeSelect?.value || "",
        };
      }
    }
    return payload;
  }

  anchorEditBtn?.addEventListener("click", () => {
    showAnchorForm(true);
  });

  anchorCancelBtn?.addEventListener("click", () => {
    showAnchorForm(false);
  });

  newCalibrationBtn?.addEventListener("click", () => {
    const willShow = calibrationFormPanel?.hidden !== false;
    if (willShow) {
      resetCalibrationForm();
    }
    showCalibrationForm(willShow);
  });

  calibrationCancelBtn?.addEventListener("click", () => {
    showCalibrationForm(false);
  });

  handfillCancelBtn?.addEventListener("click", () => {
    resetActionForm();
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
      if (editingCalibrationId) {
        await apiRequest(`/api/positioning/calibrations/${editingCalibrationId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        showToast("校准记录已更新");
      } else {
        await apiRequest("/api/positioning/calibrations", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        showToast("校准记录已保存");
      }
      showCalibrationForm(false);
      await loadCalibrations(!editingCalibrationId);
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

    const payload = buildActionPayload();

    try {
      if (editingActionId) {
        await apiRequest(`/api/positioning/actions/${editingActionId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        showToast("变更意图已更新");
      } else {
        await apiRequest(
          `/api/positioning/calibrations/${activeCalibrationId}/actions`,
          {
            method: "POST",
            body: JSON.stringify(payload),
          }
        );
        showToast("已记录变更意图");
      }
      resetActionForm();
      await selectCalibration(activeCalibrationId);
    } catch (error) {
      showToast(error.message || "保存失败", "error");
    }
  });

  actionTypeSelect?.addEventListener("change", updateHandfillFields);
  actionTargetGoalSelect?.addEventListener("change", syncGoalTypeFromSelect);

  const dateInput = document.getElementById("calibration-date");
  if (dateInput) dateInput.value = todayInputValue();
  updateHandfillFields();
  showCalibrationForm(false);

  Promise.all([loadAnchor(), loadGoals(), loadCalibrations()]).catch((error) => {
    showToast(error.message || "加载定位页失败", "error");
  });
});