document.addEventListener("DOMContentLoaded", () => {
  const goalEl = document.getElementById("dashboard-goal-content");
  const projectsEl = document.getElementById("dashboard-projects-content");
  const tasksEl = document.getElementById("dashboard-tasks-content");
  const briefingBtn = document.getElementById("ai-briefing-btn");

  if (!goalEl || !projectsEl || !tasksEl) return;

  function emptyState(strong, hint) {
    return `
      <div class="empty-state empty-state-compact">
        <strong>${escapeHtml(strong)}</strong>
        ${escapeHtml(hint)}
      </div>
    `;
  }

  async function loadDashboard() {
    const data = await apiRequest("/api/dashboard");

    if (data.mainline_goal) {
      const g = data.mainline_goal;
      goalEl.innerHTML = `
        <div class="dashboard-goal-card">
          <h3 class="entity-title">${escapeHtml(g.name)}</h3>
          <span class="tag">${escapeHtml(g.type)}</span>
        </div>
      `;
    } else {
      goalEl.innerHTML = emptyState(
        "暂无主线目标",
        "前往「目标」模块，创建类型为「当前主线」的目标"
      );
    }

    if (data.week_projects && data.week_projects.length > 0) {
      projectsEl.innerHTML = `
        <ul class="dashboard-list">
          ${data.week_projects
            .map(
              (p) => `
            <li class="dashboard-list-item">
              <span class="dashboard-item-name">${escapeHtml(p.name)}</span>
              <span class="dashboard-item-meta">${escapeHtml(p.goal_name)}</span>
            </li>
          `
            )
            .join("")}
        </ul>
      `;
    } else {
      projectsEl.innerHTML = emptyState(
        "暂无本周进行中项目",
        "在目标下拆解项目，并确保有未完成任务"
      );
    }

    if (data.today_tasks && data.today_tasks.length > 0) {
      tasksEl.innerHTML = `
        <ul class="dashboard-list">
          ${data.today_tasks
            .map(
              (t) => `
            <li class="dashboard-list-item">
              <span class="dashboard-item-name">${escapeHtml(t.name)}</span>
              <span class="dashboard-item-meta">
                ${escapeHtml(t.goal_name)} / ${escapeHtml(t.project_name)}
                · ${escapeHtml(t.status)}
              </span>
            </li>
          `
            )
            .join("")}
        </ul>
      `;
    } else {
      tasksEl.innerHTML = emptyState(
        "暂无今日推进任务",
        "在「任务」模块勾选「今日推进」后在此展示"
      );
    }
  }

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
        alert(err.message || "AI 简报生成失败");
      } finally {
        briefingBtn.disabled = false;
        briefingBtn.textContent = prev;
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