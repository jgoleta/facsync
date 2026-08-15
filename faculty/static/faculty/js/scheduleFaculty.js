document.addEventListener("DOMContentLoaded", () => {
  const calendarGrid = document.getElementById("calendarGrid");
  const legendList = document.getElementById("legendList");
  const dayLabels = document.querySelector(".day-labels");
  const viewControls = document.querySelector(".view-controls");
  const datePill = document.querySelector(".date-pill");
  const calendarSyncStatus = document.getElementById("calendar-sync-status");
  const syncCalendarBtn = document.getElementById("syncCalendarBtn");
  const walkInToggle = document.getElementById("walkInToggle");
  const walkInFeedback = document.getElementById("walkInFeedback");

  let currentView = "monthly"; // Default view
  let isEditing = false; // To track if the modal is for editing

  let activeEventContext = null;

  function getCsrfToken() {
    const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
    return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
  }

  function requestHeaders(includeJson = false) {
    const headers = { 'X-CSRFToken': getCsrfToken() };
    if (includeJson) headers['Content-Type'] = 'application/json';
    return headers;
  }

  function showWalkInFeedback(message, isError = false) {
    if (!walkInFeedback) return;
    walkInFeedback.textContent = message;
    walkInFeedback.className = `calendar-sync-status${isError ? ' error' : ''}`;
  }

  if (walkInToggle) {
    walkInToggle.addEventListener('change', async () => {
      const enabled = walkInToggle.checked;
      walkInToggle.disabled = true;
      try {
        const response = await fetch('/faculty/api/walk-ins/preference/', {
          method: 'POST',
          headers: requestHeaders(true),
          body: JSON.stringify({ enabled }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Unable to update walk-in availability.');
        walkInToggle.checked = data.walk_ins_enabled;
        showWalkInFeedback(data.walk_ins_enabled
          ? 'Students can now join your walk-in queue.'
          : 'Walk-in queue is closed to new students.');
      } catch (error) {
        walkInToggle.checked = !enabled;
        showWalkInFeedback(error.message, true);
      } finally {
        walkInToggle.disabled = false;
      }
    });
  }

  // Schedule object will be populated from the server API
  const facultySchedule = { name: null, schedule: [] };

  async function fetchEventsFromApi(sync = false) {
    try {
      const res = await fetch(`/faculty/api/events/${sync ? '?sync=1' : ''}`);
      if (!res.ok) {
        if (calendarSyncStatus) {
          calendarSyncStatus.textContent = 'Unable to load schedule.';
          calendarSyncStatus.className = 'calendar-sync-status error';
        }
        return;
      }
      const data = await res.json();
      const events = data.events || [];

      // Group events by date into facultySchedule.schedule
      const map = {};
      events.forEach((ev) => {
        const dateKey = ev.date.split('T')[0];
        if (!map[dateKey]) map[dateKey] = { date: dateKey, events: [] };
        map[dateKey].events.push({
          id: ev.id,
          title: ev.title,
          description: ev.description,
          type: ev.event_type,
          startTime: ev.start_time ? ev.start_time.split('T').pop().slice(0,5) : ev.start_time,
          endTime: ev.end_time ? ev.end_time.split('T').pop().slice(0,5) : ev.end_time,
        });
      });

      facultySchedule.schedule = Object.values(map).sort((a,b) => new Date(a.date) - new Date(b.date));
      if (calendarSyncStatus) {
        calendarSyncStatus.textContent = data.sync_error
          ? `Google sync failed: ${data.sync_error}`
          : `Google Calendar synced · ${events.length} event${events.length === 1 ? '' : 's'}`;
        calendarSyncStatus.className = `calendar-sync-status${data.sync_error ? ' error' : ''}`;
      }
      renderCalendar();
      return data;
    } catch (err) {
      console.error('Failed to fetch events', err);
      return null;
    }
  }

  async function addEvent(eventData) {
    // Send create request to API
    try {
      const payload = {
        title: eventData.title,
        description: eventData.description,
        event_type: eventData.type,
        date: eventData.date || (eventData.startTime ? eventData.startTime.split('T')[0] : null),
        start_time: eventData.startTime && eventData.startTime.includes('T') ? eventData.startTime.split('T')[1] : null,
        end_time: eventData.endTime && eventData.endTime.includes('T') ? eventData.endTime.split('T')[1] : null,
      };
      const res = await fetch('/faculty/api/events/', {
        method: 'POST',
        headers: requestHeaders(true),
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || 'Failed to create event.');
      }
      const data = await res.json();
      // Refresh events from server
      await fetchEventsFromApi();
      return data;
    } catch (err) {
      console.error('Error creating event', err);
      throw err;
    }
  }

  function formatEventTime(eventData) {
    if (eventData.type === "on-leave") return "All Day";
    return `${formatTime12(eventData.startTime)}${eventData.endTime ? ` - ${formatTime12(eventData.endTime)}` : ""}`;
  }

  function formatTime12(timeValue) {
    if (!timeValue) return "";

    const timePart = String(timeValue).split("T").pop().split(" ").pop();
    const match = timePart.match(/^(\d{1,2}):(\d{2})/);
    if (!match) return timeValue;

    const hour24 = Number(match[1]);
    const minutes = match[2];
    const period = hour24 >= 12 ? "PM" : "AM";
    const hour12 = hour24 % 12 || 12;
    return `${hour12}:${minutes} ${period}`;
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
    timeEl.textContent = formatEventTime(eventData);
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

  async function deleteEvent(dateKey, eventToDelete) {
    // If event has an id, call DELETE on API
    if (eventToDelete.id) {
      try {
        const res = await fetch(`/faculty/api/events/${eventToDelete.id}/`, {
          method: 'DELETE',
          headers: requestHeaders(),
        });
        if (!res.ok) {
          console.error('Failed to delete event');
          return;
        }
        await fetchEventsFromApi();
        return;
      } catch (err) {
        console.error('Error deleting event', err);
      }
    }

    // Fallback to client-side removal for events without id
    const dayEntry = facultySchedule.schedule.find((entry) => entry.date === dateKey);
    if (dayEntry) {
      dayEntry.events = dayEntry.events.filter((event) => event !== eventToDelete);
      if (dayEntry.events.length === 0) {
        facultySchedule.schedule = facultySchedule.schedule.filter((entry) => entry.date !== dateKey);
      }
      renderCalendar();
    }
  }

  function renderCalendar() {
    if (!calendarGrid || !legendList) return;

    calendarGrid.innerHTML = "";
    legendList.innerHTML = "";

    let daysToRender;
    const today = new Date();
    const year = today.getFullYear();
    const monthIndex = today.getMonth();
    const monthNumber = String(monthIndex + 1).padStart(2, "0");
    const monthName = today.toLocaleDateString("en-US", { month: "short" });
    const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
    if (datePill) datePill.textContent = today.toLocaleDateString("en-US", { month: "long", year: "numeric" });

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

      for (let i = 6; i <= 21; i++) {
        // 6 AM to 9 PM
        const timeLabel = document.createElement("div");
        timeLabel.className = "time-label";
        timeLabel.textContent = formatTime12(`${i}:00`);
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
      const dateKey = `${year}-${monthNumber}-${String(day).padStart(2, "0")}`;
      const dayEntry = facultySchedule.schedule.find(
        (entry) => entry.date === dateKey,
      );

      if (dayEntry) {
        const visibleEvents = dayEntry.events;

        visibleEvents.forEach((event) => {
          const item = document.createElement("div");
          item.className = "slot-item";
          item.classList.add(`slot-type-${event.type || "busy"}`);
          item.innerHTML = `
            <div>
                <strong>${event.title}</strong>
                ${formatEventTime(event)}
            </div>
          `;
          item.addEventListener("click", () => openEventModal(event, dateKey));

          if (!event.startTime || !event.endTime) {
            item.classList.add("all-day-item");
            dayContent.appendChild(item);
            const legendItem = document.createElement("li");
            legendItem.textContent = `${event.title} • All day`;
            legendList.appendChild(legendItem);
            return;
          }

          const [startHour, startMinute] = event.startTime
            .split(":")
            .map(Number);
          const [endHour, endMinute] = event.endTime.split(":").map(Number);

          const top =
            (startHour - 6) * hourHeight + (startMinute / 60) * hourHeight;
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
          legendItem.textContent = `${event.title} • ${monthName} ${day} • ${
            formatTime12(event.startTime)
          }${event.endTime ? ` - ${formatTime12(event.endTime)}` : ""}`;
          legendList.appendChild(legendItem);
        });

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
        const dayOfWeek = date.toLocaleDateString("en-US", {
          weekday: "short",
        });
        header.textContent = `${dayOfWeek} ${day}`;
        column.appendChild(header);

        const body = document.createElement("div");
        body.className = "day-body";

        const dateKey = `${year}-${monthNumber}-${String(day).padStart(2, "0")}`;
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
                    ${formatEventTime(event)}
                </div>
            `;
            item.addEventListener("click", () => openEventModal(event, dateKey));
            body.appendChild(item);

            const legendItem = document.createElement("li");
            legendItem.textContent = `${event.title} • ${monthName} ${day} • ${
              formatTime12(event.startTime)
              }${event.endTime ? ` - ${formatTime12(event.endTime)}` : ""}`;
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
  const eventDateGroup = document.getElementById("event-date-group");
  const eventDateInput = document.getElementById("eventDate");
  const timeInputsWrapper = document.getElementById("time-inputs-wrapper");
  const startTimeInput = document.getElementById("eventStartTime");
  const endTimeInput = document.getElementById("eventEndTime");

  if (eventTypeSelect && timeInputsWrapper) {
    eventTypeSelect.addEventListener("change", (e) => {
      if (e.target.value === "on-leave") {
        if (eventDateGroup) eventDateGroup.style.display = "block";
        if (eventDateInput) eventDateInput.required = true;
        timeInputsWrapper.style.display = "none";
        startTimeInput.required = false;
        endTimeInput.required = false;
      } else {
        if (eventDateGroup) eventDateGroup.style.display = "none";
        if (eventDateInput) eventDateInput.required = false;
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
      if (eventDateInput) {
        const now = new Date();
        eventDateInput.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
      }
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
    addEventForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const eventDetails = {
        title: document.getElementById("eventTitle").value,
        type: document.getElementById("eventType").value,
        description: document.getElementById("eventDescription").value,
        date: eventTypeSelect?.value === "on-leave"
          ? (eventDateInput ? eventDateInput.value : '')
          : (document.getElementById("eventStartTime").value || '').split('T')[0],
        startTime: document.getElementById("eventStartTime").value,
        endTime: document.getElementById("eventEndTime").value,
      };

      if (isEditing && activeEventContext && activeEventContext.eventData && activeEventContext.eventData.id) {
        // update via API
        try {
          const payload = {
            title: eventDetails.title,
            description: eventDetails.description,
            event_type: eventDetails.type,
            date: eventDetails.date || (eventDetails.startTime ? eventDetails.startTime.split('T')[0] : null),
            start_time: eventDetails.startTime && eventDetails.startTime.includes('T') ? eventDetails.startTime.split('T')[1] : null,
            end_time: eventDetails.endTime && eventDetails.endTime.includes('T') ? eventDetails.endTime.split('T')[1] : null,
          };
          const res = await fetch(`/faculty/api/events/${activeEventContext.eventData.id}/`, {
            method: 'PUT',
            headers: requestHeaders(true),
            body: JSON.stringify(payload),
          });
          if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.error || 'Failed to update event.');
          }
        } catch (err) {
          console.error('Error updating event', err);
          if (calendarSyncStatus) {
            calendarSyncStatus.textContent = err.message;
            calendarSyncStatus.className = 'calendar-sync-status error';
          }
          return;
        }
      } else {
        // create new event
        try {
          await addEvent(eventDetails);
        } catch (err) {
          if (calendarSyncStatus) {
            calendarSyncStatus.textContent = err.message;
            calendarSyncStatus.className = 'calendar-sync-status error';
          }
          return;
        }
      }

      addEventModal.classList.add("hidden");
      addEventForm.reset();
      if (eventTypeSelect) {
        eventTypeSelect.dispatchEvent(new Event("change"));
      }
      isEditing = false;
      activeEventContext = null;
      await fetchEventsFromApi();
    });
  }

  if (syncCalendarBtn) {
    syncCalendarBtn.addEventListener('click', async () => {
      syncCalendarBtn.disabled = true;
      syncCalendarBtn.textContent = 'Syncing...';
      await fetchEventsFromApi(true);
      syncCalendarBtn.disabled = false;
      syncCalendarBtn.textContent = '↻ Sync';
    });
  }

  // Render cached events immediately, then refresh them from Google in the background.
  fetchEventsFromApi().then((data) => {
    if (data?.calendar_connected) fetchEventsFromApi(true);
  });

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
    if (eventDateInput) eventDateInput.value = dateKey;

    if (eventData.type !== 'on-leave') {
      if (eventDateGroup) eventDateGroup.style.display = "none";
      if (eventDateInput) eventDateInput.required = false;
      timeInputsWrapper.style.display = "block";
      startTimeInput.required = true;
      endTimeInput.required = true;
      // eventData may have dateKey and startTime like '09:00'
      document.getElementById('eventStartTime').value = `${dateKey}T${eventData.startTime}`;
      document.getElementById('eventEndTime').value = `${dateKey}T${eventData.endTime}`;
    } else {
      if (eventDateGroup) eventDateGroup.style.display = "block";
      if (eventDateInput) eventDateInput.required = true;
      timeInputsWrapper.style.display = "none";
      startTimeInput.required = false;
      endTimeInput.required = false;
    }
  }
});
