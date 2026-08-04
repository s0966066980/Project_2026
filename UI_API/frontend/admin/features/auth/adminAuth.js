// @ts-check

import { adminLoginErrorMessage } from '../apiErrors.js';

/** @param {Record<string, string>} [extra] @returns {Record<string, string>} */
export function adminHeaders(extra = {}) {
  return extra;
}

/**
 * @param {{
 *   apiBaseUrl: string,
 *   onAuthenticated: (principal?: any) => Promise<void>,
 *   onPrincipal?: (principal: any) => void,
 *   fetchImpl?: typeof fetch
 * }} options
 */
export function createAdminAuthController({
  apiBaseUrl,
  onAuthenticated,
  onPrincipal = () => {},
  fetchImpl = fetch,
}) {
  const backdrop = () => document.getElementById('adminAuthBackdrop');
  let managerActive = false;
  let managerIdentity = 'admin';
  let idleTimeoutMs = 30 * 60 * 1000;
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let idleTimer;

  /** @param {boolean} active */
  function updateManagerStatus(active) {
    managerActive = active;
    const openButton = document.getElementById('managerUnlockBtn');
    const lockButton = document.getElementById('managerLockBtn');
    const status = document.getElementById('managerAccessStatus');
    if (openButton) openButton.toggleAttribute('hidden', active);
    if (lockButton) lockButton.toggleAttribute('hidden', !active);
    if (status) status.textContent = active ? '已登入' : '未登入';
  }

  async function loadUiConfig() {
    const response = await fetchImpl(`${apiBaseUrl}/api/admin/auth/ui-config`).catch(() => null);
    if (!response?.ok) return;
    const body = await response.json();
    managerIdentity = String(body.manager_login_identity || 'admin');
    idleTimeoutMs = Math.max(1000, Number(body.manager_idle_timeout_sec || 1800) * 1000);
  }

  function requireLogin() {
    globalThis.clearTimeout(idleTimer);
    updateManagerStatus(false);
    onPrincipal(null);
    const element = backdrop();
    if (element) element.style.display = 'flex';
    document.getElementById('adminLoginPassword')?.focus?.();
  }

  function scheduleIdleLock() {
    globalThis.clearTimeout(idleTimer);
    if (!managerActive) return;
    idleTimer = globalThis.setTimeout(() => { void lockManager(); }, idleTimeoutMs);
  }

  async function bootstrap() {
    await loadUiConfig();
    try {
      const response = await fetchImpl(`${apiBaseUrl}/api/admin/auth/me`, {
        headers: adminHeaders(),
        credentials: 'same-origin',
      });
      if (!response.ok) throw new Error('authentication required');
      const body = await response.json();
      const principal = body?.principal || null;
      // 沒有主管 session 時後端會發放員工身分，此時頁面仍要能用，
      // 只是導覽會依 principal 的權限自動收斂到員工可見的範圍。
      updateManagerStatus(body?.manager === true);
      onPrincipal(principal);
      const element = backdrop();
      if (element) element.style.display = 'none';
      await onAuthenticated(principal);
      scheduleIdleLock();
    } catch {
      requireLogin();
    }
  }

  function openManagerLogin() {
    const error = document.getElementById('adminAuthError');
    if (error) error.textContent = '';
    const element = backdrop();
    if (element) element.style.display = 'flex';
    document.getElementById('adminLoginPassword')?.focus?.();
  }

  function closeManagerLogin() {
    // 取消主管登入會回到員工模式，不再是死路，因此一律可關閉。
    const element = backdrop();
    if (element) element.style.display = 'none';
  }

  async function lockManager() {
    await fetchImpl(`${apiBaseUrl}/api/admin/auth/logout`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: adminHeaders(),
    }).catch(() => null);
    globalThis.clearTimeout(idleTimer);
    // 登出主管後退回員工模式，而不是把頁面鎖死。
    await bootstrap();
  }

  /** @param {SubmitEvent} event */
  async function login(event) {
    event.preventDefault();
    const password = document.getElementById('adminLoginPassword');
    const error = document.getElementById('adminAuthError');
    if (!(password instanceof HTMLInputElement)) return;
    if (error) error.textContent = '';
    const response = await fetchImpl(`${apiBaseUrl}/api/admin/auth/login`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ login_identity: managerIdentity, password: password.value }),
    }).catch(() => null);
    password.value = '';
    if (!response?.ok) {
      if (error) error.textContent = adminLoginErrorMessage(response?.status || 0);
      return;
    }
    await bootstrap();
  }

  function bind() {
    document.getElementById('adminAuthForm')?.addEventListener('submit', login);
    document.getElementById('managerUnlockBtn')?.addEventListener('click', openManagerLogin);
    document.getElementById('managerLockBtn')?.addEventListener('click', () => { void lockManager(); });
    document.getElementById('adminAuthCancel')?.addEventListener('click', closeManagerLogin);
    ['pointerdown', 'keydown'].forEach(eventName => {
      document.addEventListener?.(eventName, scheduleIdleLock, { passive: true });
    });
    void bootstrap();
  }

  return { bind, bootstrap, openManagerLogin, lockManager };
}
