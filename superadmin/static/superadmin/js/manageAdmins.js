document.addEventListener("DOMContentLoaded", function () {
  const modal = document.getElementById("inviteDeptheadModal");
  const openBtn = document.getElementById("openInviteDeptheadBtn");
  const closeBtn = document.getElementById("closeInviteDeptheadModal");
  const cancelBtn = document.getElementById("cancelInviteDeptheadModal");

  openBtn.addEventListener("click", () => modal.classList.remove("hidden"));
  closeBtn.addEventListener("click", () => modal.classList.add("hidden"));
  cancelBtn.addEventListener("click", () => modal.classList.add("hidden"));
});
