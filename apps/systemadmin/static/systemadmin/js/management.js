/* Progressive enhancement: all forms retain their existing HTML endpoints. */
(() => {
  'use strict';
  const modal = document.getElementById('system-form-modal');
  const body = document.getElementById('system-modal-body');
  const confirm = document.getElementById('system-confirm-modal');
  if (!modal || typeof modal.showModal !== 'function') return;
  let trigger = null, dirty = false, loadController = null, pending = null;
  let processing = false, navigationOverlay = null, navigationTimer = null;
  let previousNavigation = [];
  // A control named "action" shadows form.action in the DOM named-property API.
  const formURL = form => new URL(form.getAttribute('action') || location.href, location.href).href;
  const focusable = root => [...root.querySelectorAll('button, [href], input, select, textarea, [tabindex]')]
    .filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length);

  function toast(message, level = 'success') {
    const node = document.createElement('div');
    node.className = `system-toast ${level.includes('error') ? 'error' : level.includes('warning') ? 'warning' : ''}`;
    node.setAttribute('role', level.includes('error') ? 'alert' : 'status');
    node.textContent = message;
    (modal.open ? body : document.getElementById('system-toast-stack')).append(node);
    requestAnimationFrame(() => node.classList.add('show'));
    setTimeout(() => { node.classList.remove('show'); setTimeout(() => node.remove(), 250); }, 5000);
  }

  function showMessages(doc = document) {
    const messages = [...doc.querySelectorAll('[data-system-messages] .system-message')];
    messages.forEach(node => { toast(node.textContent, node.dataset.level || 'success'); node.remove(); });
    return messages.length;
  }

  function restoreFocus(source) {
    let target = source;
    if (!target?.isConnected && source?.href) {
      target = [...document.querySelectorAll('a[href]')].find(link => link.href === source.href);
    }
    if (!target?.isConnected && source?.form) {
      target = [...document.querySelectorAll('form[action]')].find(form => formURL(form) === formURL(source.form))?.querySelector('button');
    }
    (target?.isConnected ? target : document.querySelector('[data-modal-trigger]') || document.querySelector('.sidebar-nav .active'))?.focus();
  }

  modal.addEventListener('close', () => {
    loadController?.abort();
    dirty = false;
    restoreFocus(trigger);
  });
  modal.addEventListener('click', event => {
    const rect = modal.getBoundingClientRect();
    const outside = event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom;
    if (event.target === modal && outside && !dirty) modal.close();
  });
  for (const dialog of [modal, confirm]) {
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const items = focusable(dialog), first = items[0], last = items[items.length - 1];
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
  }

  function validateDomains(field) {
    if (!field || field.name !== 'domains') return;
    const values = field.value.trim().split(/[\s,;]+/).filter(Boolean).map(value => value.toLowerCase());
    const validDomain = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+edu\.ph$/;
    const invalid = values.some(value => value.length > 253 || !validDomain.test(value));
    const message = invalid ? 'Each domain must end in .edu.ph, without @, a URL or a wildcard.' : '';
    field.setCustomValidity(message);
    field.setAttribute('aria-invalid', message ? 'true' : 'false');
    const feedback = field.closest('.system-field')?.querySelector('[data-domain-feedback]');
    if (feedback) { feedback.textContent = message; feedback.hidden = !message; }
  }

  document.addEventListener('input', event => {
    if (modal.contains(event.target)) dirty = true;
    validateDomains(event.target);
  });
  document.addEventListener('change', event => {
    if (modal.contains(event.target)) dirty = true;
    if (event.target.id === 'system-school-filter') filterSchools();
    validateDomains(event.target);
  });

  function filterSchools() {
    const select = document.getElementById('system-school-filter');
    if (!select) return;
    document.querySelectorAll('[data-directory-section]').forEach(section => {
      const rows = [...section.querySelectorAll('[data-directory-row]')];
      rows.forEach(row => { row.hidden = select.value !== 'all' && row.dataset.schoolId !== select.value; });
      const empty = section.querySelector('[data-filter-empty]');
      if (empty) empty.hidden = !rows.length || rows.some(row => !row.hidden);
    });
  }

  async function readPage(response) {
    if (!response.ok) {
      let message = `Unable to complete the request (${response.status}).`;
      if (response.headers.get('Content-Type')?.includes('application/json')) {
        const data = await response.json();
        message = data.error || message;
      }
      throw new Error(message);
    }
    const url = new URL(response.url);
    if (url.origin !== location.origin || !url.pathname.startsWith('/systemadmin/')) {
      throw new Error('Your session may have expired. Reload the page and sign in again.');
    }
    return new DOMParser().parseFromString(await response.text(), 'text/html');
  }

  function insertForm(content, url, failed = false) {
    const imported = document.importNode(content, true);
    const form = imported.querySelector('form');
    form.action = url;
    document.getElementById('system-modal-title').textContent = content.dataset.formTitle;
    body.replaceChildren(imported);
    form.querySelectorAll('[name="domains"]').forEach(validateDomains);
    (failed ? form.querySelector('[aria-invalid="true"], input:not([type="hidden"]):not([disabled]), select, textarea') :
      form.querySelector('input:not([type="hidden"]):not([disabled]), select, textarea'))?.focus();
  }

  async function openForm(link) {
    if (processing) { toast('Please wait for the current request to finish.', 'warning'); return; }
    trigger = link; dirty = false;
    loadController?.abort();
    const controller = new AbortController(); loadController = controller;
    document.getElementById('system-modal-title').textContent = link.textContent.trim().replace(/^\+\s*/, '');
    const status = document.createElement('p'); status.setAttribute('role', 'status'); status.textContent = 'Loading form…';
    body.replaceChildren(status);
    modal.showModal();
    modal.querySelector('[data-close-modal]').focus();
    try {
      const response = await fetch(link.href, { credentials: 'same-origin', signal: controller.signal });
      const doc = await readPage(response);
      if (controller.signal.aborted || !modal.open) return;
      const content = doc.getElementById('system-form-content');
      if (!content) throw new Error('This form could not be loaded. Reload the page and try again.');
      insertForm(content, link.href);
    } catch (error) {
      if (error.name === 'AbortError') return;
      if (modal.open) modal.close();
      toast(error.message, 'error');
    }
  }

  document.addEventListener('click', event => {
    if (event.target.closest('[data-close-modal]') || (modal.open && event.target.closest('[data-modal-cancel]'))) {
      event.preventDefault(); modal.close(); return;
    }
    if (event.target.closest('[data-close-confirm]')) { confirm.close(); return; }
    const link = event.target.closest('[data-modal-trigger]');
    if (link && event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
      event.preventDefault(); openForm(link);
    }
  });

  confirm.addEventListener('close', () => { restoreFocus(pending?.submitter); pending = null; });
  document.getElementById('system-confirm-submit').addEventListener('click', () => {
    const action = pending;
    confirm.close();
    if (action && !processing) perform(action.form, action.submitter);
  });

  async function perform(form, submitter) {
    if (processing) return;
    // Capture the clicked action before disabling controls; disabled buttons are
    // omitted from FormData and must never turn suspend/reactivate into an empty POST.
    const payload = new FormData(form);
    const actionURL = formURL(form);
    if (submitter?.name) payload.append(submitter.name, submitter.value);
    processing = true; form.dataset.processing = 'true';
    const returnFocus = modal.contains(form) ? trigger : submitter;
    const buttons = [...document.querySelectorAll('[data-system-action] button')];
    const states = buttons.map(button => [button, button.disabled]);
    buttons.forEach(button => { button.disabled = true; });
    const originalLabel = submitter?.innerHTML;
    const label = form.dataset.processingLabel || 'Processing request…';
    if (submitter) {
      const spinner = document.createElement('span'); spinner.className = 'system-spinner'; spinner.setAttribute('aria-hidden', 'true');
      submitter.replaceChildren(spinner, document.createTextNode(label));
    }
    form.setAttribute('aria-busy', 'true');
    const indicator = document.getElementById('system-processing');
    indicator.querySelector('[data-processing-message]').textContent = label; indicator.hidden = false;
    try {
      const response = await fetch(actionURL, { method: 'POST', body: payload, credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': payload.get('csrfmiddlewaretoken') || '' } });
      const doc = await readPage(response);
      const returnedForm = doc.getElementById('system-form-content');
      if (returnedForm) {
        if (modal.contains(form)) {
          if (modal.open) { insertForm(returnedForm, actionURL, true); dirty = true; }
          else toast('The changes were not saved. Reopen the form to review them.', 'error');
        } else {
          document.getElementById('system-form-content').replaceWith(document.importNode(returnedForm, true));
          document.querySelector('#system-form-content .errorlist')?.scrollIntoView({ block: 'center' });
        }
        toast('Please review the form errors. Your changes have not been saved.', 'error');
        return;
      }
      const directory = doc.querySelector('[data-system-directory]');
      if (!directory) throw new Error('Unable to confirm the outcome. Reload the list before trying again.');
      const current = document.querySelector('[data-system-directory]');
      const selected = document.getElementById('system-school-filter')?.value;
      if (modal.open) modal.close();
      if (current) {
        current.replaceWith(document.importNode(directory, true));
        const filter = document.getElementById('system-school-filter');
        if (filter && [...filter.options].some(option => option.value === selected)) filter.value = selected;
        filterSchools();
        if (!showMessages(doc)) toast('Request completed.');
        restoreFocus(returnFocus);
      } else {
        // A direct full-page form submission still reaches its usual list URL.
        const notices = [...doc.querySelectorAll('[data-system-messages] .system-message')]
          .map(node => ({ text: node.textContent, level: node.dataset.level }));
        try { sessionStorage.setItem('system-admin-notices', JSON.stringify(notices)); } catch (_) { /* optional */ }
        location.assign(response.url);
      }
    } catch (error) {
      toast(error instanceof TypeError ? 'Unable to confirm the outcome. Check the list before trying again.' : error.message, 'error');
    } finally {
      processing = false; form.dataset.processing = 'false'; form.removeAttribute('aria-busy');
      states.forEach(([button, disabled]) => { button.disabled = disabled; });
      if (submitter && originalLabel !== undefined) submitter.innerHTML = originalLabel;
      indicator.hidden = true;
    }
  }

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!form.matches('[data-system-action]')) return;
    event.preventDefault();
    if (processing || form.dataset.processing === 'true') return;
    form.querySelectorAll('[name="domains"]').forEach(validateDomains);
    if (!form.reportValidity()) return;
    const submitter = event.submitter || form.querySelector('button[type="submit"], button:not([type])');
    if (form.dataset.confirm) {
      pending = { form, submitter };
      document.getElementById('system-confirm-title').textContent = form.dataset.confirmTitle || 'Confirm action';
      document.getElementById('system-confirm-message').textContent = form.dataset.confirm;
      confirm.showModal(); confirm.querySelector('[data-close-confirm]').focus();
    } else perform(form, submitter);
  });

  function resetSkeleton() {
    navigationOverlay?.remove(); navigationOverlay = null;
    clearTimeout(navigationTimer);
    previousNavigation.forEach(([item, active, current]) => {
      item.classList.toggle('active', active);
      if (current === null) item.removeAttribute('aria-current');
      else item.setAttribute('aria-current', current);
    });
    previousNavigation = [];
    const main = document.querySelector('main'); main.inert = false; main.removeAttribute('aria-busy');
  }
  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link || link.target || link.hasAttribute('download')) return;
    const url = new URL(link.href);
    if (url.origin !== location.origin || url.pathname === location.pathname || url.hash) return;
    const page = url.pathname === '/systemadmin/' ? 'schools' : url.pathname === '/systemadmin/superadmins/' ? 'superadmins' : url.pathname === '/systemadmin/overview/' ? 'overview' : null;
    const template = page && document.getElementById(`system-${page}-skeleton`);
    if (!template) return;
    resetSkeleton();
    previousNavigation = [...document.querySelectorAll('.sidebar-nav a')]
      .map(item => [item, item.classList.contains('active'), item.getAttribute('aria-current')]);
    previousNavigation.forEach(([item]) => {
      const active = new URL(item.href).pathname === url.pathname;
      item.classList.toggle('active', active);
      if (active) item.setAttribute('aria-current', 'page');
      else item.removeAttribute('aria-current');
    });
    navigationOverlay = document.createElement('div'); navigationOverlay.className = 'system-navigation-skeleton';
    navigationOverlay.append(template.content.cloneNode(true));
    const rect = document.querySelector('main').getBoundingClientRect();
    Object.assign(navigationOverlay.style, { top: `${Math.max(0, rect.top)}px`, left: `${rect.left}px`, width: `${rect.width}px`, height: `${innerHeight - Math.max(0, rect.top)}px` });
    document.body.append(navigationOverlay);
    const main = document.querySelector('main'); main.inert = true; main.setAttribute('aria-busy', 'true');
    navigationTimer = setTimeout(resetSkeleton, 15000);
  });
  window.addEventListener('pageshow', resetSkeleton);
  window.addEventListener('pagehide', resetSkeleton);
  document.querySelectorAll('[name="domains"]').forEach(validateDomains);
  filterSchools(); showMessages();
  try {
    const notices = JSON.parse(sessionStorage.getItem('system-admin-notices') || '[]');
    sessionStorage.removeItem('system-admin-notices');
    notices.forEach(notice => toast(notice.text, notice.level));
  } catch (_) { /* Storage is optional. */ }
})();
