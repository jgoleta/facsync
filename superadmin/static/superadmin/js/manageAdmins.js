document.addEventListener("DOMContentLoaded", function () {
  const modal = document.getElementById("inviteDeptheadModal");
  const openBtn = document.getElementById("openInviteDeptheadBtn");
  const closeBtn = document.getElementById("closeInviteDeptheadModal");
  const cancelBtn = document.getElementById("cancelInviteDeptheadModal");

  openBtn.addEventListener("click", () => modal.classList.remove("hidden"));
  closeBtn.addEventListener("click", () => modal.classList.add("hidden"));
  cancelBtn.addEventListener("click", () => modal.classList.add("hidden"));
});

document.addEventListener("DOMContentLoaded", () => {
  const editModal = document.getElementById("editDeptheadModal");
  const closeEditBtn = document.getElementById("closeEditDeptheadModal");
  if (closeEditBtn)
    closeEditBtn.addEventListener("click", () =>
      editModal.classList.add("hidden"),
    );

  document.querySelectorAll(".edit-depthead-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      document.getElementById("edit-depthead-role").value = btn.dataset.role;
      document.getElementById("edit-depthead-department").value =
        btn.dataset.department;

      const form = document.getElementById("editDeptheadForm");
      form.action = `/superadmin/admins/depthead/${id}/edit/`;

      editModal.classList.remove("hidden");
    });
  });

  editModal.addEventListener("click", (e) => {
    if (e.target === editModal) editModal.classList.add("hidden");
  });
});
