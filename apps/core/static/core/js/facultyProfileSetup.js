(() => {
  const form = document.getElementById('faculty-profile-form');
  if (!form) return;
  const button = form.querySelector('button[type=submit]');
  const label = button.textContent;
  form.addEventListener('submit', event => {
    if (form.dataset.processing === 'true') { event.preventDefault(); return; }
    form.dataset.processing = 'true';
    button.disabled = true;
    button.textContent = 'Saving profile...';
    form.setAttribute('aria-busy', 'true');
  });
  window.addEventListener('pageshow', () => {
    form.dataset.processing = 'false';
    button.disabled = false;
    button.textContent = label;
    form.removeAttribute('aria-busy');
  });
})();
