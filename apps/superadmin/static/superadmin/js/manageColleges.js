document.addEventListener("DOMContentLoaded", () => {
  const addModal = document.getElementById("addCollegeModal");

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

  // Click outside modal content to close
  [addModal].forEach((modal) => {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.add("hidden");
    });
  });
});
