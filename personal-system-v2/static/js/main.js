document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;
  document.querySelectorAll(".nav-link").forEach((link) => {
    if (link.id === "export-data-btn" || link.id === "import-data-btn") return;
    const href = link.getAttribute("href");
    if (href === path || (path === "/" && href === "/")) {
      link.classList.add("active");
    }
  });

  const exportBtn = document.getElementById("export-data-btn");
  if (exportBtn) {
    exportBtn.addEventListener("click", handleExport);
  }

  const importBtn = document.getElementById("import-data-btn");
  const importInput = document.getElementById("import-data-input");
  if (importBtn && importInput) {
    importBtn.addEventListener("click", () => importInput.click());
    importInput.addEventListener("change", handleImport);
  }
});

async function handleExport() {
  const btn = document.getElementById("export-data-btn");
  if (btn) {
    btn.disabled = true;
    btn.classList.add("is-exporting");
    btn.setAttribute("aria-busy", "true");
    btn.title = "导出中…";
  }

  try {
    const response = await fetch("/api/export");
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
  } catch (err) {
    alert(err.message || "导出失败，请稍后重试");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("is-exporting");
      btn.removeAttribute("aria-busy");
      btn.title = "导出全部数据";
    }
  }
}

async function handleImport(event) {
  const input = event.target;
  const file = input.files && input.files[0];
  input.value = "";
  if (!file) return;

  if (
    !window.confirm(
      "当前为合并导入模式：\n" +
        "· 按 id 更新或跳过记录，不会自动清空现有数据\n" +
        "· 同 id 且内容不同的记录将被覆盖更新\n" +
        "· 建议导入前先导出当前备份\n\n" +
        "确定继续导入？"
    )
  ) {
    return;
  }

  const btn = document.getElementById("import-data-btn");
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    btn.title = "导入中…";
  }

  try {
    const text = await file.text();
    let payload;
    try {
      payload = JSON.parse(text);
    } catch (_) {
      throw new Error("文件不是有效的 JSON 格式");
    }

    const response = await fetch("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      const detail = result.data
        ? `\n导入 ${result.data.imported}，跳过 ${result.data.skipped}，失败 ${result.data.failed}`
        : "";
      throw new Error((result.error || "导入失败") + detail);
    }

    const stats = result.data;
    const failed = stats.failed || 0;
    const summary = `导入完成：新增/更新 ${stats.imported} 条，跳过 ${stats.skipped} 条`;
    alert(failed > 0 ? `${summary}，失败 ${failed} 条` : summary);
  } catch (err) {
    alert(err.message || "导入失败，请稍后重试");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
      btn.title = "从 JSON 备份恢复";
    }
  }
}