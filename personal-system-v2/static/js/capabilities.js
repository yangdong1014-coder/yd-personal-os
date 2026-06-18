document.addEventListener("DOMContentLoaded", () => {
  const panels = document.querySelectorAll(".module-panel");
  const diagnoseBtn = document.getElementById("ai-diagnose-btn");
  const levelTypes = window.LEVEL_TYPES || [];

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
    container.innerHTML = "";

    if (!entries.length) {
      container.innerHTML = '<p class="history-empty">暂无记录</p>';
      return;
    }

    entries.forEach((entry) => {
      const item = document.createElement("article");
      item.className = "history-item";
      item.innerHTML = `
        <div class="history-item-head">
          <span class="history-date">${escapeHtml(entry.entry_date)}</span>
          <span class="tag">${escapeHtml(entry.level_type)}</span>
          <button type="button" class="btn btn-sm btn-ghost btn-delete-entry">删除</button>
        </div>
        <p class="history-content">${formatText(entry.content)}</p>
        ${
          entry.source_project
            ? `<p class="history-meta">来源：${escapeHtml(entry.source_project)}</p>`
            : ""
        }
      `;

      item.querySelector(".btn-delete-entry").addEventListener("click", async () => {
        if (
          !window.confirm(
            `确定删除 ${entry.entry_date} 的能力记录？此操作不可撤销。`
          )
        ) {
          return;
        }
        try {
          await apiRequest(`/api/capability-entries/${entry.id}`, {
            method: "DELETE",
          });
          showToast("能力记录已删除", "success");
          await loadAllEntries();
        } catch (err) {
          showToast(err.message, "error");
        }
      });

      container.appendChild(item);
    });
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

  async function handleAIDiagnose(button) {
    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "诊断中…";

    try {
      const result = await apiRequest("/api/ai/diagnose-capabilities", {
        method: "POST",
        body: JSON.stringify({}),
      });

      const imbalancesHtml = (result.imbalances || [])
        .map((item) => `<li>${escapeHtml(item)}</li>`)
        .join("");

      showAIViewModal({
        title: "AI 能力诊断",
        bodyHtml: `
          <div class="ai-briefing">
            <p class="ai-briefing-text">${formatMultiline(result.summary)}</p>
            ${
              imbalancesHtml
                ? `<h4 class="ai-briefing-subtitle">失衡提示</h4><ul class="ai-briefing-list">${imbalancesHtml}</ul>`
                : ""
            }
            ${
              result.focus_module
                ? `<p class="ai-briefing-focus"><strong>关注模块：</strong>${escapeHtml(result.focus_module)}${result.focus_action ? ` — ${escapeHtml(result.focus_action)}` : ""}</p>`
                : ""
            }
          </div>
        `,
      });
    } catch (err) {
      showToast(err.message || "AI 诊断失败", "error");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  async function handleAIAttribute(panel, button) {
    const module = panel.dataset.module;
    const prevText = button.textContent;
    button.disabled = true;
    button.textContent = "归因中…";

    try {
      const draft = await apiRequest("/api/ai/attribute-capability", {
        method: "POST",
        body: JSON.stringify({ module }),
      });

      showAIModal({
        title: `AI 进展归因 · ${module}`,
        bodyHtml: buildCapabilityAttributeHtml(draft, levelTypes),
        confirmLabel: "确认保存",
        onConfirm: async () => {
          const data = readCapabilityAttributeForm();
          if (!data.content) {
            throw new Error("进展内容不能为空");
          }
          await apiRequest("/api/capability-entries", {
            method: "POST",
            body: JSON.stringify({
              module,
              entry_date: panel.querySelector(".entry-date").value || today,
              content: data.content,
              source_project: data.source_project,
              level_type: data.level_type,
            }),
          });
          panel.querySelector(".entry-content").value = "";
          await loadAllEntries();
        },
      });
    } catch (err) {
      showToast(err.message || "AI 归因失败", "error");
    } finally {
      button.disabled = false;
      button.textContent = prevText;
    }
  }

  if (diagnoseBtn) {
    diagnoseBtn.addEventListener("click", () => handleAIDiagnose(diagnoseBtn));
  }

  panels.forEach((panel) => {
    const form = panel.querySelector(".entry-form");
    const attrBtn = panel.querySelector(".btn-attribute");

    if (attrBtn) {
      attrBtn.addEventListener("click", () => handleAIAttribute(panel, attrBtn));
    }

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
        showToast("能力记录已保存", "success");
        await loadAllEntries();
      } catch (err) {
        showToast(err.message, "error");
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