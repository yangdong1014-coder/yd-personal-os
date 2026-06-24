document.addEventListener("DOMContentLoaded", () => {
  const tasksList = document.getElementById("tasks-list");
  const taskOverview = document.getElementById("task-overview");
  const createTaskBtn = document.getElementById("create-task-btn");
  const recommendBtn = document.getElementById("ai-recommend-btn");
  const viewButtons = Array.from(document.querySelectorAll(".task-view-btn"));

  if (!tasksList) return;

  let currentView = "overview";
  let cachedTasks = [];
  let cachedProjects = [];

  const PRIORITY_LABELS = { high: "高", medium: "中", low: "低" };
  const PRIORITY_SCORES = { high: 3, medium: 2, low: 1 };

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

  function buildPriorityOptions(selected) {
    const current = normalizePriority(selected);
    return Object.entries(PRIORITY_LABELS)
      .map(
        ([value, label]) =>
          `<option value="${escapeAttr(value)}"${value === current ? " selected" : ""}>${escapeHtml(label)}优先级</option>`
      )
      .join("");
  }

  function buildProjectSelectMarkup(selectedId = "") {
    const selected = String(selectedId || "");
    const options = ['<option value="">选择所属项目</option>']
      .concat(
        cachedProjects.map(
          (project) =>
            `<option value="${project.id}"${String(project.id) === selected ? " selected" : ""}>${escapeHtml(project.goal_name)} / ${escapeHtml(project.name)}</option>`
        )
      )
      .join("");
    return options;
  }

  async function loadProjects() {
    cachedProjects = await apiRequest("/api/projects");
    if (currentView === "project") {
      renderCurrentView();
    }
  }

  function bindCreateTaskModalControls() {
    const projectSelect = document.getElementById("task-project");
    const decomposeBtn = document.getElementById("ai-decompose-btn");
    const formHint = document.getElementById("task-form-hint");
    if (formHint) {
      formHint.hidden = cachedProjects.length > 0;
    }
    if (!projectSelect || !decomposeBtn) return;
    decomposeBtn.disabled = !projectSelect.value;
    projectSelect.addEventListener("change", () => {
      decomposeBtn.disabled = !projectSelect.value;
    });
    decomposeBtn.addEventListener("click", () => handleAIDecompose(decomposeBtn));
  }

  async function submitCreateTask() {
    const nameInput = document.getElementById("task-name");
    const projectSelect = document.getElementById("task-project");
    const taskPrioritySelect = document.getElementById("task-priority");
    if (!nameInput || !projectSelect) {
      throw new Error("表单未就绪");
    }

    const projectId = parseInt(projectSelect.value, 10);
    const name = nameInput.value.trim();
    const priority = taskPrioritySelect ? taskPrioritySelect.value : "medium";
    if (!projectId) {
      throw new Error("请选择所属项目");
    }
    if (!name) {
      throw new Error("任务名称不能为空");
    }

    await apiRequest("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, name, priority }),
    });
    showToast("任务已保存", "success");
    await loadTasks();
  }

  function openCreateTaskModal() {
    showAIModal({
      title: "新建任务",
      bodyHtml: `
        <div class="stacked-form create-entity-form">
          <label class="form-row">
            <span class="form-label">所属项目</span>
            <select id="task-project" class="select full-width" required>
              ${buildProjectSelectMarkup()}
            </select>
          </label>
          <label class="form-row">
            <span class="form-label">任务优先级</span>
            <select id="task-priority" class="select full-width">
              <option value="high">高优先级</option>
              <option value="medium" selected>中优先级</option>
              <option value="low">低优先级</option>
            </select>
          </label>
          <label class="form-row">
            <span class="form-label">任务名称</span>
            <input type="text" id="task-name" class="input full-width" placeholder="任务名称" required>
          </label>
          <div class="form-actions-row">
            <button type="button" id="ai-decompose-btn" class="btn btn-sm btn-ai" disabled>AI拆任务</button>
          </div>
          <p class="form-hint" id="task-form-hint"${cachedProjects.length > 0 ? " hidden" : ""}>请先在「目标」页创建目标与项目</p>
        </div>
      `,
      confirmLabel: "添加任务",
      loadingLabel: "添加中…",
      onConfirm: submitCreateTask,
    });
    bindCreateTaskModalControls();
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

  function buildStatusOptions(selected) {
    return (window.TASK_STATUSES || [])
      .map(
        (s) =>
          `<option value="${escapeAttr(s)}"${s === selected ? " selected" : ""}>${escapeHtml(s)}</option>`
      )
      .join("");
  }

  function statusClass(status) {
    if (status === "进行中") return "is-doing";
    if (status === "完成") return "is-done";
    return "is-pending";
  }

  function priorityForTask(task) {
    const priority = normalizePriority(task.priority);
    return { label: priorityLabel(priority), score: priorityScore(priority), value: priority };
  }

  function priorityForProject(project) {
    const priority = normalizePriority(project.priority);
    return { label: priorityLabel(priority), score: priorityScore(priority), value: priority };
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

  function formatActivity(value) {
    if (!value) return "暂无活动";
    return String(value).slice(0, 16);
  }

  function inferProjectStatus(stats) {
    if (stats.today > 0) return "今日推进中";
    if (stats.doing > 0) return "推进中";
    if (stats.pending > 0) return "待推进";
    if (stats.total > 0) return "已完成";
    return "暂无任务";
  }

  function enrichTask(task) {
    const priority = priorityForTask(task);
    return {
      ...task,
      priority: priority.value,
      is_today_progress: isTodayProgress(task),
      display_priority: priority.label,
      display_priority_score: priority.score,
      recent_activity_at: task.created_at || "",
    };
  }

  function compareTasks(a, b) {
    const statusRank = { "进行中": 3, "待处理": 2, "完成": 1 };
    const aKey = [
      a.display_priority_score || 0,
      isTodayProgress(a) ? 1 : 0,
      statusRank[a.status] || 0,
      a.recent_activity_at || a.created_at || "",
    ];
    const bKey = [
      b.display_priority_score || 0,
      isTodayProgress(b) ? 1 : 0,
      statusRank[b.status] || 0,
      b.recent_activity_at || b.created_at || "",
    ];

    for (let i = 0; i < aKey.length; i += 1) {
      if (aKey[i] > bKey[i]) return -1;
      if (aKey[i] < bKey[i]) return 1;
    }
    return 0;
  }

  function compareProjectGroups(a, b) {
    const aKey = [
      a.displayPriorityScore,
      a.stats.today,
      a.stats.doing,
      a.stats.open,
      a.stats.open > 0 ? 1 : 0,
      a.recentActivityAt || "",
    ];
    const bKey = [
      b.displayPriorityScore,
      b.stats.today,
      b.stats.doing,
      b.stats.open,
      b.stats.open > 0 ? 1 : 0,
      b.recentActivityAt || "",
    ];

    for (let i = 0; i < aKey.length; i += 1) {
      if (aKey[i] > bKey[i]) return -1;
      if (aKey[i] < bKey[i]) return 1;
    }
    return 0;
  }

  function calculateStats(tasks) {
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

  function isFocusTask(task) {
    return (
      isTodayProgress(task) ||
      task.display_priority_score >= 3 ||
      task.status === "进行中"
    );
  }

  function splitTasks(tasks) {
    const focus = [];
    const backlog = [];
    tasks.forEach((task) => {
      if (isFocusTask(task)) {
        focus.push(task);
      } else {
        backlog.push(task);
      }
    });
    focus.sort(compareTasks);
    backlog.sort(compareTasks);
    return { focus, backlog };
  }

  function renderOverviewStats(tasks) {
    if (!taskOverview) return;
    const stats = calculateStats(tasks);
    const items = [
      ["今日推进", stats.today],
      ["进行中", stats.doing],
      ["待处理", stats.pending],
    ];

    taskOverview.innerHTML = items
      .map(
        ([label, value]) => `
          <div class="task-overview-chip task-overview-chip--compact">
            <span>${escapeHtml(label)}</span>
            <strong>${value}</strong>
          </div>
        `
      )
      .join("");
  }

  function groupTasksByProject(tasks) {
    const groups = [];
    const groupMap = new Map();

    cachedProjects.forEach((project) => {
      const key = `project-${project.id}`;
      const group = {
        key,
        projectId: project.id,
        projectName: project.name || "未命名项目",
        goalName: project.goal_name || "未归属目标",
        priority: normalizePriority(project.priority),
        createdAt: project.created_at || "",
        recentActivityAt: project.created_at || "",
        tasks: [],
      };
      groupMap.set(key, group);
      groups.push(group);
    });

    tasks.forEach((task) => {
      const hasProject = task.project_id && task.project_name;
      const key = hasProject ? `project-${task.project_id}` : "unassigned";

      if (!groupMap.has(key)) {
        const group = {
          key,
          projectId: hasProject ? task.project_id : null,
          projectName: hasProject ? task.project_name : "未归属任务",
          goalName: task.goal_name || "未归属目标",
          priority: "medium",
          createdAt: task.created_at || "",
          recentActivityAt: task.created_at || "",
          tasks: [],
        };
        groupMap.set(key, group);
        groups.push(group);
      }

      const group = groupMap.get(key);
      group.tasks.push(task);
      if ((task.created_at || "") > (group.recentActivityAt || "")) {
        group.recentActivityAt = task.created_at || "";
      }
    });

    groups.forEach((group) => {
      group.tasks.sort(compareTasks);
      group.stats = calculateStats(group.tasks);
      group.status = inferProjectStatus(group.stats);
      const priority = priorityForProject(group);
      group.displayPriority = priority.label;
      group.displayPriorityScore = priority.score;
      group.shouldExpand = group.stats.today > 0 || group.stats.doing > 0;
    });

    return groups
      .filter((group) => group.stats.total > 0 || group.projectId)
      .sort(compareProjectGroups);
  }

  function openTaskEditModal(task) {
    showAIModal({
      title: `编辑任务 — ${task.name}`,
      bodyHtml: `
        <div class="stacked-form">
          <label class="form-row">
            <span class="form-label">任务名称</span>
            <input type="text" id="edit-task-name" class="input full-width" value="${escapeAttr(task.name)}" required>
          </label>
          <label class="form-row">
            <span class="form-label">任务状态</span>
            <select id="edit-task-status" class="select full-width">${buildStatusOptions(task.status)}</select>
          </label>
          <label class="form-row">
            <span class="form-label">任务优先级</span>
            <select id="edit-task-priority" class="select full-width">${buildPriorityOptions(task.priority)}</select>
          </label>
        </div>
      `,
      confirmLabel: "保存",
      loadingLabel: "保存中…",
      onConfirm: async () => {
        const name = document.getElementById("edit-task-name").value.trim();
        const status = document.getElementById("edit-task-status").value;
        const priority = document.getElementById("edit-task-priority").value;
        if (!name) {
          throw new Error("任务名称不能为空");
        }
        await apiRequest(`/api/tasks/${task.id}`, {
          method: "PATCH",
          body: JSON.stringify({ name, status, priority }),
        });
        showToast("任务已更新", "success");
        await loadTasks();
      },
    });
  }

  async function handleAIDecompose(button) {
    const projectSelect = document.getElementById("task-project");
    const projectId = parseInt(projectSelect?.value, 10);
    if (!projectId) return;

    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "拆解中…";

    try {
      const result = await apiRequest("/api/ai/decompose-project", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId }),
      });

      showAIModal({
        title: `AI 任务拆解 — ${result.project_name}`,
        bodyHtml: buildTasksDraftHtml(result.tasks),
        confirmLabel: "确认创建",
        loadingLabel: "创建中…",
        onConfirm: async () => {
          const names = readSelectedTaskNames();
          if (names.length === 0) {
            throw new Error("请至少选择一个任务");
          }
          for (const name of names) {
            await apiRequest("/api/tasks", {
              method: "POST",
              body: JSON.stringify({ project_id: projectId, name }),
            });
          }
          await loadTasks();
        },
      });
    } catch (err) {
      showToast(err.message || "AI 拆解失败", "error");
    } finally {
      button.disabled = !projectSelect?.value;
      button.textContent = prevText;
    }
  }

  async function handleAIRecommend(button) {
    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "推荐中…";

    try {
      const result = await apiRequest("/api/ai/recommend-today-tasks", {
        method: "POST",
        body: JSON.stringify({}),
      });

      showAIModal({
        title: "AI 今日推进推荐",
        bodyHtml: buildTodayRecommendHtml(result.recommendations),
        confirmLabel: "标记今日推进",
        loadingLabel: "标记中…",
        onConfirm: async () => {
          const taskIds = readSelectedRecommendTaskIds();
          if (taskIds.length === 0) {
            throw new Error("请至少选择一个任务");
          }
          for (const taskId of taskIds) {
            await apiRequest(`/api/tasks/${taskId}/today-progress`, {
              method: "PATCH",
              body: JSON.stringify({ enabled: true }),
            });
          }
          await loadTasks();
        },
      });
    } catch (err) {
      showToast(err.message || "AI 推荐失败", "error");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  function buildTaskOverviewRelationLine(projectName, goalName) {
    const project = projectName || "未归属项目";
    const goal = goalName || "未归属目标";

    return `
      <p class="task-relation-line muted-relation">
        <span class="task-relation-part">
          <span class="relation-label">关联项目：</span>
          <span class="relation-value" title="${escapeAttr(project)}">${escapeHtml(project)}</span>
        </span>
        <span class="task-relation-sep" aria-hidden="true">｜</span>
        <span class="task-relation-part">
          <span class="relation-label">关联目标：</span>
          <span class="relation-value" title="${escapeAttr(goal)}">${escapeHtml(goal)}</span>
        </span>
      </p>
    `;
  }

  function renderTaskRow(task, mode = "overview") {
    const row = document.createElement("div");
    row.className = `task-compact-row task-compact-row--${mode}`;
    row.dataset.taskId = task.id;

    const statusOptions = buildStatusOptions(task.status);
    const todayChecked = isTodayProgress(task) ? " checked" : "";
    const projectName = task.project_name || "未归属项目";
    const goalName = task.goal_name || "未归属目标";
    const priority = task.display_priority || priorityForTask(task).label;

    row.innerHTML = `
      <div class="task-compact-main">
        <div class="task-compact-title-row">
          <span class="task-compact-title">${escapeHtml(task.name)}</span>
          <span class="relation-priority ${taskPriorityClass(priority)}">${escapeHtml(priority)}</span>
          <span class="task-status-pill ${statusClass(task.status)}">${escapeHtml(task.status)}</span>
          ${isTodayProgress(task) ? '<span class="task-today-pill">今日</span>' : ""}
        </div>
        ${mode === "overview" ? buildTaskOverviewRelationLine(projectName, goalName) : ""}
      </div>
      <div class="task-compact-actions task-compact-actions--secondary">
        <label class="today-toggle" title="今日推进">
          <input type="checkbox" class="today-checkbox"${todayChecked}>
          <span>今日</span>
        </label>
        <select class="select status-select" title="修改状态">${statusOptions}</select>
        <button type="button" class="btn btn-sm btn-ghost btn-edit-task">编辑</button>
        <button type="button" class="btn btn-sm btn-ghost btn-delete-task">删除</button>
      </div>
    `;

    bindTaskRow(row, task);
    return row;
  }

  function bindTaskRow(row, task) {
    const todayCheckbox = row.querySelector(".today-checkbox");
    todayCheckbox.addEventListener("change", async () => {
      const enabled = todayCheckbox.checked;
      try {
        await apiRequest(`/api/tasks/${task.id}/today-progress`, {
          method: "PATCH",
          body: JSON.stringify({ enabled }),
        });
        await loadTasks();
      } catch (err) {
        todayCheckbox.checked = !enabled;
        showToast(err.message, "error");
      }
    });

    row.querySelector(".btn-edit-task").addEventListener("click", () => {
      openTaskEditModal(task);
    });

    const deleteBtn = row.querySelector(".btn-delete-task");
    deleteBtn.addEventListener("click", async () => {
      if (!window.confirm(`确定删除任务「${task.name}」？此操作不可撤销。`)) {
        return;
      }
      try {
        await apiRequest(`/api/tasks/${task.id}`, { method: "DELETE" });
        showToast("任务已删除", "success");
        await loadTasks();
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    const statusSelect = row.querySelector(".status-select");
    statusSelect.addEventListener("change", async () => {
      const prev = task.status;
      try {
        await apiRequest(`/api/tasks/${task.id}/status`, {
          method: "PATCH",
          body: JSON.stringify({ status: statusSelect.value }),
        });
        task.status = statusSelect.value;
        await loadTasks();
      } catch (err) {
        statusSelect.value = prev;
        showToast(err.message, "error");
      }
    });
  }

  function renderEmptyTasks() {
    tasksList.innerHTML = `
      <div class="empty-state">
        <strong>添加第一个任务</strong>
        点击右上角「新建任务」开始
      </div>
    `;
  }

  function renderTaskSection(title, tasks, shell) {
    if (!tasks.length) return;

    const section = document.createElement("section");
    section.className = "task-focus-section";
    section.innerHTML = `<h3 class="task-focus-section-title">${escapeHtml(title)}</h3>`;

    const list = document.createElement("div");
    list.className = "task-overview-list";
    tasks.forEach((task) => {
      list.appendChild(renderTaskRow(task, "overview"));
    });
    section.appendChild(list);
    shell.appendChild(section);
  }

  function renderOverviewView(tasks) {
    tasksList.innerHTML = "";

    if (tasks.length === 0) {
      renderEmptyTasks();
      return;
    }

    const { focus, backlog } = splitTasks(tasks);
    const shell = document.createElement("div");
    shell.className = "task-focus-layout";

    renderTaskSection("今日行动", focus, shell);

    if (backlog.length > 0) {
      const section = document.createElement("section");
      section.className = "task-focus-section task-focus-section--muted";
      section.innerHTML = `
        <div class="task-focus-section-head">
          <h3 class="task-focus-section-title">其他任务（${backlog.length}）</h3>
          <button type="button" class="btn btn-sm btn-ghost btn-toggle-backlog" aria-expanded="false">展开</button>
        </div>
        <div class="task-backlog-panel" hidden></div>
      `;

      const panel = section.querySelector(".task-backlog-panel");
      const toggleBtn = section.querySelector(".btn-toggle-backlog");
      const list = document.createElement("div");
      list.className = "task-overview-list";
      backlog.forEach((task) => {
        list.appendChild(renderTaskRow(task, "overview"));
      });
      panel.appendChild(list);

      toggleBtn.addEventListener("click", () => {
        const expanded = panel.hidden;
        panel.hidden = !expanded;
        toggleBtn.textContent = expanded ? "收起" : "展开";
        toggleBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
      });

      shell.appendChild(section);
    }

    tasksList.appendChild(shell);
  }

  function renderProjectView(tasks) {
    tasksList.innerHTML = "";

    const groups = groupTasksByProject(tasks).filter((group) => group.stats.total > 0);

    if (groups.length === 0) {
      renderEmptyTasks();
      return;
    }

    groups.forEach((group) => {
      const groupStats = group.stats || calculateStats(group.tasks);
      const groupEl = document.createElement("article");
      groupEl.className = `task-project-group task-project-group--compact ${projectPriorityClasses(group.priority || group.displayPriority)}`;
      groupEl.dataset.projectId = group.projectId || "";
      groupEl.title = `项目优先级：${projectPriorityLabel(group.priority || group.displayPriority)}`;
      groupEl.setAttribute(
        "aria-label",
        `项目 ${group.projectName}，项目优先级 ${projectPriorityLabel(group.priority || group.displayPriority)}`
      );
      const detailId = `task-project-detail-${group.projectId || group.key}`;
      const shouldExpand = group.shouldExpand;

      groupEl.innerHTML = `
        <div class="task-project-group-head task-project-group-head--compact">
          <div class="task-project-group-main">
            <div class="project-title-row task-project-group-title-row">
              <span class="project-priority-dot" aria-hidden="true"></span>
              <div class="task-project-group-heading">
                <h3 class="task-project-group-title">${buildProjectTitleWithGoal(group.projectName, group.goalName)}</h3>
                <span class="project-inline-stats-sep" aria-hidden="true">｜</span>
                <span class="project-inline-stats title-meta inline-meta">
                  <span>${escapeHtml(group.status)}</span>
                  <span>今日 ${groupStats.today}</span>
                  <span>未完成 ${groupStats.open}</span>
                </span>
              </div>
            </div>
          </div>
          <div class="task-project-group-tools">
            <button
              type="button"
              class="btn btn-sm btn-ghost btn-toggle-task-project"
              aria-expanded="${shouldExpand ? "true" : "false"}"
            >${shouldExpand ? "收起" : "展开"}</button>
            <button
              type="button"
              class="btn btn-sm btn-ghost btn-expand-detail"
              data-target="${detailId}"
              aria-expanded="false"
            >详情</button>
          </div>
        </div>
        <div id="${detailId}" class="expand-detail" hidden>
          <div class="expand-detail-panel">
            <div class="expand-detail-grid">
              <span>全部 ${groupStats.total}</span>
              <span>待处理 ${groupStats.pending}</span>
              <span>进行中 ${groupStats.doing}</span>
              <span>已完成 ${groupStats.done}</span>
              <span>最近活动 ${escapeHtml(formatActivity(group.recentActivityAt))}</span>
            </div>
          </div>
        </div>
        <div class="task-project-group-body"${shouldExpand ? "" : " hidden"}>
          <div class="task-project-group-tasks"></div>
        </div>
      `;

      const body = groupEl.querySelector(".task-project-group-tasks");
      group.tasks.forEach((task) => {
        body.appendChild(renderTaskRow(task, "project"));
      });

      const toggleBtn = groupEl.querySelector(".btn-toggle-task-project");
      toggleBtn.addEventListener("click", () => {
        const expanded = groupEl.classList.toggle("task-project-group-expanded");
        body.hidden = !expanded;
        toggleBtn.textContent = expanded ? "收起" : "展开";
        toggleBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
      });

      const detailBtn = groupEl.querySelector(".btn-expand-detail");
      const detailPanel = groupEl.querySelector(`#${detailId}`);
      detailBtn.addEventListener("click", () => {
        const expanded = detailPanel.hidden;
        detailPanel.hidden = !expanded;
        detailBtn.textContent = expanded ? "收起详情" : "详情";
        detailBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
      });

      if (shouldExpand) {
        groupEl.classList.add("task-project-group-expanded");
      }

      tasksList.appendChild(groupEl);
    });
  }

  function renderCurrentView() {
    renderOverviewStats(cachedTasks);
    if (currentView === "project") {
      renderProjectView(cachedTasks);
      return;
    }
    renderOverviewView(cachedTasks);
  }

  async function loadTasks() {
    const tasks = await apiRequest("/api/tasks");
    cachedTasks = tasks.map(enrichTask).sort(compareTasks);
    renderCurrentView();
  }

  function setTaskView(view) {
    currentView = view === "project" ? "project" : "overview";

    viewButtons.forEach((button) => {
      const active = button.dataset.view === currentView;
      button.classList.toggle("is-active", active);
      button.classList.toggle("btn-ghost", !active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });

    renderCurrentView();
  }

  viewButtons.forEach((button) => {
    button.addEventListener("click", () => setTaskView(button.dataset.view));
  });

  if (createTaskBtn) {
    createTaskBtn.addEventListener("click", async () => {
      await loadProjects();
      openCreateTaskModal();
    });
  }

  if (recommendBtn) {
    recommendBtn.addEventListener("click", () => handleAIRecommend(recommendBtn));
  }

  Promise.all([loadProjects(), loadTasks()]).catch((err) => console.error(err));
});

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

function escapeAttr(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}