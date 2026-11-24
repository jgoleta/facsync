(() => {
  const form = document.querySelector('#headInviteModal form');
  if (!form) return;
  const toggle = form.elements.namedItem('include_faculty_access');
  const id = form.elements.namedItem('faculty_id');
  const home = form.elements.namedItem('faculty_department');
  const fields = document.getElementById('headFacultyFields');
  const college = document.getElementById('headFacultyCollege');
  const choices = [...home.options].filter(option => option.value).map(option => option.cloneNode(true));
  let autoSelected = false;
  function sync() {
    const enabled = toggle.checked;
    fields.hidden = !enabled;
    id.disabled = home.disabled = !enabled;
    id.required = home.required = enabled;
    const selected = new Set([...form.querySelectorAll('input[name=departments]:checked')].map(box => box.value));
    const previous = home.value;
    home.replaceChildren(new Option('Choose a Faculty department', ''));
    const allowed = choices.filter(option => selected.has(option.value));
    allowed.forEach(option => home.appendChild(option.cloneNode(true)));
    home.value = allowed.length === 1 ? allowed[0].value : !autoSelected && selected.has(previous) ? previous : '';
    autoSelected = allowed.length === 1;
    college.textContent = home.selectedOptions[0]?.dataset.college || 'Select a department';
  }
  form.addEventListener('management:open', event => {
    const data = event.detail.trigger.dataset;
    toggle.checked = data.includeFacultyAccess === 'true';
    id.value = data.facultyId || '';
    sync();
    if (data.facultyDepartment) home.value = data.facultyDepartment;
    autoSelected = home.options.length === 2;
    college.textContent = home.selectedOptions[0]?.dataset.college || 'Select a department';
  });
  form.addEventListener('change', sync);
  sync();
})();
