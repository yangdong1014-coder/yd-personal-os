(function () {
  const DEFAULT_DURATION = 4200;

  function getContainer() {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container";
      container.setAttribute("aria-live", "polite");
      document.body.appendChild(container);
    }
    return container;
  }

  function showToast(message, type = "info", duration = DEFAULT_DURATION) {
    const text = (message || "").trim();
    if (!text) return;

    const container = getContainer();
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.setAttribute("role", "alert");
    toast.textContent = text;
    container.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add("is-visible"));

    const hide = () => {
      toast.classList.remove("is-visible");
      window.setTimeout(() => toast.remove(), 280);
    };

    const timer = window.setTimeout(hide, duration);
    toast.addEventListener("click", () => {
      window.clearTimeout(timer);
      hide();
    });
  }

  window.showToast = showToast;
})();