document.addEventListener("DOMContentLoaded", function () {
  const modal = document.getElementById("removeConfirmModal");
  const nameEl = document.getElementById("removeConfirmFacultyName");
  const closeBtn = document.getElementById("closeRemoveConfirmModal");
  const cancelBtn = document.getElementById("cancelRemoveConfirmModal");
  const confirmBtn = document.getElementById("confirmRemoveBtn");

  let pendingForm = null;

  document.querySelectorAll(".btn-remove-trigger").forEach(function (btn) {
    btn.addEventListener("click", function () {
      pendingForm = btn.closest("form");
      nameEl.textContent = btn.dataset.facultyName || "this faculty member";
      modal.classList.remove("hidden");
    });
  });

  function closeModal() {
    modal.classList.add("hidden");
    pendingForm = null;
  }

  closeBtn.addEventListener("click", closeModal);
  cancelBtn.addEventListener("click", closeModal);

  confirmBtn.addEventListener("click", async function () {
    if (!pendingForm) return;
    const overlay = document.getElementById("loadingOverlay");
    const csrfToken = pendingForm.querySelector(
      "[name=csrfmiddlewaretoken]",
    ).value;
    modal.classList.add("hidden");
    if (overlay) overlay.classList.add("show");

    try {
      const response = await fetch(pendingForm.action, {
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
