document.addEventListener("DOMContentLoaded", () => {
  const taskForm = document.getElementById("task-form");
  const tasksList = document.getElementById("tasks-list");
  const projectSelect = document.getElementById("task-project");
  const formHint = document.getElementById("task-form-hint");

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
  }

  function isTodayProgress(task) {
    const today = new Date().toISOString().slice(0, 10);
    return task.today_progress === 1 && task.today_progress_date === today;
  }

  async function loadTasks() {
    const tasks = await apiRequest("/api/tasks");
    const statuses = window.TASK_STATUSES || [];

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

      const statusOptions = statuses
        .map(
          (s) =>
            `<option value="${s}"${s === task.status ? " selected" : ""}>${s}</option>`
        )
        .join("");

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
          alert(err.message);
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
          alert(err.message);
        }
      });

      tasksList.appendChild(row);
    });
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
      await loadTasks();
    } catch (err) {
      alert(err.message);
    }
  });

  Promise.all([loadProjects(), loadTasks()]).catch((err) => console.error(err));
});

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}