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

  function timeValue(value) {
    if (!value) return null;
    return String(value).split("T").pop().slice(0, 5);
  }

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
      startTime: timeValue(event.start_time),
      endTime: timeValue(event.end_time),
    };
  }

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
        && (target === null || cursor.getDay() === target)) {
        dates.push(localDateKey(cursor));
      }
    }
    return dates;
  }

  function eventDateKeys(event) {
    if (event.isRecurring) {
      return recurringDateKeys(event.dayOfWeek, event.startMonth, event.endMonth);
    }
    return event.date ? [String(event.date).split("T")[0]] : [];
  }

  function buildSchedule(events) {
    const byDate = {};
    (events || []).forEach((rawEvent) => {
      const event = normalizeEvent(rawEvent);
      eventDateKeys({ ...event, date: rawEvent.date }).forEach((dateKey) => {
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

  function activityLabel(event, monthName, day) {
    const time = event.startTime && event.endTime
      ? `${event.startTime} - ${event.endTime}`
      : event.startTime || event.endTime || "All day";
    return `${event.title} • ${monthName} ${day} • ${time}`;
  }

  window.FacSyncCalendar = Object.freeze({
    activityLabel,
    buildSchedule,
    normalizeEvent,
  });
}(window));
