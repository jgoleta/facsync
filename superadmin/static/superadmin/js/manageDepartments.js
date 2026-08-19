document.addEventListener("DOMContentLoaded", () => {
  const addModal = document.getElementById("addDepartmentModal");
  const editModal = document.getElementById("editDepartmentModal");

  // Add modal open/close
  const openAddBtn = document.getElementById("openAddDepartmentModal");
  const closeAddBtn = document.getElementById("closeAddDepartmentModal");
  if (openAddBtn)
    openAddBtn.addEventListener("click", () =>
      addModal.classList.remove("hidden"),
    );
  if (closeAddBtn)
    closeAddBtn.addEventListener("click", () =>
      addModal.classList.add("hidden"),
    );

  // Edit modal open/close + prefill
  const closeEditBtn = document.getElementById("closeEditDepartmentModal");
  if (closeEditBtn)
    closeEditBtn.addEventListener("click", () =>
      editModal.classList.add("hidden"),
    );

  document.querySelectorAll(".edit-department-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      document.getElementById("edit-dept-name").value = btn.dataset.name;
      document.getElementById("edit-dept-description").value =
        btn.dataset.description;

      const form = document.getElementById("editDepartmentForm");
      form.action = `/superadmin/departments/${id}/edit/`;

      editModal.classList.remove("hidden");
    });
  });

  // Click outside modal content to close
  [addModal, editModal].forEach((modal) => {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.add("hidden");
    });
  });
});
