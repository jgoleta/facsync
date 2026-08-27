(function () {
  const loadingId = "facultyLoadingOverlay";
  const toastId = "facultyToast";
  let loadingCount = 0;
  let toastTimer = null;

  function ensureLoadingOverlay() {
    let overlay = document.getElementById(loadingId);
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = loadingId;
    overlay.className = "loading-overlay";
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    overlay.setAttribute("aria-busy", "false");
    overlay.innerHTML = `
      <div class="faculty-loading-content">
        <div class="loading-spinner" aria-hidden="true"></div>
        <p id="facultyLoadingMessage">Processing...</p>
      </div>
    `;
    document.body.appendChild(overlay);
    return overlay;
  }

  function ensureToast() {
    let toast = document.getElementById(toastId);
    if (toast) return toast;

    toast = document.createElement("div");
    toast.id = toastId;
    toast.className = "toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    document.body.appendChild(toast);
    return toast;
  }

  function showLoading(message = "Processing...") {
    const overlay = ensureLoadingOverlay();
    const messageElement = document.getElementById("facultyLoadingMessage");
    loadingCount += 1;
    if (messageElement) messageElement.textContent = message;
    overlay.classList.add("show");
    overlay.setAttribute("aria-busy", "true");
  }

  function hideLoading() {
    loadingCount = Math.max(0, loadingCount - 1);
    const overlay = document.getElementById(loadingId);
    if (loadingCount || !overlay) return;
    overlay.classList.remove("show");
    overlay.setAttribute("aria-busy", "false");
  }

  function showToast(message, isError = false) {
    const toast = ensureToast();
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.add("show");
    toastTimer = window.setTimeout(() => toast.classList.remove("show"), 3500);
  }

  window.facultyFeedback = {
    showLoading,
    hideLoading,
    showToast,
  };
})();
