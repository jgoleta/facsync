document.addEventListener("DOMContentLoaded", function () {
  const inviteModal = document.getElementById("inviteFacultySAModal");
  document
    .getElementById("openInviteFacultyBtn")
    ?.addEventListener("click", () => inviteModal.classList.remove("hidden"));
  document
    .getElementById("closeInviteFacultySA")
    ?.addEventListener("click", () => inviteModal.classList.add("hidden"));
  document
    .getElementById("cancelInviteFacultySA")
    ?.addEventListener("click", () => inviteModal.classList.add("hidden"));

  const removeModal = document.getElementById("removeFacultySAModal");
  const removeNameEl = document.getElementById("removeFacultySAName");
  let removeUrl = null;

  document.querySelectorAll(".btn-remove-trigger-sa").forEach((btn) => {
    btn.addEventListener("click", () => {
      removeUrl = btn.dataset.removeUrl;
      removeNameEl.textContent =
        btn.dataset.facultyName || "this faculty member";
      removeModal.classList.remove("hidden");
    });
  });

  document
    .getElementById("closeRemoveFacultySA")
    ?.addEventListener("click", () => removeModal.classList.add("hidden"));
  document
    .getElementById("cancelRemoveFacultySA")
    ?.addEventListener("click", () => removeModal.classList.add("hidden"));

  document
    .getElementById("confirmRemoveFacultySA")
    ?.addEventListener("click", async () => {
      if (!removeUrl) return;
      const overlay = document.getElementById("loadingOverlay");
      const csrfToken = document.querySelector(
        "[name=csrfmiddlewaretoken]",
      ).value;
      removeModal.classList.add("hidden");
      if (overlay) overlay.classList.add("show");

      try {
        const response = await fetch(removeUrl, {
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
        window.location.reload();
      } catch (err) {
        if (overlay) overlay.classList.remove("show");
        showToast("Something went wrong.", true);
      }
    });

  const pendingMessage = sessionStorage.getItem("pendingToastMessage");
  if (pendingMessage) {
    showToast(pendingMessage, false);
    sessionStorage.removeItem("pendingToastMessage");
  }
});
