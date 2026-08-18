async function showAnnouncementsOnce() {
  const modal = document.getElementById("announcementModal");
  if (!modal) return;

  const fetchUrl = modal.dataset.fetchUrl;
  if (!fetchUrl) return;

  let announcements = [];
  try {
    const response = await fetch(fetchUrl);
    const data = await response.json();
    announcements = data.announcements || [];
  } catch (e) {
    return;
  }

  if (!announcements.length) return;

  const list = document.getElementById("announcementList");
  list.innerHTML = announcements
    .map(
      (a) => `
        <div class="announcement-item">
            <strong>${a.department}</strong>
            <p>${a.message}</p>
            <small>${a.posted_at}</small>
        </div>
    `,
    )
    .join("");

  modal.classList.remove("hidden");

  const closeBtn = document.getElementById("closeAnnouncementModal");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      modal.classList.add("hidden");
    });
  }
}

document.addEventListener("DOMContentLoaded", showAnnouncementsOnce);

const announcementForm = document.getElementById("announcement-form");
if (announcementForm) {
  announcementForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const form = e.target;
    const messageInput = document.getElementById("ann-message");
    const expiryInput = document.getElementById("ann-expiry");
    const list = document.getElementById("announcements-list");

    const formData = new FormData();
    formData.append("message", messageInput.value);
    if (expiryInput.value) {
      formData.append("expiry_date", expiryInput.value);
    }

    const csrfToken = document.querySelector(
      "[name=csrfmiddlewaretoken]",
    ).value;

    try {
      const response = await fetch(form.action, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        body: formData,
      });
      const data = await response.json();

      if (!data.success) {
        alert(data.error);
        return;
      }

      const emptyState = list.querySelector(".empty-state");
      if (emptyState) emptyState.remove();

      const item = document.createElement("div");
      item.className = "announcement-item";
      item.innerHTML = `
            <p>${data.announcement.message}</p>
            <small>Posted ${data.announcement.posted_at} · Expires ${data.announcement.expiry}</small>
        `;
      list.prepend(item);

      form.reset();
    } catch (err) {
      alert("Something went wrong posting your announcement.");
    }
  });
}
