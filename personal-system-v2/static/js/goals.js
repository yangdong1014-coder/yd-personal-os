document.addEventListener("DOMContentLoaded", () => {
  const goalForm = document.getElementById("goal-form");
  const goalsList = document.getElementById("goals-list");
  const newTypeSelect = document.getElementById("goal-type");

  if (!goalForm || !goalsList) return;

  let cachedGoals = [];

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
      alert(err.message || "AI 拆解失败");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

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
    cachedGoals = goals;

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

    const goalTypes = window.GOAL_TYPES || [];
    const typeOptions = (selected) =>
      goalTypes
        .map(
          (t) =>
            `<option value="${escapeHtml(t)}"${t === selected ? " selected" : ""}>${escapeHtml(t)}</option>`
        )
        .join("");

    goals.forEach((goal) => {
      const card = document.createElement("article");
      card.className = "entity-card";
      card.dataset.goalId = goal.id;

      const goalProjects = projectsByGoal[goal.id] || [];

      card.innerHTML = `
        <div class="entity-header">
          <div>
            <h3 class="entity-title">${escapeHtml(goal.name)}</h3>
            <select class="select goal-type-select" title="修改目标类型">${typeOptions(goal.type)}</select>
          </div>
          <div class="card-actions">
            <button type="button" class="btn btn-sm btn-ai">AI拆解</button>
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

      const aiBtn = card.querySelector(".btn-ai");
      aiBtn.addEventListener("click", (e) => {
        handleAIDecompose(goal, e.currentTarget);
      });

      const typeSelect = card.querySelector(".goal-type-select");
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
          alert(err.message);
        }
      });

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

  if (newTypeSelect) {
    newTypeSelect.addEventListener("change", () => {
      if (newTypeSelect.value !== "当前主线") return;

      const existing = findMainline(cachedGoals);
      if (existing && !confirmMainlineSwitch(existing)) {
        newTypeSelect.value = "年度";
      }
    });
  }

  goalForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById("goal-name");
    const typeSelect = document.getElementById("goal-type");
    const name = nameInput.value.trim();
    if (!name) return;

    const goalType = typeSelect.value;
    if (goalType === "当前主线") {
      const existing = findMainline(cachedGoals);
      if (existing && !confirmMainlineSwitch(existing)) {
        typeSelect.value = "年度";
        return;
      }
    }

    try {
      await apiRequest("/api/goals", {
        method: "POST",
        body: JSON.stringify({ name, type: goalType }),
      });
      nameInput.value = "";
      typeSelect.value = "年度";
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