document.addEventListener("DOMContentLoaded", () => {
  const calendarGrid = document.getElementById("calendarGrid");
  const legendList = document.getElementById("legendList");
  const dayLabels = document.querySelector(".day-labels");
  const viewControls = document.querySelector(".view-controls");

  let currentView = "monthly"; // Default view
  let isEditing = false; // To track if the modal is for editing

  // Dummy data for the faculty's schedule
  let activeEventContext = null;

  const facultySchedule = {
    name: "Dr. Morgan",
    schedule: [
      {
        date: "2026-06-02",
        events: [
          {
            title: "Class",
            startTime: "09:00",
            endTime: "10:30",
            type: "busy",
          },
        ],
      },
      {
        date: "2026-06-05",
        events: [
          {
            title: "Meeting",
            startTime: "08:30",
            endTime: "11:00",
            type: "busy",
          },
        ],
      },
      {
        date: "2026-06-09",
        events: [
          {
            title: "Class",
            startTime: "09:30",
            endTime: "12:30",
            type: "busy",
          },
        ],
      },
      {
        date: "2026-06-12",
        events: [
          {
            title: "Meeting",
            startTime: "10:00",
            endTime: "11:00",
            type: "busy",
          },
          {
            title: "Class",
            startTime: "13:00",
            endTime: "14:30",
            type: "busy",
          },
          {
            title: "Office Hours",
            startTime: "15:00",
            endTime: "16:00",
            type: "busy",
          },
        ],
      },
    ],
  };

  function addEvent(eventData) {
    const { title, type, startDate, endDate, startTime, endTime, description } = eventData;

    const loopDate = new Date(startDate);
    loopDate.setMinutes(loopDate.getMinutes() + loopDate.getTimezoneOffset());
    const lastDate = new Date(endDate || startDate);
    lastDate.setMinutes(lastDate.getMinutes() + lastDate.getTimezoneOffset());

    while (loopDate <= lastDate) {
      const dateKey = loopDate.toISOString().split("T")[0];

      let dayEntry = facultySchedule.schedule.find(
        (entry) => entry.date === dateKey,
      );
      if (!dayEntry) {
        dayEntry = { date: dateKey, events: [] };
        facultySchedule.schedule.push(dayEntry);
      }

      const newEvent = {
        title,
        type,
        description,
        startTime: type === "on-leave" ? "All Day" : startTime,
        endTime: type === "on-leave" ? "" : endTime,
      };

      dayEntry.events.push(newEvent);

      loopDate.setDate(loopDate.getDate() + 1);
    }

    facultySchedule.schedule.sort((a, b) => new Date(a.date) - new Date(b.date));
  }

  function formatEventTime(eventData) {
    if (eventData.type === "on-leave") return "All Day";
    return `${eventData.startTime}${eventData.endTime ? ` - ${eventData.endTime}` : ""}`;
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
          <span>${eventData.title}</span>
          <span class="details-item-type type-${eventData.type || "busy"}">${eventData.type || "busy"}</span>
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
    const editBtn = document.getElementById("editEventBtn");
    const removeBtn = document.getElementById("removeEventBtn");

    if (!modal || !titleEl || !typeEl || !timeEl || !descriptionEl || !removeBtn) return;

    activeEventContext = { dateKey, eventData };
    titleEl.textContent = eventData.title;
    typeEl.textContent = eventData.type || "busy";
    typeEl.className = `event-detail-type type-${eventData.type || "busy"}`;
    const timeText = eventData.type === "on-leave"
      ? "All Day"
      : `${eventData.startTime}${eventData.endTime ? ` - ${eventData.endTime}` : ""}`;
    timeEl.textContent = timeText;
    descriptionEl.textContent = eventData.description || "No description provided.";
    modal.classList.remove("hidden");

    removeBtn.onclick = () => {
      if (confirm(`Are you sure you want to delete "${eventData.title}"?`)) {
        deleteEvent(dateKey, eventData);
        modal.classList.add("hidden");
      }
    };

    editBtn.onclick = () => {
        openAddEventModalForEdit();
    };
  }

  function deleteEvent(dateKey, eventToDelete) {
    const dayEntry = facultySchedule.schedule.find(
      (entry) => entry.date === dateKey,
    );
    if (dayEntry) {
      dayEntry.events = dayEntry.events.filter(
        (event) =>
          !(
            event.title === eventToDelete.title &&
            event.startTime === eventToDelete.startTime &&
            event.endTime === eventToDelete.endTime
          ),
      );
      // If no events left for that day, remove the day entry
      if (dayEntry.events.length === 0) {
        facultySchedule.schedule = facultySchedule.schedule.filter(
          (entry) => entry.date !== dateKey,
        );
      }
      renderCalendar(); // Re-render to show the change
    }
  }

  function renderCalendar() {
    if (!calendarGrid || !legendList) return;

    calendarGrid.innerHTML = "";
    legendList.innerHTML = "";

    let daysToRender;
    const today = new Date("2026-06-09"); // Fixed date for demo purposes
    const daysInMonth = 30; // Hardcoded for June

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

      for (let i = 8; i <= 17; i++) {
        // 8 AM to 5 PM
        const timeLabel = document.createElement("div");
        timeLabel.className = "time-label";
        timeLabel.textContent =
          i > 12 ? `${i - 12}:00 PM` : i === 12 ? "12:00 PM" : `${i}:00 AM`;
        timeLabel.style.height = `${hourHeight}px`;
        timeScale.appendChild(timeLabel);

        const gridLine = document.createElement("div");
        gridLine.className = "time-grid-line";
        gridLine.style.height = `${hourHeight}px`;
        dayContent.appendChild(gridLine);
      }

      calendarGrid.appendChild(timeScale);
      calendarGrid.appendChild(dayContent);

      const day = today.getDate();
      const dateKey = `2026-06-${String(day).padStart(2, "0")}`;
      const dayEntry = facultySchedule.schedule.find(
        (entry) => entry.date === dateKey,
      );

      if (dayEntry) {
        const visibleEvents = dayEntry.events.slice(0, 2);
        const overflowEvents = dayEntry.events.slice(2);

        visibleEvents.forEach((event) => {
          const item = document.createElement("div");
          item.className = "slot-item";
          item.classList.add(`slot-type-${event.type || "busy"}`);
          item.innerHTML = `
            <div>
                <strong>${event.title}</strong>
                ${event.startTime}${event.endTime ? ` - ${event.endTime}` : ""}
            </div>
          `;
          item.addEventListener("click", () => openEventModal(event, dateKey));

          const [startHour, startMinute] = event.startTime
            .split(":")
            .map(Number);
          const [endHour, endMinute] = event.endTime.split(":").map(Number);

          const top =
            (startHour - 8) * hourHeight + (startMinute / 60) * hourHeight;
          const durationMinutes =
            endHour * 60 + endMinute - (startHour * 60 + startMinute);
          const height = (durationMinutes / 60) * hourHeight;

          item.style.position = "absolute";
          item.style.top = `${top}px`;
          item.style.height = `${height - 4}px`; // -4 for padding/border visual adjustment
          item.style.left = "8px";
          item.style.right = "8px";
          item.style.zIndex = "1";

          dayContent.appendChild(item);

          const legendItem = document.createElement("li");
          legendItem.textContent = `${event.title} • Jun ${day} • ${
            event.startTime
          }${event.endTime ? ` - ${event.endTime}` : ""}`;
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
        const dayOfWeek = date.toLocaleDateString("en-US", {
          weekday: "short",
        });
        header.textContent = `${dayOfWeek} ${day}`;
        column.appendChild(header);

        const body = document.createElement("div");
        body.className = "day-body";

        const dateKey = `2026-06-${String(day).padStart(2, "0")}`;
        const dayEntry = facultySchedule.schedule.find(
          (entry) => entry.date === dateKey,
        );

        if (dayEntry) {
          const visibleEvents = dayEntry.events.slice(0, 2);
          const overflowEvents = dayEntry.events.slice(2);

          visibleEvents.forEach((event) => {
            const item = document.createElement("div");
            item.className = "slot-item";
            item.classList.add(`slot-type-${event.type || "busy"}`);
            item.innerHTML = `
                <div>
                    <strong>${event.title}</strong>
                    ${event.startTime}${event.endTime ? ` - ${event.endTime}` : ""}
                </div>
            `;
            item.addEventListener("click", () => openEventModal(event, dateKey));
            body.appendChild(item);

            const legendItem = document.createElement("li");
            legendItem.textContent = `${event.title} • Jun ${day} • ${
              event.startTime
            }${event.endTime ? ` - ${event.endTime}` : ""}`;
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
        column.classList.add("disabled");
      }
      calendarGrid.appendChild(column);
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

  // Modal functionality for adding events
  const addEventModal = document.getElementById("addEventModal");
  const eventDetailModal = document.getElementById("eventDetailModal");
  const dayScheduleModal = document.getElementById("dayScheduleModal");
  const dayScheduleCloseBtns = document.querySelectorAll("[data-close-modal='dayScheduleModal']");
  const openModalBtn = document.getElementById("add-event-btn");
  const closeModalBtn = addEventModal?.querySelector(".modal-close-btn");

  const detailCloseBtns = document.querySelectorAll("[data-close-modal='eventDetailModal']");
  const addEventForm = document.getElementById("addEventForm");
  const eventTypeSelect = document.getElementById("eventType");
  const timeInputsWrapper = document.getElementById("time-inputs-wrapper");
  const startTimeInput = document.getElementById("eventStartTime");
  const endTimeInput = document.getElementById("eventEndTime");

  if (eventTypeSelect && timeInputsWrapper) {
    eventTypeSelect.addEventListener("change", (e) => {
      if (e.target.value === "on-leave") {
        timeInputsWrapper.style.display = "none";
        startTimeInput.required = false;
        endTimeInput.required = false;
      } else {
        timeInputsWrapper.style.display = "block";
        startTimeInput.required = true;
        endTimeInput.required = true;
      }
    });
  }

  if (openModalBtn && addEventModal) {
    openModalBtn.addEventListener("click", () => {
      isEditing = false;
      activeEventContext = null;
      addEventModal.classList.remove("hidden");

      addEventModal.querySelector('h1').textContent = 'Add a New Event';
      addEventModal.querySelector('.eyebrow').textContent = 'Schedule Management';
      addEventModal.querySelector('button[type="submit"]').textContent = 'Add Event';

      addEventForm.reset();
      if (eventTypeSelect) eventTypeSelect.dispatchEvent(new Event("change"));
    });
  }

  if (closeModalBtn && addEventModal) {
    closeModalBtn.addEventListener("click", () => {
      addEventModal.classList.add("hidden");
    });
  }

  if (addEventModal) {
    addEventModal.addEventListener("click", (e) => {
      if (e.target === addEventModal) {
        addEventModal.classList.add("hidden");
      }
    });
  }

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
  if (addEventForm) {
    addEventForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const eventDetails = {
        title: document.getElementById("eventTitle").value,
        type: document.getElementById("eventType").value,
        description: document.getElementById("eventDescription").value,
        startDate: document.getElementById("eventStartDate").value,
        endDate: document.getElementById("eventEndDate").value,
        startTime: document.getElementById("eventStartTime").value,
        endTime: document.getElementById("eventEndTime").value,
      };

      eventDetails.endDate = eventDetails.endDate || eventDetails.startDate;

      if (isEditing && activeEventContext) {
        deleteEvent(activeEventContext.dateKey, activeEventContext.eventData);
      }

      addEvent(eventDetails);

      addEventModal.classList.add("hidden");
      addEventForm.reset();
      if (eventTypeSelect) {
        eventTypeSelect.dispatchEvent(new Event("change"));
      }
      isEditing = false;
      activeEventContext = null;
      renderCalendar();
    });
  }

  renderCalendar();

  const viewWalkinsBtn = document.getElementById('view-walkins-btn');
  if (viewWalkinsBtn) {
      viewWalkinsBtn.addEventListener('click', () => {
          window.location.href = 'bookingManagement.html';
      });
  }

  function openAddEventModalForEdit() {
    if (!activeEventContext) return;

    isEditing = true;
    const { dateKey, eventData } = activeEventContext;

    eventDetailModal.classList.add("hidden");
    addEventModal.classList.remove("hidden");

    // Update modal appearance for editing
    addEventModal.querySelector('h1').textContent = 'Edit Event';
    addEventModal.querySelector('.eyebrow').textContent = 'Schedule Management';
    addEventModal.querySelector('button[type="submit"]').textContent = 'Save Changes';

    // Populate form with existing event data
    document.getElementById('eventTitle').value = eventData.title;
    document.getElementById('eventType').value = eventData.type;
    document.getElementById('eventDescription').value = eventData.description || '';
    document.getElementById('eventStartDate').value = dateKey;
    document.getElementById('eventEndDate').value = dateKey; // Default to single day

    if (eventData.type !== 'on-leave') {
        timeInputsWrapper.style.display = "block";
        startTimeInput.required = true;
        endTimeInput.required = true;
        document.getElementById('eventStartTime').value = eventData.startTime;
        document.getElementById('eventEndTime').value = eventData.endTime;
    } else {
        timeInputsWrapper.style.display = "none";
        startTimeInput.required = false;
        endTimeInput.required = false;
    }
  }
});
