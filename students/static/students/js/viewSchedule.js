const calendarGrid = document.getElementById("calendarGrid");
const legendList = document.getElementById("legendList");
const selectedFacultyName = document.getElementById("selectedFacultyName");
const facultyStatusNotify = document.getElementById("facultyStatusNotify");
const dayLabels = document.querySelector(".day-labels");
const viewControls = document.querySelector(".view-controls");

// --- Walk-in Queue Elements ---
const joinQueueBtn = document.getElementById("join-queue-btn");
const cancelQueueBtn = document.getElementById("cancel-queue-btn");
const queueInitialState = document.getElementById("queue-initial-state");
const queueActiveState = document.getElementById("queue-active-state");
const queueFacultyName = document.getElementById("queue-faculty-name");
const queueFacultyStatus = document.getElementById("queue-faculty-status");
const queuePosition = document.getElementById("queue-position");
const waitTime = document.getElementById("wait-time");
const walkInNote = document.getElementById("walk-in-note");
const queueMessage = document.getElementById("queue-message");
const isDeptClosed = document.body.dataset.deptClosed === "true";
const closureReason =
  document.body.dataset.closureReason || "This department is currently closed.";
const closureNotice = document.getElementById("departmentClosureNotice");

function applyClosureLockdown() {
  if (!isDeptClosed) return;
  if (closureNotice) {
    closureNotice.textContent = closureReason;
    closureNotice.classList.remove("hidden");
  }
  if (joinQueueBtn) {
    joinQueueBtn.disabled = true;
    joinQueueBtn.textContent = "Department Closed";
  }
  if (openModalBtn) {
    openModalBtn.disabled = true;
    openModalBtn.textContent = "Department Closed";
  }
  if (queueMessage) {
    queueMessage.textContent =
      "This department is currently closed and not accepting walk-ins.";
  }
}
const facultyId = document.body.dataset.facultyId;
let activeQueue = null;

let currentView = "monthly"; // Default view

function getCsrfToken() {
  const cookie = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="));
  return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

function updateFacultyStatusSubscriptionButton(subscribed) {
  if (!facultyStatusNotify) return;
  facultyStatusNotify.dataset.subscribed = String(subscribed);
  facultyStatusNotify.classList.toggle("subscribed", subscribed);
  facultyStatusNotify.setAttribute(
    "aria-label",
    subscribed
      ? "Stop receiving notifications for this faculty member"
      : "Receive notifications when this faculty member's status changes",
  );
  const label = facultyStatusNotify.querySelector("span");
  if (label) label.textContent = subscribed ? "Notifications on" : "Notify me";
}

if (facultyStatusNotify) {
  facultyStatusNotify.addEventListener("click", async () => {
    const subscribed = facultyStatusNotify.dataset.subscribed === "true";
    facultyStatusNotify.disabled = true;
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
      updateFacultyStatusSubscriptionButton(data.subscribed);
    } catch (error) {
      window.alert(error.message);
    } finally {
      facultyStatusNotify.disabled = false;
    }
  });
}

function ordinal(value) {
  const number = Number(value);
  const suffix =
    number % 10 === 1 && number % 100 !== 11
      ? "st"
      : number % 10 === 2 && number % 100 !== 12
        ? "nd"
        : number % 10 === 3 && number % 100 !== 13
          ? "rd"
          : "th";
  return `${number}${suffix}`;
}

