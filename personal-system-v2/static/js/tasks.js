document.addEventListener("DOMContentLoaded", () => {
  const taskForm = document.getElementById("task-form");
  const tasksList = document.getElementById("tasks-list");
  const taskOverview = document.getElementById("task-overview");
  const projectSelect = document.getElementById("task-project");
  const formHint = document.getElementById("task-form-hint");
  const decomposeBtn = document.getElementById("ai-decompose-btn");
  const recommendBtn = document.getElementById("ai-recommend-btn");
  const viewButtons = Array.from(document.querySelectorAll(".task-view-btn"));

  if (!taskForm || !tasksList) return;

  let currentView = "overview";
  let cachedTasks = [];

  async function loadProjects() {
    const projects = await apiRequest("/api/projects");
    const current = projectSelect.value;

    projectSelect.innerHTML = '<option value="">选择所属项目</option>';
    projects.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.goal_name} / ${p.name}`;
      projectSelect.appendChild(opt);
    });

    if (current) projectSelect.value = current;
    formHint.style.display = projects.length === 0 ? "block" : "none";
    if (decomposeBtn) {
      decomposeBtn.disabled = !projectSelect.value;
    }
  }

  function todayKey() {
    return new Date().toISOString().slice(0, 10);
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

  function calculateStats(tasks) {
    return tasks.reduce(
      (stats, task) => {
        stats.total += 1;
        if (isTodayProgress(task)) stats.today += 1;
        if (task.status === "待处理") stats.pending += 1;
        if (task.status === "进行中") stats.doing += 1;
        if (task.status === "完成") stats.done += 1;
        return stats;
      },
      { total: 0, today: 0, pending: 0, doing: 0, done: 0 }
    );
  }

  function renderOverviewStats(tasks) {
    if (!taskOverview) return;
    const stats = calculateStats(tasks);
    const items = [
      ["全部任务", stats.total],
      ["今日推进", stats.today],
      ["待处理", stats.pending],
      ["进行中", stats.doing],
      ["已完成", stats.done],
    ];

    taskOverview.innerHTML = items
      .map(
        ([label, value]) => `
          <div class="task-overview-chip">
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

    tasks.forEach((task) => {
      const hasProject = task.project_id && task.project_name;
      const key = hasProject ? `project-${task.project_id}` : "unassigned";

      if (!groupMap.has(key)) {
        const group = {
          key,
          projectId: hasProject ? task.project_id : null,
          projectName: hasProject ? task.project_name : "未归属任务",
          goalName: task.goal_name || "未归属目标",
          tasks: [],
        };
        groupMap.set(key, group);
        groups.push(group);
      }

      groupMap.get(key).tasks.push(task);
    });

    return groups;
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
        </div>
      `,
      confirmLabel: "保存",
      loadingLabel: "保存中…",
      onConfirm: async () => {
        const name = document.getElementById("edit-task-name").value.trim();
        const status = document.getElementById("edit-task-status").value;
        if (!name) {
          throw new Error("任务名称不能为空");
        }
        await apiRequest(`/api/tasks/${task.id}`, {
          method: "PATCH",
          body: JSON.stringify({ name, status }),
        });
        showToast("任务已更新", "success");
        await loadTasks();
      },
    });
  }

  async function handleAIDecompose(button) {
    const projectId = parseInt(projectSelect.value, 10);
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
      button.disabled = !projectSelect.value;
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

  function renderTaskRow(task, mode = "overview") {
    const row = document.createElement("div");
    row.className = `task-compact-row task-compact-row--${mode}`;
    row.dataset.taskId = task.id;

    const statusOptions = buildStatusOptions(task.status);
    const todayChecked = isTodayProgress(task) ? " checked" : "";
    const projectName = task.project_name || "未归属任务";
    const goalName = task.goal_name || "未归属目标";

    row.innerHTML = `
      <div class="task-compact-main">
        <div class="task-compact-title-row">
          <span class="task-compact-title">${escapeHtml(task.name)}</span>
          <span class="task-status-pill ${statusClass(task.status)}">${escapeHtml(task.status)}</span>
          ${isTodayProgress(task) ? '<span class="task-today-pill">今日推进</span>' : ""}
        </div>
        <div class="task-compact-meta">
          <span>项目：${escapeHtml(projectName)}</span>
          <span>目标：${escapeHtml(goalName)}</span>
        </div>
      </div>
      <div class="task-compact-actions">
        <label class="today-toggle">
          <input type="checkbox" class="today-checkbox"${todayChecked}>
          <span>今日推进</span>
        </label>
        <select class="select status-select">${statusOptions}</select>
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
        选择项目并输入任务名称
      </div>
    `;
  }

  function renderOverviewView(tasks) {
    tasksList.innerHTML = "";

    if (tasks.length === 0) {
      renderEmptyTasks();
      return;
    }

    const shell = document.createElement("div");
    shell.className = "task-overview-list";
    tasks.forEach((task) => {
      shell.appendChild(renderTaskRow(task, "overview"));
    });
    tasksList.appendChild(shell);
  }

  function renderProjectView(tasks) {
    tasksList.innerHTML = "";

    if (tasks.length === 0) {
      renderEmptyTasks();
      return;
    }

    const groups = groupTasksByProject(tasks);
    groups.forEach((group) => {
      const groupStats = calculateStats(group.tasks);
      const groupEl = document.createElement("article");
      groupEl.className = "task-project-group";
      groupEl.dataset.projectId = group.projectId || "";

      groupEl.innerHTML = `
        <div class="task-project-group-head">
          <div class="task-project-group-main">
            <h3 class="task-project-group-title">${escapeHtml(group.projectName)}</h3>
            <p class="task-project-group-goal">${escapeHtml(group.goalName)}</p>
          </div>
          <div class="task-project-group-stats">
            <span>全部 ${groupStats.total}</span>
            <span>待处理 ${groupStats.pending}</span>
            <span>进行中 ${groupStats.doing}</span>
            <span>已完成 ${groupStats.done}</span>
            <span>今日 ${groupStats.today}</span>
          </div>
          <button type="button" class="btn btn-sm btn-ghost btn-toggle-task-project" aria-expanded="false">展开</button>
        </div>
        <div class="task-project-group-body" hidden></div>
      `;

      const body = groupEl.querySelector(".task-project-group-body");
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
    cachedTasks = await apiRequest("/api/tasks");
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

  if (projectSelect && decomposeBtn) {
    projectSelect.addEventListener("change", () => {
      decomposeBtn.disabled = !projectSelect.value;
    });
    decomposeBtn.addEventListener("click", () => handleAIDecompose(decomposeBtn));
  }

  if (recommendBtn) {
    recommendBtn.addEventListener("click", () => handleAIRecommend(recommendBtn));
  }

  taskForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById("task-name");
    const projectId = parseInt(projectSelect.value, 10);
    const name = nameInput.value.trim();

    if (!projectId || !name) return;

    try {
      await apiRequest("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId, name }),
      });
      nameInput.value = "";
      showToast("任务已保存", "success");
      await loadTasks();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  Promise.all([loadProjects(), loadTasks()]).catch((err) => console.error(err));
});

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}
