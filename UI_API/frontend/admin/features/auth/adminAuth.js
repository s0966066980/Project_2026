// @ts-check

/** @returns {string} */
export function adminToken() {
  return sessionStorage.getItem('admin_demo_token') || '';
}

/** @param {Record<string, string>} [extra] @returns {Record<string, string>} */
export function adminHeaders(extra = {}) {
  const token = adminToken();
  return token ? { ...extra, 'X-Admin-Token': token, Authorization: `Bearer ${token}` } : extra;
}

/**
 * @param {{
 *   apiBaseUrl: string,
 *   onAuthenticated: (principal?: any) => Promise<void>,
 *   onPrincipal?: (principal: any) => void,
 *   fetchImpl?: typeof fetch
 * }} options
 */
export function createAdminAuthController({ apiBaseUrl, onAuthenticated, onPrincipal = () => {}, fetchImpl = fetch }) {
  const backdrop = () => document.getElementById('adminAuthBackdrop');

  async function bootstrap() {
    try {
      const response = await fetchImpl(`${apiBaseUrl}/api/admin/auth/me`, {
        headers: adminHeaders(),
        credentials: 'same-origin',
      });
      if (!response.ok) throw new Error('authentication required');
      const body = await response.json();
      const principal = body?.principal || null;
      onPrincipal(principal);
      const element = backdrop();
      if (element) element.style.display = 'none';
      await onAuthenticated(principal);
    } catch {
      const element = backdrop();
      if (element) element.style.display = 'flex';
    }
  }

  /** @param {SubmitEvent} event */
  async function login(event) {
    event.preventDefault();
    const identity = document.getElementById('adminLoginIdentity');
    const password = document.getElementById('adminLoginPassword');
    const error = document.getElementById('adminAuthError');
    if (!(identity instanceof HTMLInputElement) || !(password instanceof HTMLInputElement)) return;
    if (error) error.textContent = '';
    const response = await fetchImpl(`${apiBaseUrl}/api/admin/auth/login`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ login_identity: identity.value, password: password.value }),
    }).catch(() => null);
    password.value = '';
    if (!response?.ok) {
      if (error) error.textContent = '登入失敗，請確認帳號與密碼。';
      return;
    }
    await bootstrap();
  }

  function bind() {
    document.getElementById('adminAuthForm')?.addEventListener('submit', login);
    void bootstrap();
  }

  return { bind, bootstrap };
}
