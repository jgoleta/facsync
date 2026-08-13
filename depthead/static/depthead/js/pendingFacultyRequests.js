document.addEventListener("DOMContentLoaded", function () {
  const modal = document.getElementById("inviteFacultyModal");
  const openBtn = document.getElementById("openInviteModalBtn");
  const closeBtn = document.getElementById("closeInviteModal");
  const cancelBtn = document.getElementById("cancelInviteModal");

  openBtn.addEventListener("click", () => modal.classList.remove("hidden"));
  closeBtn.addEventListener("click", () => modal.classList.add("hidden"));
  cancelBtn.addEventListener("click", () => modal.classList.add("hidden"));
});
