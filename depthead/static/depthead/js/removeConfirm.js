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

  confirmBtn.addEventListener("click", function () {
    if (pendingForm) pendingForm.submit();
  });
});
