document.addEventListener('DOMContentLoaded', () => {
    const collegeSelector = document.getElementById('college-selector');
    const collegeViewContainer = document.getElementById('college-view-container');
    const collegeViewHeader = document.getElementById('college-view-header');
    const collegeSummaryCards = document.getElementById('college-summary-cards');
    const collegeInsightsPanel = document.getElementById('college-insights-panel');

    let consultationTrendChart = null;
    let collegeKpiChart = null;

    // Dummy data for college analytics
    const collegeData = {
        ccs: {
            name: 'College of Computer Studies',
            stats: {
                consultations: '1,284',
                faculty: '24',
                waitTime: '12m 30s',
                availability: '92%'
            },
            trends: {
                consultations: '+12% this month',
                faculty: '85% available now',
                waitTime: '-5% from yesterday',
                availability: '+3% this week'
            },
            insights: `
                <h2>AI-Generated Insights</h2>
                <p><strong>Observation:</strong> Consultation requests peak on Tuesdays and Thursdays between 1 PM and 3 PM, likely due to project submission deadlines.</p>
                <p><strong>Suggestion:</strong> Recommend that more faculty set their status to 'Available' during these peak hours to reduce student wait times.</p>
            `
        },
        coe: {
            name: 'College of Engineering',
            stats: {
                consultations: '950',
                faculty: '35',
                waitTime: '18m 15s',
                availability: '88%'
            },
            trends: {
                consultations: '+9% this month',
                faculty: '80% available now',
                waitTime: '+2% from yesterday',
                availability: '-1% this week'
            },
            insights: `
                <h2>AI-Generated Insights</h2>
                <p><strong>Observation:</strong> A high number of walk-in consultations are for "Basic Engineering Questions", suggesting a need for a FAQ or resource page.</p>
                <p><strong>Suggestion:</strong> Create a "Common Questions" guide for first-year engineering students to reduce faculty load on repetitive queries.</p>
            `
        },
        // Data for other colleges can be added here
    };

    function renderConsultationTrendChart(collegeKey) {
        const ctx = document.getElementById('consultationTrendChart');
        if (!ctx) return;

        if (consultationTrendChart) {
            consultationTrendChart.destroy();
        }

        // Static data for demo
        const trendData = {
            labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
            data: {
                ccs: [120, 150, 180, 160, 200, 210],
                coe: [80, 90, 110, 100, 130, 140]
            }
        };

        consultationTrendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: trendData.labels,
                datasets: [{
                    label: 'Total Consultations',
                    data: trendData.data[collegeKey] || [50, 60, 70, 80, 90, 100], // default data
                    fill: false,
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: { display: true, text: 'Monthly Consultation Volume' }
                }
            }
        });
    }

    function renderCollegeKpiChart(collegeKey) {
        const ctx = document.getElementById('collegeKpiChart');
        if (!ctx) return;

        if (collegeKpiChart) {
            collegeKpiChart.destroy();
        }

        const kpiData = {
            labels: ['Availability', 'Student Satisfaction', 'Low Wait Time', 'Faculty Engagement', 'Completed Requests'],
            data: {
                ccs: [92, 85, 75, 88, 95],
                coe: [88, 82, 65, 80, 90]
            }
        };

        collegeKpiChart = new Chart(ctx, {
            type: 'radar',
            data: {
                labels: kpiData.labels,
                datasets: [{
                    label: collegeData[collegeKey].name,
                    data: kpiData.data[collegeKey] || [80, 70, 85, 75, 90], // default
                    fill: true,
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    borderColor: 'rgb(54, 162, 235)',
                    pointBackgroundColor: 'rgb(54, 162, 235)',
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: { display: true, text: 'College Performance KPIs (%)' }
                },
                scales: {
                    r: {
                        angleLines: {
                            display: false
                        },
                        suggestedMin: 0,
                        suggestedMax: 100
                    }
                }
            }
        });
    }


    collegeSelector.addEventListener('change', () => {
        const selectedCollege = collegeSelector.value;

        if (selectedCollege && collegeData[selectedCollege]) {
            const data = collegeData[selectedCollege];

            collegeViewHeader.textContent = `${data.name} Overview`;

            collegeSummaryCards.innerHTML = `
                <div class="card">
                    <h3>Total Consultations</h3>
                    <p class="stat">${data.stats.consultations}</p>
                    <span class="trend">${data.trends.consultations}</span>
                </div>
                <div class="card">
                    <h3>Active Faculty</h3>
                    <p class="stat">${data.stats.faculty}</p>
                    <span class="trend">${data.trends.faculty}</span>
                </div>
                <div class="card">
                    <h3>Avg. Wait Time</h3>
                    <p class="stat">${data.stats.waitTime}</p>
                    <span class="trend trend-bad">${data.trends.waitTime}</span>
                </div>
                <div class="card">
                    <h3>Availability Rate</h3>
                    <p class="stat">${data.stats.availability}</p>
                    <span class="trend">${data.trends.availability}</span>
                </div>
            `;

            collegeInsightsPanel.innerHTML = data.insights;

            collegeViewContainer.classList.remove('hidden');

            renderConsultationTrendChart(selectedCollege);
            renderCollegeKpiChart(selectedCollege);
        } else {
            collegeViewContainer.classList.add('hidden');
        }
    });
});
