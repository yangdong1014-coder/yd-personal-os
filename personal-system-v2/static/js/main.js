document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;
  document.querySelectorAll(".nav-link").forEach((link) => {
    if (link.id === "export-data-btn") return;
    const href = link.getAttribute("href");
    if (href === path || (path === "/" && href === "/")) {
      link.classList.add("active");
    }
  });

  const exportBtn = document.getElementById("export-data-btn");
  if (exportBtn) {
    exportBtn.addEventListener("click", handleExport);
  }
});

async function handleExport() {
  const btn = document.getElementById("export-data-btn");
  const prevText = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "导出中…";
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
      btn.textContent = prevText;
    }
  }
}