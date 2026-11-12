(() => {
  let processing = false;
  const confirmDialog = document.getElementById('managementConfirmDialog');
  const confirmMessage = document.getElementById('management-confirm-message');
  const confirmSubmit = confirmDialog?.querySelector('[data-confirm-submit]');
  let pendingConfirmation = null;
  function confirmManagementAction(message) {
    if (pendingConfirmation) return Promise.resolve(false);
    if (!confirmDialog || !confirmSubmit) return Promise.resolve(window.confirm(message));
    confirmMessage.textContent = message;
    confirmDialog.showModal();
    return new Promise(resolve => { pendingConfirmation = resolve; });
  }
  confirmDialog?.querySelectorAll('[data-confirm-cancel]').forEach(button => button.addEventListener('click', () => {
    confirmDialog.close(); pendingConfirmation?.(false); pendingConfirmation = null;
  }));
  confirmSubmit?.addEventListener('click', () => {
    confirmDialog.close(); pendingConfirmation?.(true); pendingConfirmation = null;
  });
  confirmDialog?.addEventListener('cancel', event => { event.preventDefault(); confirmDialog.close(); pendingConfirmation?.(false); pendingConfirmation = null; });
  document.querySelectorAll('form:not([data-managed-form])').forEach(form => form.addEventListener('submit', async event => {
    const message = event.submitter?.dataset.confirm;
    if (!message || form.dataset.confirmed === 'true') return;
    event.preventDefault();
    if (await confirmManagementAction(message)) { form.dataset.confirmed = 'true'; form.submit(); }
  }));
  const overlay = document.getElementById('managementLoading');
  const triggers = new WeakMap();
  function validateDepartments(form) {
    const boxes = [...form.querySelectorAll('input[type=checkbox][name=departments]')];
    if (boxes.length) boxes[0].setCustomValidity(boxes.some(box => box.checked) ? '' : 'Choose at least one department.');
  }
  document.querySelectorAll('[data-department-options]').forEach(group => {
    group.addEventListener('change', () => validateDepartments(group.closest('form')));
  });
  function close(dialog) { if (!processing) { dialog.close(); triggers.get(dialog)?.focus(); } }
  function toast(message, error = false) {
    document.querySelector('.management-toast')?.remove();
    const item = document.createElement('div'); item.className = `management-toast${error ? ' error' : ''}`;
    item.setAttribute('role', error ? 'alert' : 'status'); item.textContent = message;
    document.body.appendChild(item); setTimeout(() => item.remove(), 5000);
  }
  try {
    const warning = sessionStorage.getItem('managementDeliveryWarning');
    if (warning) { sessionStorage.removeItem('managementDeliveryWarning'); toast(warning, true); }
  } catch (_) { /* Feedback still works when browser storage is unavailable. */ }
  document.querySelectorAll('[data-open-modal]').forEach(button => button.addEventListener('click', () => {
    if (processing) return;
    const dialog = document.getElementById(button.dataset.openModal), form = dialog?.querySelector('form');
    if (!dialog || !form) return;
    form.reset(); dialog.dataset.dirty = 'false'; form.dataset.historyCount = button.dataset.historyCount || '0'; form.dataset.initialStatus = button.dataset.accountStatus || '';
    const error = form.querySelector('[data-form-error]'); if (error) error.hidden = true;
    form.setAttribute('action', button.dataset.editUrl || form.dataset.createUrl || form.getAttribute('action'));
    for (const field of ['name','code','college','description','email','title','account_status','unit']) {
      const input = form.elements.namedItem(field);
      if (input && button.dataset[field === 'account_status' ? 'accountStatus' : field] !== undefined)
        input.value = button.dataset[field === 'account_status' ? 'accountStatus' : field];
      if (field === 'code' && input) input.disabled = !!button.dataset.editUrl;
    }
    const selected = new Set((button.dataset.departments || '').split(','));
    const select = form.querySelector('select[name=departments]');
    if (select) [...select.options].forEach(option => option.selected = selected.has(option.value));
    form.querySelectorAll('input[type=checkbox][name=departments]').forEach(box => box.checked = selected.has(box.value));
    if (button.dataset.permissions !== undefined) {
      const permissions = new Set(button.dataset.permissions.split(','));
      form.querySelectorAll('input[type=checkbox][name=permissions]').forEach(box => box.checked = permissions.has(box.value));
    }
    validateDepartments(form);
    const title = dialog.querySelector('[data-modal-title]');
    if (title) title.textContent = button.dataset.editUrl ? title.dataset.editTitle : title.dataset.createTitle;
    triggers.set(dialog, button); dialog.showModal();
    (dialog.querySelector('form input:not([type=hidden]):not(:disabled), form select:not(:disabled), form textarea:not(:disabled)') || dialog.querySelector('button'))?.focus();
  }));
  document.querySelectorAll('dialog.management-dialog').forEach(dialog => {
    dialog.addEventListener('input', () => dialog.dataset.dirty = 'true');
    dialog.addEventListener('change', () => dialog.dataset.dirty = 'true');
    dialog.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', () => close(dialog)));
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(dialog); });
    dialog.addEventListener('click', event => {
      const box = dialog.getBoundingClientRect();
      if (event.target === dialog && dialog.dataset.dirty !== 'true' &&
          (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) close(dialog);
    });
  });
  document.querySelectorAll('form[data-managed-form]').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault(); if (processing) return;
    const domainField = form.querySelector('[name="domain"]');
    if (form.classList.contains('school-details-form') && domainField
        && domainField.value.trim().toLowerCase() !== (form.dataset.currentDomain || '').trim().toLowerCase()
        && !window.confirm('Replace your school’s email domain? New students using the old domain will no longer be able to register under this school. Existing accounts keep their school and sign-in access while active.')) return;
    if (form.elements.namedItem('account_status')?.value === 'deactivated' && form.dataset.initialStatus === 'active'
        && !window.confirm(`${form.dataset.historyCount} consultation record(s) will be preserved. Login and booking access will be removed. Deactivate this account?`)) return;
    const confirmation = event.submitter?.dataset.confirm;
    if (confirmation && !(await confirmManagementAction(confirmation))) return;
    const data = new FormData(form); // Capture before disabling controls, including action.
    const enabled = [...form.elements].filter(input => !input.disabled);
    const dialog = form.closest('dialog'), error = form.querySelector('[data-form-error]');
    if (error) error.hidden = true;
    processing = true; enabled.forEach(input => input.disabled = true); form.setAttribute('aria-busy','true');
    if (overlay) { (dialog || document.body).appendChild(overlay); overlay.classList.add('show'); overlay.setAttribute('aria-hidden','false'); }
    let succeeded = false;
    try {
      const response = await fetch(form.getAttribute('action'), { method:'POST', credentials:'same-origin',
        headers:{'X-CSRFToken':data.get('csrfmiddlewaretoken'), 'X-Requested-With':'XMLHttpRequest'}, body:data });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.success) throw new Error(result.error || 'Unable to save. Your session may have expired; sign in again if needed.');
      succeeded = true; toast(result.message || 'Changes saved.', result.email_sent === false);
      if (result.email_sent === false) {
        try { sessionStorage.setItem('managementDeliveryWarning', result.message); } catch (_) { /* Keep the visible toast. */ }
      }
      setTimeout(() => window.location.reload(), 800);
    } catch (failure) {
      const message = failure instanceof TypeError ? 'The connection was interrupted. Check the list before retrying; the change may have been saved.' : failure.message;
      if (error) { error.textContent = message; error.hidden = false; } else toast(message, true);
    } finally {
      if (!succeeded) { processing = false; enabled.forEach(input => input.disabled = false); form.removeAttribute('aria-busy'); overlay?.classList.remove('show'); overlay?.setAttribute('aria-hidden','true'); }
    }
  }));
  document.querySelectorAll('[data-directory-filter]').forEach(filter => filter.addEventListener('change', () => {
    document.querySelectorAll('[data-department-ids]').forEach(row => row.hidden = filter.value !== 'all' && !row.dataset.departmentIds.split(',').includes(filter.value));
    document.querySelectorAll('[data-filter-empty]').forEach(row => {
      row.hidden = [...row.closest('tbody').querySelectorAll('[data-department-ids]')].some(item => !item.hidden);
    });
  }));
  document.querySelectorAll('[data-faculty-filter]').forEach(filter => filter.addEventListener('change', () => {
    const unit = document.querySelector('[data-faculty-filter=unit]').value;
    const college = document.querySelector('[data-faculty-filter=college]')?.value || 'all';
    const rows = [...document.querySelectorAll('[data-faculty-row]')];
    rows.forEach(row => row.hidden = (unit !== 'all' && row.dataset.unit !== unit) || (college !== 'all' && row.dataset.college !== college));
    const empty = document.querySelector('[data-faculty-empty]');
    if (empty) empty.hidden = rows.some(row => !row.hidden);
  }));
})();
