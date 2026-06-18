document.addEventListener("DOMContentLoaded", () => {
  const panels = document.querySelectorAll(".module-panel");
  if (!panels.length) return;

  const today = new Date().toISOString().slice(0, 10);
  panels.forEach((panel) => {
    const dateInput = panel.querySelector(".entry-date");
    if (dateInput) dateInput.value = today;
  });

  async function loadProjects() {
    const projects = await apiRequest("/api/projects");
    panels.forEach((panel) => {
      const select = panel.querySelector(".entry-project");
      if (!select) return;
      const current = select.value;
      select.innerHTML = '<option value="">无</option>';
      projects.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = `${p.goal_name} / ${p.name}`;
        opt.textContent = opt.value;
        select.appendChild(opt);
      });
      if (current) select.value = current;
    });
  }

  function renderHistory(container, entries) {
    if (!entries.length) {
      container.innerHTML = '<p class="history-empty">暂无记录</p>';
      return;
    }

    container.innerHTML = entries
      .map(
        (e) => `
        <article class="history-item">
          <div class="history-item-head">
            <span class="history-date">${escapeHtml(e.entry_date)}</span>
            <span class="tag">${escapeHtml(e.level_type)}</span>
          </div>
          <p class="history-content">${formatText(e.content)}</p>
          ${
            e.source_project
              ? `<p class="history-meta">来源：${escapeHtml(e.source_project)}</p>`
              : ""
          }
        </article>
      `
      )
      .join("");
  }

  async function loadAllEntries() {
    const entries = await apiRequest("/api/capability-entries");
    const byModule = {};
    entries.forEach((e) => {
      if (!byModule[e.module]) byModule[e.module] = [];
      byModule[e.module].push(e);
    });

    panels.forEach((panel) => {
      const module = panel.dataset.module;
      const list = panel.querySelector(".history-list");
      renderHistory(list, byModule[module] || []);
    });
  }

  panels.forEach((panel) => {
    const form = panel.querySelector(".entry-form");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const module = panel.dataset.module;

      const payload = {
        module,
        entry_date: panel.querySelector(".entry-date").value,
        content: panel.querySelector(".entry-content").value,
        source_project: panel.querySelector(".entry-project").value,
        level_type: panel.querySelector(".entry-level").value,
      };

      try {
        await apiRequest("/api/capability-entries", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        panel.querySelector(".entry-content").value = "";
        await loadAllEntries();
      } catch (err) {
        alert(err.message);
      }
    });
  });

  Promise.all([loadProjects(), loadAllEntries()]).catch((err) =>
    console.error(err)
  );
});

function formatText(text) {
  return escapeHtml(text || "").replace(/\n/g, "<br>");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}