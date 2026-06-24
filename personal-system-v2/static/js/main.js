const UI_THEME_STORAGE_KEY = "personal-os-ui-theme";

const UI_THEMES = [
  { id: "theme-dark-warm", label: "外观：深色暖色" },
  { id: "theme-dark-cool", label: "外观：深色冷色" },
  { id: "theme-light-warm", label: "外观：浅色暖色" },
  { id: "theme-light-cool", label: "外观：浅色冷色" },
];

function getStoredUiTheme() {
  const saved = localStorage.getItem(UI_THEME_STORAGE_KEY);
  return UI_THEMES.some((theme) => theme.id === saved) ? saved : UI_THEMES[0].id;
}

function applyUiTheme(themeId) {
  const theme =
    UI_THEMES.find((item) => item.id === themeId) || UI_THEMES[0];
  const root = document.documentElement;

  UI_THEMES.forEach((item) => root.classList.remove(item.id));
  root.classList.add(theme.id);
  localStorage.setItem(UI_THEME_STORAGE_KEY, theme.id);

  const label = document.getElementById("theme-toggle-label");
  if (label) {
    label.textContent = theme.label;
  }
}

function cycleUiTheme() {
  const current = getStoredUiTheme();
  const index = UI_THEMES.findIndex((item) => item.id === current);
  const next = UI_THEMES[(index + 1) % UI_THEMES.length];
  applyUiTheme(next.id);
}

function authFetchOptions(options = {}) {
  return {
    credentials: "same-origin",
    ...options,
    headers: {
      ...getAccessTokenHeaders(),
      ...(options.headers || {}),
    },
  };
}

document.addEventListener("DOMContentLoaded", () => {
  applyUiTheme(getStoredUiTheme());

  const themeBtn = document.getElementById("theme-toggle-btn");
  if (themeBtn) {
    themeBtn.addEventListener("click", cycleUiTheme);
  }

  const path = window.location.pathname;
  document.querySelectorAll(".nav-link").forEach((link) => {
    if (
      link.id === "export-data-btn" ||
      link.id === "export-obsidian-btn" ||
      link.id === "import-data-btn"
    ) {
      return;
    }
    const href = link.getAttribute("href");
    if (href === path || (path === "/" && href === "/")) {
      link.classList.add("active");
    }
  });

  const exportBtn = document.getElementById("export-data-btn");
  if (exportBtn) {
    exportBtn.addEventListener("click", handleExport);
  }

  const obsidianBtn = document.getElementById("export-obsidian-btn");
  if (obsidianBtn) {
    obsidianBtn.addEventListener("click", handleObsidianExport);
  }

  const importBtn = document.getElementById("import-data-btn");
  const importInput = document.getElementById("import-data-input");
  if (importBtn && importInput) {
    importBtn.addEventListener("click", () => importInput.click());
    importInput.addEventListener("change", handleImportSelect);
  }

  bindImportPanelEvents();
});

let pendingImportPayload = null;

function bindImportPanelEvents() {
  const previewOverlay = document.getElementById("import-preview-overlay");
  const previewClose = document.getElementById("import-preview-close");
  const previewCancel = document.getElementById("import-preview-cancel");
  const previewConfirm = document.getElementById("import-preview-confirm");
  const resultOverlay = document.getElementById("import-result-overlay");
  const resultClose = document.getElementById("import-result-close");
  const resultDone = document.getElementById("import-result-done");

  if (previewClose) {
    previewClose.addEventListener("click", () => closeImportPreview());
  }
  if (previewCancel) {
    previewCancel.addEventListener("click", () => closeImportPreview());
  }
  if (previewConfirm) {
    previewConfirm.addEventListener("click", () => executeImport());
  }
  if (previewOverlay) {
    previewOverlay.addEventListener("click", (e) => {
      if (e.target === previewOverlay) closeImportPreview();
    });
  }

  if (resultClose) {
    resultClose.addEventListener("click", () => closeImportResult());
  }
  if (resultDone) {
    resultDone.addEventListener("click", () => closeImportResult());
  }
  if (resultOverlay) {
    resultOverlay.addEventListener("click", (e) => {
      if (e.target === resultOverlay) closeImportResult();
    });
  }
}

function renderImportStats(container, items) {
  if (!container) return;
  container.innerHTML = items
    .map(
      ({ label, value }) => `
        <div class="import-stat">
          <span class="import-stat-label">${label}</span>
          <span class="import-stat-value">${value ?? 0}</span>
        </div>
      `
    )
    .join("");
}

