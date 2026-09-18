(() => {
  'use strict';
  const root = document.getElementById('analytics-browser');
  if (!root) return;
  const toggle = document.getElementById('analytics-chat-toggle');
  const panel = document.getElementById('analytics-chat-panel');
  const close = document.getElementById('analytics-chat-close');
  const messages = document.getElementById('analytics-chat-messages');
  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close analytics browser' : 'Open analytics browser');
    (open ? close : toggle).focus();
  }
  // A restored browser page also starts a fresh conversation.
  function reset() {
    messages.replaceChildren();
    panel.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Open analytics browser');
  }
  reset();
  window.addEventListener('pageshow', reset);
  toggle.hidden = false;
  toggle.addEventListener('click', () => setOpen(panel.hidden));
  close.addEventListener('click', () => setOpen(false));
  root.addEventListener('keydown', event => {
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
      const reply = element('div', 'Loading analytics...', 'analytics-message received');
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
          const link = element('a', 'View source analytics');
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
