(() => {
  'use strict';
  const root = document.getElementById('analytics-browser');
  if (!root) return;
  const toggle = document.getElementById('analytics-chat-toggle');
  const panel = document.getElementById('analytics-chat-panel');
  const close = document.getElementById('analytics-chat-close');
  const messages = document.getElementById('analytics-chat-messages');
  const label = root.dataset.label || 'analytics browser';
  const narrow = window.matchMedia('(max-width: 1279px)');
  const background = document.querySelector('.admin-shell, .page-shell');
  let previousInert = null;
  function layout() {
    const open = !panel.hidden;
    document.body.classList.toggle('analytics-chat-open', open);
    toggle.hidden = open;
    panel.setAttribute('aria-modal', String(open && narrow.matches));
    if (background && open && narrow.matches) {
      if (previousInert === null) previousInert = background.inert;
      background.inert = true;
    } else if (background && previousInert !== null) {
      background.inert = previousInert;
      previousInert = null;
    }
  }
  narrow.addEventListener('change', () => {
    layout();
    if (!panel.hidden && narrow.matches) close.focus();
  });
  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', `${open ? 'Close' : 'Open'} ${label}`);
    layout();
    (open ? close : toggle).focus();
  }
  // A restored browser page also starts a fresh conversation.
  function reset() {
    messages.replaceChildren();
    panel.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', `Open ${label}`);
    layout();
  }
  reset();
  window.addEventListener('pageshow', reset);
  toggle.hidden = false;
  toggle.addEventListener('click', () => setOpen(panel.hidden));
  close.addEventListener('click', () => setOpen(false));
  root.addEventListener('keydown', event => {
    if (event.key === 'Tab' && !panel.hidden && narrow.matches) {
      const controls = Array.from(panel.querySelectorAll('button, a[href], [tabindex="0"]'));
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }
    if (event.key === 'Escape' && !panel.hidden) {
      event.preventDefault();
      setOpen(false);
    }
  });
  function element(tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function scrollLatest() { messages.scrollTop = messages.scrollHeight; }
  root.querySelectorAll('[data-metric]').forEach(button => {
    button.addEventListener('click', async () => {
      messages.append(element('p', button.textContent, 'analytics-message sent'));
      const reply = element('div', 'Loading answer...', 'analytics-message received');
      reply.setAttribute('aria-busy', 'true');
      messages.append(reply);
      scrollLatest();
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 20000);
      try {
        const url = new URL(root.dataset.endpoint, window.location.origin);
        url.searchParams.set('metric', button.dataset.metric);
        const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
        if (!response.ok) throw new Error('Request failed');
        const data = await response.json();
        if (!Array.isArray(data.lines)) throw new Error('Invalid response');
        reply.replaceChildren(element('p', data.period, 'analytics-answer-period'));
        const list = document.createElement('ul');
        data.lines.forEach(line => list.append(element('li', line)));
        reply.append(list, element('p', data.note));
        const source = new URL(data.source_url, window.location.origin);
        if (source.origin === window.location.origin) {
          const link = element('a', data.source_label || root.dataset.sourceLabel || 'View source analytics');
          link.href = source.href;
          reply.append(link);
        }
      } catch (_) {
        reply.replaceChildren(element('p', "Sorry, I couldn't load that right now. Please try again."));
      } finally {
        clearTimeout(timeout);
        reply.setAttribute('aria-busy', 'false');
        scrollLatest();
      }
    });
  });
})();