function renderErrorList(listEl, errors) {
  if (!listEl) return;
  if (!errors || errors.length === 0) {
    listEl.hidden = true;
    listEl.innerHTML = "";
    return;
  }
  listEl.hidden = false;
  listEl.innerHTML = errors.map((e) => `<li>${escapeHtml(String(e))}</li>`).join("");
}

function openImportPreview(stats) {
  const overlay = document.getElementById("import-preview-overlay");
  const statsEl = document.getElementById("import-preview-stats");
  const errorsEl = document.getElementById("import-preview-errors");
  const confirmBtn = document.getElementById("import-preview-confirm");

  renderImportStats(statsEl, [
    { label: "预计新增", value: stats.will_import },
    { label: "预计更新", value: stats.will_update },
    { label: "预计跳过", value: stats.will_skip },
    { label: "预计失败", value: stats.will_fail },
  ]);
  renderErrorList(errorsEl, stats.errors);

  if (confirmBtn) {
    confirmBtn.disabled = stats.will_fail > 0;
    confirmBtn.textContent =
      stats.will_fail > 0 ? "存在错误，无法导入" : "确认导入";
  }

  if (overlay) overlay.hidden = false;
}

function closeImportPreview() {
  const overlay = document.getElementById("import-preview-overlay");
  if (overlay) overlay.hidden = true;
  pendingImportPayload = null;
}

function showImportResult(stats, isError) {
  const overlay = document.getElementById("import-result-overlay");
  const titleEl = document.getElementById("import-result-title");
  const statsEl = document.getElementById("import-result-stats");
  const noteEl = document.getElementById("import-result-note");
  const errorsEl = document.getElementById("import-result-errors");

  const rolledBack = Boolean(stats.rolled_back);
  const created = rolledBack ? 0 : (stats.created ?? 0);
  const updated = rolledBack ? 0 : (stats.updated ?? 0);
  const skipped = rolledBack ? 0 : (stats.skipped ?? 0);
  const failed = stats.failed ?? 0;

  if (titleEl) {
    titleEl.textContent = rolledBack ? "导入失败" : "导入结果";
  }

  renderImportStats(statsEl, [
    { label: "新增", value: created },
    { label: "更新", value: updated },
    { label: "跳过", value: skipped },
    { label: "失败", value: failed },
  ]);
  renderErrorList(errorsEl, stats.errors);

  if (noteEl) {
    if (rolledBack) {
      noteEl.hidden = false;
      noteEl.textContent =
        stats.message ||
        "导入失败，所有变更已回滚，数据库未被修改。";
    } else if (skipped > 0) {
      noteEl.hidden = false;
      noteEl.textContent = `${skipped} 条记录因内容相同已跳过合并。`;
    } else {
      noteEl.hidden = true;
    }
  }

  if (overlay) overlay.hidden = false;

  if (rolledBack || (isError && created === 0 && updated === 0)) {
    showToast("导入失败，已回滚，数据未改变", "error");
  } else if (failed > 0) {
    showToast(
      `导入部分完成：新增 ${created}，更新 ${updated}，失败 ${failed}`,
      "warning"
    );
  } else if (skipped > 0 && created === 0 && updated === 0) {
    showToast("导入完成，数据已是最新", "info");
  } else {
    showToast(`导入完成：新增 ${created}，更新 ${updated}`, "success");
  }
}

function closeImportResult() {
  const overlay = document.getElementById("import-result-overlay");
  if (overlay) overlay.hidden = true;
}

function setImportBusy(busy) {
  const btn = document.getElementById("import-data-btn");
  if (!btn) return;
  btn.disabled = busy;
  if (busy) {
    btn.setAttribute("aria-busy", "true");
    btn.title = "处理中…";
  } else {
    btn.removeAttribute("aria-busy");
    btn.title = "从 JSON 备份恢复";
  }
}

async function handleImportSelect(event) {
  const input = event.target;
  const file = input.files && input.files[0];
  input.value = "";
  if (!file) return;

  setImportBusy(true);
  try {
    const text = await file.text();
    let payload;
    try {
      payload = JSON.parse(text);
    } catch (_) {
      throw new Error("文件不是有效的 JSON 格式");
    }

    const response = await fetch(
      "/api/import/preview",
      authFetchOptions({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
    );
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.error || "导入预览失败");
    }

    pendingImportPayload = payload;
    openImportPreview(result.data);

    if (result.data.will_fail > 0) {
      showToast("预览发现错误记录，请修正备份后重试", "warning");
    } else {
      showToast("预览完成，请确认后导入", "info");
    }
  } catch (err) {
    showToast(err.message || "导入预览失败", "error");
    pendingImportPayload = null;
  } finally {
    setImportBusy(false);
  }
}

