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
  function userFacingError(message) {
    if (['college_school_code_unique', 'college_school_name_unique'].some(constraint => message.includes(constraint)))
      return 'This College already exist';
    if (['department_school_code_unique', 'department_school_name_unique'].some(constraint => message.includes(constraint)))
      return 'This Department already exist';
    return message;
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
    for (const field of ['name','code','college','description','email','title','account_status','unit','department']) {
      const input = form.elements.namedItem(field);
      const dataKey = field === 'account_status' ? 'accountStatus' : field;
      if (input && button.dataset[dataKey] !== undefined) input.value = button.dataset[dataKey];
      if (field === 'code' && input) input.disabled = !!button.dataset.editUrl;
    }
    const selected = new Set((button.dataset.departments || '').split(','));
    const select = form.querySelector('select[name=departments]');
    if (select) {
      if (select.hasAttribute('data-educational-department')) select.multiple = true;
      [...select.options].forEach(option => option.selected = selected.has(option.value));
    }
    form.querySelectorAll('input[type=checkbox][name=departments]').forEach(box => box.checked = selected.has(box.value));
    if (button.dataset.permissions !== undefined) {
      const permissions = new Set(button.dataset.permissions.split(','));
      form.querySelectorAll('input[type=checkbox][name=permissions]').forEach(box => box.checked = permissions.has(box.value));
    }
    if (button.dataset.studentLevels !== undefined) {
      const levels = new Set(button.dataset.studentLevels.split(','));
      const levelSelect = form.querySelector('select[name=student_levels]');
      if (levelSelect) levelSelect.value = [...levels][0] || '';
      form.querySelectorAll('input[type=checkbox][name=student_levels]').forEach(box => box.checked = levels.has(box.value));
    }
    form.dispatchEvent(new CustomEvent('management:open', { detail: { trigger: button } }));
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
      succeeded = true; toast(result.message || 'Changes saved.', result.email_sent === false || form.dataset.toastDanger === 'true');
      if (result.email_sent === false) {
        try { sessionStorage.setItem('managementDeliveryWarning', result.message); } catch (_) { /* Keep the visible toast. */ }
      }
      setTimeout(() => window.location.reload(), 800);
    } catch (failure) {
      const message = userFacingError(failure instanceof TypeError ? 'The connection was interrupted. Check the list before retrying; the change may have been saved.' : failure.message);
      if (error && form.dataset.toastErrors !== 'true') { error.textContent = message; error.hidden = false; } else toast(message, true);
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

  const inviteOptions = new WeakMap();
  function filterFacultyInviteUnits(form, selectedValue) {
    const level = form?.elements.namedItem('educational_level');
    const unit = form?.elements.namedItem('unit');
    if (!level || !unit) return;
    const previous = selectedValue ?? unit.value;
    const matching = inviteOptions.get(form).filter(option =>
      level.value && (option.dataset.educationalLevels || '').split(',').includes(level.value));
    unit.replaceChildren(new Option(matching.length ? 'Select a department or office' :
      (level.value ? 'No matching departments or offices' : 'Select an educational level or office first'), ''),
      ...matching.map(option => option.cloneNode(true)));
    unit.value = matching.some(option => option.value === previous) ? previous : '';
  }

  document.querySelectorAll('#facultyInviteModal form').forEach(form => {
    const level = form.elements.namedItem('educational_level');
    const unit = form.elements.namedItem('unit');
    inviteOptions.set(form, [...unit.options].filter(option => option.value).map(option => option.cloneNode(true)));
    level?.addEventListener('change', () => filterFacultyInviteUnits(form));
    form.addEventListener('management:open', event => {
      const selectedValue = event.detail.trigger.dataset.unit || '';
      const selected = inviteOptions.get(form).find(option => option.value === selectedValue);
      const availableLevels = selected?.dataset.educationalLevels?.split(',') || [];
      const allowed = [...level.options].find(option => option.value && availableLevels.includes(option.value));
      if (allowed) {
        level.value = allowed.value;
      } else if (!level.value) {
        const firstLevel = [...level.options].find(option => option.value && option.value !== 'office');
        if (firstLevel) level.value = firstLevel.value;
      }
      filterFacultyInviteUnits(form, selectedValue);
    });
    filterFacultyInviteUnits(form);
  });

  document.querySelectorAll('[data-educational-level-filter]').forEach(level => {
    const form = level.closest('form');
    const department = form?.elements.namedItem('departments');
    const title = form?.elements.namedItem('title');
    if (!department) return;
    const options = [...department.options].map(option => option.cloneNode(true));
    const group = department.closest('.modal-form-group');
    const college = form.elements.namedItem('assigned_college');
    const collegeGroup = form.querySelector('[data-head-college-group]');
    function filterDepartments(preferredLevel) {
      const selected = preferredLevel || level.value;
      if (title) {
        const collegeHead = [...title.options].find(option => option.value === 'dean');
        if (collegeHead) {
          collegeHead.hidden = selected !== 'college';
          collegeHead.style.display = collegeHead.hidden ? 'none' : '';
          if (collegeHead.hidden && title.value === 'dean') title.value = 'chairperson';
        }
      }
      const selectedDepartments = new Set([...department.selectedOptions].map(option => option.value));
      const matching = options.filter(option => option.value && (title?.value === 'dean' || (option.dataset.educationalLevels || '').split(',').includes(selected)));
      const multiple = title?.value === 'dean';
      department.multiple = multiple;
      department.required = !multiple;
      department.replaceChildren(new Option('Choose a department', ''), ...matching.map(option => option.cloneNode(true)));
      [...department.options].forEach(option => option.selected = selectedDepartments.has(option.value));
      if (!multiple && selectedDepartments.size !== 1) department.value = '';
      group.hidden = multiple;
      group.style.display = multiple ? 'none' : '';
      collegeGroup.hidden = !multiple;
      college.disabled = !multiple;
      college.required = multiple;
      if (multiple) {
        [...department.options].forEach(option => {
          option.selected = !!college.value && option.dataset.college === college.value;
        });
      }
    }
    college.addEventListener('change', () => filterDepartments());
    level.addEventListener('change', () => filterDepartments());
    title?.addEventListener('change', () => filterDepartments());
    form.addEventListener('management:open', event => {
      const ids = new Set((event.detail.trigger.dataset.departments || '').split(','));
      department.multiple = true;
      department.replaceChildren(...options.map(option => option.cloneNode(true)));
      [...department.options].forEach(option => option.selected = ids.has(option.value));
      const selected = department.options[department.selectedIndex];
      const collegeIds = new Set([...department.selectedOptions].map(option => option.dataset.college).filter(Boolean));
      college.value = collegeIds.size === 1 ? [...collegeIds][0] : '';
      const served = selected?.dataset.educationalLevels?.split(',') || [];
      const available = [...level.options].map(option => option.value).filter(Boolean);
      level.value = served.find(item => available.includes(item)) || level.value || available[0] || '';
      if (title?.value === 'dean') level.value = 'college';
      filterDepartments();
    });
    filterDepartments();
  });

  document.querySelectorAll('#departmentModal form').forEach(form => {
    const level = form.elements.namedItem('student_levels');
    const college = form.elements.namedItem('college');
    if (!level || !college) return;
    const group = college.closest('.modal-form-group');
    function syncCollege() {
      const available = level.value === 'college';
      group.hidden = !available;
      group.style.display = available ? '' : 'none';
      college.disabled = !available;
      college.hidden = !available;
      if (!available) college.value = '';
    }
    level.addEventListener('change', syncCollege);
    form.addEventListener('management:open', syncCollege);
    syncCollege();
  });
})();