function renderWalkInState(data) {
  activeQueue = data.queue;
  if (queueFacultyName) queueFacultyName.textContent = data.faculty_name;
  if (queueFacultyStatus) {
    const statusLabels = {
      available: "available",
      busy: "busy",
      virtual_only: "virtual only",
      on_leave: "on leave",
      unavailable: "unavailable",
    };
    queueFacultyStatus.textContent =
      statusLabels[data.faculty_status] ||
      data.faculty_status ||
      "status unavailable";
    const statusClasses = {
      available: "available",
      busy: "busy",
      virtual_only: "virtual",
      on_leave: "on-leave",
      unavailable: "unavailable",
    };
    queueFacultyStatus.className = `status-${statusClasses[data.faculty_status] || "offline"}`;
  }

  if (activeQueue) {
    queueInitialState?.classList.add("hidden");
    queueActiveState?.classList.remove("hidden");
    // Keep the faculty notification visible while the student is in the active queue state.
    queueActiveState?.classList.toggle(
      "is-called",
      activeQueue.status === "called",
    );
    if (queuePosition)
      queuePosition.textContent = ordinal(activeQueue.position);
    if (queueMessage) {
      const isCalled = activeQueue.status === "called";
      queueMessage.textContent = isCalled
        ? "You are being called now. Please enter the faculty office."
        : "You are in the walk-in queue. Please wait for the faculty notification.";
      queueMessage.classList.toggle("is-called", isCalled);
      queueMessage.classList.toggle("is-waiting", !isCalled);
    }
    return;
  }

  queueInitialState?.classList.remove("hidden");
  queueActiveState?.classList.add("hidden");
  queueActiveState?.classList.remove("is-called");
  if (joinQueueBtn) {
    joinQueueBtn.disabled = !data.walk_ins_enabled;
    joinQueueBtn.textContent = data.walk_ins_enabled
      ? "Join Walk-in Queue"
      : "Walk-ins Unavailable";
  }
  if (walkInNote) {
    walkInNote.textContent = data.walk_ins_enabled
      ? "This faculty is currently accepting walk-ins."
      : "The faculty member is not accepting new walk-in students.";
    walkInNote.classList.remove("hidden");
  }
  if (queueMessage) {
    queueMessage.textContent = "";
    queueMessage.classList.remove("is-called", "is-waiting");
  }
}

async function loadWalkInStatus() {
  if (!facultyId) {
    if (joinQueueBtn) {
      joinQueueBtn.disabled = true;
      joinQueueBtn.textContent = "Faculty Unavailable";
    }
    if (queueMessage)
      queueMessage.textContent =
        "Select a faculty member to join a walk-in queue.";
    return;
  }
  try {
    const response = await fetch(
      `/student/api/walk-ins/status/?faculty_id=${encodeURIComponent(facultyId)}`,
    );
    const data = await response.json();
    if (!response.ok)
      throw new Error(data.error || "Unable to check walk-in availability.");
    renderWalkInState(data);
  } catch (error) {
    if (joinQueueBtn) joinQueueBtn.disabled = true;
    if (queueMessage) queueMessage.textContent = error.message;
  }
}

const facultySchedule = {
  name: selectedFacultyName?.textContent || "Faculty Schedule",
  schedule: [],
};

const weekdayIndexes = {
  sunday: 0, monday: 1, tuesday: 2, wednesday: 3,
  thursday: 4, friday: 5, saturday: 6,
};

function localDateKey(value) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function monthIsIncluded(month, startMonth, endMonth) {
  if (!startMonth || !endMonth) return true;
  if (startMonth <= endMonth) return month >= startMonth && month <= endMonth;
  return month >= startMonth || month <= endMonth;
}

function recurringDateKeys(dayOfWeek, startMonth, endMonth) {
  const today = new Date();
  const first = new Date(today.getFullYear(), today.getMonth(), 1 - 7);
  const last = new Date(today.getFullYear(), today.getMonth() + 1, 7);
  const target = dayOfWeek ? weekdayIndexes[dayOfWeek] : null;
  const dates = [];
  for (let cursor = new Date(first); cursor <= last; cursor.setDate(cursor.getDate() + 1)) {
    if (monthIsIncluded(cursor.getMonth() + 1, startMonth, endMonth)
      && (target === null || cursor.getDay() === target)) dates.push(localDateKey(cursor));
  }
  return dates;
}

