(() => {
  const form = document.getElementById('consultationForm');
  const dateInput = document.getElementById('dateSelect');
  const timeInput = document.getElementById('timeSelect');
  if (!form || !dateInput || !timeInput) return;

  const formatter = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  });

  function validateAppointment() {
    const parts = Object.fromEntries(formatter.formatToParts(new Date()).map(part => [part.type, part.value]));
    const today = `${parts.year}-${parts.month}-${parts.day}`;
    dateInput.min = today;
    dateInput.setCustomValidity('');
    timeInput.setCustomValidity('');
    if (!dateInput.value || !timeInput.value) return;

    if (dateInput.value < today || (dateInput.value === today && `${timeInput.value}:00` <= `${parts.hour}:${parts.minute}:${parts.second}`)) {
      dateInput.setCustomValidity('Choose a future consultation date and time.');
    } else if (new Date(`${dateInput.value}T12:00:00Z`).getUTCDay() === 0) {
      dateInput.setCustomValidity('Choose a consultation date from Monday to Saturday.');
    }
    if (timeInput.value < '09:00' || timeInput.value > '17:00') {
      timeInput.setCustomValidity('Choose a start time between 9 AM and 5 PM (Philippine time).');
    }
  }

  form.addEventListener('input', validateAppointment);
  form.addEventListener('change', validateAppointment);
  form.addEventListener('focusin', validateAppointment);
  document.getElementById('book-consultation-btn')?.addEventListener('click', validateAppointment);
  form.addEventListener('submit', event => {
    validateAppointment();
    if (!form.reportValidity()) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  validateAppointment();
})();
