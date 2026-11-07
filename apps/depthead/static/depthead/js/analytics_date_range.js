/* Date selection only; the existing GET forms still apply the report filters. */
(() => {
  'use strict';
  if (typeof HTMLDialogElement === 'undefined' || !HTMLDialogElement.prototype.showModal) return;
  const dateKey = date => `${String(date.getFullYear()).padStart(4, '0')}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  const parseDate = value => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const [year, month, day] = value.split('-').map(Number);
    const result = new Date(0);
    result.setHours(12, 0, 0, 0);
    result.setFullYear(year, month - 1, day);
    return dateKey(result) === value ? result : null;
  };
  const monthLabel = date => date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  const dayLabel = date => date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

  document.querySelectorAll('[data-date-range]').forEach(root => {
    const trigger = root.querySelector('[data-date-open]');
    const panel = root.querySelector('[data-date-panel]');
    const form = panel.querySelector('form');
    const fields = [...form.querySelectorAll('input[type="date"]')];
    if (fields.length !== 2) return;
    const [start, end] = fields;
    const dialog = document.createElement('dialog');
    dialog.className = 'analytics-date-dialog';
    dialog.setAttribute('aria-labelledby', panel.querySelector('h2').id);
    dialog.append(panel);
    root.append(dialog);
    trigger.hidden = false;
    panel.querySelectorAll('[data-date-cancel], [data-range-calendar]').forEach(node => { node.hidden = false; });
    const days = panel.querySelector('[data-calendar-days]');
    const hint = panel.querySelector('[data-range-hint]');
    let month, selectingEnd = false, snapshot;

    function render() {
      panel.querySelector('[data-month-title]').textContent = monthLabel(month);
      days.setAttribute('aria-label', monthLabel(month));
      const fragment = document.createDocumentFragment();
      const first = new Date(month); first.setDate(1);
      for (let i = 0; i < first.getDay(); i++) {
        const blank = document.createElement('span'); blank.setAttribute('aria-hidden', 'true'); fragment.append(blank);
      }
      for (let date = new Date(first); date.getMonth() === first.getMonth(); date.setDate(date.getDate() + 1)) {
        const value = dateKey(date);
        const button = document.createElement('button');
        button.type = 'button'; button.dataset.date = value;
        button.textContent = date.getDate(); button.setAttribute('aria-label', dayLabel(date));
        const endpoint = value === start.value || value === end.value;
        button.setAttribute('aria-pressed', String(endpoint));
        button.classList.toggle('is-range-edge', endpoint);
        button.classList.toggle('is-in-range', Boolean(start.value && end.value && value > start.value && value < end.value));
        if (value === dateKey(new Date())) button.setAttribute('aria-current', 'date');
        if (end.max && value > end.max) button.disabled = true;
        fragment.append(button);
      }
      days.replaceChildren(fragment);
      panel.querySelector('[data-month-step="-1"]').disabled = month.getFullYear() === 1 && month.getMonth() === 0;
      panel.querySelector('[data-month-step="1"]').disabled = month.getFullYear() === 9999 && month.getMonth() === 11;
      hint.textContent = selectingEnd ? 'Now choose an end date.' : start.value && end.value
        ? `${start.value} to ${end.value}. Choose a date to start a new range.` : 'Choose a start date.';
    }

    function open() {
      snapshot = fields.map(field => field.value);
      month = parseDate(start.value) || new Date(); month.setDate(1);
      selectingEnd = Boolean(start.value && !end.value);
      render(); dialog.showModal();
      (days.querySelector('[aria-pressed="true"]') || days.querySelector('button'))?.focus();
    }
    trigger.addEventListener('click', open);
    panel.querySelectorAll('[data-date-cancel]').forEach(button => button.addEventListener('click', () => dialog.close()));
    dialog.addEventListener('close', () => {
      fields.forEach((field, i) => { field.value = snapshot[i]; });
      trigger.focus();
    });
    dialog.addEventListener('click', event => {
      const rect = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
    });
    panel.querySelectorAll('[data-month-step]').forEach(button => button.addEventListener('click', () => {
      month.setMonth(month.getMonth() + Number(button.dataset.monthStep)); render();
    }));
    days.addEventListener('click', event => {
      const button = event.target.closest('[data-date]');
      if (!button) return;
      const value = button.dataset.date;
      if (!selectingEnd) { start.value = value; end.value = ''; selectingEnd = true; }
      else {
        const ordered = [start.value, value].sort();
        [start.value, end.value] = ordered; selectingEnd = false;
      }
      render(); days.querySelector(`[data-date="${value}"]`)?.focus();
    });
    days.addEventListener('keydown', event => {
      const steps = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
      if (!steps[event.key] || !event.target.dataset.date) return;
      event.preventDefault();
      const date = parseDate(event.target.dataset.date); date.setDate(date.getDate() + steps[event.key]);
      if (date.getFullYear() < 1 || date.getFullYear() > 9999) return;
      month = new Date(date); month.setDate(1); render();
      days.querySelector(`[data-date="${dateKey(date)}"]`)?.focus();
    });
    fields.forEach(field => field.addEventListener('change', () => {
      const date = parseDate(field.value);
      if (date) { month = date; month.setDate(1); }
      selectingEnd = Boolean(start.value && !end.value); render();
    }));
    if (form.hasAttribute('data-date-errors')) open();
  });
})();
