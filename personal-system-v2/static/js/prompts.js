document.addEventListener("DOMContentLoaded", () => {
  const moduleFilter = document.getElementById("module-filter");
  const sceneList = document.getElementById("scene-list");
  const editor = document.getElementById("prompt-editor");
  const statusEl = document.getElementById("prompt-status");

  if (!moduleFilter || !sceneList || !editor) return;

  const SCENE_LABELS = {
    briefing: "今日简报",
    "dispatch-actions": "行动分发",
    "decompose-projects": "拆解项目",
    "decompose-tasks": "拆解任务",
    "recommend-today": "今日推荐",
    "refine-to-asset": "提炼资产",
    "complete-fields": "补全字段",
    "aggregate-weekly": "周复盘聚合",
    optimize: "优化润色",
    classify: "归类建议",
    template: "模板化",
    attribute: "进展归因",
    diagnose: "能力诊断",
  };

  const SCENE_HINTS = {
    briefing: "用户上下文由系统自动拼装（主线/项目/任务/复盘）",
    "dispatch-actions": "用户上下文含项目与任务 id 列表，由系统自动拼装",
    "recommend-today": "用户上下文为未完成任务列表，由系统自动拼装",
    "aggregate-weekly": "用户上下文为选中的日复盘全文，由系统自动拼装",
    attribute: "用户上下文为近期任务/复盘/资产，由系统自动拼装",
    diagnose: "用户上下文为八模块统计数据，由系统自动拼装",
  };

  const USER_VARS = {
    "decompose-projects": "{goal_name} {goal_type} {existing_projects}",
    "decompose-tasks":
      "{project_name} {goal_name} {goal_type} {existing_tasks}",
    "refine-to-asset":
      "{review_date} {review_type} {what_done} {stuck} {next_adjust} {depositable}",
    "complete-fields": "{review_type} {what_done}",
    optimize: "{title} {trigger_context} {core_content}",
    classify:
      "{title} {asset_type} {capability_tags} {trigger_context} {core_content}",
    template: "{title} {asset_type} {trigger_context} {core_content}",
  };

  const SYSTEM_VARS = {
    "refine-to-asset": "{capability_list}",
    classify: "{asset_types} {capability_list}",
    template: "{target_type}",
    attribute: "{module}",
  };

  let allItems = [];
  let activeModule = moduleFilter.querySelector(".filter-chip.active")?.dataset.module;
  let activeScene = null;

  function setStatus(message, isError = false) {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.classList.toggle("prompt-status-error", isError);
  }

  function sceneLabel(scene) {
    return SCENE_LABELS[scene] || scene;
  }

  function groupByScene(items) {
    const scenes = {};
    items.forEach((item) => {
      if (!scenes[item.scene]) {
        scenes[item.scene] = { scene: item.scene, hasSystem: false, hasUser: false };
      }
      if (item.kind === "system") scenes[item.scene].hasSystem = true;
      if (item.kind === "user") scenes[item.scene].hasUser = true;
    });
    return Object.values(scenes).sort((a, b) => a.scene.localeCompare(b.scene));
  }

  function renderSceneList() {
    const items = allItems.filter((item) => item.module === activeModule);
    const scenes = groupByScene(items);

    if (scenes.length === 0) {
      sceneList.innerHTML = '<p class="prompt-list-hint">该模块暂无提示词</p>';
      return;
    }

    sceneList.innerHTML = scenes
      .map(
        (s) => `
      <button
        type="button"
        class="prompt-scene-item${activeScene === s.scene ? " active" : ""}"
        data-scene="${escapeAttr(s.scene)}"
      >
        <span class="prompt-scene-name">${escapeHtml(sceneLabel(s.scene))}</span>
        <span class="prompt-scene-meta">${escapeHtml(s.scene)}</span>
      </button>
    `
      )
      .join("");

    sceneList.querySelectorAll(".prompt-scene-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        loadScene(btn.dataset.scene);
      });
    });
  }

  function renderEditor(data) {
    const hint = SCENE_HINTS[data.scene];
    const userVars = USER_VARS[data.scene];
    const systemVars = SYSTEM_VARS[data.scene];
    const hasUser = data.user !== null && data.user !== undefined;

    editor.innerHTML = `
      <header class="prompt-editor-head">
        <div>
          <h3 class="prompt-editor-title">${escapeHtml(sceneLabel(data.scene))}</h3>
          <p class="form-hint">${escapeHtml(data.module)} / ${escapeHtml(data.scene)}</p>
        </div>
      </header>

      <div class="stacked-form">
        <div class="form-row">
          <div class="prompt-field-head">
            <label class="form-label" for="prompt-system">系统提示词</label>
            <button type="button" class="btn btn-sm" id="save-system-btn">保存</button>
          </div>
          ${systemVars ? `<p class="form-hint">可用变量：${escapeHtml(systemVars)}</p>` : ""}
          <textarea id="prompt-system" class="textarea prompt-textarea" rows="14">${escapeHtml(data.system || "")}</textarea>
        </div>

        <div class="form-row">
          <div class="prompt-field-head">
            <label class="form-label" for="prompt-user">用户上下文模板</label>
            ${
              hasUser
                ? '<button type="button" class="btn btn-sm" id="save-user-btn">保存</button>'
                : ""
            }
          </div>
          ${
            hint
              ? `<p class="form-hint">${escapeHtml(hint)}</p>`
              : userVars
                ? `<p class="form-hint">可用变量：${escapeHtml(userVars)}</p>`
                : '<p class="form-hint">此场景无用户模板文件</p>'
          }
          <textarea
            id="prompt-user"
            class="textarea prompt-textarea"
            rows="10"
            ${hint || !hasUser ? "disabled" : ""}
          >${escapeHtml(data.user || "")}</textarea>
        </div>
      </div>
    `;

    document.getElementById("save-system-btn").addEventListener("click", () => {
      savePrompt("system");
    });

    const saveUserBtn = document.getElementById("save-user-btn");
    if (saveUserBtn) {
      saveUserBtn.addEventListener("click", () => savePrompt("user"));
    }
  }

  async function loadScene(scene) {
    activeScene = scene;
    renderSceneList();
    editor.innerHTML = '<p class="prompt-loading">加载中…</p>';
    setStatus("");

    try {
      const data = await apiRequest(`/api/ai/prompts/${activeModule}/${scene}`);
      renderEditor(data);
    } catch (err) {
      editor.innerHTML = `
        <div class="empty-state empty-state-compact">
          <strong>加载失败</strong>
          ${escapeHtml(err.message)}
        </div>
      `;
    }
  }

  async function savePrompt(kind) {
    const textarea = document.getElementById(
      kind === "system" ? "prompt-system" : "prompt-user"
    );
    if (!textarea || !activeModule || !activeScene) return;

    const btn = document.getElementById(
      kind === "system" ? "save-system-btn" : "save-user-btn"
    );
    const prev = btn?.textContent;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "保存中…";
    }

    try {
      const result = await apiRequest(
        `/api/ai/prompts/${activeModule}/${activeScene}`,
        {
          method: "PUT",
          body: JSON.stringify({ kind, content: textarea.value }),
        }
      );
      setStatus(`已保存 ${result.path || kind}`);
      await loadCatalog(false);
    } catch (err) {
      setStatus(err.message || "保存失败", true);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = prev;
      }
    }
  }

  async function loadCatalog(selectFirstScene = true) {
    allItems = await apiRequest("/api/ai/prompts");
    renderSceneList();

    if (selectFirstScene) {
      const scenes = groupByScene(
        allItems.filter((item) => item.module === activeModule)
      );
      if (scenes.length > 0) {
        await loadScene(scenes[0].scene);
        return;
      }
    }

    if (activeScene) {
      const exists = allItems.some(
        (item) => item.module === activeModule && item.scene === activeScene
      );
      if (exists) {
        await loadScene(activeScene);
        return;
      }
    }

    activeScene = null;
    editor.innerHTML = `
      <div class="empty-state empty-state-compact">
        <strong>选择左侧场景</strong>
        编辑系统提示词与用户上下文模板
      </div>
    `;
  }

  moduleFilter.addEventListener("click", async (e) => {
    const chip = e.target.closest(".filter-chip");
    if (!chip) return;

    moduleFilter.querySelectorAll(".filter-chip").forEach((el) => {
      el.classList.remove("active");
    });
    chip.classList.add("active");
    activeModule = chip.dataset.module;
    activeScene = null;
    setStatus("");
    await loadCatalog(true);
  });

  loadCatalog(true).catch((err) => {
    setStatus(err.message || "加载提示词列表失败", true);
  });
});

function escapeAttr(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}