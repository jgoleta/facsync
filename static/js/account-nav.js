(() => {
  const toggle = document.getElementById('accountNavToggle');
  const actions = document.getElementById('accountNavActions');
  if (!toggle || !actions) return;

  const closeMenu = () => {
    actions.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Open account menu');
  };

  toggle.addEventListener('click', (event) => {
    event.stopPropagation();
    const isOpen = toggle.getAttribute('aria-expanded') === 'true';
    actions.hidden = isOpen;
    toggle.setAttribute('aria-expanded', String(!isOpen));
    toggle.setAttribute('aria-label', isOpen ? 'Open account menu' : 'Close account menu');
  });

  document.addEventListener('click', (event) => {
    if (!actions.contains(event.target) && event.target !== toggle) closeMenu();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeMenu();
      toggle.focus();
    }
  });
})();
