(function () {
  const DEFAULT_DURATION = 4200;
  const MAX_VISIBLE_TOASTS = 3;

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

  function trimOldToasts(container) {
    const toasts = container.querySelectorAll(".toast");
    const overflow = toasts.length - MAX_VISIBLE_TOASTS + 1;
    if (overflow <= 0) return;
    for (let i = 0; i < overflow; i += 1) {
      toasts[i].remove();
    }
  }

  function showToast(message, type = "info", duration = DEFAULT_DURATION) {
    const text = (message || "").trim();
    if (!text) return;

    const container = getContainer();
    trimOldToasts(container);

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