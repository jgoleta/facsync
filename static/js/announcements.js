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
  list.replaceChildren(...announcements.map((announcement) => {
    const item = document.createElement('div');
    item.className = 'announcement-item';
    const college = document.createElement('strong');
    college.className = 'announcement-item-college';
    college.textContent = announcement.college;
    const message = document.createElement('p');
    message.textContent = announcement.message;
    const posted = document.createElement('small');
    posted.className = 'announcement-item-date';
    posted.textContent = announcement.posted_at;
    item.append(college, message, posted);
    return item;
  }));
  modal.showModal();
}

document.addEventListener("DOMContentLoaded", showAnnouncementsOnce);

const announcementForm = document.getElementById("announcement-form");
if (announcementForm) {
  announcementForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const form = e.target;
    if (form.dataset.saving === 'true') return;
    form.dataset.saving = 'true';
    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    const list = document.getElementById("announcements-list");
    const overlay = document.getElementById("loadingOverlay");

    const formData = new FormData(form);
    let confirmed = false;

    const csrfToken = document.querySelector(
      "[name=csrfmiddlewaretoken]",
    ).value;

    try {
      confirmed = await confirmCollegeAction('Post Announcement?', announcementConfirmationMessage(formData.get('audience'), form.dataset.college));
      if (!confirmed) return;
      overlay.classList.add("show");
      const response = await fetch(form.action, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        body: formData,
      });
      const data = await response.json();

      if (!data.success) {
        showToast(data.error, true);
        return;
      }

      const emptyState = list.querySelector(".empty-state");
      if (emptyState) emptyState.remove();

      const item = document.createElement("div");
      item.className = "announcement-item";
      const message = document.createElement('p');
      message.textContent = data.announcement.message;
      const details = document.createElement('small');
      details.textContent = `${data.announcement.audience_label} ? Posted ${data.announcement.posted_at} ? Expires ${data.announcement.expiry}`;
      item.append(message, details);
      list.prepend(item);

      form.reset();
      showToast("Announcement posted successfully.");
    } catch (err) {
      showToast("Something went wrong posting your announcement.", true);
    } finally {
      if (confirmed) closeCollegeConfirmation();
      overlay.classList.remove("show");
      form.dataset.saving = 'false';
      submitButton.disabled = false;
    }
  });
}

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
