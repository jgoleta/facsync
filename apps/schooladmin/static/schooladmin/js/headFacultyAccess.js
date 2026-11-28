(() => {
  const form = document.querySelector('#headInviteModal form');
  if (!form) return;
  const toggle = form.elements.namedItem('include_faculty_access');
  const home = form.elements.namedItem('faculty_department');
  const fields = document.getElementById('headFacultyFields');
  const choices = [...home.options].filter(option => option.value).map(option => option.cloneNode(true));
  let autoSelected = false;
  function sync() {
    const enabled = toggle.checked;
    const departmentSelect = form.elements.namedItem('departments');
    const selected = new Set([...departmentSelect.selectedOptions].map(option => option.value));
    const previous = home.value;
    home.replaceChildren(new Option('Choose a Faculty department', ''));
    const allowed = choices.filter(option => selected.has(option.value));
    allowed.forEach(option => home.appendChild(option.cloneNode(true)));
    home.value = allowed.length === 1 ? allowed[0].value : !autoSelected && selected.has(previous) ? previous : '';
    autoSelected = allowed.length === 1;
    fields.hidden = !enabled || allowed.length <= 1;
    home.disabled = !enabled || allowed.length <= 1;
    home.required = enabled && allowed.length > 1;
  }
  form.addEventListener('management:open', event => {
    const data = event.detail.trigger.dataset;
    toggle.checked = data.includeFacultyAccess === 'true';
    sync();
    if (data.facultyDepartment) home.value = data.facultyDepartment;
    autoSelected = home.options.length === 2;
  });
  form.addEventListener('change', sync);
  sync();
})();
