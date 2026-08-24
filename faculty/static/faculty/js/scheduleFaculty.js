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
  const uploadScheduleBtn = document.getElementById("upload-schedule-btn");
  const viewUploadPreviewBtn = document.getElementById("view-upload-preview-btn");
  const clearScheduleBtn = document.getElementById("clear-schedule-btn");
  const scheduleCsvInput = document.getElementById("schedule-csv-input");
  const scheduleUploadStatus = document.getElementById("schedule-upload-status");
  const schedulePreviewModal = document.getElementById("schedule-preview-modal");
  const schedulePreviewCard = document.getElementById("schedule-preview-card");
  const schedulePreviewClose = document.getElementById("schedule-preview-close");
  const schedulePreviewBody = document.getElementById("schedule-preview-body");
  const schedulePreviewEmpty = document.getElementById("schedule-preview-empty");
  const schedulePreviewCount = document.getElementById("schedule-preview-count");
  let schedulePreviewEventIds = [];

  let currentView = "monthly"; // Default view
  let isEditing = false; // To track if the modal is for editing

  let activeEventContext = null;

  // --- Request and Feedback Helpers ---

  // Retrieve the CSRF token required by schedule API requests.
  function getCsrfToken() {
    const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
    return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
  }

  // Build request headers for JSON and multipart schedule API calls.
  function requestHeaders(includeJson = false) {
    const headers = { 'X-CSRFToken': getCsrfToken() };
    if (includeJson) headers['Content-Type'] = 'application/json';
    return headers;
  }

  // Show the result of changing walk-in availability.
  function showWalkInFeedback(message, isError = false) {
    if (!walkInFeedback) return;
    walkInFeedback.textContent = message;
    walkInFeedback.className = `calendar-sync-status${isError ? ' error' : ''}`;
  }

  // --- Walk-in Availability ---

  // Save the faculty member's walk-in availability preference.
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

  // --- Calendar Data and API ---

  // Store the schedule returned by the server for calendar rendering.
  const facultySchedule = { name: null, schedule: [] };
  const weekdayIndexes = {
    sunday: 0, monday: 1, tuesday: 2, wednesday: 3,
    thursday: 4, friday: 5, saturday: 6,
  };

  // Convert a Date object into the YYYY-MM-DD key used by the calendar.
  function localDateKey(value) {
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
  }

  // Determine whether a month falls inside an event's recurring month range.
  function monthIsIncluded(month, startMonth, endMonth) {
    if (!startMonth || !endMonth) return true;
    if (startMonth <= endMonth) return month >= startMonth && month <= endMonth;
    return month >= startMonth || month <= endMonth;
  }

  // Expand a recurring weekday event into the date keys shown by the calendar.
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

  // Fetch schedule events, normalize them, and refresh the calendar display.
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

      // Group one-off events by date and expand recurring weekday events into
      // the dates visible around the current month.
      const map = {};
      events.forEach((ev) => {
        const eventData = {
          id: ev.id,
          title: ev.title,
          description: ev.description,
          location: ev.location || "",
          status: ev.status || ev.event_type,
          type: ev.event_type,
          isRecurring: Boolean(ev.is_recurring),
          dayOfWeek: ev.day_of_week === "none" ? "" : (ev.day_of_week || ""),
          startMonth: ev.start_month,
          endMonth: ev.end_month,
          startTime: ev.start_time ? ev.start_time.split('T').pop().slice(0,5) : ev.start_time,
          endTime: ev.end_time ? ev.end_time.split('T').pop().slice(0,5) : ev.end_time,
          isConsultation: Boolean(ev.is_consultation),
        };
        const dateKeys = ev.is_recurring
          ? recurringDateKeys(eventData.dayOfWeek, ev.start_month, ev.end_month)
          : (ev.date ? [ev.date.split('T')[0]] : []);
        dateKeys.forEach((dateKey) => {
          if (!map[dateKey]) map[dateKey] = { date: dateKey, events: [] };
          map[dateKey].events.push(eventData);
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

  // --- Schedule CSV Upload ---

  // Display validation, upload, or deletion feedback for schedule CSV actions.
  function setScheduleUploadStatus(message, isError = false) {
    if (!scheduleUploadStatus) return;
    scheduleUploadStatus.textContent = message;
    scheduleUploadStatus.className = `calendar-sync-status${isError ? " error" : ""}`;
  }

  // Render the rows returned by a schedule CSV upload in the preview modal.
  function renderSchedulePreview(rows) {
    if (!schedulePreviewCard || !schedulePreviewBody) return;
    schedulePreviewBody.innerHTML = "";
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      [row.event_title, row.short_description || "—", row.room_location || "—", row.recurring_day || "None",
        `${row.start_month || "—"}-${row.end_month || "—"}`, row.start_time, row.end_time, row.status_type || "Busy"]
        .forEach((value) => {
          const td = document.createElement("td");
          td.textContent = value;
          tr.appendChild(td);
        });
      schedulePreviewBody.appendChild(tr);
    });
    if (schedulePreviewCount) {
      schedulePreviewCount.textContent = `${rows.length} row${rows.length === 1 ? "" : "s"}`;
    }
    if (schedulePreviewEmpty) schedulePreviewEmpty.classList.toggle("hidden", rows.length > 0);
    if (schedulePreviewModal) schedulePreviewModal.classList.remove("hidden");
  }

  // Hide the uploaded schedule preview modal.
  function closeSchedulePreview() {
    if (schedulePreviewModal) schedulePreviewModal.classList.add("hidden");
  }

  if (schedulePreviewClose) schedulePreviewClose.addEventListener("click", closeSchedulePreview);
  if (schedulePreviewModal) {
    schedulePreviewModal.addEventListener("click", (event) => {
      if (event.target === schedulePreviewModal) closeSchedulePreview();
    });
  }

  if (viewUploadPreviewBtn) {
    viewUploadPreviewBtn.addEventListener("click", () => {
      if (schedulePreviewModal) schedulePreviewModal.classList.remove("hidden");
    });
  }

  // Validate and upload a faculty schedule CSV file.
  async function uploadSchedule(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setScheduleUploadStatus("Please choose a .csv file.", true);
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    if (uploadScheduleBtn) {
      uploadScheduleBtn.disabled = true;
      uploadScheduleBtn.textContent = "Uploading...";
    }
    setScheduleUploadStatus("Validating and saving schedule...");
    try {
      const response = await fetch("/faculty/api/schedule/upload/", {
        method: "POST",
        headers: requestHeaders(),
        body: formData,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const details = (data.errors || [data.error || "Unable to upload schedule."]).join(" ");
        throw new Error(details);
      }
      renderSchedulePreview(data.preview || []);
      schedulePreviewEventIds = (data.events || [])
        .map((event) => event.id)
        .filter((id) => id !== undefined && id !== null);
      setScheduleUploadStatus(data.message || "Schedule uploaded successfully.");
      await fetchEventsFromApi();
    } catch (error) {
      setScheduleUploadStatus(error.message, true);
    } finally {
      if (uploadScheduleBtn) {
        uploadScheduleBtn.disabled = false;
        uploadScheduleBtn.textContent = "Upload Schedule";
      }
      if (scheduleCsvInput) scheduleCsvInput.value = "";
    }
  }

  if (uploadScheduleBtn && scheduleCsvInput) {
    uploadScheduleBtn.addEventListener("click", () => scheduleCsvInput.click());
    scheduleCsvInput.addEventListener("change", () => uploadSchedule(scheduleCsvInput.files[0]));
  }

  if (clearScheduleBtn) {
    clearScheduleBtn.addEventListener("click", async () => {
      if (!window.confirm("Delete the uploaded schedule shown in this preview? This cannot be undone.")) return;
      clearScheduleBtn.disabled = true;
      setScheduleUploadStatus("Deleting schedule...");
      try {
        const response = await fetch("/faculty/api/schedule/clear/", {
          method: "POST",
          headers: requestHeaders(true),
          body: JSON.stringify({ event_ids: schedulePreviewEventIds }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Unable to delete schedule.");
        if (schedulePreviewBody) schedulePreviewBody.innerHTML = "";
        if (schedulePreviewEmpty) schedulePreviewEmpty.classList.remove("hidden");
        schedulePreviewEventIds = [];
        closeSchedulePreview();
        setScheduleUploadStatus("Schedule deleted. You can upload a new CSV now.");
        await fetchEventsFromApi();
      } catch (error) {
        setScheduleUploadStatus(error.message, true);
      } finally {
        clearScheduleBtn.disabled = false;
      }
    });
  }

  // --- Event CRUD and Display Helpers ---

  // Create a new schedule event through the faculty API.
  async function addEvent(eventData) {
    try {
      const payload = {
        title: eventData.title,
        description: eventData.description,
        location: eventData.location,
        event_type: eventData.type,
        date: eventData.date || null,
        day_of_week: eventData.dayOfWeek || '',
        start_month: eventData.startMonth || null,
        end_month: eventData.endMonth || null,
        start_date: eventData.startDate || null,
        end_date: eventData.endDate || null,
        start_time: timeValue(eventData.startTime),
        end_time: timeValue(eventData.endTime),
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

  // Format an event's time range for calendar and modal labels.
  function formatEventTime(eventData) {
    if (eventData.type === "on-leave") return "All Day";
    return `${formatTime12(eventData.startTime)}${eventData.endTime ? ` - ${formatTime12(eventData.endTime)}` : ""}`;
  }

  // Convert a 24-hour time value into a readable 12-hour format.
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

  // Open a modal listing every event for a selected calendar day.
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

  // Show the selected event's details and available actions.
  function openEventModal(eventData, dateKey) {
    const modal = document.getElementById("eventDetailModal");
    const titleEl = document.getElementById("eventDetailTitle");
    const typeEl = document.getElementById("eventDetailType");
    const timeEl = document.getElementById("eventDetailTime");
    const descriptionEl = document.getElementById("eventDetailDescription");
    const locationEl = document.getElementById("eventDetailLocation");
    const editBtn = document.getElementById("editEventBtn");
    const removeBtn = document.getElementById("removeEventBtn");

    if (!modal || !titleEl || !typeEl || !timeEl || !descriptionEl || !removeBtn) return;

    activeEventContext = { dateKey, eventData };
    titleEl.textContent = eventData.title;
    typeEl.textContent = eventData.status || eventData.type || "busy";
    typeEl.className = `event-detail-type type-${eventData.type || "busy"}`;
    timeEl.textContent = formatEventTime(eventData);
    descriptionEl.textContent = eventData.description || "No description provided.";
    if (locationEl) locationEl.textContent = eventData.location || "Not specified.";
    if (editBtn) editBtn.style.display = eventData.isConsultation ? "none" : "";
    removeBtn.style.display = eventData.isConsultation ? "none" : "";
    modal.classList.remove("hidden");

    removeBtn.onclick = () => {
      if (confirm(`Are you sure you want to delete "${eventData.title}"?`)) {
        deleteEvent(dateKey, eventData);
        modal.classList.add("hidden");
      }
    };

    if (editBtn) {
      editBtn.onclick = () => {
        openAddEventModalForEdit();
      };
    }
  }

  // Delete a schedule event from the API or remove it from local state.
  async function deleteEvent(dateKey, eventToDelete) {
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

  // --- Calendar Rendering ---

  // Render the current schedule in monthly, weekly, or daily view.
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
      const dayStartHour = 6;
      const dayEndHour = 18;

      // Keep the daily faculty schedule limited to the requested 6 AM–6 PM window.
      for (let i = dayStartHour; i <= dayEndHour; i++) {
        const timeLabel = document.createElement("div");
        timeLabel.className = "time-label";
        timeLabel.textContent = formatTime12(`${i}:00`);
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
          const eventStartMinutes = startHour * 60 + startMinute;
          const eventEndMinutes = endHour * 60 + endMinute;
          const visibleStartMinutes = Math.max(eventStartMinutes, dayStartHour * 60);
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

  // Change the active calendar view and render it again.
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

  // --- Add and Edit Event Modal ---

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
  const eventDayGroup = document.getElementById("event-day-group");
  const eventDayInput = document.getElementById("eventDay");

  // Extract the month number from an HTML date or datetime value.
  function monthFromDate(value) {
    return value ? Number(value.slice(5, 7)) : null;
  }

  // Extract the time portion expected by the schedule API.
  function timeValue(value) {
    return value ? value.split('T').pop() : null;
  }
  // Extract the date portion from an HTML datetime value.
  function dateValue(value) {
    return value ? value.split('T')[0] : '';
  }

  // Return the selected recurring weekday, or an empty value for one-time events.
  function selectedRecurringDay() {
    const value = eventDayInput?.value || '';
    return value && value.toLowerCase() !== 'none' ? value : '';
  }

  // Keep the date and time fields in sync with recurring-event selection.
  if (eventDayInput) {
    eventDayInput.addEventListener("change", () => {
      if (eventTypeSelect) eventTypeSelect.dispatchEvent(new Event("change"));
    });
  }

  const timeInputsWrapper = document.getElementById("time-inputs-wrapper");
  const startTimeInput = document.getElementById("eventStartTime");
  const endTimeInput = document.getElementById("eventEndTime");

  // Show and validate the form fields appropriate for the selected event type.
  if (eventTypeSelect && timeInputsWrapper) {
    eventTypeSelect.addEventListener("change", (e) => {
      if (selectedRecurringDay()) {
        if (eventDateGroup) eventDateGroup.style.display = "none";
        if (eventDateInput) eventDateInput.required = false;
      } else if (e.target.value === "on-leave") {
        if (eventDateGroup) eventDateGroup.style.display = "block";
        if (eventDateInput) eventDateInput.required = true;
        timeInputsWrapper.style.display = "none";
        startTimeInput.required = false;
        endTimeInput.required = false;
      } else {
        if (eventDateGroup) eventDateGroup.style.display = "none";
        if (eventDateInput) eventDateInput.required = false;
        timeInputsWrapper.style.display = "grid";
        startTimeInput.required = true;
        endTimeInput.required = true;
      }
    });
  }

  // Reset and open the form for creating a new event.
  if (openModalBtn && addEventModal) {
    openModalBtn.addEventListener("click", () => {
      isEditing = false;
      activeEventContext = null;
      addEventModal.classList.remove("hidden");

      addEventModal.querySelector('h1').textContent = 'Add a New Event';
      addEventModal.querySelector('.eyebrow').textContent = 'Schedule Management';
      addEventModal.querySelector('button[type="submit"]').textContent = 'Add Event';

      addEventForm.reset();
      if (eventDayInput) eventDayInput.value = '';
      if (eventDateGroup) eventDateGroup.classList.remove("hidden");
      if (eventDateInput) {
        const now = new Date();
        eventDateInput.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
      }
      if (eventTypeSelect) eventTypeSelect.dispatchEvent(new Event("change"));
    });
  }

  // Close the add-event modal from its close button.
  if (closeModalBtn && addEventModal) {
    closeModalBtn.addEventListener("click", () => {
      addEventModal.classList.add("hidden");
    });
  }

  // Close the add-event modal when the backdrop is clicked.
  if (addEventModal) {
    addEventModal.addEventListener("click", (e) => {
      if (e.target === addEventModal) {
        addEventModal.classList.add("hidden");
      }
    });
  }

  // Close the event-detail modal when its backdrop is clicked.
  if (eventDetailModal) {
    eventDetailModal.addEventListener("click", (e) => {
      if (e.target === eventDetailModal) {
        eventDetailModal.classList.add("hidden");
      }
    });
  }

  // Close the day-schedule modal when its backdrop is clicked.
  if (dayScheduleModal) {
  dayScheduleModal.addEventListener("click", (e) => {
    if (e.target === dayScheduleModal) {
      dayScheduleModal.classList.add("hidden");
    }
  });
}

  // Close the day-schedule modal from its close buttons.
  dayScheduleCloseBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    if (dayScheduleModal) dayScheduleModal.classList.add("hidden");
  });
});
  // Create or update an event from the add-event form submission.
  if (addEventForm) {
    addEventForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const recurringDay = selectedRecurringDay();
      const isRecurring = Boolean(recurringDay);
      const startInputValue = document.getElementById("eventStartTime").value;
      const endInputValue = document.getElementById("eventEndTime").value;
      const eventDetails = {
        title: document.getElementById("eventTitle").value,
        type: document.getElementById("eventType").value,
        description: document.getElementById("eventDescription").value,
        location: document.getElementById("eventLocation").value,
        date: isRecurring
          ? null
          : (eventTypeSelect?.value === "on-leave" ? (eventDateInput ? eventDateInput.value : '') : dateValue(startInputValue)),
        dayOfWeek: recurringDay,
        startDate: dateValue(startInputValue),
        endDate: dateValue(endInputValue),
        startMonth: isRecurring ? monthFromDate(dateValue(startInputValue)) : null,
        endMonth: isRecurring ? monthFromDate(dateValue(endInputValue)) : null,
        startTime: startInputValue,
        endTime: endInputValue,
      };

      if (isEditing && activeEventContext && activeEventContext.eventData && activeEventContext.eventData.id) {
        // update via API
        try {
          const payload = {
            title: eventDetails.title,
            description: eventDetails.description,
            location: eventDetails.location,
            event_type: eventDetails.type,
            date: eventDetails.date || null,
            day_of_week: eventDetails.dayOfWeek,
            start_month: eventDetails.startMonth || null,
            end_month: eventDetails.endMonth || null,
            start_date: eventDetails.startDate || null,
            end_date: eventDetails.endDate || null,
            start_time: timeValue(eventDetails.startTime),
            end_time: timeValue(eventDetails.endTime),
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

  // Refresh the schedule from Google Calendar on demand.
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

  // Open the event form and populate it with the selected event for editing.
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
    document.getElementById('eventLocation').value = eventData.location || '';
    let recurringStartDate = dateKey;
    let recurringEndDate = dateKey;
    if (eventData.isRecurring) {
      if (eventDateGroup) eventDateGroup.classList.add('hidden');
      if (eventDateInput) eventDateInput.required = false;
      if (eventDayGroup) eventDayGroup.classList.remove('hidden');
      if (eventDayInput) eventDayInput.value = eventData.dayOfWeek || '';
      const allocationYear = new Date().getFullYear();
      const endYear = eventData.endMonth < eventData.startMonth ? allocationYear + 1 : allocationYear;
      recurringStartDate = eventData.startMonth
        ? `${allocationYear}-${String(eventData.startMonth).padStart(2, '0')}-01`
        : dateKey;
      recurringEndDate = eventData.endMonth
        ? `${endYear}-${String(eventData.endMonth).padStart(2, '0')}-01`
        : dateKey;
    } else if (eventDayInput) {
      eventDayInput.value = '';
      if (eventDateGroup) eventDateGroup.classList.remove('hidden');
    }
    if (eventDateInput) eventDateInput.value = dateKey;

    if (eventData.type !== 'on-leave') {
      if (eventDateGroup) eventDateGroup.style.display = "none";
      if (eventDateInput) eventDateInput.required = false;
      timeInputsWrapper.style.display = "grid";
      startTimeInput.required = true;
      endTimeInput.required = true;
      document.getElementById('eventStartTime').value = `${recurringStartDate}T${eventData.startTime || '00:00'}`;
      document.getElementById('eventEndTime').value = `${recurringEndDate}T${eventData.endTime || '00:00'}`;
    } else {
      if (eventDateGroup) eventDateGroup.style.display = "block";
      if (eventDateInput) eventDateInput.required = true;
      timeInputsWrapper.style.display = "none";
      startTimeInput.required = false;
      endTimeInput.required = false;
    }
  }
});
