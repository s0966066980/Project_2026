const PAGE_PERMISSIONS = Object.freeze({
  stats: ['operations.read', 'recommendations.effectiveness.read'],
  promotions: ['campaigns.read'],
  recommendations: ['recommendations.effectiveness.read'],
  availability: ['catalog.availability.read'],
  members: ['members.read'],
  settings: ['settings.write'],
  rag: ['rag.read'],
  emotion: ['settings.write'],
  health: ['operations.read'],
  test: ['system.debug'],
});

/** @param {string[]} permissions @param {string} page */
export function canViewAdminPage(permissions, page) {
  const granted = new Set(permissions || []);
  if (granted.has('*')) return true;
  return (/** @type {Record<string, string[]>} */ (PAGE_PERMISSIONS)[page] || []).some(permission => granted.has(permission));
}

/** @param {{permissions?: string[]}|null} principal @param {Document|HTMLElement} [root] */
export function applyAdminNavigation(principal, root = document) {
  const permissions = principal?.permissions || [];
  root.querySelectorAll('.nav-item[data-page]').forEach(rawButton => {
    const button = /** @type {HTMLButtonElement} */ (rawButton);
    const allowed = canViewAdminPage(permissions, button.dataset.page || '');
    button.hidden = !allowed;
    button.setAttribute('aria-hidden', allowed ? 'false' : 'true');
  });
  root.querySelectorAll('[data-nav-pages]').forEach(rawLabel => {
    const label = /** @type {HTMLElement} */ (rawLabel);
    const pages = String(label.dataset.navPages || '').split(',').filter(Boolean);
    const visible = pages.some(page => {
      const button = root.querySelector(`.nav-item[data-page="${page}"]`);
      return button && !button.hasAttribute('hidden');
    });
    label.hidden = !visible;
  });
  const active = /** @type {HTMLButtonElement|null} */ (
    root.querySelector('.nav-item.active:not([hidden])') || root.querySelector('.nav-item[data-page]:not([hidden])')
  );
  if (active && !active.classList.contains('active')) active.click();
  return [...root.querySelectorAll('.nav-item[data-page]:not([hidden])')]
    .map(button => /** @type {HTMLButtonElement} */ (button).dataset.page || '');
}
