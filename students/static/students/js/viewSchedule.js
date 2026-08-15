const calendarGrid = document.getElementById("calendarGrid");
const legendList = document.getElementById("legendList");
const selectedFacultyName = document.getElementById("selectedFacultyName");
const dayLabels = document.querySelector('.day-labels');
const viewControls = document.querySelector('.view-controls');

// --- Walk-in Queue Elements ---
const joinQueueBtn = document.getElementById('join-queue-btn');
const cancelQueueBtn = document.getElementById('cancel-queue-btn');
const queueInitialState = document.getElementById('queue-initial-state');
const queueActiveState = document.getElementById('queue-active-state');
const queueFacultyName = document.getElementById('queue-faculty-name');
const queueFacultyStatus = document.getElementById('queue-faculty-status');
const queuePosition = document.getElementById('queue-position');
const waitTime = document.getElementById('wait-time');
const walkInNote = document.getElementById('walk-in-note');
const queueMessage = document.getElementById('queue-message');
const facultyId = document.body.dataset.facultyId;
let activeQueue = null;

let currentView = 'monthly'; // Default view

function getCsrfToken() {
  const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
  return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
}

function ordinal(value) {
  const number = Number(value);
  const suffix = number % 10 === 1 && number % 100 !== 11 ? 'st'
    : number % 10 === 2 && number % 100 !== 12 ? 'nd'
      : number % 10 === 3 && number % 100 !== 13 ? 'rd' : 'th';
  return `${number}${suffix}`;
}

function renderWalkInState(data) {
  activeQueue = data.queue;
  if (queueFacultyName) queueFacultyName.textContent = data.faculty_name;
  if (queueFacultyStatus) {
    const statusLabels = {
      available: 'available',
      busy: 'busy',
      virtual_only: 'virtual only',
      on_leave: 'on leave',
      unavailable: 'unavailable',
    };
    queueFacultyStatus.textContent = statusLabels[data.faculty_status] || data.faculty_status || 'status unavailable';
    queueFacultyStatus.className = `status-${data.faculty_status || 'offline'}`;
  }

  if (activeQueue) {
    queueInitialState?.classList.add('hidden');
    queueActiveState?.classList.remove('hidden');
    if (queuePosition) queuePosition.textContent = ordinal(activeQueue.position);
    if (queueMessage) {
      queueMessage.textContent = activeQueue.status === 'called'
        ? 'The faculty member asked you to enter the office now.'
        : 'You are in the walk-in queue. Please wait for the faculty notification.';
    }
    return;
  }

  queueInitialState?.classList.remove('hidden');
  queueActiveState?.classList.add('hidden');
  if (joinQueueBtn) {
    joinQueueBtn.disabled = !data.walk_ins_enabled;
    joinQueueBtn.textContent = data.walk_ins_enabled ? 'Join Walk-in Queue' : 'Walk-ins Unavailable';
  }
  if (walkInNote) {
    walkInNote.textContent = data.walk_ins_enabled
      ? 'This faculty is currently accepting walk-ins.'
      : 'The faculty member is not accepting new walk-in students.';
    walkInNote.classList.remove('hidden');
  }
  if (queueMessage) queueMessage.textContent = '';
}

