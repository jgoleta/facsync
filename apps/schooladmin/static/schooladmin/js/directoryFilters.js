document.querySelectorAll('[data-directory-filters]').forEach(form => {
  let submitting = false;
  form.addEventListener('change', () => {
    if (submitting) return;
    submitting = true;
    form.setAttribute('aria-busy', 'true');
    form.requestSubmit();
  });
});
