(() => {
  'use strict';
  const config = document.getElementById('admin-navigation-destinations');
  const main = document.querySelector('main.main-content');
  if (!config || !main) return;
  const destinations = JSON.parse(config.textContent);
  let overlay = null;
  let timer = null;
  let previousInert = false;

  function reset() {
    if (!overlay) return;
    overlay.remove();
    overlay = null;
    clearTimeout(timer);
    main.classList.remove('admin-navigation-pending');
    main.inert = previousInert;
  }

  function position() {
    if (!overlay) return;
    const rect = main.getBoundingClientRect();
    const top = Math.max(0, rect.top);
    Object.assign(overlay.style, {
      left: `${rect.left}px`, top: `${top}px`, width: `${rect.width}px`,
      height: `${Math.max(0, window.innerHeight - top)}px`,
    });
  }

  function placeholder(parent, extra = '') {
    const line = document.createElement('div');
    line.className = `admin-navigation-placeholder ${extra}`;
    parent.append(line);
  }

  function block(parent, type) {
    const card = document.createElement('div');
    card.className = 'admin-navigation-block';
    parent.append(card);
    placeholder(card);
    if (type === 'chart') placeholder(card, 'admin-navigation-chart');
    else for (let i = 0; i < (type === 'table' ? 5 : 3); i++) {
      placeholder(card, type === 'table' ? 'admin-navigation-row' : type === 'form' ? 'admin-navigation-form' : '');
    }
  }

  function show(title, type) {
    reset();
    previousInert = main.inert;
    overlay = document.createElement('section');
    overlay.className = 'admin-navigation-loading';
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.textContent = `Loading ${title}…`;
    overlay.append(status);
    const shapes = document.createElement('div');
    shapes.setAttribute('aria-hidden', 'true');
    overlay.append(shapes);
    if (type === 'cards' || type === 'dashboard') {
      const grid = document.createElement('div');
      grid.className = 'admin-navigation-grid';
      shapes.append(grid);
      for (let i = 0; i < (type === 'cards' ? 6 : 3); i++) block(grid, 'card');
      if (type === 'dashboard') block(shapes, 'chart');
    } else block(shapes, type);
    document.body.append(overlay);
    position();
    main.inert = true;
    main.classList.add('admin-navigation-pending');
    // Recover if navigation is cancelled, downloads unexpectedly, or stalls.
    // This never delays or cancels the browser's normal navigation.
    timer = setTimeout(reset, 15000);
  }

  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link || !link.closest('.sidebar') || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    const target = new URL(link.href, window.location.href);
    if (target.origin !== window.location.origin || target.hash || target.href === window.location.href) return;
    const destination = destinations[target.pathname];
    if (!destination) return;
    show(...destination);
    // Other click handlers may cancel the navigation after this handler runs.
    queueMicrotask(() => { if (event.defaultPrevented) reset(); });
  });
  window.addEventListener('pageshow', reset);
  window.addEventListener('pagehide', reset);
  window.addEventListener('resize', position);
  window.addEventListener('scroll', position, {passive: true});
  window.addEventListener('keydown', event => { if (event.key === 'Escape') reset(); });
})();
