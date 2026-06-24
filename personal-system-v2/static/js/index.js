document.addEventListener("DOMContentLoaded", () => {
  const goalEl = document.getElementById("dashboard-goal-content");
  const projectsEl = document.getElementById("dashboard-projects-content");
  const tasksEl = document.getElementById("dashboard-tasks-content");
  const briefingBtn = document.getElementById("ai-briefing-btn");
  const dispatchBtn = document.getElementById("ai-dispatch-btn");

  if (!goalEl || !projectsEl || !tasksEl) return;

  const TODAY_TASK_LIMIT = 3;
  const FOCUS_PROJECT_LIMIT = 5;
  const expandedProjectIds = new Set();
  let tasksByProject = {};
  let mainlineExpandMode = null;
  let currentMainlineGoal = null;
  let currentTodayTasks = [];

  function emptyState(strong, hint) {
    return `
      <div class="empty-state empty-state-compact">
        <strong>${escapeHtml(strong)}</strong>
        ${escapeHtml(hint)}
      </div>
    `;
  }

  function taskPriorityClass(priority) {
    if (priority === "高") return "is-high";
    if (priority === "中") return "is-medium";
    return "is-low";
  }

  function projectPriorityKey(priority) {
    if (priority === "high" || priority === "高") return "high";
    if (priority === "low" || priority === "低") return "low";
    return "medium";
  }

  function projectPriorityClasses(priority) {
    const key = projectPriorityKey(priority);
    return `project-priority-${key} priority-strip-${key}`;
  }

  function projectPriorityLabel(priority) {
    const labels = { high: "高", medium: "中", low: "低" };
    return labels[projectPriorityKey(priority)];
  }

  function priorityScore(project) {
    return Number(project.priority_score || project.display_priority_score || 0);
  }

  function projectStats(project) {
    return project.stats || {};
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

  function taskPriorityLabel(priority) {
    return projectPriorityLabel(priority);
  }

  function buildParenMeta(parts) {
    const text = parts.map((part) => escapeHtml(String(part))).join(" · ");
    return `<span class="inline-meta muted-inline-meta compact-meta">（${text}）</span>`;
  }

  function taskPriorityScore(priority) {
    const scores = { high: 3, medium: 2, low: 1 };
    return scores[projectPriorityKey(priority)] || 2;
  }

  function compareTasks(a, b) {
    const statusRank = { 进行中: 3, 待处理: 2, 完成: 1 };
    const aKey = [
      taskPriorityScore(a.priority),
      isTodayProgress(a) ? 1 : 0,
      statusRank[a.status] || 0,
      a.created_at || "",
    ];
    const bKey = [
      taskPriorityScore(b.priority),
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

  function collectProjects(data) {
    const projects = [];
    const seen = new Set();
    (data.goal_groups || []).forEach((goal) => {
      (goal.projects || []).forEach((project) => {
        if (seen.has(project.id)) return;
        seen.add(project.id);
        projects.push(project);
      });
    });
    (data.week_projects || []).forEach((project) => {
      if (seen.has(project.id)) return;
      seen.add(project.id);
      projects.push(project);
    });
    return projects;
  }

  function isKeyProject(project) {
    const stats = projectStats(project);
    const isHigh = project.priority === "high" || priorityScore(project) >= 3;
    return isHigh || stats.today > 0 || stats.doing > 0 || stats.open > 0;
  }

  function compareProjects(a, b) {
    const aStats = projectStats(a);
    const bStats = projectStats(b);
    const aKey = [
      priorityScore(a),
      aStats.today || 0,
      aStats.doing || 0,
      aStats.open || 0,
      a.recent_activity_at || "",
    ];
    const bKey = [
      priorityScore(b),
      bStats.today || 0,
      bStats.doing || 0,
      bStats.open || 0,
      b.recent_activity_at || "",
    ];
    for (let i = 0; i < aKey.length; i += 1) {
      if (aKey[i] > bKey[i]) return -1;
      if (aKey[i] < bKey[i]) return 1;
    }
    return 0;
  }

  function selectKeyProjects(data) {
    return collectProjects(data).filter(isKeyProject).sort(compareProjects);
  }

  function renderMainlineStatusHint(goal) {
    const stats = goal.stats || {};
    const today = Number(goal.today_task_count ?? stats.today ?? 0);
    if (today > 0) return "";
    return '<span class="meta-muted dashboard-mainline-hint">暂无今日推进</span>';
  }

  function getMainlineProjects(goal) {
    const projects = goal?.projects || [];
    return [...projects].sort(compareProjects);
  }

  function getMainlineTodayTasks(goal, todayTasks) {
    if (!goal) return [];
    return (todayTasks || []).filter((task) => task.goal_name === goal.name);
  }

  function renderMainlineProjectItem(project) {
    const stats = projectStats(project);

    return `
      <li
        class="mainline-expand-item dashboard-mainline-project-item ${projectPriorityClasses(project.priority || project.display_priority)}"
        title="项目优先级：${escapeAttr(projectPriorityLabel(project.priority || project.display_priority))}"
      >
        <div class="mainline-expand-item-main">
          <span class="project-priority-dot" aria-hidden="true"></span>
          <span class="mainline-expand-item-title">${escapeHtml(project.name || "未命名项目")}</span>
          <span class="mainline-expand-item-meta meta-muted">
            ${escapeHtml(project.status || "系统推导")} · 今日 ${Number(stats.today || project.today_task_count || 0)} · 未完成 ${Number(stats.open || project.open_task_count || 0)}
          </span>
        </div>
      </li>
    `;
  }

  function renderMainlineTaskContext(task, goal) {
    const projectName = task.project_name || "未归属项目";
    const goalName = task.goal_name || goal?.name || "";
    if (!goalName || goalName === goal?.name) {
      return escapeHtml(projectName);
    }
    return `${escapeHtml(projectName)}${buildInlineGoalContext(goalName)}`;
  }

  function renderMainlineTodayTaskItem(task, goal) {
    const priority = task.display_priority || taskPriorityLabel(task.priority);

    return `
      <li class="mainline-expand-item dashboard-mainline-task-item">
        <div class="mainline-expand-item-main">
          <span class="mainline-expand-item-title">${escapeHtml(task.name || "未命名任务")}</span>
          <span class="mainline-expand-item-meta muted-relation">
            ${renderMainlineTaskContext(task, goal)}
          </span>
        </div>
        <div class="mainline-expand-item-badges">
          <span class="relation-priority ${taskPriorityClass(task.display_priority || priority)}">${escapeHtml(priority)}</span>
          <span class="relation-pill">${escapeHtml(task.status || "待处理")}</span>
        </div>
      </li>
    `;
  }

  function renderMainlineProjectsPanel(goal) {
    const projects = getMainlineProjects(goal);
    if (!projects.length) {
      return '<p class="mainline-expand-empty muted">暂无关联项目</p>';
    }

    return `
      <ul class="mainline-expand-list dashboard-mainline-project-list">
        ${projects.map((project) => renderMainlineProjectItem(project)).join("")}
      </ul>
    `;
  }

  function renderMainlineTodayPanel(goal, todayTasks) {
    const tasks = getMainlineTodayTasks(goal, todayTasks);
    if (!tasks.length) {
      return '<p class="mainline-expand-empty muted">暂无今日推进任务</p>';
    }

    return `
      <ul class="mainline-expand-list dashboard-mainline-task-list">
        ${tasks.map((task) => renderMainlineTodayTaskItem(task, goal)).join("")}
      </ul>
    `;
  }

  function renderMainlineExpandPanel(goal, todayTasks) {
    if (!mainlineExpandMode) return "";

    const panelContent =
      mainlineExpandMode === "projects"
        ? renderMainlineProjectsPanel(goal)
        : renderMainlineTodayPanel(goal, todayTasks);

    return `
      <div class="mainline-expand-panel" data-mainline-panel="${mainlineExpandMode}">
        ${panelContent}
      </div>
    `;
  }

  function renderMainlineGoal(goal, todayTasks = currentTodayTasks) {
    currentMainlineGoal = goal || null;
    currentTodayTasks = todayTasks || [];

    if (!goal) {
      mainlineExpandMode = null;
      goalEl.innerHTML = emptyState(
        "暂无主线目标",
        "前往「目标」模块，创建类型为「当前主线」的目标"
      );
      return;
    }

    const stats = goal.stats || {};
    const projectCount = Number(goal.project_count ?? stats.projects ?? 0);
    const todayCount = Number(goal.today_task_count ?? stats.today ?? 0);

    goalEl.innerHTML = `
      <div class="dashboard-mainline-card dashboard-mainline-card--slim">
        <div class="dashboard-mainline-head">
          <h3 class="entity-title">${escapeHtml(goal.name)}</h3>
          <div class="relation-meta-line relation-meta-line--compact">
            <span class="tag">${escapeHtml(goal.type)}</span>
            ${renderMainlineStatusHint(goal)}
          </div>
        </div>
        <div class="dashboard-mainline-metric-actions" role="group" aria-label="主线目标统计">
          <button
            type="button"
            class="metric-action-button${mainlineExpandMode === "projects" ? " is-active" : ""}"
            data-mainline-expand="projects"
            data-action="toggle-mainline-panel"
            aria-expanded="${mainlineExpandMode === "projects" ? "true" : "false"}"
          >关联项目 <strong class="metric-action-value">${projectCount}</strong></button>
          <button
            type="button"
            class="metric-action-button${mainlineExpandMode === "today" ? " is-active" : ""}"
            data-mainline-expand="today"
            data-action="toggle-mainline-panel"
            aria-expanded="${mainlineExpandMode === "today" ? "true" : "false"}"
          >今日推进 <strong class="metric-action-value">${todayCount}</strong></button>
        </div>
        ${renderMainlineExpandPanel(goal, todayTasks)}
      </div>
    `;
  }

  function isInsideMainlineSection(event) {
    const section = document.getElementById("dashboard-goal");
    if (!section) return false;
    return event.composedPath().some((node) => {
      if (node === section || node === goalEl) return true;
      return node instanceof Element && section.contains(node);
    });
  }

  function handleMainlineExpandClick(event) {
    const button = event.target.closest("[data-mainline-expand]");
    if (!button || !goalEl.contains(button)) return;

    event.preventDefault();
    event.stopPropagation();

    const mode = button.dataset.mainlineExpand;
    if (mainlineExpandMode === mode) {
      mainlineExpandMode = null;
    } else {
      mainlineExpandMode = mode;
    }
    renderMainlineGoal(currentMainlineGoal, currentTodayTasks);
  }

  function handleMainlineOutsideClick(event) {
    if (!mainlineExpandMode) return;
    if (isInsideMainlineSection(event)) return;
    mainlineExpandMode = null;
    renderMainlineGoal(currentMainlineGoal, currentTodayTasks);
  }

  function renderProjectTaskItem(task, project) {
    const priority = task.display_priority || taskPriorityLabel(task.priority);
    const todayLabel = isTodayProgress(task) ? "今日推进" : "—";
    const contextProject = task.project_name || project.name || "未归属项目";
    const contextGoal = task.goal_name || project.goal_name;

    return `
      <li class="dashboard-project-task-item">
        <span class="dashboard-project-task-name title-with-context">
          ${escapeHtml(task.name || "未命名任务")}${buildParenMeta([
            priority,
            task.status || "待处理",
            todayLabel,
          ])}
        </span>
        <span class="dashboard-project-task-context muted-relation">
          ${escapeHtml(contextProject)}${buildInlineGoalContext(contextGoal)}
        </span>
      </li>
    `;
  }

  function renderProjectTasksPanel(project) {
    const projectId = Number(project.id);
    const tasks = tasksByProject[projectId] || [];
    const sortedTasks = [...tasks].sort(compareTasks);
    const isExpanded = expandedProjectIds.has(projectId);

    return `
      <div class="dashboard-project-tasks-panel"${isExpanded ? "" : " hidden"}>
        ${
          sortedTasks.length > 0
            ? `<ul class="dashboard-project-task-list">
                ${sortedTasks.map((task) => renderProjectTaskItem(task, project)).join("")}
              </ul>`
            : '<p class="dashboard-project-task-empty muted">暂无关联任务</p>'
        }
      </div>
    `;
  }

  function renderProjectCard(project, index) {
    const stats = projectStats(project);
    const projectId = Number(project.id);
    const isExpanded = expandedProjectIds.has(projectId);
    const priorityHint = projectPriorityLabel(project.priority || project.display_priority);

    return `
      <article
        class="dashboard-project-card dashboard-project-card--compact ${projectPriorityClasses(project.priority || project.display_priority)}${project.is_focus_project ? " is-focus" : ""}"
        data-project-id="${project.id || index}"
        title="项目优先级：${escapeHtml(priorityHint)}"
        aria-label="项目 ${escapeHtml(project.name || "未命名项目")}，项目优先级 ${escapeHtml(priorityHint)}"
      >
        <div class="dashboard-project-card-main">
            <div class="project-title-row">
              <span class="project-priority-dot" aria-hidden="true"></span>
              <h4>${buildProjectTitleWithGoal(project.name, project.goal_name)}</h4>
            </div>
          <div class="key-metric-row key-metric-row--inline dashboard-project-metrics">
            <span class="relation-pill">${escapeHtml(project.status || "系统推导")}</span>
            <span class="meta-muted">今日 ${Number(stats.today || project.today_task_count || 0)}</span>
            <span class="meta-muted">未完成 ${Number(stats.open || project.open_task_count || 0)}</span>
          </div>
        </div>
        <button
          type="button"
          class="btn btn-sm btn-ghost btn-expand-detail dashboard-project-tasks-toggle"
          data-project-id="${project.id || index}"
          aria-expanded="${isExpanded ? "true" : "false"}"
        >${isExpanded ? "收起" : "详情"}</button>
        ${renderProjectTasksPanel(project)}
      </article>
    `;
  }

  function handleProjectTasksToggle(event) {
    const button = event.target.closest(".dashboard-project-tasks-toggle");
    if (!button || !projectsEl.contains(button)) return;

    const projectId = Number(button.dataset.projectId);
    if (!Number.isFinite(projectId)) return;

    const card = button.closest(".dashboard-project-card");
    const panel = card ? card.querySelector(".dashboard-project-tasks-panel") : null;
    if (!panel) return;

    const expanded = panel.hidden;
    panel.hidden = !expanded;
    if (expanded) {
      expandedProjectIds.add(projectId);
    } else {
      expandedProjectIds.delete(projectId);
    }
    button.textContent = expanded ? "收起" : "详情";
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
  }

  function renderKeyProjects(projects) {
    if (!projects.length) {
      projectsEl.innerHTML = emptyState(
        "暂无重点项目",
        "为高优先级项目添加任务，或标记今日推进后会出现在这里"
      );
      return;
    }

    const visible = projects.slice(0, FOCUS_PROJECT_LIMIT);
    const hiddenCount = Math.max(projects.length - FOCUS_PROJECT_LIMIT, 0);

    projectsEl.innerHTML = `
      <div class="dashboard-project-grid">
        ${visible.map((project, index) => renderProjectCard(project, index)).join("")}
      </div>
      ${
        hiddenCount > 0
          ? `
            <div id="dashboard-more-projects" class="dashboard-project-grid dashboard-more-projects" hidden>
              ${projects
                .slice(FOCUS_PROJECT_LIMIT)
                .map((project, index) => renderProjectCard(project, index + FOCUS_PROJECT_LIMIT))
                .join("")}
            </div>
            <button type="button" id="dashboard-show-more-projects" class="btn btn-sm btn-ghost btn-show-more">
              展开更多项目（${hiddenCount}）
            </button>
          `
          : ""
      }
    `;

    const showMoreBtn = document.getElementById("dashboard-show-more-projects");
    const morePanel = document.getElementById("dashboard-more-projects");
    if (showMoreBtn && morePanel) {
      showMoreBtn.addEventListener("click", () => {
        const expanded = morePanel.hidden;
        morePanel.hidden = !expanded;
        showMoreBtn.textContent = expanded
          ? "收起更多项目"
          : `展开更多项目（${hiddenCount}）`;
      });
    }
  }

  function renderTodayTasks(tasks) {
    const allTasks = tasks || [];
    if (allTasks.length === 0) {
      tasksEl.innerHTML = emptyState(
        "今天还没有必须推进的任务",
        "在「任务」页勾选「今日推进」后，会优先显示在这里"
      );
      return;
    }

    const visible = allTasks.slice(0, TODAY_TASK_LIMIT);
    const hiddenCount = Math.max(allTasks.length - TODAY_TASK_LIMIT, 0);

    tasksEl.innerHTML = `
      <div class="dashboard-today-task-list">
        ${visible
          .map(
            (task) => `
              <article class="dashboard-today-task dashboard-today-task--action">
                <div class="dashboard-today-task-main">
                  <h3>${escapeHtml(task.name || "未命名任务")}</h3>
                  ${buildTaskContextLine(task.project_name, task.goal_name)}
                </div>
                <div class="dashboard-today-task-badges">
                  <span class="relation-priority ${taskPriorityClass(task.display_priority)}">
                    ${escapeHtml(task.display_priority || "中")}
                  </span>
                  <span class="relation-pill">${escapeHtml(task.status || "待处理")}</span>
                </div>
              </article>
            `
          )
          .join("")}
      </div>
      ${
        hiddenCount > 0
          ? `<p class="dashboard-more-hint meta-muted">另有 ${hiddenCount} 项今日推进任务，请前往「任务」页查看</p>`
          : ""
      }
    `;
  }

  async function loadDashboard() {
    const [data, tasks] = await Promise.all([
      apiRequest("/api/dashboard"),
      apiRequest("/api/tasks"),
    ]);

    tasksByProject = {};
    tasks.forEach((task) => {
      const projectId = task.project_id;
      if (!tasksByProject[projectId]) tasksByProject[projectId] = [];
      tasksByProject[projectId].push(task);
    });

    const activeProjectIds = new Set(collectProjects(data).map((project) => project.id));
    expandedProjectIds.forEach((projectId) => {
      if (!activeProjectIds.has(projectId)) expandedProjectIds.delete(projectId);
    });

    mainlineExpandMode = null;
    const todayTasks = data.today_task_context || data.today_tasks || [];
    renderMainlineGoal(data.mainline_goal, todayTasks);
    renderTodayTasks(todayTasks);
    renderKeyProjects(selectKeyProjects(data));
  }

  const goalSection = document.getElementById("dashboard-goal");
  (goalSection || goalEl).addEventListener("click", handleMainlineExpandClick);
  document.addEventListener("click", handleMainlineOutsideClick);
  projectsEl.addEventListener("click", handleProjectTasksToggle);

  if (briefingBtn) {
    briefingBtn.addEventListener("click", async () => {
      const prev = briefingBtn.textContent;
      briefingBtn.disabled = true;
      briefingBtn.textContent = "生成中…";

      try {
        const result = await apiRequest("/api/ai/dashboard-briefing", {
          method: "POST",
          body: JSON.stringify({}),
        });

        const prioritiesHtml = (result.priorities || [])
          .map((p) => `<li>${escapeHtml(p)}</li>`)
          .join("");

        showAIViewModal({
          title: "AI 今日作战简报",
          bodyHtml: `
            <div class="ai-briefing">
              <p class="ai-briefing-text">${formatMultiline(result.briefing)}</p>
              ${
                prioritiesHtml
                  ? `<h4 class="ai-briefing-subtitle">优先事项</h4><ul class="ai-briefing-list">${prioritiesHtml}</ul>`
                  : ""
              }
              ${
                result.focus
                  ? `<p class="ai-briefing-focus"><strong>今日聚焦：</strong>${escapeHtml(result.focus)}</p>`
                  : ""
              }
            </div>
          `,
        });
      } catch (err) {
        showToast(err.message || "AI 简报生成失败", "error");
      } finally {
        briefingBtn.disabled = false;
        briefingBtn.textContent = prev;
      }
    });
  }

  if (dispatchBtn) {
    dispatchBtn.addEventListener("click", async () => {
      const prev = dispatchBtn.textContent;
      dispatchBtn.disabled = true;
      dispatchBtn.textContent = "分发中…";

      try {
        const result = await apiRequest("/api/ai/dispatch-actions", {
          method: "POST",
          body: JSON.stringify({}),
        });

        showAIModal({
          title: "AI 行动分发",
          bodyHtml: buildDispatchActionsHtml(result),
          confirmLabel: "确认执行",
          loadingLabel: "执行中…",
          onConfirm: async () => {
            const { markToday, newTasks } = readSelectedDispatchActions();
            if (markToday.length === 0 && newTasks.length === 0) {
              throw new Error("请至少选择一项行动");
            }
            for (const taskId of markToday) {
              await apiRequest(`/api/tasks/${taskId}/today-progress`, {
                method: "PATCH",
                body: JSON.stringify({ enabled: true }),
              });
            }
            for (const item of newTasks) {
              await apiRequest("/api/tasks", {
                method: "POST",
                body: JSON.stringify({
                  project_id: item.project_id,
                  name: item.name,
                }),
              });
            }
            await loadDashboard();
          },
        });
      } catch (err) {
        showToast(err.message || "AI 行动分发失败", "error");
      } finally {
        dispatchBtn.disabled = false;
        dispatchBtn.textContent = prev;
      }
    });
  }

  loadDashboard().catch((err) => console.error(err));
});

function formatMultiline(text) {
  return escapeHtml(text || "").replace(/\n/g, "<br>");
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