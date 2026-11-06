(() => {
  const form = document.getElementById('student-profile-form');
  if (!form) return;
  const level = form.elements.namedItem('educational_level');
  const year = form.elements.namedItem('year_level');
  const department = form.elements.namedItem('department');
  const choices = JSON.parse(document.getElementById('student-year-choices').textContent);
  const colleges = JSON.parse(document.getElementById('student-department-colleges').textContent);
  function collegeLabel() {
    document.getElementById('student-college-label').textContent = department.value ? `College: ${colleges[department.value] || 'No college'}` : '';
  }
  function update(rebuild) {
    if (rebuild) {
      year.replaceChildren(new Option('Select your grade / year', ''), ...(choices[level.value] || []).map(([value, label]) => new Option(label, value)));
      year.value = '';
    }
    const college = level.value === 'college';
    document.getElementById('grade-year-label').textContent = college ? 'Year level' : 'Grade level';
    document.getElementById('student-department-group').hidden = !college;
    department.disabled = !college;
    department.required = college;
    if (!college) department.value = '';
    collegeLabel();
  }
  level.addEventListener('change', () => update(true));
  department.addEventListener('change', collegeLabel);
  update(false);
  form.addEventListener('submit', event => {
    if (form.dataset.processing === 'true') { event.preventDefault(); return; }
    form.dataset.processing = 'true';
    const button = form.querySelector('button[type=submit]');
    button.disabled = true; button.textContent = 'Saving profile…';
    form.setAttribute('aria-busy', 'true');
  });
  window.addEventListener('pageshow', event => {
    if (event.persisted) {
      form.dataset.processing = 'false'; form.removeAttribute('aria-busy');
      const button = form.querySelector('button[type=submit]'); button.disabled = false; button.textContent = 'Continue to Dashboard';
    }
  });
})();
