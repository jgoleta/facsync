document.addEventListener("DOMContentLoaded", () => {
  const collegeSelector = document.getElementById("college-selector");
  const collegeViewContainer = document.getElementById(
    "college-view-container",
  );
  const collegeViewHeader = document.getElementById("college-view-header");
  const collegeSummaryCards = document.getElementById("college-summary-cards");

  let collegeData = {};
  const dataEl = document.getElementById("college-data");
  if (dataEl) {
    try {
      const list = JSON.parse(dataEl.textContent || "[]");
      list.forEach((c) => {
        collegeData[c.code] = c;
      });
    } catch (e) {
      collegeData = {};
    }
  }

  collegeSelector.value = "";
  collegeViewContainer.hidden = true;

  collegeSelector.addEventListener("change", () => {
    const selectedCollege = collegeSelector.value;
    const data = collegeData[selectedCollege];

    if (data) {
      collegeViewHeader.textContent = `${data.name} Overview`;

      collegeSummaryCards.innerHTML = `
        <article class="overview-stat-card consultations-card">
          <div class="stat-icon" aria-hidden="true">Q</div>
          <div><p class="stat-label">Total Consultations</p><p class="stat">${data.total_consultations}</p><p class="stat-caption">Requests recorded</p></div>
        </article>
        <article class="overview-stat-card faculty-card">
          <div class="stat-icon" aria-hidden="true">F</div>
          <div><p class="stat-label">Registered Faculty</p><p class="stat">${data.active_faculty}</p><p class="stat-caption">Faculty profiles</p></div>
        </article>
        <article class="overview-stat-card colleges-card">
          <div class="stat-icon" aria-hidden="true">A</div>
          <div><p class="stat-label">Availability Rate</p><p class="stat">${data.availability_rate}%</p><p class="stat-caption">Faculty available now</p></div>
        </article>
            `;

      collegeViewContainer.hidden = false;
    } else {
      collegeViewContainer.hidden = true;
      collegeViewHeader.textContent = "";
      collegeSummaryCards.replaceChildren();
    }
  });
});
