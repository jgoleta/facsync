(function () {
  const STORAGE_KEY = "college_announcements";

  function $(sel, ctx = document) {
    return ctx.querySelector(sel);
  }
  function $all(sel, ctx = document) {
    return Array.from(ctx.querySelectorAll(sel));
  }

  function loadAnnouncements() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      console.error("Failed to parse announcements", e);
      return [];
    }
  }
  function saveAnnouncements(list) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
})();

document.addEventListener("DOMContentLoaded", function () {
  const closureForm = document.getElementById("closure-form");
  if (!closureForm) return;

  closureForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const overlay = document.getElementById("loadingOverlay");
    const csrfToken = closureForm.querySelector(
      "[name=csrfmiddlewaretoken]",
    ).value;
    const formData = new FormData(closureForm);

    if (overlay) overlay.classList.add("show");

    try {
      const response = await fetch(closureForm.action || window.location.href, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        body: formData,
      });
      const data = await response.json();

      if (!data.success) {
        showToast(data.error, true);
        return;
      }

      showToast("Office closure settings updated.");
    } catch (err) {
      showToast("Something went wrong saving closure settings.", true);
    } finally {
      if (overlay) overlay.classList.remove("show");
    }
  });
});
