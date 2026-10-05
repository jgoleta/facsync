(() => {
  'use strict';
  function skeleton(title, type) {
    const box = document.createElement('section');
    box.className = `faculty-skeleton faculty-skeleton-${type}`;
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.textContent = `Loading ${title}…`;
    box.append(status);
    const shapes = document.createElement('div');
    shapes.className = 'faculty-skeleton-shapes';
    shapes.setAttribute('aria-hidden', 'true');
    for (let i = 0; i < (type === 'calendar' ? 35 : 4); i++) {
      const shape = document.createElement('div');
      shape.className = 'faculty-skeleton-shape';
      shapes.append(shape);
    }
    box.append(shapes);
    return box;
  }
  window.facultyInitialLoading = window.pageInitialLoading = (region, title, type) => {
    if (!region) return () => {};
    const box = skeleton(title, type);
    const children = Array.from(region.children);
    const saved = children.map(child => [child, child.style.visibility, child.inert]);
    saved.forEach(([child]) => { child.style.visibility = 'hidden'; child.inert = true; });
    region.classList.add('faculty-loading-region');
    region.setAttribute('aria-busy', 'true');
    region.append(box);
    return () => {
      box.remove();
      region.classList.remove('faculty-loading-region');
      region.removeAttribute('aria-busy');
      saved.forEach(([child, visibility, inert]) => { child.style.visibility = visibility; child.inert = inert; });
    };
  };
  document.addEventListener('DOMContentLoaded', () => {
    const config = document.getElementById('faculty-navigation-destinations') || document.getElementById('student-navigation-destinations');
    const main = document.querySelector('main');
    if (!config || !main) return;
    const destinations = JSON.parse(config.textContent);
    let overlay, timer, previous;
    function reset() {
      if (!overlay) return;
      overlay.remove(); overlay = null;
      clearTimeout(timer);
      main.style.visibility = previous.visibility;
      main.inert = previous.inert;
    }
    function position() {
      if (!overlay) return;
      const rect = main.getBoundingClientRect();
      const header = document.querySelector('.topbar')?.getBoundingClientRect();
      const top = Math.max(0, header?.bottom || 0, rect.top);
      Object.assign(overlay.style, { left: `${rect.left}px`, top: `${top}px`, width: `${rect.width}px`, height: `${Math.max(0, innerHeight - top)}px` });
    }
    document.addEventListener('click', event => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = event.target.closest('a[href]');
      if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
      const url = new URL(link.href, location.href);
      if (url.origin !== location.origin || url.hash || url.href === location.href || !destinations[url.pathname]) return;
      reset();
      previous = { visibility: main.style.visibility, inert: main.inert };
      overlay = skeleton(...destinations[url.pathname]);
      overlay.classList.add('faculty-transition');
      document.body.append(overlay);
      position(); main.style.visibility = 'hidden'; main.inert = true;
      timer = setTimeout(reset, 15000);
      queueMicrotask(() => { if (event.defaultPrevented) reset(); });
    });
    window.addEventListener('pageshow', reset);
    window.addEventListener('pagehide', reset);
    window.addEventListener('resize', position);
    window.addEventListener('scroll', position, { passive: true });
    window.addEventListener('keydown', event => { if (event.key === 'Escape') reset(); });
  });
})();
