document.addEventListener("DOMContentLoaded", () => {
  const addModal = document.getElementById("addCollegeModal");
  const officeModal = document.getElementById("addOfficeModal");

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
  document.getElementById("openAddOfficeModal")?.addEventListener("click", () => officeModal.classList.remove("hidden"));
  document.getElementById("closeAddOfficeModal")?.addEventListener("click", () => officeModal.classList.add("hidden"));

  // Click outside modal content to close
  [addModal, officeModal].filter(Boolean).forEach((modal) => {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.add("hidden");
    });
  });
});
