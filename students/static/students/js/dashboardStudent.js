const collegeFilter = document.getElementById("collegeFilter");
const availableToggle = document.getElementById("availableToggle");
const searchInput = document.getElementById("searchInput");
const facultyGrid = document.getElementById("facultyGrid");
const statusBanner = document.getElementById("collegeStatusBanner");
const studentFeedback = window.studentFeedback;

let closedColleges = {};

function loadClosedCollegesFromDOM() {
  const dataElement = document.getElementById("closed-colleges");
  if (!dataElement) return;
  try {
    closedColleges = JSON.parse(dataElement.textContent || "{}");
  } catch (error) {
    closedColleges = {};
  }
}

let cards = [];

function parseISOToDisplay(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch (e) {
    return iso;
  }
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

function getInitials(name) {
  return String(name || "F")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}

function getStatusLabel(status) {
  return {
    available: "Available",
    busy: "Busy",
    virtual_only: "Virtual only",
    on_leave: "On leave",
    unavailable: "Unavailable",
  }[status] || "Status unavailable";
}

function populateColleges() {
  const colleges = Array.from(new Set(cards.map((c) => c.dataset.college))).sort();
  // clear existing except the 'all' option
  Array.from(collegeFilter.options)
    .slice(1)
    .forEach((o) => o.remove());
  colleges.forEach((d) => {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = d;
    collegeFilter.appendChild(opt);
  });
}

function renderCollegeStatus() {
  const selectedCollege = collegeFilter.value;
  if (statusBanner && selectedCollege !== "all") {
    if (closedColleges[selectedCollege]) {
      statusBanner.textContent = closedColleges[selectedCollege];
      statusBanner.className = "college-status-banner closed";
    } else {
      statusBanner.textContent = `The ${selectedCollege} is currently open.`;
      statusBanner.className = "college-status-banner open";
    }
  } else if (statusBanner) {
    statusBanner.className = "hidden";
  }
}

function renderCards() {
  const college = collegeFilter.value;
  const onlyAvailable = availableToggle.checked;
  const q = searchInput.value.trim().toLowerCase();
  renderCollegeStatus();

  let visibleCount = 0;
  cards.forEach((card) => {
    const cCollege = card.dataset.college || "";
    const status = card.dataset.status || "";
    const name = (
      card.querySelector(".card-title")?.textContent || ""
    ).toLowerCase();
    let show = true;
    if (college !== "all" && cCollege !== college) show = false;
    if (onlyAvailable && status !== "available") show = false;
    if (q && !name.includes(q)) show = false;

    // If a college is selected and it's closed, don't show any faculty from it.
    if (college !== "all" && closedColleges[college]) {
      show = false;
    }

    card.style.display = show ? "" : "none";
    if (show) visibleCount++;
  });

  let noResults = facultyGrid.querySelector(".no-results");
  if (visibleCount === 0) {
    if (!noResults) {
      noResults = document.createElement("div");
      noResults.className = "no-results";
      facultyGrid.appendChild(noResults);
    }
    noResults.style.display = "block";
    if (college !== "all" && closedColleges[college]) {
      noResults.textContent =
        "Faculty are not shown because this college is currently closed.";
    } else {
      noResults.textContent = "No faculty match your filters.";
    }
  } else if (noResults) {
    noResults.style.display = "none";
  }
}

function attachCardHandlers() {
  facultyGrid.querySelectorAll(".btn.join").forEach((b) =>
    b.addEventListener("click", (e) => {
      const id = e.target.dataset.id;
      const card = facultyGrid.querySelector(`.card[data-id="${id}"]`);
      alert(
        `Joining queue for ${card.querySelector(".card-title").textContent}`,
      );
    }),
  );
  facultyGrid.querySelectorAll(".btn.view").forEach((b) =>
    b.addEventListener("click", (e) => {
      const id = e.target.dataset.id;
      const card = facultyGrid.querySelector(`.card[data-id="${id}"]`);
      window.location.href = `/student/view-schedule/?faculty_id=${encodeURIComponent(id)}`;
    }),
  );
  facultyGrid.querySelectorAll(".card-notify").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const facultyId = button.dataset.id;
      const subscribed = button.dataset.subscribed === "true";
      button.disabled = true;
      studentFeedback?.showLoading(subscribed ? "Turning off notifications..." : "Enabling notifications...");
      try {
        const response = await fetch(
          `/student/api/faculty/${encodeURIComponent(facultyId)}/notification-subscription/`,
          {
            method: subscribed ? "DELETE" : "POST",
            headers: { "X-CSRFToken": getCsrfToken() },
          },
        );
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Unable to update notification preference.");
        setSubscriptionButton(button, data.subscribed);
        studentFeedback?.showToast(
          data.subscribed ? "Notifications enabled." : "Notifications disabled.",
        );
      } catch (error) {
        studentFeedback?.showToast(error.message, true);
      } finally {
        studentFeedback?.hideLoading();
        button.disabled = false;
      }
    });
  });
}

