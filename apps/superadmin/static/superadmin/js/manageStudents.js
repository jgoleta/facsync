document.addEventListener("DOMContentLoaded", function () {
  const modal = document.getElementById("removeStudentSAModal");
  const nameEl = document.getElementById("removeStudentSAName");
  let removeUrl = null;

  document.querySelectorAll(".btn-remove-trigger-student").forEach((btn) => {
    btn.addEventListener("click", () => {
      removeUrl = btn.dataset.removeUrl;
      nameEl.textContent = btn.dataset.studentName || "this student";
      modal.classList.remove("hidden");
    });
  });

  document
    .getElementById("closeRemoveStudentSA")
    ?.addEventListener("click", () => modal.classList.add("hidden"));
  document
    .getElementById("cancelRemoveStudentSA")
    ?.addEventListener("click", () => modal.classList.add("hidden"));

  document
    .getElementById("confirmRemoveStudentSA")
    ?.addEventListener("click", async () => {
      if (!removeUrl) return;
      const overlay = document.getElementById("loadingOverlay");
      const csrfToken = document.querySelector(
        "[name=csrfmiddlewaretoken]",
      ).value;
      modal.classList.add("hidden");
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
