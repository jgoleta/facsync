document.addEventListener("DOMContentLoaded", function () {
  const modal = document.getElementById("inviteFacultyModal");
  const openBtn = document.getElementById("openInviteModalBtn");
  const closeBtn = document.getElementById("closeInviteModal");
  const cancelBtn = document.getElementById("cancelInviteModal");

  openBtn.addEventListener("click", () => modal.classList.remove("hidden"));
  closeBtn.addEventListener("click", () => modal.classList.add("hidden"));
  cancelBtn.addEventListener("click", () => modal.classList.add("hidden"));
});

document.addEventListener("DOMContentLoaded", function () {
  const pendingMessage = sessionStorage.getItem("pendingToastMessage");
  if (pendingMessage) {
    showToast(
      pendingMessage,
      sessionStorage.getItem("pendingToastIsError") === "true",
    );
    sessionStorage.removeItem("pendingToastMessage");
    sessionStorage.removeItem("pendingToastIsError");
  }

  document.querySelectorAll(".status-action-form").forEach((form) => {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const overlay = document.getElementById("loadingOverlay");
      const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;
      if (overlay) overlay.classList.add("show");

      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: { "X-CSRFToken": csrfToken },
        });
        const data = await response.json();
        if (!data.success) {
          if (overlay) overlay.classList.remove("show");
          showToast(data.error || "Something went wrong.", true);
          return;
        }
        sessionStorage.setItem("pendingToastMessage", data.message);
        sessionStorage.setItem("pendingToastIsError", "false");
        window.location.reload();
      } catch (err) {
        if (overlay) overlay.classList.remove("show");
        showToast("Something went wrong.", true);
      }
    });
  });
});