async function executeImport() {
  if (!pendingImportPayload) return;

  const confirmBtn = document.getElementById("import-preview-confirm");
  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.textContent = "导入中…";
  }
  setImportBusy(true);

  try {
    const response = await fetch(
      "/api/import",
      authFetchOptions({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pendingImportPayload),
      })
    );
    const result = await response.json();

    closeImportPreview();

    if (!response.ok || !result.ok) {
      showImportResult(
        result.data || {
          created: 0,
          updated: 0,
          skipped: 0,
          imported: 0,
          failed: 1,
          errors: [result.error || "导入失败"],
          rolled_back: true,
          message: "导入失败，所有变更已回滚，数据库未被修改",
        },
        true
      );
      return;
    }

    showImportResult(result.data, false);
  } catch (err) {
    closeImportPreview();
    showToast(err.message || "导入失败，请稍后重试", "error");
  } finally {
    pendingImportPayload = null;
    setImportBusy(false);
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = "确认导入";
    }
  }
}

async function handleObsidianExport() {
  const btn = document.getElementById("export-obsidian-btn");
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    btn.title = "导出中…";
  }

  try {
    const response = await fetch("/api/export/obsidian.zip", authFetchOptions());
    if (!response.ok) {
      let message = "Obsidian 导出失败，请稍后重试";
      try {
        const payload = await response.json();
        if (payload.error) message = payload.error;
      } catch (_) {
        /* ignore */
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    let filename = "obsidian_export.zip";
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^";\n]+)"?/);
    if (match) filename = match[1];

    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    showToast("Obsidian Markdown 已导出", "success");
  } catch (err) {
    showToast(err.message || "Obsidian 导出失败", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
      btn.title = "导出 Obsidian Markdown zip";
    }
  }
}

async function handleExport() {
  const btn = document.getElementById("export-data-btn");
  if (btn) {
    btn.disabled = true;
    btn.classList.add("is-exporting");
    btn.setAttribute("aria-busy", "true");
    btn.title = "导出中…";
  }

  try {
    const response = await fetch("/api/export", authFetchOptions());
    if (!response.ok) {
      let message = "导出失败，请稍后重试";
      try {
        const payload = await response.json();
        if (payload.error) message = payload.error;
      } catch (_) {
        /* ignore parse error */
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    let filename = "backup.json";
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^";\n]+)"?/);
    if (match) filename = match[1];

    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    showToast("备份已导出", "success");
  } catch (err) {
    showToast(err.message || "导出失败，请稍后重试", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("is-exporting");
      btn.removeAttribute("aria-busy");
      btn.title = "导出全部数据";
    }
  }
}

function buildInlineGoalContext(goalName) {
  const goal = goalName || "未归属目标";
  return `<span class="inline-parent-context muted-context relation-parent title-context" title="${escapeHtml(goal)}">（${escapeHtml(goal)}）</span>`;
}

function buildProjectTitleWithGoal(projectName, goalName) {
  const project = projectName || "未命名项目";
  return `<span class="title-with-context">${escapeHtml(project)}${buildInlineGoalContext(goalName)}</span>`;
}

function buildTaskContextLine(projectName, goalName) {
  const project = projectName || "未归属项目";
  return `<p class="task-context-line relation-line muted-relation item-context"><span>${escapeHtml(project)}${buildInlineGoalContext(goalName)}</span></p>`;
}

function buildTaskContextGoalOnly(goalName) {
  return `<p class="task-context-line relation-line muted-relation item-context">${buildInlineGoalContext(goalName)}</p>`;
}

function buildProjectRelationLine(goalName) {
  const goal = goalName || "未归属目标";
  return `<p class="relation-line meta-line muted-relation item-context"><span>目标 · ${escapeHtml(goal)}</span></p>`;
}

function buildTaskRelationLine(goalName, projectName) {
  return buildTaskContextLine(projectName, goalName);
}

function buildSourceRelationLine(label, value) {
  const text = (value || "").trim();
  if (!text) return "";
  const prefix = label || "来源";
  return `<p class="relation-line meta-line muted-relation item-context"><span>${escapeHtml(prefix)} · ${escapeHtml(text)}</span></p>`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}