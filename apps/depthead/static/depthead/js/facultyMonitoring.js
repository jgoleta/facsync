function timeAgo(isoString) {
  if (!isoString) return "No update yet";
  const then = new Date(isoString);
  const now = new Date();
  const seconds = Math.floor((now - then) / 1000);

  const units = [
    ["year", 31536000],
    ["month", 2592000],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [name, secondsInUnit] of units) {
    const value = Math.floor(seconds / secondsInUnit);
    if (value >= 1) {
      return `${value} ${name}${value > 1 ? "s" : ""} ago`;
    }
  }
  return "Just now";
}

function escapeHtml(value) {
  return String(value || "").replace(
    /[&<>'"]/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;",
      })[character],
  );
}

function renderFacultyCard(item) {
  return `
    <div class="faculty-card ${escapeHtml(item.status_class)}">
      <div class="faculty-avatar fs-avatar" aria-hidden="true"><span class="fs-avatar-fallback">${escapeHtml((item.name || "?").charAt(0).toUpperCase())}</span>${item.photo_url ? `<img src="${escapeHtml(item.photo_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" data-avatar-image>` : ''}</div>
      <div class="card-header">
        <div>
          <p class="faculty-label">Faculty member</p>
          <h4>${escapeHtml(item.name)}</h4>
        </div>
        <span class="status-badge">${escapeHtml(item.status_label)}</span>
      </div>
      <button type="button" class="view-schedule-btn" data-faculty-id="${escapeHtml(item.id)}">View Schedule</button>
      <div class="faculty-card-footer">
        <span class="status-line"><i></i>Currently ${escapeHtml((item.status_label || "").toLowerCase())}</span>
        <span class="updated-time">${timeAgo(item.updated_at_iso)}</span>
      </div>
    </div>
  `;
}

function formatScheduleTime(value) {
  if (!value) return "All day";
  const [hours, minutes] = value.split(":").map(Number);
  const suffix = hours >= 12 ? "PM" : "AM";
  const hour = hours % 12 || 12;
  return `${hour}:${String(minutes).padStart(2, "0")} ${suffix}`;
}

function renderScheduleEvents(events) {
  if (!events.length) return '<p class="empty-state">No schedule entries for this month.</p>';
  return events.map((event) => `
    <article class="monitoring-schedule-item">
      <div class="monitoring-schedule-date">${escapeHtml(new Date(`${event.date}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }))}</div>
      <div class="monitoring-schedule-details">
        <strong>${escapeHtml(event.title || "Untitled schedule")}</strong>
        <span>${escapeHtml(formatScheduleTime(event.start_time))}${event.end_time ? ` – ${escapeHtml(formatScheduleTime(event.end_time))}` : ""}</span>
        ${event.location ? `<span>${escapeHtml(event.location)}</span>` : ""}
      </div>
      <span class="monitoring-schedule-status">${escapeHtml(event.status || event.event_type || "Schedule")}</span>
    </article>
  `).join("");
}

async function openFacultySchedule(facultyId) {
  const grid = document.getElementById("monitoringGrid");
  const modal = document.getElementById("facultyScheduleModal");
  const body = document.getElementById("facultyScheduleModalBody");
  const title = document.getElementById("facultyScheduleModalTitle");
  const month = document.getElementById("facultyScheduleModalMonth");
  if (!grid || !modal || !body) return;
  const url = grid.dataset.scheduleUrlTemplate.replace("__faculty__", encodeURIComponent(facultyId));
  modal.classList.remove("hidden");
  body.innerHTML = '<p class="empty-state">Loading schedule...</p>';
  try {
    const response = await fetch(url, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Unable to load schedule.");
    title.textContent = data.faculty_name || "Faculty Schedule";
    month.textContent = data.month_label || "Current month";
    body.innerHTML = renderScheduleEvents(data.events || []);
  } catch (error) {
    body.innerHTML = `<p class="empty-state">${escapeHtml(error.message)}</p>`;
  }
}

function closeFacultySchedule() {
  document.getElementById("facultyScheduleModal")?.classList.add("hidden");
}

async function refreshFacultyMonitoring() {
  const grid = document.getElementById("monitoringGrid");
  if (!grid) return;
  const url = grid.dataset.refreshUrl;
  if (!url) return;

  try {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) return;
    const data = await response.json();
    const facultyList = data.faculty_list || [];

    if (facultyList.length === 0) {
      grid.innerHTML =
        '<p class="empty-state">No registered faculty in your college yet.</p>';
    } else {
      grid.innerHTML = facultyList.map(renderFacultyCard).join("");
    }

    const liveCount = document.getElementById("monitoringLiveCount");
    if (liveCount) liveCount.textContent = facultyList.length;
    const counts = new Map((data.status_counts || []).map(item => [item.key, item.count]));
    document.querySelectorAll('[data-status-count]').forEach(element => {
      const count = String(counts.get(element.dataset.statusCount) ?? 0);
      if (element.textContent !== count) element.textContent = count;
    });
  } catch (error) {}
}

window.setInterval(refreshFacultyMonitoring, 10000);

document.addEventListener("click", (event) => {
  if (event.target.closest(".view-schedule-btn")) {
    openFacultySchedule(event.target.closest(".view-schedule-btn").dataset.facultyId);
  } else if (event.target.id === "closeFacultyScheduleModal" || event.target.id === "facultyScheduleModal") {
    closeFacultySchedule();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeFacultySchedule();
});
