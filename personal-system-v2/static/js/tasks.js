document.addEventListener("DOMContentLoaded", () => {
  const taskForm = document.getElementById("task-form");
  const tasksList = document.getElementById("tasks-list");
  const projectSelect = document.getElementById("task-project");
  const formHint = document.getElementById("task-form-hint");
  const decomposeBtn = document.getElementById("ai-decompose-btn");
  const recommendBtn = document.getElementById("ai-recommend-btn");

  if (!taskForm || !tasksList) return;

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

  function isTodayProgress(task) {
    const today = new Date().toISOString().slice(0, 10);
    return task.today_progress === 1 && task.today_progress_date === today;
  }

  function buildStatusOptions(selected) {
    return (window.TASK_STATUSES || [])
      .map(
        (s) =>
          `<option value="${escapeAttr(s)}"${s === selected ? " selected" : ""}>${escapeHtml(s)}</option>`
      )
      .join("");
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

  async function loadTasks() {
    const tasks = await apiRequest("/api/tasks");

    tasksList.innerHTML = "";

    if (tasks.length === 0) {
      tasksList.innerHTML = `
        <div class="empty-state">
          <strong>添加第一个任务</strong>
          选择项目并输入任务名称
        </div>
      `;
      return;
    }

    tasks.forEach((task) => {
      const row = document.createElement("div");
      row.className = "task-row";
      row.dataset.taskId = task.id;

      const statusOptions = buildStatusOptions(task.status);

      const todayChecked = isTodayProgress(task) ? " checked" : "";

      row.innerHTML = `
        <div class="task-info">
          <span class="task-name">${escapeHtml(task.name)}</span>
          <span class="task-meta">${escapeHtml(task.goal_name)} / ${escapeHtml(task.project_name)}</span>
        </div>
        <div class="task-actions">
          <label class="today-toggle">
            <input type="checkbox" class="today-checkbox"${todayChecked}>
            <span>今日推进</span>
          </label>
          <select class="select status-select">${statusOptions}</select>
          <button type="button" class="btn btn-sm btn-ghost btn-edit-task">编辑</button>
          <button type="button" class="btn btn-sm btn-ghost btn-delete-task">删除</button>
        </div>
      `;

      const todayCheckbox = row.querySelector(".today-checkbox");
      todayCheckbox.addEventListener("change", async () => {
        const enabled = todayCheckbox.checked;
        try {
          await apiRequest(`/api/tasks/${task.id}/today-progress`, {
            method: "PATCH",
            body: JSON.stringify({ enabled }),
          });
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
        if (
          !window.confirm(
            `确定删除任务「${task.name}」？此操作不可撤销。`
          )
        ) {
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
        } catch (err) {
          statusSelect.value = prev;
          showToast(err.message, "error");
        }
      });

      tasksList.appendChild(row);
    });
  }

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
  div.textContent = text;
  return div.innerHTML;
}
