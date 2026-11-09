document.addEventListener("DOMContentLoaded", function () {
  const modal = document.getElementById("removeStudentSAModal");
  const nameEl = document.getElementById("removeStudentSAName");
  let removeUrl = null;
  let action = "deactivate";
  let processing = false;

  document.querySelectorAll(".btn-remove-trigger-student").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (processing) return;
      removeUrl = btn.dataset.removeUrl;
      action = btn.dataset.action;
      document.getElementById("studentAccessTitle").textContent = action === "reactivate" ? "Reactivate Student" : "Deactivate Student";
      document.getElementById("studentAccessWarning").textContent = action === "reactivate" ? "Restore access for " : `${btn.dataset.historyCount} consultation record(s) will be preserved. Login and booking access will be removed. Deactivate `;
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
      if (!removeUrl || processing) return;
      processing = true;
      document.getElementById("confirmRemoveStudentSA").disabled = true;
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
          body: new URLSearchParams({action}),
        });
        const data = await response.json();
        if (!data.success) {
          if (overlay) overlay.classList.remove("show");
          processing = false; document.getElementById("confirmRemoveStudentSA").disabled = false;
          showToast(data.error || "Something went wrong.", true);
          return;
        }
        sessionStorage.setItem("pendingToastMessage", data.message);
        window.location.reload();
      } catch (err) {
        if (overlay) overlay.classList.remove("show");
          processing = false; document.getElementById("confirmRemoveStudentSA").disabled = false;
        showToast("Something went wrong.", true);
      }
    });

  const pendingMessage = sessionStorage.getItem("pendingToastMessage");
  if (pendingMessage) {
    showToast(pendingMessage, false);
    sessionStorage.removeItem("pendingToastMessage");
  }
});
