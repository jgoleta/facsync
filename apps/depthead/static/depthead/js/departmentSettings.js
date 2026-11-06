(() => {
  const source = document.getElementById('department-settings-data');
  const layout = document.querySelector('[data-settings-key]');
  if (!source || !layout) return;
  const departments = JSON.parse(source.textContent);
  document.querySelectorAll('form[data-department-editor]').forEach(form => {
    const select = form.elements.namedItem('department_id');
    const kind = form.dataset.departmentEditor;
    const fields = kind === 'description' ? ['description'] : ['is_closed', 'reason', 'closure_start', 'closure_end'];
    const drafts = new Map();
    const key = `facsync:department-settings:${layout.dataset.settingsKey}:${kind}`;
    let current = select.value;
    function read() {
      return Object.fromEntries(fields.map(name => {
        const input = form.elements.namedItem(name);
        return [name, input.type === 'checkbox' ? input.checked : input.value];
      }));
    }
    function load(id) {
      const saved = departments[id];
      if (!saved) return;
      const values = drafts.get(id) || saved;
      fields.forEach(name => {
        const input = form.elements.namedItem(name);
        if (input.type === 'checkbox') input.checked = !!values[name];
        else input.value = values[name] || '';
      });
      const label = form.querySelector('[data-department-college]');
      if (label) label.textContent = saved.college;
      const status = form.closest('.settings-card').querySelector('[data-department-status]');
      if (status) status.textContent = `Currently ${saved.is_closed ? 'closed' : 'open'} for new bookings.`;
      const error = form.querySelector('[data-form-error]');
      if (error) { error.hidden = true; error.textContent = ''; }
      current = id;
      try { sessionStorage.setItem(key, id); } catch (_) { /* Storage may be unavailable. */ }
    }
    try {
      const previous = sessionStorage.getItem(key);
      if ([...select.options].some(option => option.value === previous)) select.value = previous;
    } catch (_) { /* Keep the server-selected department. */ }
    load(select.value);
    select.addEventListener('change', () => {
      drafts.set(current, read());
      load(select.value);
    });
  });
})();
