document.addEventListener("DOMContentLoaded", () => {
  const collegeSelector = document.getElementById("college-selector");
  const collegeViewContainer = document.getElementById(
    "college-view-container",
  );
  const collegeViewHeader = document.getElementById("college-view-header");
  const collegeSummaryCards = document.getElementById("college-summary-cards");
  const collegeInsightsPanel = document.getElementById(
    "college-insights-panel",
  );

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

  if (collegeInsightsPanel) collegeInsightsPanel.remove();

  collegeSelector.addEventListener("change", () => {
    const selectedCollege = collegeSelector.value;
    const data = collegeData[selectedCollege];

    if (data) {
      collegeViewHeader.textContent = `${data.name} Overview`;

      collegeSummaryCards.innerHTML = `
                <div class="card">
                    <h3>Total Consultations</h3>
                    <p class="stat">${data.total_consultations}</p>
                </div>
                <div class="card">
                    <h3>Active Faculty</h3>
                    <p class="stat">${data.active_faculty}</p>
                </div>
                <div class="card">
                    <h3>Availability Rate</h3>
                    <p class="stat">${data.availability_rate}%</p>
                </div>
            `;

      collegeViewContainer.classList.remove("hidden");
    } else {
      collegeViewContainer.classList.add("hidden");
    }
  });
});
