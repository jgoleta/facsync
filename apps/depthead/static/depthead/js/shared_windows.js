(() => {
  'use strict';
  const card = document.querySelector('.shared-window-card');
  if (!card || !window.fetch) return;
  let pending = false;
  card.addEventListener('click', event => {
    const button = event.target.closest('.shared-window-tabs button');
    if (!button || pending) return;
    card.querySelectorAll('.shared-window-tabs button').forEach(item => {
      item.setAttribute('aria-pressed', String(item === button));
    });
    card.querySelectorAll('.shared-window-result').forEach(panel => {
      panel.hidden = panel.id !== button.getAttribute('aria-controls');
    });
  });
  card.addEventListener('submit', async event => {
    const form = event.target;
    if (!form.matches('.shared-window-form')) return;
    event.preventDefault();
    if (pending) return;
    pending = true;
    const button = form.querySelector('button[type="submit"]');
    const loading = card.querySelector('.shared-window-loading');
    const error = card.querySelector('.shared-window-error');
    button.disabled = true;
    error.hidden = true;
    loading.hidden = false;
    card.setAttribute('aria-busy', 'true');
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    try {
      const url = new URL(card.dataset.endpoint, window.location.origin);
      url.search = new URLSearchParams(new FormData(form)).toString();
      const response = await fetch(url, {
        credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        headers: { Accept: 'application/json' },
      });
      if (response.redirected) throw new Error('Please reload the page and sign in again.');
      const payload = await response.json();
      if ((response.ok || response.status === 400) && typeof payload.html === 'string') {
        // HTML comes from our authenticated, autoescaped Django partial.
        card.innerHTML = payload.html;
        card.querySelector('.shared-window-form button').focus();
      } else {
        throw new Error(payload.error || 'Unable to find best times. Please try again.');
      }
    } catch (failure) {
      error.textContent = failure.name === 'AbortError'
        ? 'The request took too long. Please try again.'
        : failure.message || 'Unable to find best times. Please try again.';
      error.hidden = false;
    } finally {
      window.clearTimeout(timeout);
      pending = false;
      button.disabled = false;
      loading.hidden = true;
      card.removeAttribute('aria-busy');
    }
  });
})();