async function loadWalkInStatus() {
  if (!facultyId) {
    if (joinQueueBtn) {
      joinQueueBtn.disabled = true;
      joinQueueBtn.textContent = 'Faculty Unavailable';
    }
    if (queueMessage) queueMessage.textContent = 'Select a faculty member to join a walk-in queue.';
    return;
  }
  try {
    const response = await fetch(`/student/api/walk-ins/status/?faculty_id=${encodeURIComponent(facultyId)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Unable to check walk-in availability.');
    renderWalkInState(data);
  } catch (error) {
    if (joinQueueBtn) joinQueueBtn.disabled = true;
    if (queueMessage) queueMessage.textContent = error.message;
  }
}

const facultySchedule = [
  {
    name: "Arthur Morgan",
    department: "College of Computer Studies",
    schedule: [
      {
        date: "2026-06-02",
        events: [{ title: "Class", startTime: "09:00", endTime: "10:30" }],
      },
      {
        date: "2026-06-05",
        events: [{ title: "Meeting", startTime: "08:30", endTime: "11:00" }],
      },
      {
        date: "2026-06-09",
        events: [{ title: "Class", startTime: "09:30", endTime: "12:30" }],
      },
      {
        date: "2026-06-12",
        events: [
          { title: "Meeting", startTime: "10:00", endTime: "11:00" },
          { title: "Class", startTime: "13:00", endTime: "14:30" },
          { title: "Office Hours", startTime: "15:00", endTime: "16:00" },
        ],
      },
      {
        date: "2026-06-17",
        events: [{ title: "Class", startTime: "09:00", endTime: "13:00" }],
      },
      {
        date: "2026-06-21",
        events: [{ title: "Meeting", startTime: "11:00", endTime: "12:00" }],
      },
      {
        date: "2026-06-26",
        events: [{ title: "Class", startTime: "08:00", endTime: "12:00" }],
      },
      {
        date: "2026-06-30",
        events: [{ title: "Meeting", startTime: "09:00", endTime: "10:00" }],
      },
    ],
  },
  {
    name: "Leon Kennedy",
    department: "College of Business and Accountancy",
    schedule: [
        { date: "2026-06-03", events: [{ title: "Class", startTime: "13:00", endTime: "15:00" }] },
        { date: "2026-06-10", events: [{ title: "Class", startTime: "13:00", endTime: "15:00" }] },
    ]
  },
  {
    name: "Joel Miller",
    department: "College of Humanities and Social Sciences",
    schedule: [
        { date: "2026-06-04", events: [{ title: "Consultation Hours", startTime: "10:00", endTime: "12:00" }] },
    ]
  },
  {
    name: "Max Payne",
    department: "College of Computer Studies",
    schedule: []
  },
  {
    name: "Geralt of Rivia",
    department: "College of Nursing",
    schedule: [
        { date: "2026-06-08", events: [{ title: "Lab Supervision", startTime: "09:00", endTime: "12:00" }] },
    ]
  },
  {
    name: "Frank Ortiz",
    department: "College of Nursing",
    schedule: []
  },
  {
    name: "Grace Kim",
    department: "College of Engineering",
    schedule: []
  },
  {
    name: "Henry Alvarez",
    department: "College of Humanities and Social Sciences",
    schedule: []
  },
  {
    name: "Irene Patel",
    department: "College of Humanities and Social Sciences",
    schedule: []
  },
  {
    name: "Julia Rivers",
    department: "College of Education",
    schedule: []
  },
  {
    name: "Kevin Zhou",
    department: "College of Computer Studies",
    schedule: []
  },
];

let activeEventContext = null;

function formatEventTime(eventData) {
  return `${eventData.startTime} - ${eventData.endTime}`;
}

function openDayScheduleModal(dateKey, dayLabel, events) {
  const modal = document.getElementById('dayScheduleModal');
  const titleEl = document.getElementById('dayScheduleTitle');
  const listEl = document.getElementById('dayScheduleList');

  if (!modal || !titleEl || !listEl) return;

  titleEl.textContent = `Schedule for ${dayLabel}`;
  listEl.innerHTML = '';

  events.forEach((eventData) => {
    const item = document.createElement('li');
    item.innerHTML = `
      <div class="details-item-title">
        <span>${eventData.title}</span>
        <span class="details-item-type type-${eventData.type || 'busy'}">${eventData.type || 'busy'}</span>
      </div>
      <div class="details-item-meta">${formatEventTime(eventData)}</div>
    `;
    item.addEventListener('click', () => {
      openEventModal(eventData, dateKey);
      modal.classList.add('hidden');
    });
    listEl.appendChild(item);
  });

  modal.classList.remove('hidden');
}

function openEventModal(eventData, dateKey) {
  const modal = document.getElementById('eventDetailModal');
  const titleEl = document.getElementById('eventDetailTitle');
  const typeEl = document.getElementById('eventDetailType');
  const timeEl = document.getElementById('eventDetailTime');
  const descriptionEl = document.getElementById('eventDetailDescription');

  if (!modal || !titleEl || !typeEl || !timeEl || !descriptionEl) return;

  activeEventContext = { dateKey, eventData };
  titleEl.textContent = eventData.title;
  typeEl.textContent = eventData.type || 'busy';
  typeEl.className = `event-detail-type type-${eventData.type || 'busy'}`;
  const timeText = `${eventData.startTime} - ${eventData.endTime}`;
  timeEl.textContent = timeText;
  descriptionEl.textContent = eventData.description || 'No description provided.';
  modal.classList.remove('hidden');
}

function renderCalendar() {
  const urlParams = new URLSearchParams(window.location.search);
  const facultyNameFromURL = urlParams.get('faculty');
  const facultyStatusFromURL = urlParams.get('status') || 'on-leave';

  const selectedFaculty = facultySchedule.find(f => f.name === facultyNameFromURL) || {
    name: selectedFacultyName?.textContent || 'Faculty Schedule',
    schedule: [],
  };
  calendarGrid.innerHTML = "";
  legendList.innerHTML = "";
  selectedFacultyName.textContent = selectedFaculty.name;

  // Walk-in availability is loaded from the faculty's persisted setting.
  if (joinQueueBtn) {
    joinQueueBtn.disabled = true;
    joinQueueBtn.textContent = 'Checking Walk-ins...';
  }

  let daysToRender;
  const today = new Date('2026-06-09'); // Fixed date for demo purposes
  const daysInMonth = 30; // Hardcoded for June

  if (currentView === 'monthly') {
    daysToRender = Array.from({ length: daysInMonth }, (_, i) => i + 1);
    calendarGrid.classList.remove('daily-view-grid');
    calendarGrid.style.gridTemplateColumns = '';
    if (dayLabels) dayLabels.style.display = '';
  } else if (currentView === 'weekly') {
    const dayOfMonth = today.getDate();
    const dayOfWeek = (today.getDay() + 6) % 7; // Mon=0
    const weekStart = dayOfMonth - dayOfWeek;
    daysToRender = Array.from({ length: 7 }, (_, i) => weekStart + i);
    calendarGrid.classList.remove('daily-view-grid');
    calendarGrid.style.gridTemplateColumns = '';
    if (dayLabels) dayLabels.style.display = '';
  } else { // daily
    if (dayLabels) dayLabels.style.display = 'none';
    calendarGrid.style.gridTemplateColumns = 'auto 1fr';
    calendarGrid.classList.add('daily-view-grid');

    const timeScale = document.createElement('div');
    timeScale.className = 'time-scale';

    const dayContent = document.createElement('div');
    dayContent.className = 'day-content';

    const hourHeight = 60; // 60px per hour.

    for (let i = 8; i <= 17; i++) { // 8 AM to 5 PM
      const timeLabel = document.createElement('div');
      timeLabel.className = 'time-label';
      timeLabel.textContent = i > 12 ? `${i - 12}:00 PM` : (i === 12 ? '12:00 PM' : `${i}:00 AM`);
      timeLabel.style.height = `${hourHeight}px`;
      timeScale.appendChild(timeLabel);

      const gridLine = document.createElement('div');
      gridLine.className = 'time-grid-line';
      gridLine.style.height = `${hourHeight}px`;
      dayContent.appendChild(gridLine);
    }

    calendarGrid.appendChild(timeScale);
    calendarGrid.appendChild(dayContent);

    const day = today.getDate();
    const dateKey = `2026-06-${String(day).padStart(2, "0")}`;
    const dayEntry = selectedFaculty.schedule.find(entry => entry.date === dateKey);

    if (dayEntry) {
      const visibleEvents = dayEntry.events.slice(0, 2);
      const overflowEvents = dayEntry.events.slice(2);

      visibleEvents.forEach(event => {
        const item = document.createElement("div");
        item.className = "slot-item";
        item.innerHTML = `<strong>${event.title}</strong>${event.startTime} - ${event.endTime}`;
        item.addEventListener('click', () => openEventModal(event, dateKey));

        const [startHour, startMinute] = event.startTime.split(':').map(Number);
        const [endHour, endMinute] = event.endTime.split(':').map(Number);

        const top = ((startHour - 8) * hourHeight) + (startMinute / 60 * hourHeight);
        const durationMinutes = (endHour * 60 + endMinute) - (startHour * 60 + startMinute);
        const height = (durationMinutes / 60) * hourHeight;

        item.style.position = 'absolute';
        item.style.top = `${top}px`;
        item.style.height = `${height - 4}px`; // -4 for padding/border visual adjustment
        item.style.left = '8px';
        item.style.right = '8px';
        item.style.zIndex = '1';

        dayContent.appendChild(item);

        const legendItem = document.createElement("li");
        legendItem.textContent = `${event.title} • Jun ${day} • ${event.startTime} - ${event.endTime}`;
        legendList.appendChild(legendItem);
      });

      if (overflowEvents.length > 0) {
        const overflowBtn = document.createElement("button");
        overflowBtn.className = "overflow-pill";
        overflowBtn.type = "button";
        overflowBtn.textContent = `+${overflowEvents.length} more`;
        overflowBtn.addEventListener("click", (event) => {
          event.stopPropagation();
          openDayScheduleModal(dateKey, `Jun ${day}`, dayEntry.events);
        });
        dayContent.appendChild(overflowBtn);
      }
    }
    return; // Exit before the generic loop for monthly/weekly views
  }

  daysToRender.forEach((day) => {
    const column = document.createElement("div");
    column.className = "day-column";

    const header = document.createElement("div");
    header.className = "day-header";

    if (day > 0 && day <= daysInMonth) {
      const date = new Date(2026, 5, day); // 5 is June
      const dayOfWeek = date.toLocaleDateString('en-US', { weekday: 'short' });
      header.textContent = `${dayOfWeek} ${day}`;
      column.appendChild(header);

      const body = document.createElement("div");
      body.className = "day-body";

      const dateKey = `2026-06-${String(day).padStart(2, "0")}`;
      const dayEntry = selectedFaculty.schedule.find(
        (entry) => entry.date === dateKey,
      );
      if (dayEntry) {
        const visibleEvents = dayEntry.events.slice(0, 2);
        const overflowEvents = dayEntry.events.slice(2);

        visibleEvents.forEach((event) => {
          const item = document.createElement("div");
          item.className = "slot-item";
          item.innerHTML = `<strong>${event.title}</strong>${event.startTime} - ${event.endTime}`;
          item.addEventListener('click', () => openEventModal(event, dateKey));
          body.appendChild(item);

          const legendItem = document.createElement("li");
          legendItem.textContent = `${event.title} • Jun ${day} • ${event.startTime} - ${event.endTime}`;
          legendList.appendChild(legendItem);
        });

        if (overflowEvents.length > 0) {
          const overflowBtn = document.createElement("button");
          overflowBtn.className = "overflow-pill";
          overflowBtn.type = "button";
          overflowBtn.textContent = `+${overflowEvents.length} more`;
          overflowBtn.addEventListener("click", (event) => {
            event.stopPropagation();
            openDayScheduleModal(dateKey, `Jun ${day}`, dayEntry.events);
          });
          body.appendChild(overflowBtn);
        }
      }
      column.appendChild(body);
    } else {
      column.classList.add('disabled');
    }
    calendarGrid.appendChild(column);
  });
}

// Modal functionality
const consultationModal = document.getElementById('consultationModal');
const eventDetailModal = document.getElementById('eventDetailModal');
const dayScheduleModal = document.getElementById('dayScheduleModal');
const dayScheduleCloseBtns = document.querySelectorAll("[data-close-modal='dayScheduleModal']");
const openModalBtn = document.getElementById('book-consultation-btn');
const closeModalBtn = document.querySelector('#consultationModal .modal-close-btn');
const consultationForm = document.getElementById('consultationForm');
const myConsultationsBtn = document.getElementById('my-consultations-btn');
const detailCloseBtns = document.querySelectorAll("[data-close-modal='eventDetailModal']");

if (myConsultationsBtn) {
    myConsultationsBtn.addEventListener('click', () => {
        window.location.href = 'consultationRequests.html';
    });
}

if (joinQueueBtn) {
  joinQueueBtn.addEventListener('click', async () => {
    joinQueueBtn.disabled = true;
    if (queueMessage) queueMessage.textContent = 'Joining walk-in queue...';
    try {
      const response = await fetch('/student/api/walk-ins/join/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ faculty_id: facultyId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Unable to join the walk-in queue.');
      await loadWalkInStatus();
    } catch (error) {
      if (queueMessage) queueMessage.textContent = error.message;
      await loadWalkInStatus();
    }
  });
}

if (cancelQueueBtn) {
  cancelQueueBtn.addEventListener('click', async () => {
    if (!activeQueue) return;
    cancelQueueBtn.disabled = true;
    try {
      const response = await fetch(`/faculty/api/walk-ins/${encodeURIComponent(activeQueue.queue_id)}/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'cancel' }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Unable to leave the queue.');
      await loadWalkInStatus();
    } catch (error) {
      if (queueMessage) queueMessage.textContent = error.message;
    } finally {
      cancelQueueBtn.disabled = false;
    }
  });
}

