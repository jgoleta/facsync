let activeCollegeConfirmation = null;

window.closeCollegeConfirmation = function () {
  if (!activeCollegeConfirmation) return;
  const current = activeCollegeConfirmation;
  activeCollegeConfirmation = null;
  current.cleanup();
};

window.confirmCollegeAction = function (title, message) {
  if (activeCollegeConfirmation) return Promise.resolve(false);
  const overlay = document.getElementById('settings-confirm');
  const save = document.getElementById('settings-confirm-save');
  const cancel = document.getElementById('settings-confirm-cancel');
  const previousFocus = document.activeElement;
  document.getElementById('settings-confirm-title').textContent = title;
  document.getElementById('settings-confirm-message').textContent = message;
  save.disabled = false;
  return new Promise(resolve => {
    let decided = false;
    function dismiss() {
      closeCollegeConfirmation();
      if (!decided) { decided = true; resolve(false); }
    }
    function confirm() {
      if (decided) return;
      decided = true;
      save.disabled = true;
      resolve(true);
    }
    function backdrop(event) {
      if (event.target === overlay) dismiss();
    }
    function keydown(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        dismiss();
      } else if (event.key === 'Tab') {
        event.preventDefault();
        const next = document.activeElement === cancel && !save.disabled ? save : cancel;
        next.focus();
      }
    }
    activeCollegeConfirmation = {
      cleanup() {
        overlay.classList.add('hidden');
        save.removeEventListener('click', confirm);
        cancel.removeEventListener('click', dismiss);
        overlay.removeEventListener('click', backdrop);
        overlay.removeEventListener('keydown', keydown);
        previousFocus?.focus();
      },
    };
    save.addEventListener('click', confirm);
    cancel.addEventListener('click', dismiss);
    overlay.addEventListener('click', backdrop);
    overlay.addEventListener('keydown', keydown);
    overlay.classList.remove('hidden');
    cancel.focus();
  });
};

window.closureConfirmationMessage = function (wasClosed, willClose, college) {
  if (!wasClosed && willClose) return `This will close ${college} for new consultation requests. Faculty will be notified by email. You can update the closure details or reopen the college later.`;
  if (wasClosed && !willClose) return `This will reopen ${college} for new consultation requests.`;
  return "This will update your college?s closure details.";
};

window.announcementConfirmationMessage = function (audience, college) {
  return {
    faculty: `This will notify all active faculty in ${college}. Faculty with an email address will also receive an email.`,
    students: `This will notify all active students in ${college}.`,
    both: `This will notify all active students and faculty in ${college}. Faculty with an email address will also receive an email.`,
  }[audience];
};

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('closure-form');
  if (!form) return;
  const badge = document.getElementById('closure-status');
  let inFlight = null;
  let saving = false;
  function updateBadge(closed) {
    badge.textContent = closed ? 'Closed' : 'Open';
    badge.className = `closure-badge ${closed ? 'closed' : 'open'}`;
  }
  function readState() {
    if (inFlight) return inFlight;
    inFlight = (async () => {
      try {
        const response = await fetch(form.dataset.statusUrl, {cache: 'no-store'});
        if (!response.ok) throw new Error('Status unavailable');
        const data = await response.json();
        if (typeof data.is_closed !== 'boolean') throw new Error('Invalid status');
        updateBadge(data.is_closed);
        return data.is_closed;
      } catch (error) {
        badge.textContent = 'Status unavailable';
        badge.className = 'closure-badge unavailable';
        throw error;
      } finally { inFlight = null; }
    })();
    return inFlight;
  }
  readState().catch(() => {});
  window.setInterval(() => { if (!saving && !document.hidden) readState().catch(() => {}); }, 10000);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (saving) return;
    saving = true;
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    const payload = new FormData(form);
    const overlay = document.getElementById('loadingOverlay');
    let confirmed = false;
    try {
      let current;
      try {
        if (inFlight) await inFlight.catch(() => {});
        current = await readState();
      } catch (error) {
        showToast('Unable to check the current closure status. Please try again.', true);
        return;
      }
      confirmed = await confirmCollegeAction('Save Closure Settings?', closureConfirmationMessage(current, payload.has('is_closed'), form.dataset.college));
      if (!confirmed) return;
      overlay?.classList.add('show');
      const response = await fetch(form.action || window.location.href, {
        method: 'POST', headers: {'X-CSRFToken': payload.get('csrfmiddlewaretoken')}, body: payload,
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || 'Unable to save closure settings.');
      updateBadge(data.is_closed);
      showToast('Office closure settings updated.');
    } catch (error) {
      showToast(error.message || 'Something went wrong saving closure settings.', true);
    } finally {
      if (confirmed) closeCollegeConfirmation();
      saving = false;
      button.disabled = false;
      overlay?.classList.remove('show');
    }
  });
});
