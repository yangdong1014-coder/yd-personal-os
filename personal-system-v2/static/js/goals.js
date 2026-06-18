document.addEventListener("DOMContentLoaded", () => {
  const goalForm = document.getElementById("goal-form");
  const goalsList = document.getElementById("goals-list");
  if (!goalForm || !goalsList) return;

  function renderEmpty() {
    goalsList.innerHTML = `
      <div class="empty-state">
        <strong>添加第一个目标</strong>
        输入名称与类型后即时保存
      </div>
    `;
  }

  async function loadGoals() {
    const goals = await apiRequest("/api/goals");
    const projects = await apiRequest("/api/projects");

    const projectsByGoal = {};
    projects.forEach((p) => {
      if (!projectsByGoal[p.goal_id]) projectsByGoal[p.goal_id] = [];
      projectsByGoal[p.goal_id].push(p);
    });

    goalsList.innerHTML = "";

    if (goals.length === 0) {
      renderEmpty();
      return;
    }

    goals.forEach((goal) => {
      const card = document.createElement("article");
      card.className = "entity-card";
      card.dataset.goalId = goal.id;

      const goalProjects = projectsByGoal[goal.id] || [];

      card.innerHTML = `
        <div class="entity-header">
          <div>
            <h3 class="entity-title">${escapeHtml(goal.name)}</h3>
            <span class="tag">${escapeHtml(goal.type)}</span>
          </div>
        </div>
        <div class="nested-block">
          <h4 class="nested-title">项目（${goalProjects.length}）</h4>
          <ul class="nested-list">
            ${goalProjects.map((p) => `<li>${escapeHtml(p.name)}</li>`).join("")}
            ${goalProjects.length === 0 ? '<li class="muted">暂无项目</li>' : ""}
          </ul>
          <form class="inline-form nested-form project-form">
            <input type="text" class="input project-name" placeholder="新建项目名称" required>
            <button type="submit" class="btn btn-sm">添加项目</button>
          </form>
        </div>
      `;

      const projectForm = card.querySelector(".project-form");
      projectForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = projectForm.querySelector(".project-name");
        const name = input.value.trim();
        if (!name) return;

        try {
          await apiRequest("/api/projects", {
            method: "POST",
            body: JSON.stringify({ goal_id: goal.id, name }),
          });
          input.value = "";
          await loadGoals();
        } catch (err) {
          alert(err.message);
        }
      });

      goalsList.appendChild(card);
    });
  }

  goalForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById("goal-name");
    const typeSelect = document.getElementById("goal-type");
    const name = nameInput.value.trim();
    if (!name) return;

    try {
      await apiRequest("/api/goals", {
        method: "POST",
        body: JSON.stringify({ name, type: typeSelect.value }),
      });
      nameInput.value = "";
      await loadGoals();
    } catch (err) {
      alert(err.message);
    }
  });

  loadGoals().catch((err) => console.error(err));
});

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}