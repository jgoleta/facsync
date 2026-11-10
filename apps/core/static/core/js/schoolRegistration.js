(() => {
  if (document.querySelector('.school-preview-banner')) return;
  document.querySelectorAll('form[data-school-request-submit]').forEach(form => {
    form.addEventListener('submit', event => {
      if (form.dataset.processing === 'true') { event.preventDefault(); return; }
      form.dataset.processing = 'true'; form.setAttribute('aria-busy', 'true');
      const button = form.querySelector('button[type=submit]');
      button.dataset.originalLabel = button.textContent;
      button.disabled = true; button.textContent = 'Processing request…';
    });
  });
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('form[data-school-request-submit]').forEach(form => {
      form.dataset.processing = 'false'; form.removeAttribute('aria-busy');
      const button = form.querySelector('button[type=submit]');
      button.disabled = false;
      if (button.dataset.originalLabel) button.textContent = button.dataset.originalLabel;
    });
  });
})();