async function loadFacultySchedule() {
  if (!facultyId) {
    renderCalendar();
    return;
  }

  try {
    const response = await fetch(
      `/student/api/schedule-events/?faculty_id=${encodeURIComponent(facultyId)}`,
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Unable to load schedule.");

    const byDate = {};
    (data.events || []).forEach((event) => {
      const eventData = {
        id: event.id,
        title: event.title,
        description: event.description,
        location: event.location || "",
        status: event.status || event.event_type,
        type: event.event_type,
        isRecurring: Boolean(event.is_recurring),
        dayOfWeek: event.day_of_week === "none" ? "" : (event.day_of_week || ""),
        startMonth: event.start_month,
        endMonth: event.end_month,
        startTime: event.start_time ? event.start_time.slice(0, 5) : null,
        endTime: event.end_time ? event.end_time.slice(0, 5) : null,
      };
      const dateKeys = event.is_recurring
        ? recurringDateKeys(eventData.dayOfWeek, event.start_month, event.end_month)
        : (event.date ? [event.date] : []);
      dateKeys.forEach((dateKey) => {
        if (!byDate[dateKey]) byDate[dateKey] = { date: dateKey, events: [] };
        byDate[dateKey].events.push(eventData);
      });
    });

    facultySchedule.schedule = Object.values(byDate).sort(
      (a, b) => new Date(a.date) - new Date(b.date),
    );
    renderCalendar();
  } catch (error) {
    console.error("Failed to load faculty schedule", error);
    facultySchedule.schedule = [];
    renderCalendar();
  }
}

let activeEventContext = null;

function formatEventTime(eventData) {
  if (!eventData.startTime && !eventData.endTime) return "All day";
  return `${eventData.startTime || ""}${eventData.endTime ? ` - ${eventData.endTime}` : ""}`;
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);
}

function openDayScheduleModal(dateKey, dayLabel, events) {
  const modal = document.getElementById("dayScheduleModal");
  const titleEl = document.getElementById("dayScheduleTitle");
  const listEl = document.getElementById("dayScheduleList");

  if (!modal || !titleEl || !listEl) return;

  titleEl.textContent = `Schedule for ${dayLabel}`;
  listEl.innerHTML = "";

  events.forEach((eventData) => {
    const item = document.createElement("li");
    item.innerHTML = `
      <div class="details-item-title">
        <span>${escapeHtml(eventData.title)}</span>
        <span class="details-item-type type-${escapeHtml(eventData.type || "busy")}">${escapeHtml(eventData.type || "busy")}</span>
      </div>
      <div class="details-item-meta">${formatEventTime(eventData)}</div>
    `;
    item.addEventListener("click", () => {
      openEventModal(eventData, dateKey);
      modal.classList.add("hidden");
    });
    listEl.appendChild(item);
  });

  modal.classList.remove("hidden");
}

function openEventModal(eventData, dateKey) {
  const modal = document.getElementById("eventDetailModal");
  const titleEl = document.getElementById("eventDetailTitle");
  const typeEl = document.getElementById("eventDetailType");
  const timeEl = document.getElementById("eventDetailTime");
  const descriptionEl = document.getElementById("eventDetailDescription");

  if (!modal || !titleEl || !typeEl || !timeEl || !descriptionEl) return;

  activeEventContext = { dateKey, eventData };
  titleEl.textContent = eventData.title;
  typeEl.textContent = eventData.type || "busy";
  typeEl.className = `event-detail-type type-${eventData.type || "busy"}`;
  timeEl.textContent = formatEventTime(eventData);
  descriptionEl.textContent =
    eventData.description || "No description provided.";
  modal.classList.remove("hidden");
}

