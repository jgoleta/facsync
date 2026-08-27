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
  const inactiveClass = item.is_inactive ? " inactive" : "";
  const inactiveBadge = item.is_inactive
    ? '<span class="inactive-badge">⚠ Inactive — no login in 30+ days</span>'
    : "";
  return `
    <div class="faculty-card ${escapeHtml(item.status_class)}${inactiveClass}">
      <div class="faculty-avatar">${escapeHtml((item.name || "?").charAt(0).toUpperCase())}</div>
      <div class="card-header">
        <div>
          <p class="faculty-label">Faculty member</p>
          <h4>${escapeHtml(item.name)}</h4>
        </div>
        <span class="status-badge">${escapeHtml(item.status_label)}</span>
      </div>
      ${inactiveBadge}
      <div class="faculty-card-footer">
        <span class="status-line"><i></i>Currently ${escapeHtml((item.status_label || "").toLowerCase())}</span>
        <span class="updated-time">${timeAgo(item.updated_at_iso)}</span>
      </div>
    </div>
  `;
}

async function refreshFacultyMonitoring() {
  const grid = document.getElementById("monitoringGrid");
  if (!grid) return;
  const url = grid.dataset.refreshUrl;
  if (!url) return;

  try {
    const response = await fetch(url);
    if (!response.ok) return;
    const data = await response.json();
    const facultyList = data.faculty_list || [];

    if (facultyList.length === 0) {
      grid.innerHTML =
        '<p class="empty-state">No active faculty in your department yet.</p>';
    } else {
      grid.innerHTML = facultyList.map(renderFacultyCard).join("");
    }

    const liveCount = document.getElementById("monitoringLiveCount");
    if (liveCount) liveCount.textContent = facultyList.length;
  } catch (error) {}
}

window.setInterval(refreshFacultyMonitoring, 10000);
