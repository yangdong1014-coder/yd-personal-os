document.addEventListener("DOMContentLoaded", () => {
  const goalEl = document.getElementById("dashboard-goal-content");
  const projectsEl = document.getElementById("dashboard-projects-content");
  const tasksEl = document.getElementById("dashboard-tasks-content");
  const valueEl = document.getElementById("value-dashboard-content");
  const cockpitEl = document.getElementById("dashboard-cockpit-content");
  const briefingBtn = document.getElementById("ai-briefing-btn");
  const dispatchBtn = document.getElementById("ai-dispatch-btn");

  if (!goalEl || !projectsEl || !tasksEl) return;

  const TODAY_TASK_LIMIT = 3;
  const FOCUS_PROJECT_LIMIT = 6;
  const expandedProjectIds = new Set();
  let cachedFocusProjects = [];
  let focusProjectsExpanded = false;
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

  function isHighPriorityProject(project) {
    return project.priority === "high";
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

  function compareFocusProjects(a, b) {
    const aStats = projectStats(a);
    const bStats = projectStats(b);
    const aKey = [
      (aStats.today || 0) > 0 ? 1 : 0,
      aStats.open || 0,
      a.recent_activity_at || "",
      a.created_at || "",
      -(Number(a.id) || 0),
    ];
    const bKey = [
      (bStats.today || 0) > 0 ? 1 : 0,
      bStats.open || 0,
      b.recent_activity_at || "",
      b.created_at || "",
      -(Number(b.id) || 0),
    ];
    for (let i = 0; i < aKey.length; i += 1) {
      if (aKey[i] > bKey[i]) return -1;
      if (aKey[i] < bKey[i]) return 1;
    }
    return 0;
  }

  function selectFocusProjects(data) {
    return collectProjects(data)
      .filter(isHighPriorityProject)
      .sort(compareFocusProjects);
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

  function renderProjectCard(project, index, collapsedHidden = false) {
    const stats = projectStats(project);
    const projectId = Number(project.id);
    const isExpanded = expandedProjectIds.has(projectId);
    const priorityHint = projectPriorityLabel(project.priority || project.display_priority);

    return `
      <article
        class="dashboard-project-card dashboard-project-card--compact ${projectPriorityClasses(project.priority || project.display_priority)}${project.is_focus_project ? " is-focus" : ""}"
        data-project-id="${project.id || index}"
        ${collapsedHidden ? " hidden" : ""}
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
        "暂无高优先级项目",
        "在目标页将项目设置为高优先级后会出现在这里"
      );
      return;
    }

    const hiddenCount = Math.max(projects.length - FOCUS_PROJECT_LIMIT, 0);
    const showToggle = hiddenCount > 0;

    projectsEl.innerHTML = `
      <div class="dashboard-project-grid dashboard-focus-project-grid">
        ${projects
          .map((project, index) =>
            renderProjectCard(
              project,
              index,
              showToggle && !focusProjectsExpanded && index >= FOCUS_PROJECT_LIMIT
            )
          )
          .join("")}
      </div>
      ${
        showToggle
          ? `<button type="button" id="dashboard-show-more-projects" class="btn btn-sm btn-ghost btn-show-more">${
              focusProjectsExpanded ? "收起" : `展开更多（剩余${hiddenCount}）`
            }</button>`
          : ""
      }
    `;

    const showMoreBtn = document.getElementById("dashboard-show-more-projects");
    if (showMoreBtn) {
      showMoreBtn.addEventListener("click", () => {
        focusProjectsExpanded = !focusProjectsExpanded;
        renderKeyProjects(cachedFocusProjects);
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

  function cockpitCard(title, value, meta, tone = "") {
    return `
      <article class="dashboard-cockpit-card ${tone ? `dashboard-cockpit-card--${tone}` : ""}">
        <span class="dashboard-cockpit-label">${escapeHtml(title)}</span>
        <strong>${escapeHtml(value || "暂无")}</strong>
        <p>${escapeHtml(meta || "")}</p>
      </article>
    `;
  }

  function pickValueBottleneck(valueData) {
    if (!valueData) {
      return {
        title: "等待价值链数据",
        meta: "正在读取机会、实验、反馈和资产状态",
        tone: "muted",
      };
    }
    const pendingDeposit = [
      ...(valueData.pending_deposit || []),
      ...(valueData.completed_experiments_without_assets || []),
    ];
    if (pendingDeposit.length > 0) {
      return {
        title: "待资产化",
        meta: `${pendingDeposit.length} 个强反馈或实验结果需要沉淀`,
        tone: "deposit",
      };
    }
    if ((valueData.pending_validation || []).length > 0) {
      return {
        title: "待验证",
        meta: `${valueData.pending_validation.length} 个机会等待最小验证`,
        tone: "validate",
      };
    }
    if ((valueData.pending_stop_review || []).length > 0) {
      return {
        title: "待停止审查",
        meta: `${valueData.pending_stop_review.length} 个事项需要判断是否止损`,
        tone: "stop",
      };
    }
    return {
      title: "链路顺畅",
      meta: "当前没有明显堵点，优先推进今日行动",
      tone: "clear",
    };
  }

  function renderCockpitSummary(data, valueData, todayTasks) {
    if (!cockpitEl) return;
    const goal = data.mainline_goal;
    const firstTask = (todayTasks || [])[0];
    const bottleneck = pickValueBottleneck(valueData);
    cockpitEl.innerHTML = [
      cockpitCard(
        "当前主线",
        goal?.name || "暂无主线目标",
        goal ? `${goal.type || "目标"} · ${Number(goal.today_task_count || goal.stats?.today || 0)} 个今日推进` : "在目标页设置“当前主线”目标",
        "mainline"
      ),
      cockpitCard(
        "今日最小推进",
        firstTask?.name || "暂无今日推进",
        firstTask ? `${firstTask.project_name || "未归属项目"} · ${firstTask.status || ""}` : "在任务页标记今日推进任务",
        "today"
      ),
      cockpitCard(
        "价值链最大堵点",
        bottleneck.title,
        bottleneck.meta,
        bottleneck.tone
      ),
    ].join("");
  }

  function chainStageClass(stage) {
    const map = {
      "待验证": "validate",
      "进行中": "running",
      "待反馈": "feedback",
      "待沉淀": "deposit",
      "待停止观察": "stop",
      "已完成": "done",
    };
    return map[stage] || "default";
  }

  function chainPrimaryAction(chain) {
    const stage = chain.stage || "";
    if (stage === "待验证") return { label: "启动实验", href: "/experiments", suggestion: "设计 7 天 MVP" };
    if (stage === "进行中") return { label: "更新实验", href: "/experiments", suggestion: "更新实验进展或记录观察" };
    if (stage === "待反馈") return { label: "记录反馈", href: "/feedback", suggestion: "记录真实反馈" };
    if (stage === "待沉淀") return { label: "沉淀案例", href: "/assets", suggestion: "沉淀案例资产" };
    if (stage === "待停止观察") return { label: "复盘判断", href: "/experiments", suggestion: "判断停止、调整或继续" };
    if (stage === "已完成") return { label: "确认归档", href: "", suggestion: "已具备归档条件，可确认后归档" };
    return { label: "查看机会", href: "/opportunities", suggestion: "确认下一步" };
  }

  function chainEditAction(chain) {
    const stage = chain.stage || "";
    if (stage === "待验证") return { label: "修改当前链路", href: "/opportunities" };
    if (stage === "进行中" || stage === "待反馈" || stage === "待停止观察") {
      return { label: "修改当前链路", href: "/experiments" };
    }
    if (stage === "待沉淀") return { label: "修改当前链路", href: "/feedback" };
    if (stage === "已完成") return { label: "修改当前链路", href: "/assets" };
    return { label: "修改当前链路", href: "/opportunities" };
  }

  function chainStep(label, item, fallback, metaParts = []) {
    const meta = metaParts.filter(Boolean).join(" · ");
    return `
      <div class="value-chain-step">
        <span class="value-chain-step-label">${escapeHtml(label)}</span>
        <strong>${escapeHtml(item?.title || fallback)}</strong>
        ${meta ? `<span>${escapeHtml(meta)}</span>` : ""}
      </div>
    `;
  }

  function chainStatusLine(label, value, meta = "", tone = "") {
    return `
      <div class="value-chain-status-line ${tone ? `value-chain-status-line--${tone}` : ""}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value || "未记录")}</strong>
        ${meta ? `<small>${escapeHtml(meta)}</small>` : ""}
      </div>
    `;
  }

  function renderCurrentChainState(chain) {
    const opportunity = chain.opportunity || {};
    const experiment = chain.latest_experiment;
    const feedback = chain.latest_feedback;
    const asset = chain.latest_asset;
    const stage = chain.stage || "";

    if (stage === "待验证") {
      return `
        <div class="value-chain-current">
          ${chainStatusLine("当前状态", "机会待验证", "需要启动最小实验", "active")}
          ${chainStatusLine("机会", opportunity.title || "未命名机会", `${opportunity.score || 0} 分 · ${opportunity.status || ""}`)}
        </div>
      `;
    }
    if (stage === "进行中") {
      return `
        <div class="value-chain-current">
          ${chainStatusLine("当前状态", "实验进行中", "继续推进并记录观察", "active")}
          ${chainStatusLine("实验", experiment?.title || "当前实验", [experiment?.status, experiment?.experiment_type].filter(Boolean).join(" · "))}
        </div>
      `;
    }
    if (stage === "待反馈") {
      return `
        <div class="value-chain-current">
          ${chainStatusLine("当前状态", "等待真实反馈", "实验已有进展，需要补充反馈", "active")}
          ${chainStatusLine("实验", experiment?.title || "当前实验", experiment?.status || "")}
          <p class="value-chain-soft-note">反馈：尚未记录真实反馈</p>
        </div>
      `;
    }
    if (stage === "待沉淀") {
      const sourceTitle = feedback?.title || experiment?.title || opportunity.title;
      const sourceMeta = feedback?.level || experiment?.status || "";
      return `
        <div class="value-chain-current">
          ${chainStatusLine("当前状态", "结果待资产化", "把已验证结果沉淀为可复用资产", "active")}
          ${chainStatusLine(feedback ? "最新反馈" : "最新实验", sourceTitle, sourceMeta)}
          ${chainStatusLine("当前缺口", "还没有沉淀案例资产", "", "gap")}
        </div>
      `;
    }
    if (stage === "待停止观察") {
      const source = experiment || opportunity;
      return `
        <div class="value-chain-current">
          ${chainStatusLine("当前状态", "需要停止/调整判断", "先复盘，再决定继续投入", "active")}
          ${chainStatusLine(experiment ? "相关实验" : "相关机会", source?.title || source?.name || opportunity.title, source?.status || "")}
        </div>
      `;
    }
    if (stage === "已完成") {
      return `
        <div class="value-chain-current">
          ${chainStatusLine("当前状态", "已沉淀资产", "可以复用，也可以从首页归档", "active")}
          ${chainStatusLine("资产", asset?.title || "已沉淀资产", [asset?.asset_level, asset?.asset_type].filter(Boolean).join(" · "))}
          <div class="value-chain-reuse-actions">
            <a href="/assets">查看资产</a>
            <a href="/assets">复用资产</a>
          </div>
        </div>
      `;
    }
    return `
      <div class="value-chain-current">
        ${chainStatusLine("当前状态", stage || "待确认", chain.stage_reason || "")}
        ${chainStatusLine("机会", opportunity.title || "未命名机会", opportunity.status || "")}
      </div>
    `;
  }

  function chainSupplementItem(label, title, meta = "", extraHtml = "") {
    return `
      <div class="value-chain-supplement-item">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(title || "未记录")}</strong>
        ${meta ? `<small>${escapeHtml(meta)}</small>` : ""}
        ${extraHtml}
      </div>
    `;
  }

  function renderChainSupplement(chain) {
    const items = [];
    const experiment = chain.latest_experiment;
    const feedback = chain.latest_feedback;
    const asset = chain.latest_asset;
    if (experiment) {
      items.push(chainSupplementItem(
        "当前实验",
        experiment.title,
        [experiment.status, experiment.experiment_type].filter(Boolean).join(" · ")
      ));
    }
    if (feedback) {
      items.push(chainSupplementItem(
        "最新反馈",
        feedback.title,
        [feedback.level, feedback.source].filter(Boolean).join(" · ")
      ));
    } else if (chain.stage === "待反馈") {
      items.push(chainSupplementItem("反馈状态", "尚未记录真实反馈", "补充一次真实反馈后再判断是否沉淀"));
    }
    if (asset) {
      items.push(chainSupplementItem(
        "已沉淀资产",
        asset.title,
        [asset.asset_level, asset.asset_type].filter(Boolean).join(" · "),
        `<a href="/assets">查看资产</a>`
      ));
    } else if (chain.stage === "待沉淀") {
      items.push(chainSupplementItem("资产化缺口", "还没有沉淀案例资产", "优先把强反馈或已验证结果沉淀为案例资产"));
    }
    if (!items.length) {
      const hint = chain.stage === "待验证"
        ? "暂无更多补充信息，建议先启动实验。"
        : "当前暂无更多链路补充信息，可通过回查链路查看完整历史。";
      return `<p class="value-chain-supplement-empty">${escapeHtml(hint)}</p>`;
    }
    return `<div class="value-chain-supplement-list">${items.join("")}</div>`;
  }

  function chainCompactSummary(chain) {
    const opportunity = chain.opportunity || {};
    const experiment = chain.latest_experiment;
    const feedback = chain.latest_feedback;
    const asset = chain.latest_asset;
    const stage = chain.stage || "";
    if (stage === "待验证") return "当前：机会待验证，需要启动最小实验";
    if (stage === "进行中") {
      return `当前：实验进行中，${experiment?.title || opportunity.title || "当前实验"}`;
    }
    if (stage === "待反馈") {
      return `当前：等待真实反馈，${experiment?.title || "当前实验"}尚未记录反馈`;
    }
    if (stage === "待沉淀") {
      if (feedback) return `当前：已有 ${String(feedback.level || "强")} 反馈，尚未沉淀案例资产`;
      return "当前：结果待资产化，尚未沉淀案例资产";
    }
    if (stage === "待停止观察") {
      return `当前：需要停止/调整判断，${experiment?.status || opportunity.status || "状态待确认"}`;
    }
    if (stage === "已完成") {
      return `当前：已沉淀资产：${asset?.title || "可复用资产"}`;
    }
    return `当前：${chain.stage_reason || stage || "待确认"}`;
  }

  function renderChainCard(chain) {
    const opportunity = chain.opportunity || {};
    const action = chainPrimaryAction(chain);
    const editAction = chainEditAction(chain);
    const actionHtml = action.href
      ? `<a class="btn btn-sm btn-primary value-chain-primary-action" href="${escapeAttr(action.href)}">${escapeHtml(action.label)}</a>`
      : `<button type="button" class="btn btn-sm btn-primary value-chain-primary-action btn-chain-complete">${escapeHtml(action.label)}</button>`;
    return `
      <article class="value-chain-card" data-opportunity-id="${opportunity.id}" data-links-url="${escapeAttr(chain.links_url || "")}">
        <div class="value-chain-compact">
          <div class="value-chain-main">
            <div class="value-chain-title-row">
              <h3>${escapeHtml(opportunity.title || "未命名机会")}</h3>
              <span class="value-chain-stage value-chain-stage--${chainStageClass(chain.stage)}">${escapeHtml(chain.stage || "待确认")}</span>
            </div>
            <p class="value-chain-current-line">${escapeHtml(chainCompactSummary(chain))}</p>
          </div>
          <div class="value-chain-action-summary">
            <p><span>下一步</span>${escapeHtml(chain.next_action || action.suggestion)}</p>
            <div class="value-chain-counts">
              <span>实验 ${Number(chain.counts?.experiments || 0)}</span>
              <span>反馈 ${Number(chain.counts?.feedback || 0)}</span>
              <span>资产 ${Number(chain.counts?.assets || 0)}</span>
            </div>
          </div>
          <div class="value-chain-primary-actions">
            ${actionHtml}
            <button type="button" class="btn btn-sm btn-ghost btn-chain-expand" aria-expanded="false">展开</button>
          </div>
        </div>
        <div class="value-chain-details" hidden>
          ${renderChainSupplement(chain)}
          <div class="value-chain-foot">
            <div class="value-chain-actions">
              <button type="button" class="btn btn-sm btn-ghost btn-chain-links" aria-expanded="false">回查链路</button>
              <a class="btn btn-sm btn-ghost btn-chain-edit" href="${escapeAttr(editAction.href)}">${escapeHtml(editAction.label)}</a>
              <button type="button" class="btn btn-sm btn-ghost btn-chain-archive">归档</button>
            </div>
          </div>
          <div class="value-chain-links-panel" hidden></div>
        </div>
      </article>
    `;
  }

  function renderChainLinksPanel(links, chain) {
    return `
      <div class="value-chain-links-summary">
        <span>关联实验 ${Number(links.counts?.experiments || 0)}</span>
        <span>关联反馈 ${Number(links.counts?.feedback || 0)}</span>
        <span>关联资产 ${Number(links.counts?.assets || 0)}</span>
      </div>
      <div class="value-chain-links-latest">
        ${chainStep("最新实验", chain.latest_experiment, "暂无实验", [
          chain.latest_experiment?.status,
          chain.latest_experiment?.experiment_type,
        ])}
        ${chainStep("最新反馈", chain.latest_feedback, "暂无反馈", [
          chain.latest_feedback?.level,
          chain.latest_feedback?.source,
        ])}
        ${chainStep("最新资产", chain.latest_asset, "暂无案例资产", [
          chain.latest_asset?.asset_level,
          chain.latest_asset?.asset_type,
        ])}
      </div>
      <a class="btn btn-sm btn-ghost value-chain-full-link" href="/opportunities">去机会页查看完整链路</a>
    `;
  }

  async function toggleChainLinks(card, chain) {
    const button = card.querySelector(".btn-chain-links");
    const panel = card.querySelector(".value-chain-links-panel");
    const expanded = button.getAttribute("aria-expanded") === "true";
    if (expanded) {
      button.setAttribute("aria-expanded", "false");
      button.textContent = "回查链路";
      panel.hidden = true;
      return;
    }
    button.setAttribute("aria-expanded", "true");
    button.textContent = "收起回查";
    panel.hidden = false;
    panel.innerHTML = `<p class="form-hint">链路加载中…</p>`;
    try {
      const links = await apiRequest(chain.links_url);
      panel.innerHTML = renderChainLinksPanel(links, chain);
    } catch (err) {
      panel.innerHTML = `<p class="form-hint">链路加载失败</p>`;
    }
  }

  async function archiveChain(chain) {
    const opportunity = chain.opportunity || {};
    if (!opportunity.id) return;
    if (!confirm(`确认归档「${opportunity.title || "未命名机会"}」？归档后仍可在机会页查看。`)) return;
    await apiRequest(`/api/opportunities/${opportunity.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "已归档" }),
    });
    showToast("链路已归档", "success");
    await loadDashboard();
  }

  function toggleChainDetails(card) {
    const button = card.querySelector(".btn-chain-expand");
    const details = card.querySelector(".value-chain-details");
    const expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", expanded ? "false" : "true");
    button.textContent = expanded ? "展开" : "收起";
    details.hidden = expanded;
  }

  function bindValueChainCards(chains) {
    valueEl.querySelectorAll(".value-chain-card").forEach((card) => {
      const opportunityId = Number(card.dataset.opportunityId);
      const chain = chains.find((item) => item.opportunity?.id === opportunityId);
      if (!chain) return;
      card.querySelector(".btn-chain-expand")?.addEventListener("click", () => toggleChainDetails(card));
      card.querySelector(".btn-chain-links")?.addEventListener("click", () => toggleChainLinks(card, chain));
      card.querySelector(".btn-chain-archive")?.addEventListener("click", () => archiveChain(chain));
      card.querySelector(".btn-chain-complete")?.addEventListener("click", () => {
        showToast("该链路已完成，可使用归档按钮从首页移出。", "success");
      });
    });
  }

  function renderValueDashboard(data) {
    if (!valueEl) return;
    const chains = data.chains || [];
    if (!chains.length) {
      valueEl.innerHTML = `
        <div class="value-chain-overview">
          <div class="value-chain-summary">
            <strong>未归档链路 0 条</strong>
            <span>暂无未归档价值链路。</span>
          </div>
          <div class="empty-state empty-state-compact">
            <strong>暂无未归档价值链路</strong>
            你可以从机会页新增机会，或在归档链路中查看历史。
          </div>
        </div>
      `;
      return;
    }
    valueEl.innerHTML = `
      <div class="value-chain-overview">
        <div class="value-chain-summary">
          <strong>未归档链路 ${chains.length} 条</strong>
          <span>按机会聚合最新实验、反馈和案例资产</span>
        </div>
        <div class="value-chain-list">
          ${chains.map(renderChainCard).join("")}
        </div>
      </div>
    `;
    bindValueChainCards(chains);
  }

  async function loadDashboard() {
    const [data, tasks, valueData] = await Promise.all([
      apiRequest("/api/dashboard"),
      apiRequest("/api/tasks"),
      valueEl ? apiRequest("/api/value-dashboard") : Promise.resolve(null),
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
    focusProjectsExpanded = false;
    cachedFocusProjects = selectFocusProjects(data);
    renderKeyProjects(cachedFocusProjects);
    renderCockpitSummary(data, valueData, todayTasks);
    if (valueData) {
      renderValueDashboard(valueData);
    }
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
          title: "AI 审计瓶颈",
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
          title: "AI 今日推进",
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
        showToast(err.message || "AI 今日推进失败", "error");
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
