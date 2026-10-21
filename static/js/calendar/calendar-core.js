(function (window) {
  "use strict";

  const weekdayIndexes = {
    sunday: 0,
    monday: 1,
    tuesday: 2,
    wednesday: 3,
    thursday: 4,
    friday: 5,
    saturday: 6,
  };

  // Converts a date/time value into the calendar's five-character HH:MM format.
  function timeValue(value) {
    if (!value) return null;
    return String(value).split("T").pop().slice(0, 5);
  }

  // Formats a 24-hour time value as a user-friendly 12-hour time with AM/PM.
  function formatTime(value) {
    if (!value) return "";
    const [hourValue, minuteValue] = String(value).split(":").map(Number);
    if (Number.isNaN(hourValue) || Number.isNaN(minuteValue)) return value;
    const period = hourValue >= 12 ? "PM" : "AM";
    const hour = hourValue % 12 || 12;
    return `${hour}:${String(minuteValue).padStart(2, "0")} ${period}`;
  }

  // Maps an API event into the consistent shape used by the calendar UI.
  function normalizeEvent(event) {
    return {
      id: event.id,
      requestId: event.request_id || null,
      title: event.title,
      description: event.description,
      location: event.location || "",
      status: event.status || event.event_type,
      type: event.event_type,
      isRecurring: Boolean(event.is_recurring),
      isConsultation: Boolean(event.is_consultation),
      dayOfWeek: event.day_of_week === "none" ? "" : (event.day_of_week || ""),
      startMonth: event.start_month,
      endMonth: event.end_month,
      startDate: event.recurrence_start_date || null,
      endDate: event.recurrence_end_date || null,
      excludedDates: Array.isArray(event.recurrence_excluded_dates) ? event.recurrence_excluded_dates : [],
      startTime: timeValue(event.start_time),
      endTime: timeValue(event.end_time),
    };
  }

  // Creates a local YYYY-MM-DD key without introducing UTC date shifts.
  function localDateKey(value) {
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
  }

  // Checks whether a month falls within a normal or year-spanning month range.
  function monthIsIncluded(month, startMonth, endMonth) {
    if (!startMonth || !endMonth) return true;
    if (startMonth <= endMonth) return month >= startMonth && month <= endMonth;
    return month >= startMonth || month <= endMonth;
  }

  // Generates the visible date keys for a recurring event around the reference month.
  function recurringDateKeys(
    dayOfWeek,
    startMonth,
    endMonth,
    startDate = null,
    endDate = null,
    excludedDates = [],
    referenceDate = new Date(),
  ) {
    const first = new Date(referenceDate.getFullYear(), referenceDate.getMonth(), 1 - 7);
    const last = new Date(referenceDate.getFullYear(), referenceDate.getMonth() + 1, 7);
    const target = dayOfWeek ? weekdayIndexes[dayOfWeek] : null;
    const dates = [];
    for (let cursor = new Date(first); cursor <= last; cursor.setDate(cursor.getDate() + 1)) {
      const dateKey = localDateKey(cursor);
      if (monthIsIncluded(cursor.getMonth() + 1, startMonth, endMonth)
        && (!startDate || dateKey >= startDate)
        && (!endDate || dateKey <= endDate)
        && !excludedDates.includes(dateKey)
        && (target === null || cursor.getDay() === target)) {
        dates.push(dateKey);
      }
    }
    return dates;
  }

  // Returns either the recurring occurrence dates or the date of a one-time event.
  function eventDateKeys(event, referenceDate) {
    if (event.isRecurring) {
      return recurringDateKeys(
        event.dayOfWeek,
        event.startMonth,
        event.endMonth,
        event.startDate,
        event.endDate,
        event.excludedDates,
        referenceDate,
      );
    }
    return event.date ? [String(event.date).split("T")[0]] : [];
  }

  // Groups events by date, sorts events within each date, and sorts the date groups.
  function buildSchedule(events, referenceDate = new Date()) {
    const byDate = {};
    (events || []).forEach((rawEvent) => {
      const event = normalizeEvent(rawEvent);
      eventDateKeys({ ...event, date: rawEvent.date }, referenceDate).forEach((dateKey) => {
        if (!byDate[dateKey]) byDate[dateKey] = { date: dateKey, events: [] };
        byDate[dateKey].events.push(event);
      });
    });

    return Object.values(byDate)
      .map((entry) => ({
        ...entry,
        events: entry.events.sort((a, b) => (a.startTime || "").localeCompare(b.startTime || "")),
      }))
      .sort((a, b) => new Date(a.date) - new Date(b.date));
  }

  // Builds accessible text describing an event's title, date, and time.
  function activityLabel(event, monthName, day) {
    const time = event.startTime && event.endTime
      ? `${formatTime(event.startTime)} - ${formatTime(event.endTime)}`
      : formatTime(event.startTime || event.endTime) || "All day";
    return `${event.title} • ${monthName} ${day} • ${time}`;
  }

  window.FacSyncCalendar = Object.freeze({
    activityLabel,
    buildSchedule,
    formatTime,
    normalizeEvent,
  });
}(window));