function getCsrfToken() {
  const cookie = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="));
  return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

function setSubscriptionButton(button, subscribed) {
  button.dataset.subscribed = String(subscribed);
  button.classList.toggle("subscribed", subscribed);
  button.setAttribute(
    "aria-label",
    subscribed
      ? "Stop receiving notifications for this faculty member"
      : "Receive notifications when this faculty member's status changes",
  );
  button.title = subscribed
    ? "Notifications enabled — click to unsubscribe"
    : "Notify me when this faculty member's status changes";
}

function renderFacultyDirectory() {
  const dataElement = document.getElementById("faculty-directory");
  if (!dataElement) return;
  let directory = [];
  try {
    directory = JSON.parse(dataElement.textContent || "[]");
  } catch (error) {
    return;
  }
  if (!directory.length) return;

  facultyGrid.innerHTML = directory
    .map(
      (faculty) => `
    <article class="card${faculty.is_college_closed ? " card-closed" : ""}" data-id="${escapeHtml(faculty.faculty_id)}" data-college="${escapeHtml(faculty.college)}" data-status="${escapeHtml(faculty.status)}" data-lastupdated="${escapeHtml(faculty.updated_at || "")}">
      <div class="card-left">
        <div class="avatar" aria-hidden="true">${escapeHtml(getInitials(faculty.name))}</div>
      </div>
      <div class="card-body">
        <div class="card-title">${escapeHtml(faculty.name)}</div>
        <div class="card-sub">${escapeHtml(faculty.college)}</div>
        <button type="button" class="card-notify${faculty.is_subscribed ? " subscribed" : ""}" data-id="${escapeHtml(faculty.faculty_id)}" data-subscribed="${faculty.is_subscribed ? "true" : "false"}" aria-label="${faculty.is_subscribed ? "Stop receiving notifications for this faculty member" : "Receive notifications when this faculty member's status changes"}" title="${faculty.is_subscribed ? "Notifications enabled — click to unsubscribe" : "Notify me when this faculty member's status changes"}">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M12 22a2 2 0 0 0 2.2-1.7H9.8A2.3 2.3 0 0 0 12 22Zm7-5.4-1.4-1.7V10a5.6 5.6 0 0 0-4.4-5.5V3.8a1.2 1.2 0 1 0-2.4 0v.7A5.6 5.6 0 0 0 6.4 10v4.9L5 16.6v1h14v-1Z"/></svg>
        </button>
        <div class="status-row"><span class="status-badge status-${faculty.status}" aria-hidden="true"></span>
          <span class="status-label">${escapeHtml(getStatusLabel(faculty.status))}</span>
          <span class="status-note">${escapeHtml(faculty.walk_ins_enabled ? "Accepting walk-ins" : faculty.note || "Walk-ins unavailable")}</span>
        </div>
        <div class="meta">${escapeHtml(faculty.updated_at ? `Last updated: ${parseISOToDisplay(faculty.updated_at)}` : "No recent status update")}</div>
        <div class="card-actions">
          <button type="button" class="btn view" data-id="${escapeHtml(faculty.faculty_id)}">View Schedule</button>
        </div>
      </div>
    </article>
  `,
    )
    .join("");
}

function loadCardsFromDOM() {
  loadClosedCollegesFromDOM();
  renderFacultyDirectory();
  cards = Array.from(facultyGrid.querySelectorAll(".card"));
  cards.forEach((c) => {
    const iso = c.dataset.lastupdated;
    const meta = c.querySelector(".meta");
    if (meta && iso)
      meta.textContent = "Last updated: " + parseISOToDisplay(iso);
  });
  populateColleges();
  attachCardHandlers();
  renderCards();
}

async function refreshFacultyDirectory() {
  try {
    const response = await fetch("/student/api/faculty-statuses/");
    const data = await response.json();
    if (!response.ok) return;
    const dataElement = document.getElementById("faculty-directory");
    if (dataElement)
      dataElement.textContent = JSON.stringify(data.faculty || []);
    const closedElement = document.getElementById("closed-colleges");
    if (closedElement)
      closedElement.textContent = JSON.stringify(data.closed_colleges || {});
    loadClosedCollegesFromDOM();
    renderFacultyDirectory();
    cards = Array.from(facultyGrid.querySelectorAll(".card"));
    attachCardHandlers();
    renderCards();
  } catch (error) {
    // Keep the last known directory visible if a background refresh fails.
  }
}

// Wire up filters
collegeFilter.addEventListener("change", renderCards);
availableToggle.addEventListener("change", renderCards);
let searchTimer = null;
searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(renderCards, 200);
});

// Init
loadCardsFromDOM();
window.setInterval(refreshFacultyDirectory, 10000);
