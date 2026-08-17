const deptFilter = document.getElementById("deptFilter");
const availableToggle = document.getElementById("availableToggle");
const searchInput = document.getElementById("searchInput");
const facultyGrid = document.getElementById("facultyGrid");
const statusBanner = document.getElementById("departmentStatusBanner");

let closedDepartments = {};

function loadClosedDepartmentsFromDOM() {
  const dataElement = document.getElementById("closed-departments");
  if (!dataElement) return;
  try {
    closedDepartments = JSON.parse(dataElement.textContent || "{}");
  } catch (error) {
    closedDepartments = {};
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

function populateDepartments() {
  const depts = Array.from(new Set(cards.map((c) => c.dataset.dept))).sort();
  // clear existing except the 'all' option
  Array.from(deptFilter.options)
    .slice(1)
    .forEach((o) => o.remove());
  depts.forEach((d) => {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = d;
    deptFilter.appendChild(opt);
  });
}

function renderDepartmentStatus() {
  const selectedDept = deptFilter.value;
  if (statusBanner && selectedDept !== "all") {
    if (closedDepartments[selectedDept]) {
      statusBanner.textContent = closedDepartments[selectedDept];
      statusBanner.className = "department-status-banner closed";
    } else {
      statusBanner.textContent = `The ${selectedDept} is currently open.`;
      statusBanner.className = "department-status-banner open";
    }
  } else if (statusBanner) {
    statusBanner.className = "hidden";
  }
}

function renderCards() {
  const dept = deptFilter.value;
  const onlyAvailable = availableToggle.checked;
  const q = searchInput.value.trim().toLowerCase();
  renderDepartmentStatus();

  let visibleCount = 0;
  cards.forEach((card) => {
    const cDept = card.dataset.dept || "";
    const status = card.dataset.status || "";
    const name = (
      card.querySelector(".card-title")?.textContent || ""
    ).toLowerCase();
    let show = true;
    if (dept !== "all" && cDept !== dept) show = false;
    if (onlyAvailable && status !== "available") show = false;
    if (q && !name.includes(q)) show = false;

    // If a department is selected and it's closed, don't show any faculty from it.
    if (dept !== "all" && closedDepartments[dept]) {
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
    if (dept !== "all" && closedDepartments[dept]) {
      noResults.textContent =
        "Faculty are not shown because this department is currently closed.";
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
  facultyGrid.querySelectorAll(".card-notify").forEach((b) =>
    b.addEventListener("click", (e) => {
      const card = e.target.closest(".card");
      alert(
        `Notifications for ${card.querySelector(".card-title").textContent}`,
      );
    }),
  );
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
    <article class="card" data-id="${escapeHtml(faculty.faculty_id)}" data-dept="${escapeHtml(faculty.department)}" data-status="${escapeHtml(faculty.status)}" data-lastupdated="${escapeHtml(faculty.updated_at || "")}">
      <div class="card-left">
        <svg class="avatar" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <circle cx="12" cy="8" r="3.2" fill="#e6eefc" />
          <path d="M4 20c0-3.3 4-5 8-5s8 1.7 8 5v1H4v-1z" fill="#e6eefc" />
        </svg>
      </div>
      <div class="card-body">
        <div class="card-title">${escapeHtml(faculty.name)}</div>
        <div class="card-sub">${escapeHtml(faculty.department)}</div>
        <div class="status-row"><span class="status-badge status-${faculty.status}"></span>
          <i class="status-note">${escapeHtml(faculty.walk_ins_enabled ? "Accepting walk-ins" : faculty.note || "Walk-ins unavailable")}</i>
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

function insertNotifyButtons() {
  cards.forEach((card) => {
    if (card.querySelector(".card-notify")) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "card-notify";
    button.setAttribute("aria-label", "View notifications");
    button.innerHTML =
      '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6V10c0-3.1-1.6-5.8-4.5-6.6V3.5c0-.8-.7-1.5-1.5-1.5S10.5 2.7 10.5 3.5v.9C7.6 4.2 6 6.9 6 10v6l-2 2v1h16v-1l-2-2z"/></svg>';
    card.appendChild(button);
  });
}

function loadCardsFromDOM() {
  loadClosedDepartmentsFromDOM();
  renderFacultyDirectory();
  cards = Array.from(facultyGrid.querySelectorAll(".card"));
  cards.forEach((c) => {
    const iso = c.dataset.lastupdated;
    const meta = c.querySelector(".meta");
    if (meta && iso)
      meta.textContent = "Last updated: " + parseISOToDisplay(iso);
  });
  insertNotifyButtons();
  populateDepartments();
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
    const closedElement = document.getElementById("closed-departments");
    if (closedElement)
      closedElement.textContent = JSON.stringify(data.closed_departments || {});
    loadClosedDepartmentsFromDOM();
    renderFacultyDirectory();
    cards = Array.from(facultyGrid.querySelectorAll(".card"));
    insertNotifyButtons();
    attachCardHandlers();
    renderCards();
  } catch (error) {
    // Keep the last known directory visible if a background refresh fails.
  }
}

// Wire up filters
deptFilter.addEventListener("change", renderCards);
availableToggle.addEventListener("change", renderCards);
let searchTimer = null;
searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(renderCards, 200);
});

// Init
loadCardsFromDOM();
window.setInterval(refreshFacultyDirectory, 10000);
