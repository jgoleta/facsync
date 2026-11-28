document.querySelectorAll('[data-directory-filters]').forEach(form => {
  let submitting = false;
  const levelFilter = form.querySelector('[data-student-level-filter]');
  const yearFilter = form.querySelector('[data-student-year-filter]');
  const departmentFilter = form.querySelector('[data-department-filter]');
  const choicesElement = document.getElementById('student-filter-year-choices');
  const refreshDepartments = () => {
    if (!levelFilter || !departmentFilter) return;
    [...departmentFilter.options].forEach(option => {
      const levels = (option.dataset.studentLevels || '').split(',').filter(Boolean);
      option.hidden = Boolean(levelFilter.value) && option.value !== '' && !levels.includes(levelFilter.value);
    });
    if (departmentFilter.selectedOptions[0]?.hidden) departmentFilter.value = '';
  };
  if (levelFilter && departmentFilter) {
    levelFilter.addEventListener('change', refreshDepartments);
    refreshDepartments();
  }
  if (levelFilter && yearFilter && choicesElement) {
    const yearChoices = JSON.parse(choicesElement.textContent);
    const refreshYears = () => {
      const selected = yearFilter.dataset.selected || '';
      yearFilter.replaceChildren(new Option('All grades / years', ''));
      (yearChoices[levelFilter.value] || []).forEach(([value, label]) => {
        yearFilter.appendChild(new Option(label, value));
      });
      yearFilter.value = selected;
      yearFilter.disabled = !levelFilter.value;
    };
    levelFilter.addEventListener('change', () => { yearFilter.dataset.selected = ''; refreshYears(); });
    refreshYears();
  }
  form.addEventListener('change', () => {
    if (submitting) return;
    submitting = true;
    form.setAttribute('aria-busy', 'true');
    form.requestSubmit();
  });
});