function renderCalendar() {
  const selectedFaculty = facultySchedule;
  calendarGrid.innerHTML = "";
  legendList.innerHTML = "";
  selectedFacultyName.textContent = selectedFaculty.name;

  // Walk-in availability is loaded from the faculty's persisted setting.
  if (joinQueueBtn) {
    joinQueueBtn.disabled = true;
    joinQueueBtn.textContent = "Checking Walk-ins...";
  }

  let daysToRender;
  const today = new Date();
  const year = today.getFullYear();
  const monthIndex = today.getMonth();
  const monthName = today.toLocaleDateString("en-US", { month: "short" });
  const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
  const monthNumber = String(monthIndex + 1).padStart(2, "0");

  if (currentView === "monthly") {
    daysToRender = Array.from({ length: daysInMonth }, (_, i) => i + 1);
    calendarGrid.classList.remove("daily-view-grid");
    calendarGrid.style.gridTemplateColumns = "";
    if (dayLabels) dayLabels.style.display = "";
  } else if (currentView === "weekly") {
    const dayOfMonth = today.getDate();
    const dayOfWeek = (today.getDay() + 6) % 7; // Mon=0
    const weekStart = dayOfMonth - dayOfWeek;
    daysToRender = Array.from({ length: 7 }, (_, i) => weekStart + i);
    calendarGrid.classList.remove("daily-view-grid");
    calendarGrid.style.gridTemplateColumns = "";
    if (dayLabels) dayLabels.style.display = "";
  } else {
    // daily
    if (dayLabels) dayLabels.style.display = "none";
    calendarGrid.style.gridTemplateColumns = "auto 1fr";
    calendarGrid.classList.add("daily-view-grid");

    const timeScale = document.createElement("div");
    timeScale.className = "time-scale";

    const dayContent = document.createElement("div");
    dayContent.className = "day-content";

    const hourHeight = 60; // 60px per hour.
    const dayStartHour = 6;
    const dayEndHour = 18;

    // Keep the student daily schedule aligned with the faculty 6 AM–6 PM window.
    for (let i = dayStartHour; i <= dayEndHour; i++) {
      const timeLabel = document.createElement("div");
      timeLabel.className = "time-label";
      timeLabel.textContent =
        i > 12 ? `${i - 12}:00 PM` : i === 12 ? "12:00 PM" : `${i}:00 AM`;
      timeLabel.style.height = `${i === dayEndHour ? 0 : hourHeight}px`;
      if (i === dayEndHour) timeLabel.classList.add("time-label-end");
      timeScale.appendChild(timeLabel);

      if (i === dayEndHour) continue;
      const gridLine = document.createElement("div");
      gridLine.className = "time-grid-line";
      gridLine.style.height = `${hourHeight}px`;
      dayContent.appendChild(gridLine);
    }

    calendarGrid.appendChild(timeScale);
    calendarGrid.appendChild(dayContent);

    const day = today.getDate();
    const dateKey = `${year}-${monthNumber}-${String(day).padStart(2, "0")}`;
    const dayEntry = selectedFaculty.schedule.find(
      (entry) => entry.date === dateKey,
    );

    if (dayEntry) {
      const visibleDayEvents = dayEntry.events.filter((event) => {
        if (!event.startTime || !event.endTime) return true;
        const [startHour, startMinute] = event.startTime.split(":").map(Number);
        const [endHour, endMinute] = event.endTime.split(":").map(Number);
        return (
          endHour * 60 + endMinute > dayStartHour * 60 &&
          startHour * 60 + startMinute < dayEndHour * 60
        );
      });
      const visibleEvents = visibleDayEvents.slice(0, 2);
      const overflowEvents = visibleDayEvents.slice(2);

      visibleEvents.forEach((event) => {
        const item = document.createElement("div");
        item.className = "slot-item";
        const eventTime =
          event.startTime && event.endTime
            ? `${event.startTime} - ${event.endTime}`
            : "All day";
        item.innerHTML = `<strong>${escapeHtml(event.title)}</strong>${eventTime}`;
        item.addEventListener("click", () => openEventModal(event, dateKey));

        if (!event.startTime || !event.endTime) {
          item.classList.add("all-day-item");
          dayContent.appendChild(item);
          return;
        }

        const [startHour, startMinute] = event.startTime.split(":").map(Number);
        const [endHour, endMinute] = event.endTime.split(":").map(Number);
        const eventStartMinutes = startHour * 60 + startMinute;
        const eventEndMinutes = endHour * 60 + endMinute;
        const visibleStartMinutes = Math.max(
          eventStartMinutes,
          dayStartHour * 60,
        );
        const visibleEndMinutes = Math.min(eventEndMinutes, dayEndHour * 60);

        // Skip events outside the visible daily range and clip overlapping events to it.
        if (visibleEndMinutes <= visibleStartMinutes) return;

        const top =
          ((visibleStartMinutes - dayStartHour * 60) / 60) * hourHeight;
        const durationMinutes = visibleEndMinutes - visibleStartMinutes;
        const height = (durationMinutes / 60) * hourHeight;

        item.style.position = "absolute";
        item.style.top = `${top}px`;
        item.style.height = `${height - 4}px`; // -4 for padding/border visual adjustment
        item.style.left = "8px";
        item.style.right = "8px";
        item.style.zIndex = "1";

        dayContent.appendChild(item);

        const legendItem = document.createElement("li");
        legendItem.textContent = `${event.title} • ${monthName} ${day} • ${event.startTime} - ${event.endTime}`;
        legendList.appendChild(legendItem);
      });

      if (overflowEvents.length > 0) {
        const overflowBtn = document.createElement("button");
        overflowBtn.className = "overflow-pill";
        overflowBtn.type = "button";
        overflowBtn.textContent = `+${overflowEvents.length} more`;
        overflowBtn.addEventListener("click", (event) => {
          event.stopPropagation();
          openDayScheduleModal(dateKey, `${monthName} ${day}`, dayEntry.events);
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
      const date = new Date(year, monthIndex, day);
      const dayOfWeek = date.toLocaleDateString("en-US", { weekday: "short" });
      header.textContent = `${dayOfWeek} ${day}`;
      column.appendChild(header);

      const body = document.createElement("div");
      body.className = "day-body";

      const dateKey = `${year}-${monthNumber}-${String(day).padStart(2, "0")}`;
      const dayEntry = selectedFaculty.schedule.find(
        (entry) => entry.date === dateKey,
      );
      if (dayEntry) {
        const visibleEvents = dayEntry.events.slice(0, 2);
        const overflowEvents = dayEntry.events.slice(2);

        visibleEvents.forEach((event) => {
          const item = document.createElement("div");
          item.className = "slot-item";
          item.innerHTML = `<strong>${escapeHtml(event.title)}</strong>${formatEventTime(event)}`;
          item.addEventListener("click", () => openEventModal(event, dateKey));
          body.appendChild(item);

          const legendItem = document.createElement("li");
          legendItem.textContent = `${event.title} • ${monthName} ${day} • ${event.startTime} - ${event.endTime}`;
          legendList.appendChild(legendItem);
        });

        if (overflowEvents.length > 0) {
          const overflowBtn = document.createElement("button");
          overflowBtn.className = "overflow-pill";
          overflowBtn.type = "button";
          overflowBtn.textContent = `+${overflowEvents.length} more`;
          overflowBtn.addEventListener("click", (event) => {
            event.stopPropagation();
            openDayScheduleModal(dateKey, `${monthName} ${day}`, dayEntry.events);
          });
          body.appendChild(overflowBtn);
        }
      }
      column.appendChild(body);
    } else {
      column.classList.add("disabled");
    }
    calendarGrid.appendChild(column);
  });
}

// Modal functionality
const consultationModal = document.getElementById("consultationModal");
const eventDetailModal = document.getElementById("eventDetailModal");
const dayScheduleModal = document.getElementById("dayScheduleModal");
const dayScheduleCloseBtns = document.querySelectorAll(
  "[data-close-modal='dayScheduleModal']",
);
const openModalBtn = document.getElementById("book-consultation-btn");
const closeModalBtn = document.querySelector(
  "#consultationModal .modal-close-btn",
);
const consultationForm = document.getElementById("consultationForm");
const myConsultationsBtn = document.getElementById("my-consultations-btn");
const detailCloseBtns = document.querySelectorAll(
  "[data-close-modal='eventDetailModal']",
);

if (myConsultationsBtn) {
  myConsultationsBtn.addEventListener("click", () => {
    // Use Django's resolved URL so this works from any student page.
    window.location.href =
      myConsultationsBtn.dataset.consultationsUrl ||
      "/student/consultation-requests/";
  });
}

if (joinQueueBtn) {
  joinQueueBtn.addEventListener("click", async () => {
    joinQueueBtn.disabled = true;
    if (queueMessage) queueMessage.textContent = "Joining walk-in queue...";
    try {
      const response = await fetch("/student/api/walk-ins/join/", {
        method: "POST",
        headers: {
          "X-CSRFToken": getCsrfToken(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ faculty_id: facultyId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(data.error || "Unable to join the walk-in queue.");
      await loadWalkInStatus();
    } catch (error) {
      if (queueMessage) queueMessage.textContent = error.message;
      await loadWalkInStatus();
    }
  });
}

if (cancelQueueBtn) {
  cancelQueueBtn.addEventListener("click", async () => {
    if (!activeQueue) return;
    cancelQueueBtn.disabled = true;
    try {
      const response = await fetch(
        `/faculty/api/walk-ins/${encodeURIComponent(activeQueue.queue_id)}/`,
        {
          method: "POST",
          headers: {
            "X-CSRFToken": getCsrfToken(),
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ action: "cancel" }),
        },
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(data.error || "Unable to leave the queue.");
      await loadWalkInStatus();
    } catch (error) {
      if (queueMessage) queueMessage.textContent = error.message;
    } finally {
      cancelQueueBtn.disabled = false;
    }
  });
}

openModalBtn.addEventListener("click", () => {
  consultationModal.classList.remove("hidden");
});

closeModalBtn.addEventListener("click", () => {
  consultationModal.classList.add("hidden");
});

consultationModal.addEventListener("click", (e) => {
  if (e.target === consultationModal) {
    consultationModal.classList.add("hidden");
  }
});

if (eventDetailModal) {
  eventDetailModal.addEventListener("click", (e) => {
    if (e.target === eventDetailModal) {
      eventDetailModal.classList.add("hidden");
    }
  });
}

if (dayScheduleModal) {
  dayScheduleModal.addEventListener("click", (e) => {
    if (e.target === dayScheduleModal) {
      dayScheduleModal.classList.add("hidden");
    }
  });
}

dayScheduleCloseBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    if (dayScheduleModal) dayScheduleModal.classList.add("hidden");
  });
});

detailCloseBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    if (eventDetailModal) eventDetailModal.classList.add("hidden");
  });
});

