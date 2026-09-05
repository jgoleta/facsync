function showToast(message, isError = false) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.className = "toast" + (isError ? " error" : "");
  toast.textContent = message;
  document.body.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add("show"));

  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 250);
  }, 3000);
}

function getCsrfToken() {
  return document.querySelector("[name=csrfmiddlewaretoken]").value;
}

document.addEventListener("DOMContentLoaded", function () {
  const inviteModal = document.getElementById("inviteDeptheadModal");
  const openBtn = document.getElementById("openInviteDeptheadBtn");
  const closeBtn = document.getElementById("closeInviteDeptheadModal");
  const cancelBtn = document.getElementById("cancelInviteDeptheadModal");
  const inviteForm = document.querySelector("#inviteDeptheadModal form");
  const overlay = document.getElementById("loadingOverlay");

  openBtn.addEventListener("click", () =>
    inviteModal.classList.remove("hidden"),
  );
  closeBtn.addEventListener("click", () => inviteModal.classList.add("hidden"));
  cancelBtn.addEventListener("click", () =>
    inviteModal.classList.add("hidden"),
  );

  inviteForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(inviteForm);
    overlay.classList.add("show");
    try {
      const response = await fetch(inviteForm.action, {
        method: "POST",
        headers: { "X-CSRFToken": getCsrfToken() },
        body: formData,
      });
      const data = await response.json();
      if (!data.success) {
        showToast(data.error, true);
        return;
      }
      showToast(data.message);
      inviteModal.classList.add("hidden");
      inviteForm.reset();
    } catch (err) {
      console.error("Invite depthead error:", err);
      showToast("Something went wrong sending the invite.", true);
    } finally {
      overlay.classList.remove("show");
    }
  });
});

document.addEventListener("DOMContentLoaded", () => {
  const editModal = document.getElementById("editDeptheadModal");
  const closeEditBtn = document.getElementById("closeEditDeptheadModal");
  const editForm = document.getElementById("editDeptheadForm");
  const overlay = document.getElementById("loadingOverlay");

  if (closeEditBtn) {
    closeEditBtn.addEventListener("click", () =>
      editModal.classList.add("hidden"),
    );
  }

  document.querySelectorAll(".edit-depthead-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      document.getElementById("edit-depthead-role").value = btn.dataset.role;
      document.getElementById("edit-depthead-college").value =
        btn.dataset.college;
      document.getElementById("edit-depthead-title").value = btn.dataset.title;
      document.getElementById("edit-depthead-status").value =
        btn.dataset.status;

      editForm.action = `/superadmin/admins/depthead/${id}/edit/`;
      editModal.classList.remove("hidden");
    });
  });

  editModal.addEventListener("click", (e) => {
    if (e.target === editModal) editModal.classList.add("hidden");
  });

  editForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(editForm);
    overlay.classList.add("show");
    try {
      const response = await fetch(editForm.action, {
        method: "POST",
        headers: { "X-CSRFToken": getCsrfToken() },
        body: formData,
      });
      const data = await response.json();
      if (!data.success) {
        showToast(data.error, true);
        return;
      }
      showToast(data.message);
      editModal.classList.add("hidden");
      updateDeptheadRow(data.depthead);
    } catch (err) {
      console.error("Edit depthead error:", err);
      showToast("Something went wrong saving changes.", true);
    } finally {
      overlay.classList.remove("show");
    }
  });
});

function updateDeptheadRow(depthead) {
  const row = document.querySelector(`tr[data-depthead-id="${depthead.id}"]`);
  if (!row) return;

  row.querySelector(".depthead-college").textContent = depthead.college;
  row.querySelector(".depthead-title").textContent = depthead.title_display;

  const statusCell = row.querySelector(".depthead-status");
  statusCell.innerHTML = `<span class="status-pill status-${depthead.status}">${depthead.status_display}</span>`;

  const editBtn = row.querySelector(".edit-depthead-btn");
  editBtn.dataset.status = depthead.status;
  editBtn.dataset.college = depthead.college;
}
