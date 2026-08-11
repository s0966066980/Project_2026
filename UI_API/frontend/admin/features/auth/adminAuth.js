// @ts-check

/** @param {Record<string, string>} [extra] @returns {Record<string, string>} */
export function adminHeaders(extra = {}) {
  return extra;
}

/** One verification attempt may never outlive this bound. */
const VERIFY_TIMEOUT_MS = 5000;
/** First auto-retry delay while the service is still starting. */
const RETRY_BASE_MS = 1000;
/** Auto-retry never backs off further than this, so recovery stays visible. */
const RETRY_MAX_MS = 30000;

const READINESS_LABELS = {
  database: '資料庫',
  migration: '資料庫結構',
  commercial_scope: '門市設定',
  shared_infrastructure: '共用基礎設施',
};

/**
 * Admin access is derived exclusively from the device session cookie.  There is
 * deliberately no second password/session state in the browser.
 *
 * Verification observes the Device Verification Boundary: every attempt is
 * bounded, and the surface always rests in one of three visible outcomes —
 * verified, service starting (auto-retrying), or device unauthorised (needs a
 * person).  A service that is merely warming up must never be reported as an
 * unauthorised device, because that sends staff to re-provision hardware that
 * is working.
 *
 * @param {{
 *   apiBaseUrl: string,
 *   onAuthenticated: (principal?: any) => Promise<void>,
 *   onPrincipal?: (principal: any) => void,
 *   fetchImpl?: typeof fetch,
 *   timers?: { setTimeout: typeof setTimeout, clearTimeout: typeof clearTimeout }
 * }} options
 */
export function createAdminAuthController({
  apiBaseUrl,
  onAuthenticated,
  onPrincipal = () => {},
  fetchImpl = fetch,
  timers = { setTimeout, clearTimeout },
}) {
  /** Only the newest attempt may write to the surface. */
  let currentAttempt = 0;
  let retryDelayMs = RETRY_BASE_MS;
  /** @type {any} */
  let scheduledRetry = null;

  /** @param {string} id */
  const byId = id => document.getElementById(id);

  /** @param {string} message */
  function setAccessStatus(message) {
    const status = byId('adminAccessStatus');
    if (status) status.textContent = message;
  }

  /** @param {string} message */
  function setAuthMessage(message) {
    const target = byId('adminAuthMessage');
    if (target) target.textContent = message;
  }

  /** @param {'flex'|'none'} display */
  function setBackdrop(display) {
    const backdrop = byId('adminAuthBackdrop');
    if (backdrop) backdrop.style.display = display;
  }

  /** @param {boolean} disabled */
  function setRetryDisabled(disabled) {
    const retry = /** @type {HTMLButtonElement|null} */ (byId('adminAuthRetry'));
    if (retry) retry.disabled = disabled;
  }

  function cancelScheduledRetry() {
    if (scheduledRetry === null) return;
    timers.clearTimeout(scheduledRetry);
    scheduledRetry = null;
  }

  /**
   * Resolve or reject within VERIFY_TIMEOUT_MS whatever the transport does.
   * The abort signal is the polite path; the deadline is the guarantee.
   *
   * @param {string} url
   * @param {RequestInit} [options]
   */
  async function fetchBounded(url, options = {}) {
    const controller = new AbortController();
    /** @type {any} */
    let deadline = null;
    try {
      return await Promise.race([
        fetchImpl(url, { ...options, signal: controller.signal }),
        new Promise((_resolve, reject) => {
          deadline = timers.setTimeout(() => {
            controller.abort();
            reject(new Error('device verification timed out'));
          }, VERIFY_TIMEOUT_MS);
        }),
      ]);
    } finally {
      if (deadline !== null) timers.clearTimeout(deadline);
    }
  }

  /**
   * Name what the server itself says is not ready, so "service starting" is a
   * report rather than a guess.  A silent server tells us nothing, which is
   * itself the common case while startup work blocks the port.
   *
   * @returns {Promise<string>}
   */
  async function readinessReason() {
    try {
      const response = await fetchBounded(`${apiBaseUrl}/ready`, { credentials: 'same-origin' });
      const body = await (/** @type {any} */ (response)).json();
      if (body?.ready === true) return '';
      const checks = body?.required_checks || {};
      const pending = Object.keys(checks)
        .filter(name => !['ok', 'skipped'].includes(String(checks[name]?.status)))
        .map(name => READINESS_LABELS[/** @type {keyof typeof READINESS_LABELS} */ (name)] || name);
      return pending.join('、');
    } catch {
      return '';
    }
  }

  function scheduleRetry() {
    cancelScheduledRetry();
    const delay = retryDelayMs;
    retryDelayMs = Math.min(retryDelayMs * 2, RETRY_MAX_MS);
    scheduledRetry = timers.setTimeout(() => {
      scheduledRetry = null;
      void bootstrap();
    }, delay);
  }

  /** The device is fine; the service has not finished starting.  Keep retrying. */
  async function showServiceStarting() {
    onPrincipal(null);
    setAccessStatus('服務啟動中');
    const reason = await readinessReason();
    setAuthMessage(
      reason
        ? `服務正在啟動（${reason} 尚未就緒），畫面會自動重試，不需要重新註冊裝置。`
        : '服務尚未回應，畫面會自動重試。裝置設定不需要更動；若持續無法連線，請確認後端狀態。',
    );
    setBackdrop('flex');
    setRetryDisabled(false);
    scheduleRetry();
  }

  /** The service answered and refused this device.  Only a person can fix it. */
  function showVerificationFailure(status = 0) {
    onPrincipal(null);
    setAccessStatus('裝置未驗證');
    setAuthMessage(
      status === 403
        ? '此裝置沒有管理後台權限，請回到裝置設定重新註冊。'
        : '裝置尚未完成驗證，請先前往裝置設定完成註冊，再回來重試。',
    );
    setBackdrop('flex');
    setRetryDisabled(false);
  }

  async function bootstrap() {
    cancelScheduledRetry();
    const attempt = ++currentAttempt;
    const superseded = () => attempt !== currentAttempt;

    setRetryDisabled(true);
    setAccessStatus('正在驗證裝置');

    /** @type {any} */
    let response;
    try {
      response = await fetchBounded(`${apiBaseUrl}/api/admin/auth/me`, {
        headers: adminHeaders(),
        credentials: 'same-origin',
      });
    } catch {
      if (superseded()) return;
      await showServiceStarting();
      return;
    }

    if (superseded()) return;

    if (response.status === 401 || response.status === 403) {
      showVerificationFailure(response.status);
      return;
    }
    if (!response.ok) {
      // 5xx and anything else the service produced while coming up is transient.
      await showServiceStarting();
      return;
    }

    /** @type {any} */
    let principal = null;
    try {
      const body = await response.json();
      principal = body?.principal || null;
    } catch {
      principal = null;
    }
    if (superseded()) return;
    if (!principal) {
      showVerificationFailure(401);
      return;
    }

    retryDelayMs = RETRY_BASE_MS;
    onPrincipal(principal);
    setAccessStatus('裝置已驗證');
    setBackdrop('none');
    setRetryDisabled(false);
    await onAuthenticated(principal);
  }

  function bind() {
    byId('adminAuthRetry')?.addEventListener('click', () => {
      retryDelayMs = RETRY_BASE_MS;
      return bootstrap();
    });
    void bootstrap();
  }

  return { bind, bootstrap };
}
