(() => {
  'use strict';
  document.documentElement.classList.add('faculty-navigation-shell');
  function block(className, children = []) {
    const node = document.createElement('div');
    node.className = className;
    children.forEach(child => node.append(child));
    return node;
  }
  function shape(className = '') {
    const node = document.createElement('div');
    node.className = `faculty-skeleton-shape ${className}`.trim();
    return node;
  }
  function schedulePage() {
    const days = Array.from({ length: 42 }, (_, index) => {
      const cell = block('faculty-skeleton-day', [shape('day-label')]);
      if (index > 8 && index % 4 !== 1 && index % 7 !== 3) {
        cell.append(block(`faculty-skeleton-event event-${index % 3}`, [shape(), shape('short')]));
        if (index % 5 === 0) cell.append(block('faculty-skeleton-event secondary', [shape()]));
      }
      return cell;
    });
    const activities = Array.from({ length: 6 }, (_, i) => block('faculty-skeleton-activity', [shape('activity-dot'), shape(i % 2 ? 'activity-line medium' : 'activity-line')]));
    return block('faculty-skeleton-layout schedule-page', [
      block('faculty-skeleton-schedule-card', [
        block('faculty-skeleton-schedule-heading', [block('faculty-skeleton-heading-copy', [shape('eyebrow'), shape('title'), shape('subtitle')]), block('faculty-skeleton-calendar-controls', [shape('sync'), shape('select'), shape('select')])]),
        block('faculty-skeleton-view-tabs', [shape('active'), shape(), shape()]),
        block('faculty-skeleton-calendar-grid', days)
      ]),
      block('faculty-skeleton-activities-card', [
        block('faculty-skeleton-activities-heading', [shape('eyebrow'), shape('sidebar-title'), shape('subtitle')]),
        block('faculty-skeleton-activities-list', activities),
        block('faculty-skeleton-activities-actions', [shape(), shape(), shape(), shape(), shape('link'), shape('link')])
      ])
    ]);
  }
  function dashboardPage() {
    const statuses = ['available', 'busy', 'virtual', 'leave', 'unavailable'].map(type => shape(`status-${type}`));
    const metrics = Array.from({ length: 3 }, () => block('faculty-skeleton-metric', [shape('metric-value'), shape('metric-label')]));
    const requests = Array.from({ length: 3 }, () => block('faculty-skeleton-request', [block('request-copy', [shape(), shape('medium'), shape('short')]), block('request-actions', [shape(), shape()])]));
    return block('faculty-skeleton-layout dashboard-page', [
      block('faculty-skeleton-dashboard-main', [
        block('faculty-skeleton-welcome', [shape('eyebrow'), shape('welcome-title'), shape('subtitle')]),
        block('faculty-skeleton-status-panel', [shape('section-title'), shape('section-copy'), block('faculty-skeleton-statuses', statuses), block('faculty-skeleton-inputs', [shape(), shape()]), block('faculty-skeleton-status-mode', [shape(), shape('mode-button')]), shape('update-button')]),
        block('faculty-skeleton-requests-panel', [block('requests-heading', [shape('section-title'), shape('count-pill')]), block('request-filters', [shape(), shape(), shape()]), ...requests])
      ]),
      block('faculty-skeleton-dashboard-aside', [
        block('aside-section', [shape('eyebrow'), shape('section-title'), shape('status-badge'), shape('aside-copy')]),
        block('aside-section', [shape('section-title'), block('faculty-skeleton-metrics', metrics)]),
        block('aside-section aside-links', [shape(), shape()]),
        block('aside-section', [shape('section-title'), shape('aside-copy'), shape('aside-button'), shape('aside-copy short')])
      ])
    ]);
  }
  function profilePage() {
    const detailFields = Array.from({ length: 4 }, (_, index) => block('faculty-skeleton-profile-field', [shape('field-label'), block('field-value', [shape(index % 2 ? 'medium' : '')])]));
    const syncOptions = Array.from({ length: 2 }, () => block('faculty-skeleton-sync-option', [block('sync-copy', [shape('medium'), shape('short')]), shape('toggle')]));
    const shortcuts = Array.from({ length: 3 }, () => block('faculty-skeleton-shortcut', [shape(), shape('arrow')]));
    return block('faculty-skeleton-layout profile-page', [
      block('faculty-skeleton-profile-header', [block('profile-header-copy', [shape('eyebrow'), shape('profile-title'), shape('subtitle')]), shape('account-badge')]),
      block('faculty-skeleton-profile-grid', [
        block('faculty-skeleton-personal-card', [
          block('profile-identity', [shape('profile-avatar'), block('identity-copy', [shape('eyebrow'), shape('identity-name'), shape('identity-college')])]),
          block('photo-section', [shape('section-title'), shape('section-copy'), shape('file-field'), shape('upload-button')]),
          block('personal-details', [block('details-heading', [block('details-heading-copy', [shape('eyebrow'), shape('section-title')]), shape('details-caption')]), block('profile-fields', detailFields)]),
          block('biography-section', [shape('section-title'), shape('section-copy'), shape('biography-line'), shape('biography-line medium'), shape('biography-line short')])
        ]),
        block('faculty-skeleton-profile-aside', [
          block('integration-card', [block('aside-heading', [shape('eyebrow'), shape('section-title')]), block('calendar-connection', [shape('calendar-icon'), block('connection-copy', [shape('medium'), shape('connection-status')]), shape('connect-button')]), ...syncOptions]),
          block('shortcuts-card', [block('aside-heading', [shape('eyebrow'), shape('section-title')]), ...shortcuts])
        ])
      ])
    ]);
  }
  function studentHomePage() {
    const services = Array.from({ length: 4 }, () => block('student-home-service-card', [
      block('student-home-service-heading', [shape('service-icon'), block('student-home-service-copy', [shape('service-title'), shape('service-subtitle')])]),
      block('student-home-service-details', [shape('service-detail-label'), shape('service-detail-value'), shape('service-detail-label'), shape('service-detail-value')]),
      shape('service-link')
    ]));
    const actions = Array.from({ length: 2 }, () => block('student-home-action-card', [
      block('student-home-action-heading', [shape('action-icon'), shape('action-title')]),
      block('action-copy'),
      block('action-copy medium'),
      block('student-home-action-footer', [shape('action-link'), shape('action-arrow')])
    ]));
    const stats = Array.from({ length: 2 }, () => block('student-home-stat', [shape('stat-value'), shape('stat-label')]));
    return block('student-home-layout', [
      block('student-home-announcement', [shape('announcement-icon'), block('student-home-announcement-copy', [shape('announcement-title'), shape('announcement-text')])]),
      block('student-home-intro', [
        block('student-home-intro-copy', [shape('eyebrow'), shape('welcome-title'), shape('intro-text'), shape('intro-text medium')]),
        block('student-home-summary', [shape('summary-chip'), ...stats, shape('summary-college')])
      ]),
      block('student-home-content', [
        block('student-home-services', [block('student-home-services-heading', [shape('section-title'), shape('section-copy')]), block('student-home-services-grid', services)]),
        block('student-home-actions', [block('student-home-actions-heading', [shape('section-title'), shape('section-copy')]), ...actions])
      ])
    ]);
  }
  function studentDashboardPage() {
    const facultyCards = Array.from({ length: 4 }, () => block('student-faculty-card', [
      block('student-faculty-identity', [shape('faculty-avatar'), block('student-faculty-name-copy', [shape('faculty-name'), shape('faculty-college')])]),
      block('student-faculty-status', [shape('status-dot'), shape('status-label')]),
      shape('faculty-note'),
      shape('faculty-meta'),
      shape('faculty-action')
    ]));
    return block('student-dashboard-layout', [
      block('student-dashboard-hero', [shape('eyebrow'), shape('hero-copy'), shape('hero-copy medium')]),
      block('student-availability-panel', [
        block('student-dashboard-toolbar', [
          block('student-dashboard-heading', [shape('section-title'), shape('section-copy')]),
          block('student-dashboard-controls', [
            block('student-dashboard-control', [shape('control-label'), shape('control-input')]),
            block('student-dashboard-toggle', [shape('toggle-track'), shape('toggle-label')]),
            block('student-dashboard-control', [shape('control-label'), shape('control-input')])
          ])
        ]),
        block('student-faculty-grid', facultyCards)
      ])
    ]);
  }
  function studentRequestsPage() {
    const requests = Array.from({ length: 4 }, () => block('student-request-card', [
      block('student-request-status', [shape('request-status-badge'), shape('request-status-action')]),
      block('student-request-info', [
        block('student-request-faculty', [shape('request-avatar'), block('student-request-faculty-copy', [shape('faculty-label'), shape('faculty-name')])]),
        shape('appointment-label'),
        shape('appointment-value'),
        shape('request-type'),
        shape('request-message')
      ]),
      shape('request-id')
    ]));
    return block('student-requests-layout', [
      block('student-requests-intro', [block('student-requests-intro-copy', [shape('eyebrow'), shape('requests-title'), shape('requests-description')]), shape('return-button')]),
      block('student-requests-panel', [
        block('student-requests-toolbar', [block('student-requests-heading', [shape('section-title'), shape('request-count')]), block('student-requests-filter', [shape('control-label'), shape('control-input')])]),
        block('student-requests-grid', requests)
      ])
    ]);
  }
  function skeleton(title, type, fullPage = false) {
    const box = document.createElement('section');
    box.className = `faculty-skeleton faculty-skeleton-${type}`;
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.textContent = `Loading ${title}…`;
    box.append(status);
    const layout = fullPage && type === 'calendar' ? schedulePage() : fullPage && type === 'dashboard' ? dashboardPage() : fullPage && type === 'profile' ? profilePage() : fullPage && type === 'student-home' ? studentHomePage() : fullPage && type === 'student-dashboard' ? studentDashboardPage() : fullPage && type === 'student-requests' ? studentRequestsPage() : (() => {
      const shapes = document.createElement('div');
      shapes.className = 'faculty-skeleton-shapes';
      for (let i = 0; i < (type === 'calendar' ? 35 : 4); i++) {
        const placeholder = document.createElement('div');
        placeholder.className = 'faculty-skeleton-shape';
        shapes.append(placeholder);
      }
      return shapes;
    })();
    layout.setAttribute('aria-hidden', 'true');
    box.append(layout);
    if (type.startsWith('student-')) box.classList.add('student-transition');
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
      document.documentElement.style.overflow = previous.rootOverflow;
      document.body.style.overflow = previous.bodyOverflow;
    }
    function position() {
      if (!overlay) return;
      const rect = main.getBoundingClientRect();
      const header = document.querySelector('.topbar')?.getBoundingClientRect();
      const top = Math.max(0, header?.bottom || 0, rect.top);
      const isDashboard = overlay.classList.contains('faculty-skeleton-dashboard');
      const width = isDashboard ? Math.min(innerWidth * 0.96, 1600) : rect.width;
      const left = isDashboard ? (innerWidth - width) / 2 : rect.left;
      Object.assign(overlay.style, { left: `${left}px`, top: `${top}px`, width: `${width}px`, height: `${Math.max(0, innerHeight - top)}px` });
    }
    document.addEventListener('click', event => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = event.target.closest('a[href]');
      if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
      const url = new URL(link.href, location.href);
      if (url.origin !== location.origin || url.hash || url.href === location.href || !destinations[url.pathname]) return;
      reset();
      previous = { visibility: main.style.visibility, inert: main.inert };
      const [title, type] = destinations[url.pathname];
      overlay = skeleton(title, type, true);
      overlay.classList.add('faculty-transition');
      document.body.append(overlay);
      position();
      previous.rootOverflow = document.documentElement.style.overflow;
      previous.bodyOverflow = document.body.style.overflow;
      document.documentElement.style.overflow = 'hidden';
      document.body.style.overflow = 'hidden';
      main.style.visibility = 'hidden'; main.inert = true;
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
