document.addEventListener("DOMContentLoaded", () => {
  const addModal = document.getElementById("addCollegeModal");
  const editModal = document.getElementById("editCollegeModal");

  // Add modal open/close
  const openAddBtn = document.getElementById("openAddCollegeModal");
  const closeAddBtn = document.getElementById("closeAddCollegeModal");
  if (openAddBtn)
    openAddBtn.addEventListener("click", () =>
      addModal.classList.remove("hidden"),
    );
  if (closeAddBtn)
    closeAddBtn.addEventListener("click", () =>
      addModal.classList.add("hidden"),
    );

  // Edit modal open/close + prefill
  const closeEditBtn = document.getElementById("closeEditCollegeModal");
  if (closeEditBtn)
    closeEditBtn.addEventListener("click", () =>
      editModal.classList.add("hidden"),
    );

  document.querySelectorAll(".edit-college-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      document.getElementById("edit-college-name").value = btn.dataset.name;
      document.getElementById("edit-college-description").value =
        btn.dataset.description;

      const form = document.getElementById("editCollegeForm");
      form.action = `/superadmin/colleges/${id}/edit/`;

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
