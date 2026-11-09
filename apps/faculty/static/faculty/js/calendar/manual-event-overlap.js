/* Safe text-only warnings; confirmation retries the exact original edit. */
(() => {
  'use strict';
  function confirmOverlap(warning) {
    return new Promise(resolve => {
      const previous = document.activeElement;
      const dialog = document.createElement('dialog');
      dialog.className = 'schedule-overlap-dialog';
      dialog.setAttribute('aria-labelledby', 'schedule-overlap-title');
      const title = document.createElement('h2'); title.id = 'schedule-overlap-title';
      title.textContent = 'This time overlaps another event';
      const explanation = document.createElement('p');
      explanation.textContent = 'Nothing has been saved yet. Review these commitments. Go back to change the time, or save the overlap intentionally.';
      const list = document.createElement('ul');
      const format = value => new Date(value).toLocaleString('en-PH', {
        timeZone: 'Asia/Manila', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
      });
      for (const conflict of warning.conflicts || []) {
        const item = document.createElement('li');
        const name = document.createElement('strong'); name.textContent = conflict.title;
        const time = document.createElement('p'); time.textContent = `${format(conflict.start)} – ${format(conflict.end)} (Philippine time)`;
        const source = document.createElement('small'); source.textContent = conflict.source;
        item.append(name, time, source); list.append(item);
      }
      const count = document.createElement('p');
      if (warning.conflict_count > (warning.conflicts || []).length) count.textContent = `Showing the first ${warning.conflicts.length} of ${warning.conflict_count} overlaps.`;
      const actions = document.createElement('div'); actions.className = 'schedule-overlap-actions';
      const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'btn-secondary'; cancel.textContent = 'Go back';
      const save = document.createElement('button'); save.type = 'button'; save.className = 'btn-primary'; save.textContent = 'Save anyway';
      actions.append(cancel, save); dialog.append(title, explanation, list, count, actions);
      let accepted = false;
      cancel.addEventListener('click', () => dialog.close());
      save.addEventListener('click', () => { accepted = true; dialog.close(); });
      dialog.addEventListener('close', () => { dialog.remove(); previous?.focus(); resolve(accepted); }, { once: true });
      dialog.addEventListener('click', event => {
        const rect = dialog.getBoundingClientRect();
        if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
      });
      document.body.append(dialog); dialog.showModal(); cancel.focus();
    });
  }
  async function request(url, options, callbacks = {}) {
    let body = JSON.parse(options.body);
    while (true) {
      const response = await fetch(url, { ...options, body: JSON.stringify(body) });
      if (response.status !== 409) return response;
      const warning = await response.clone().json().catch(() => ({}));
      if (warning.code !== 'schedule_overlap') return response;
      callbacks.pause?.();
      if (!(await confirmOverlap(warning))) {
        const error = new Error('Saving cancelled. Choose another time if needed.');
        error.name = 'ScheduleOverlapCancelled'; throw error;
      }
      callbacks.resume?.();
      body = { ...body, overlap_confirmation: warning.overlap_confirmation };
    }
  }
  window.FacSyncManualOverlap = Object.freeze({ request });
})();