openModalBtn.addEventListener('click', () => {
  consultationModal.classList.remove('hidden');
});

closeModalBtn.addEventListener('click', () => {
  consultationModal.classList.add('hidden');
});

consultationModal.addEventListener('click', (e) => {
  if (e.target === consultationModal) {
    consultationModal.classList.add('hidden');
  }
});

if (eventDetailModal) {
  eventDetailModal.addEventListener('click', (e) => {
    if (e.target === eventDetailModal) {
      eventDetailModal.classList.add('hidden');
    }
  });
}

if (dayScheduleModal) {
  dayScheduleModal.addEventListener('click', (e) => {
    if (e.target === dayScheduleModal) {
      dayScheduleModal.classList.add('hidden');
    }
  });
}

dayScheduleCloseBtns.forEach((btn) => {
  btn.addEventListener('click', () => {
    if (dayScheduleModal) dayScheduleModal.classList.add('hidden');
  });
});

detailCloseBtns.forEach((btn) => {
  btn.addEventListener('click', () => {
    if (eventDetailModal) eventDetailModal.classList.add('hidden');
  });
});

consultationForm.addEventListener('submit', (e) => {
    e.preventDefault();
    console.log('Form submitted');
    consultationModal.classList.add('hidden');
    alert('Consultation booked!');
});

if (viewControls) {
    const viewButtons = viewControls.querySelectorAll('.view-btn');
    viewButtons.forEach(button => {
        button.addEventListener('click', () => {
            viewControls.querySelector('.active').classList.remove('active');
            button.classList.add('active');
            currentView = button.dataset.view;
            renderCalendar();
        });
    });
}

renderCalendar();
loadWalkInStatus();
window.setInterval(loadWalkInStatus, 10000);