if (consultationForm) {
  consultationForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const submitButton = consultationForm.querySelector(
      'button[type="submit"]',
    );
    if (submitButton) submitButton.disabled = true;

    try {
      // Save the request before closing the modal so it appears in My Consultations.
      const response = await fetch("/student/api/consultation-requests/", {
        method: "POST",
        headers: {
          "X-CSRFToken": getCsrfToken(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          faculty_id: facultyId,
          date: document.getElementById("dateSelect").value,
          start_time: document.getElementById("timeSelect").value,
          message: document.getElementById("message").value,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(data.error || "Unable to book the consultation.");
      consultationModal.classList.add("hidden");
      consultationForm.reset();
      alert("Consultation request sent.");
    } catch (error) {
      alert(error.message);
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  });
}

if (viewControls) {
  const viewButtons = viewControls.querySelectorAll(".view-btn");
  viewButtons.forEach((button) => {
    button.addEventListener("click", () => {
      viewControls.querySelector(".active").classList.remove("active");
      button.classList.add("active");
      currentView = button.dataset.view;
      renderCalendar();
    });
  });
}

renderCalendar();
loadFacultySchedule();
applyClosureLockdown();
if (!isDeptClosed) {
  loadWalkInStatus();
  window.setInterval(loadWalkInStatus, 10000);
}
