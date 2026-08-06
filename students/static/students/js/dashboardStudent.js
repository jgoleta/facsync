const deptFilter = document.getElementById('deptFilter');
const availableToggle = document.getElementById('availableToggle');
const searchInput = document.getElementById('searchInput');
const facultyGrid = document.getElementById('facultyGrid');
const statusBanner = document.getElementById('departmentStatusBanner');

// In a real application, this data would be fetched from a server.
const closedDepartments = {
    "College of Engineering": "The College of Engineering is closed today for a department-wide event.",
    "College of Nursing": "The College of Nursing will be closed until next week."
};

let cards = [];

function parseISOToDisplay(iso){
  try{return new Date(iso).toLocaleString();}catch(e){return iso}
}

function populateDepartments(){
  const depts = Array.from(new Set(cards.map(c=>c.dataset.dept))).sort();
  // clear existing except the 'all' option
  Array.from(deptFilter.options).slice(1).forEach(o=>o.remove());
  depts.forEach(d=>{const opt=document.createElement('option');opt.value=d;opt.textContent=d;deptFilter.appendChild(opt);});
}

function renderDepartmentStatus(){
  const selectedDept = deptFilter.value;
  if (statusBanner && selectedDept !== 'all') {
    if (closedDepartments[selectedDept]) {
      statusBanner.textContent = closedDepartments[selectedDept];
      statusBanner.className = 'department-status-banner closed';
    } else {
      statusBanner.textContent = `The ${selectedDept} is currently open.`;
      statusBanner.className = 'department-status-banner open';
    }
  } else if (statusBanner) {
    statusBanner.className = 'hidden';
  }
}

function renderCards(){
  const dept = deptFilter.value;
  const onlyAvailable = availableToggle.checked;
  const q = searchInput.value.trim().toLowerCase();
  renderDepartmentStatus();

  let visibleCount = 0;
  cards.forEach(card=>{
    const cDept = card.dataset.dept || '';
    const status = card.dataset.status || '';
    const name = (card.querySelector('.card-title')?.textContent||'').toLowerCase();
    let show = true;
    if(dept!=='all' && cDept!==dept) show=false;
    if(onlyAvailable && status!=='available') show=false;
    if(q && !name.includes(q)) show=false;

    // If a department is selected and it's closed, don't show any faculty from it.
    if (dept !== 'all' && closedDepartments[dept]) {
        show = false;
    }

    card.style.display = show ? '' : 'none';
    if(show) visibleCount++;
  });

  let noResults = facultyGrid.querySelector('.no-results');
  if (visibleCount === 0) {
    if (!noResults) {
        noResults = document.createElement('div');
        noResults.className = 'no-results';
        facultyGrid.appendChild(noResults);
    }
    noResults.style.display = 'block';
    if (dept !== 'all' && closedDepartments[dept]) {
        noResults.textContent = 'Faculty are not shown because this department is currently closed.';
    } else {
        noResults.textContent = 'No faculty match your filters.';
    }
  } else if (noResults) {
      noResults.style.display = 'none';
  }
}

function attachCardHandlers(){
  facultyGrid.querySelectorAll('.btn.join').forEach(b=>b.addEventListener('click',e=>{
    const id = e.target.dataset.id; const card = facultyGrid.querySelector(`.card[data-id="${id}"]`);
    alert(`Joining queue for ${card.querySelector('.card-title').textContent}`);
  }));
  facultyGrid.querySelectorAll('.btn.view').forEach(b=>b.addEventListener('click',e=>{
    const id = e.target.dataset.id; const card = facultyGrid.querySelector(`.card[data-id="${id}"]`);
    const facultyName = card.querySelector('.card-title').textContent.trim();
    const facultyStatus = card.dataset.status;
    window.location.href = `viewSchedule.html?faculty=${encodeURIComponent(facultyName)}&status=${encodeURIComponent(facultyStatus)}`;
  }));
  facultyGrid.querySelectorAll('.card-notify').forEach(b=>b.addEventListener('click',e=>{
    const card = e.target.closest('.card');
    alert(`Notifications for ${card.querySelector('.card-title').textContent}`);
  }));
}

function insertNotifyButtons(){
  cards.forEach(card=>{
    if(card.querySelector('.card-notify')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'card-notify';
    button.setAttribute('aria-label', 'View notifications');
    button.innerHTML = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6V10c0-3.1-1.6-5.8-4.5-6.6V3.5c0-.8-.7-1.5-1.5-1.5S10.5 2.7 10.5 3.5v.9C7.6 4.2 6 6.9 6 10v6l-2 2v1h16v-1l-2-2z"/></svg>';
    card.appendChild(button);
  });
}

function loadCardsFromDOM(){
  // Cards are already in the DOM (inlined in dashboardStudent.html)
  cards = Array.from(facultyGrid.querySelectorAll('.card'));
  cards.forEach(c=>{
    const iso = c.dataset.lastupdated;
    const meta = c.querySelector('.meta');
    if(meta && iso) meta.textContent = 'Last updated: ' + parseISOToDisplay(iso);
  });
  insertNotifyButtons();
  populateDepartments();
  attachCardHandlers();
  renderCards();
}

// Wire up filters
deptFilter.addEventListener('change',renderCards);
availableToggle.addEventListener('change',renderCards);
let searchTimer=null;searchInput.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(renderCards,200);});

// Init
loadCardsFromDOM();
