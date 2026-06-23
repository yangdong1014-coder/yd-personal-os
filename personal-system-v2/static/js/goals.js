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
        </div>
      `,
      confirmLabel: "保存",
      loadingLabel: "保存中…",
      onConfirm: async () => {
        const name = document.getElementById("edit-project-name").value.trim();
        if (!name) {
          throw new Error("项目名称不能为空");
        }
        await apiRequest(`/api/projects/${project.id}`, {
          method: "PATCH",
          body: JSON.stringify({ name }),
        });
        showToast("项目已更新", "success");
        await loadGoals();
      },
    });
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

    goals.forEach((goal) => {
      const card = document.createElement("article");
      card.className = "entity-card";
      card.dataset.goalId = goal.id;

      const goalProjects = projectsByGoal[goal.id] || [];

      card.innerHTML = `
        <div class="entity-header">
          <div>
            <h3 class="entity-title">${escapeHtml(goal.name)}</h3>
            <select class="select goal-type-select" title="修改目标类型">${buildGoalTypeOptions(goal.type)}</select>
          </div>
          <div class="card-actions">
            <button type="button" class="btn btn-sm btn-ai">AI拆解</button>
            <button type="button" class="btn btn-sm btn-ghost btn-edit-goal">编辑</button>
            <button type="button" class="btn btn-sm btn-ghost btn-delete-goal">删除</button>
          </div>
        </div>
        <div class="nested-block">
          <h4 class="nested-title">项目（${goalProjects.length}）</h4>
          <ul class="nested-list">
            ${goalProjects
              .map(
                (p) => `
              <li class="nested-item">
                <span>${escapeHtml(p.name)}</span>
                <div class="nested-item-actions">
                  <button type="button" class="btn btn-sm btn-ghost btn-edit-project" data-project-id="${p.id}">编辑</button>
                  <button type="button" class="btn btn-sm btn-ghost btn-delete-project" data-project-id="${p.id}">删除</button>
                </div>
              </li>`
              )
              .join("")}
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

      card.querySelector(".btn-edit-goal").addEventListener("click", () => {
        openGoalEditModal(goal);
      });

      card.querySelectorAll(".btn-edit-project").forEach((btn) => {
        btn.addEventListener("click", () => {
          const projectId = parseInt(btn.dataset.projectId, 10);
          const project = goalProjects.find((p) => p.id === projectId);
          if (project) openProjectEditModal(project);
        });
      });

      const deleteGoalBtn = card.querySelector(".btn-delete-goal");
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
          showToast("项目已添加", "success");
          await loadGoals();
        } catch (err) {
          showToast(err.message, "error");
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
      showToast("目标已保存", "success");
      await loadGoals();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  loadGoals().catch((err) => console.error(err));
});

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
