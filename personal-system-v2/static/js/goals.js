document.addEventListener("DOMContentLoaded", () => {
  const goalsList = document.getElementById("goals-list");
  const createGoalBtn = document.getElementById("create-goal-btn");

  if (!goalsList) return;

  let cachedGoals = [];
  const expandedGoalIds = new Set();
  const expandedProjectIds = new Set();
  const PRIORITY_LABELS = { high: "高", medium: "中", low: "低" };
  const PRIORITY_SCORES = { high: 3, medium: 2, low: 1 };
  const VISIBLE_PROJECT_LIMIT = 3;

  function normalizePriority(priority) {
    return Object.prototype.hasOwnProperty.call(PRIORITY_LABELS, priority)
      ? priority
      : "medium";
  }

  function priorityLabel(priority) {
    return PRIORITY_LABELS[normalizePriority(priority)];
  }

  function priorityScore(priority) {
    return PRIORITY_SCORES[normalizePriority(priority)];
  }

  function projectPriorityClasses(priority) {
    const current = normalizePriority(priority);
    return `project-priority-${current} priority-strip-${current}`;
  }

  function projectPriorityHint(priority) {
    return `项目优先级：${priorityLabel(priority)}`;
  }

  function buildParenMeta(parts, extraClass = "") {
    const text = parts.map((part) => escapeHtml(String(part))).join(" · ");
    const classNames = ["inline-meta", "muted-inline-meta", "compact-meta", extraClass]
      .filter(Boolean)
      .join(" ");
    return `<span class="${classNames}">（${text}）</span>`;
  }

  function buildPriorityOptions(selected) {
    const current = normalizePriority(selected);
    return Object.entries(PRIORITY_LABELS)
      .map(
        ([value, label]) =>
          `<option value="${escapeAttr(value)}"${value === current ? " selected" : ""}>${escapeHtml(label)}优先级</option>`
      )
      .join("");
  }

  function todayKey() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${now.getFullYear()}-${month}-${day}`;
  }

  function isTodayProgress(task) {
    return Number(task.today_progress) === 1 && task.today_progress_date === todayKey();
  }

  function calculateProjectStats(tasks) {
    return tasks.reduce(
      (stats, task) => {
        stats.total += 1;
        if (isTodayProgress(task)) stats.today += 1;
        if (task.status === "待处理") stats.pending += 1;
        if (task.status === "进行中") stats.doing += 1;
        if (task.status === "完成") stats.done += 1;
        stats.open = stats.pending + stats.doing;
        return stats;
      },
      { total: 0, today: 0, pending: 0, doing: 0, done: 0, open: 0 }
    );
  }

  function inferProjectStatus(stats) {
    if (stats.today > 0) return "今日推进中";
    if (stats.doing > 0) return "推进中";
    if (stats.pending > 0) return "待推进";
    if (stats.total > 0) return "已完成";
    return "暂无任务";
  }

  function compareTasks(a, b) {
    const statusRank = { 进行中: 3, 待处理: 2, 完成: 1 };
    const aKey = [
      priorityScore(a.priority),
      isTodayProgress(a) ? 1 : 0,
      statusRank[a.status] || 0,
      a.created_at || "",
    ];
    const bKey = [
      priorityScore(b.priority),
      isTodayProgress(b) ? 1 : 0,
      statusRank[b.status] || 0,
      b.created_at || "",
    ];
    for (let i = 0; i < aKey.length; i += 1) {
      if (aKey[i] > bKey[i]) return -1;
      if (aKey[i] < bKey[i]) return 1;
    }
    return 0;
  }

  function compareProjects(a, b) {
    const aKey = [
      priorityScore(a.priority),
      a.stats.today,
      a.stats.doing,
      a.stats.open,
      a.created_at || "",
    ];
    const bKey = [
      priorityScore(b.priority),
      b.stats.today,
      b.stats.doing,
      b.stats.open,
      b.created_at || "",
    ];
    for (let i = 0; i < aKey.length; i += 1) {
      if (aKey[i] > bKey[i]) return -1;
      if (aKey[i] < bKey[i]) return 1;
    }
    return 0;
  }

  function enrichProject(project, tasks) {
    const stats = calculateProjectStats(tasks);
    return {
      ...project,
      stats,
      status: inferProjectStatus(stats),
    };
  }

  function findMainline(goals, excludeId = null) {
    return (
      goals.find((g) => g.type === "当前主线" && g.id !== excludeId) || null
    );
  }

  function confirmMainlineSwitch(mainline) {
    return window.confirm(
      `当前主线已是「${mainline.name}」，确认切换吗？`
    );
  }

  function buildGoalTypeOptions(selected) {
    return (window.GOAL_TYPES || [])
      .map(
        (t) =>
          `<option value="${escapeAttr(t)}"${t === selected ? " selected" : ""}>${escapeHtml(t)}</option>`
      )
      .join("");
  }

  function openGoalEditModal(goal) {
    showAIModal({
      title: `编辑目标 — ${goal.name}`,
      bodyHtml: `
        <div class="stacked-form">
          <label class="form-row">
            <span class="form-label">目标名称</span>
            <input type="text" id="edit-goal-name" class="input full-width" value="${escapeAttr(goal.name)}" required>
          </label>
          <label class="form-row">
            <span class="form-label">目标类型</span>
            <select id="edit-goal-type" class="select full-width">${buildGoalTypeOptions(goal.type)}</select>
          </label>
        </div>
      `,
      confirmLabel: "保存",
      loadingLabel: "保存中…",
      onConfirm: async () => {
        const name = document.getElementById("edit-goal-name").value.trim();
        const type = document.getElementById("edit-goal-type").value;
        if (!name) {
          throw new Error("目标名称不能为空");
        }
        if (type === "当前主线" && type !== goal.type) {
          const existing = findMainline(cachedGoals, goal.id);
          if (existing && !confirmMainlineSwitch(existing)) {
            throw new Error("已取消切换当前主线");
          }
        }
        await apiRequest(`/api/goals/${goal.id}`, {
          method: "PATCH",
          body: JSON.stringify({ name, type }),
        });
        showToast("目标已更新", "success");
        await loadGoals();
      },
    });
  }

  function openProjectEditModal(project) {
    showAIModal({
      title: `编辑项目 — ${project.name}`,
      bodyHtml: `
        <div class="stacked-form">
          <label class="form-row">
            <span class="form-label">项目名称</span>
            <input type="text" id="edit-project-name" class="input full-width" value="${escapeAttr(project.name)}" required>
          </label>
          <label class="form-row">
            <span class="form-label">项目优先级</span>
            <select id="edit-project-priority" class="select full-width">${buildPriorityOptions(project.priority)}</select>
          </label>
        </div>
      `,
      confirmLabel: "保存",
      loadingLabel: "保存中…",
      onConfirm: async () => {
        const name = document.getElementById("edit-project-name").value.trim();
        const priority = document.getElementById("edit-project-priority").value;
        if (!name) {
          throw new Error("项目名称不能为空");
        }
        await apiRequest(`/api/projects/${project.id}`, {
          method: "PATCH",
          body: JSON.stringify({ name, priority }),
        });
        showToast("项目已更新", "success");
        await loadGoals();
      },
    });
  }

  function openCreateProjectModal(goal) {
    showAIModal({
      title: `添加项目 — ${goal.name}`,
      bodyHtml: `
        <div class="stacked-form create-entity-form">
          <label class="form-row">
            <span class="form-label">项目名称</span>
            <input type="text" id="create-project-name" class="input full-width" placeholder="新建项目名称" required>
          </label>
          <label class="form-row">
            <span class="form-label">项目优先级</span>
            <select id="create-project-priority" class="select full-width">${buildPriorityOptions("medium")}</select>
          </label>
        </div>
      `,
      confirmLabel: "添加项目",
      loadingLabel: "添加中…",
      onConfirm: async () => {
        const name = document.getElementById("create-project-name").value.trim();
        const priority = document.getElementById("create-project-priority").value;
        if (!name) {
          throw new Error("项目名称不能为空");
        }
        await apiRequest("/api/projects", {
          method: "POST",
          body: JSON.stringify({ goal_id: goal.id, name, priority }),
        });
        showToast("项目已添加", "success");
        await loadGoals();
      },
    });

    document.getElementById("create-project-name")?.focus();
  }

  async function handleAIDecompose(goal, button) {
    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "拆解中…";

    try {
      const result = await apiRequest("/api/ai/decompose-goal", {
        method: "POST",
        body: JSON.stringify({ goal_id: goal.id }),
      });

      showAIModal({
        title: `AI 项目拆解 — ${result.goal_name}`,
        bodyHtml: buildProjectsDraftHtml(result.projects),
        confirmLabel: "确认创建",
        loadingLabel: "创建中…",
        onConfirm: async () => {
          const names = readSelectedProjectNames();
          if (names.length === 0) {
            throw new Error("请至少选择一个项目");
          }
          for (const name of names) {
            await apiRequest("/api/projects", {
              method: "POST",
              body: JSON.stringify({ goal_id: goal.id, name }),
            });
          }
          await loadGoals();
        },
      });
    } catch (err) {
      showToast(err.message || "AI 拆解失败", "error");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  function renderEmpty() {
    goalsList.innerHTML = `
      <div class="empty-state">
        <strong>添加第一个目标</strong>
        点击右上角「新建目标」开始
      </div>
    `;
  }

  async function submitCreateGoal() {
    const nameInput = document.getElementById("goal-name");
    const typeSelect = document.getElementById("goal-type");
    if (!nameInput || !typeSelect) {
      throw new Error("表单未就绪");
    }

    const name = nameInput.value.trim();
    if (!name) {
      throw new Error("目标名称不能为空");
    }

    const goalType = typeSelect.value;
    if (goalType === "当前主线") {
      const existing = findMainline(cachedGoals);
      if (existing && !confirmMainlineSwitch(existing)) {
        typeSelect.value = "年度";
        throw new Error("已取消切换当前主线");
      }
    }

    await apiRequest("/api/goals", {
      method: "POST",
      body: JSON.stringify({ name, type: goalType }),
    });
    showToast("目标已保存", "success");
    await loadGoals();
  }

  function openCreateGoalModal() {
    showAIModal({
      title: "新建目标",
      bodyHtml: `
        <div class="stacked-form create-entity-form">
          <label class="form-row">
            <span class="form-label">目标名称</span>
            <input type="text" id="goal-name" class="input full-width" placeholder="目标名称" required>
          </label>
          <label class="form-row">
            <span class="form-label">目标类型</span>
            <select id="goal-type" class="select full-width">${buildGoalTypeOptions("年度")}</select>
          </label>
        </div>
      `,
      confirmLabel: "添加目标",
      loadingLabel: "添加中…",
      onConfirm: submitCreateGoal,
    });

    const typeSelect = document.getElementById("goal-type");
    if (!typeSelect) return;
    typeSelect.addEventListener("change", () => {
      if (typeSelect.value !== "当前主线") return;
      const existing = findMainline(cachedGoals);
      if (existing && !confirmMainlineSwitch(existing)) {
        typeSelect.value = "年度";
      }
    });
  }

  function isGoalProjectsExpanded(goalId) {
    return expandedGoalIds.has(Number(goalId));
  }

  function setGoalProjectsExpanded(goalId, expanded) {
    const id = Number(goalId);
    if (!Number.isFinite(id)) return;
    if (expanded) {
      expandedGoalIds.add(id);
    } else {
      expandedGoalIds.delete(id);
    }
  }

  function syncGoalProjectsToggle(card, goalId) {
    const toggleBtn = card.querySelector(".goal-projects-toggle");
    const morePanel = card.querySelector(".goal-projects-more");
    if (!toggleBtn || !morePanel) return;

    const expanded = isGoalProjectsExpanded(goalId);
    morePanel.hidden = !expanded;
    toggleBtn.textContent = expanded ? "收起" : toggleBtn.dataset.collapsedLabel;
    toggleBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
  }

  function handleGoalProjectsToggle(event) {
    const toggleBtn = event.target.closest(".goal-projects-toggle");
    if (!toggleBtn || !goalsList.contains(toggleBtn)) return;

    const goalId = Number(toggleBtn.dataset.goalId);
    if (!Number.isFinite(goalId)) return;

    const card = toggleBtn.closest(".goal-group-card");
    if (!card) return;

    setGoalProjectsExpanded(goalId, !isGoalProjectsExpanded(goalId));
    syncGoalProjectsToggle(card, goalId);
  }

  function isProjectTasksExpanded(projectId) {
    return expandedProjectIds.has(Number(projectId));
  }

  function setProjectTasksExpanded(projectId, expanded) {
    const id = Number(projectId);
    if (!Number.isFinite(id)) return;
    if (expanded) {
      expandedProjectIds.add(id);
    } else {
      expandedProjectIds.delete(id);
    }
  }

  function syncProjectTasksToggle(entry, projectId) {
    const toggleBtn = entry.querySelector(".goal-project-tasks-toggle");
    const tasksPanel = entry.querySelector(".goal-project-tasks-panel");
    if (!toggleBtn || !tasksPanel) return;

    const expanded = isProjectTasksExpanded(projectId);
    tasksPanel.hidden = !expanded;
    toggleBtn.textContent = expanded ? "收起任务" : "展开任务";
    toggleBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
  }

  function handleProjectTasksToggle(event) {
    const toggleBtn = event.target.closest(".goal-project-tasks-toggle");
    if (!toggleBtn || !goalsList.contains(toggleBtn)) return;

    const projectId = Number(toggleBtn.dataset.projectId);
    if (!Number.isFinite(projectId)) return;

    const entry = toggleBtn.closest(".goal-project-entry");
    if (!entry) return;

    setProjectTasksExpanded(projectId, !isProjectTasksExpanded(projectId));
    syncProjectTasksToggle(entry, projectId);
  }

  function renderGoalProjectTaskItem(task) {
    const priority = priorityLabel(task.priority);
    const todayLabel = isTodayProgress(task) ? "今日推进" : "—";
    return `
      <li class="goal-project-task-item">
        <span class="goal-project-task-name title-with-context">
          ${escapeHtml(task.name)}${buildParenMeta([priority, task.status, todayLabel])}
        </span>
      </li>
    `;
  }

  function renderProjectTasksPanel(project, tasks) {
    const isTasksExpanded = isProjectTasksExpanded(project.id);
    const sortedTasks = [...tasks].sort(compareTasks);

    return `
      <div class="goal-project-tasks-panel"${isTasksExpanded ? "" : " hidden"}>
        ${
          sortedTasks.length > 0
            ? `<ul class="goal-project-task-list">
                ${sortedTasks.map((task) => renderGoalProjectTaskItem(task)).join("")}
              </ul>`
            : '<p class="goal-project-task-empty muted">暂无关联任务</p>'
        }
      </div>
    `;
  }

  function renderProjectItem(project, tasks = []) {
    const stats = project.stats || {};
    const isTasksExpanded = isProjectTasksExpanded(project.id);
    return `
      <li class="goal-project-entry" data-project-id="${project.id}">
        <div
          class="goal-project-item ${projectPriorityClasses(project.priority)}"
          title="${escapeAttr(projectPriorityHint(project.priority))}"
          aria-label="项目 ${escapeAttr(project.name)}，${escapeAttr(projectPriorityHint(project.priority))}"
        >
          <span class="project-priority-dot" aria-hidden="true"></span>
          <div class="goal-project-item-main">
            <span class="goal-project-name title-with-context">
              ${escapeHtml(project.name)}${buildParenMeta([
                project.status,
                `今日 ${stats.today}`,
                `未完成 ${stats.open}`,
              ])}
            </span>
          </div>
          <div class="nested-item-actions">
            <button
              type="button"
              class="btn btn-sm btn-ghost goal-project-tasks-toggle"
              data-project-id="${project.id}"
              aria-expanded="${isTasksExpanded ? "true" : "false"}"
            >${isTasksExpanded ? "收起任务" : "展开任务"}</button>
            <button type="button" class="btn btn-sm btn-ghost btn-edit-project" data-project-id="${project.id}">编辑</button>
            <button type="button" class="btn btn-sm btn-ghost btn-delete-project" data-project-id="${project.id}">删除</button>
          </div>
        </div>
        ${renderProjectTasksPanel(project, tasks)}
      </li>
    `;
  }

  function bindGoalCard(card, goal, goalProjects) {
    const aiBtn = card.querySelector(".btn-ai");
    if (aiBtn) {
      aiBtn.addEventListener("click", (e) => {
        handleAIDecompose(goal, e.currentTarget);
      });
    }

    const editGoalBtn = card.querySelector(".btn-edit-goal");
    if (editGoalBtn) {
      editGoalBtn.addEventListener("click", () => {
        openGoalEditModal(goal);
      });
    }

    card.querySelectorAll(".btn-edit-project").forEach((btn) => {
      btn.addEventListener("click", () => {
        const projectId = parseInt(btn.dataset.projectId, 10);
        const project = goalProjects.find((p) => p.id === projectId);
        if (project) openProjectEditModal(project);
      });
    });

    const createProjectBtn = card.querySelector(".btn-create-project");
    if (createProjectBtn) {
      createProjectBtn.addEventListener("click", () => {
        openCreateProjectModal(goal);
      });
    }

    const deleteGoalBtn = card.querySelector(".btn-delete-goal");
    if (deleteGoalBtn) {
      deleteGoalBtn.addEventListener("click", async () => {
      const projectCount = goalProjects.length;
      const countHint =
        projectCount > 0
          ? `（当前含 ${projectCount} 个项目及下属任务）`
          : "";
      if (
        !window.confirm(
          `确定删除目标「${goal.name}」？${countHint}\n\n删除目标将级联删除其下所有项目与任务，操作不可撤销。`
        )
      ) {
        return;
      }
      try {
        await apiRequest(`/api/goals/${goal.id}`, { method: "DELETE" });
        showToast("目标已删除", "success");
        await loadGoals();
      } catch (err) {
        showToast(err.message, "error");
      }
      });
    }

    card.querySelectorAll(".btn-delete-project").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const projectId = parseInt(btn.dataset.projectId, 10);
        const project = goalProjects.find((p) => p.id === projectId);
        if (!project) return;
        if (
          !window.confirm(
            `确定删除项目「${project.name}」？\n\n删除项目将级联删除其下所有任务，操作不可撤销。`
          )
        ) {
          return;
        }
        try {
          await apiRequest(`/api/projects/${projectId}`, {
            method: "DELETE",
          });
          showToast("项目已删除", "success");
          await loadGoals();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    const typeSelect = card.querySelector(".goal-type-select");
    if (typeSelect) {
      typeSelect.addEventListener("change", async () => {
      const prev = goal.type;
      const next = typeSelect.value;

      if (next === "当前主线") {
        const existing = findMainline(cachedGoals, goal.id);
        if (existing && !confirmMainlineSwitch(existing)) {
          typeSelect.value = prev;
          return;
        }
      }

      try {
        await apiRequest(`/api/goals/${goal.id}`, {
          method: "PATCH",
          body: JSON.stringify({ type: next }),
        });
        await loadGoals();
      } catch (err) {
        typeSelect.value = prev;
        showToast(err.message, "error");
      }
      });
    }
  }

  async function loadGoals() {
    const [goals, projects, tasks] = await Promise.all([
      apiRequest("/api/goals"),
      apiRequest("/api/projects"),
      apiRequest("/api/tasks"),
    ]);
    cachedGoals = goals;

    const activeGoalIds = new Set(goals.map((goal) => goal.id));
    expandedGoalIds.forEach((goalId) => {
      if (!activeGoalIds.has(goalId)) expandedGoalIds.delete(goalId);
    });

    const activeProjectIds = new Set(projects.map((project) => project.id));
    expandedProjectIds.forEach((projectId) => {
      if (!activeProjectIds.has(projectId)) expandedProjectIds.delete(projectId);
    });

    const tasksByProject = {};
    tasks.forEach((task) => {
      if (!tasksByProject[task.project_id]) tasksByProject[task.project_id] = [];
      tasksByProject[task.project_id].push(task);
    });

    const projectsByGoal = {};
    projects.forEach((p) => {
      const enriched = enrichProject(p, tasksByProject[p.id] || []);
      if (!projectsByGoal[p.goal_id]) projectsByGoal[p.goal_id] = [];
      projectsByGoal[p.goal_id].push(enriched);
    });
    Object.values(projectsByGoal).forEach((list) => list.sort(compareProjects));

    goalsList.innerHTML = "";

    if (goals.length === 0) {
      renderEmpty();
      return;
    }

    goals.forEach((goal) => {
      const card = document.createElement("article");
      card.className = "entity-card goal-group-card";
      card.dataset.goalId = goal.id;

      const goalProjects = projectsByGoal[goal.id] || [];
      const goalStats = goalProjects.reduce(
        (acc, project) => {
          acc.projects += 1;
          acc.open += project.stats.open;
          acc.today += project.stats.today;
          return acc;
        },
        { projects: 0, open: 0, today: 0 }
      );

      const visibleProjects = goalProjects.slice(0, VISIBLE_PROJECT_LIMIT);
      const hiddenProjects = goalProjects.slice(VISIBLE_PROJECT_LIMIT);
      const hiddenCount = hiddenProjects.length;
      const isExpanded = isGoalProjectsExpanded(goal.id);

      card.innerHTML = `
        <div class="entity-header goal-group-head">
          <div class="goal-group-head-main">
            <h3 class="entity-title title-with-context">
              ${escapeHtml(goal.name)}${buildParenMeta(
                [
                  goal.type,
                  `项目 ${goalStats.projects}`,
                  `未完成 ${goalStats.open}`,
                  `今日 ${goalStats.today}`,
                ],
                "title-meta"
              )}
            </h3>
          </div>
          <div class="card-actions">
            <select class="select goal-type-select" title="修改目标类型">${buildGoalTypeOptions(goal.type)}</select>
            <button type="button" class="btn btn-sm btn-ai">AI拆解</button>
            <button type="button" class="btn btn-sm btn-ghost btn-edit-goal">编辑</button>
            <button type="button" class="btn btn-sm btn-ghost btn-delete-goal">删除</button>
          </div>
        </div>
        <div class="goal-projects-block">
          <div class="goal-projects-block-head">
            <div class="goal-projects-title-row">
              <h4 class="nested-title">重点项目</h4>
            </div>
            <div class="goal-projects-actions">
              ${
                hiddenCount > 0
                  ? `<button
                      type="button"
                      class="btn btn-sm btn-ghost btn-toggle-goal-projects goal-projects-toggle"
                      data-goal-id="${goal.id}"
                      data-collapsed-label="展开全部（${goalProjects.length}）"
                      aria-expanded="${isExpanded ? "true" : "false"}"
                    >${isExpanded ? "收起" : `展开全部（${goalProjects.length}）`}</button>`
                  : ""
              }
              <button type="button" class="btn btn-sm btn-create-project">添加项目</button>
            </div>
          </div>
          <ul class="goal-project-list">
            ${
              visibleProjects.length > 0
                ? visibleProjects
                    .map((p) => renderProjectItem(p, tasksByProject[p.id] || []))
                    .join("")
                : '<li class="muted goal-project-empty">暂无项目</li>'
            }
          </ul>
          ${
            hiddenCount > 0
              ? `<ul class="goal-project-list goal-projects-more"${isExpanded ? "" : " hidden"}>
                  ${hiddenProjects
                    .map((p) => renderProjectItem(p, tasksByProject[p.id] || []))
                    .join("")}
                </ul>`
              : ""
          }
        </div>
      `;

      bindGoalCard(card, goal, goalProjects);
      goalsList.appendChild(card);
    });
  }

  goalsList.addEventListener("click", (event) => {
    handleGoalProjectsToggle(event);
    handleProjectTasksToggle(event);
  });

  if (createGoalBtn) {
    createGoalBtn.addEventListener("click", openCreateGoalModal);
  }

  loadGoals().catch((err) => console.error(err));
});

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
