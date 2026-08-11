// @ts-check

/** One device request may never outlive this bound. */
const DEVICE_REQUEST_TIMEOUT_MS = 5000;
/** First auto-retry delay while the service is still starting. */
const RETRY_BASE_MS = 1000;
/** Auto-retry never backs off further than this, so recovery stays visible. */
const RETRY_MAX_MS = 30000;

/** @param {number} status */
export function deviceProvisioningErrorMessage(status) {
  if (status === 0) return '無法連線到本機 API，請確認服務已啟動。';
  if (status === 401) return '裝置金鑰或憑證不正確，請重新輸入。';
  if (status === 403) return '此裝置憑證已停用，請由主管重新配置。';
  if (status === 429) return '嘗試次數過多，請稍後再試。';
  return '裝置設定失敗，請確認 provisioning 檔案仍在有效期限內。';
}

/**
 * Kiosk device identity observes the Device Verification Boundary: every
 * request is bounded, and the surface always rests in one of three visible
 * outcomes — authenticated, service starting (auto-retrying), or device not
 * provisioned (needs a person).  A service that has not finished starting must
 * not be presented as a credential problem, or staff will type provisioning
 * secrets at a kiosk whose device registration was never in question.
 *
 * @param {{
 *   apiBaseUrl: string,
 *   onAuthenticated: (principal?: any) => Promise<void>,
 *   fetchImpl?: typeof fetch,
 *   timers?: { setTimeout: typeof setTimeout, clearTimeout: typeof clearTimeout }
 * }} options
 */
export function createDeviceIdentityController({
  apiBaseUrl,
  onAuthenticated,
  fetchImpl = fetch,
  timers = { setTimeout, clearTimeout },
}) {
  let retryDelayMs = RETRY_BASE_MS;
  /** @type {any} */
  let scheduledRetry = null;

  // Browser timer functions are receiver-sensitive Web APIs. Keeping them in
  // the injectable `timers` object and invoking them as methods changes `this`
  // to that object, which Chromium rejects with "Illegal invocation" before a
  // valid device session can dismiss the verification boundary.
  /** @param {TimerHandler} run @param {number} delay */
  const schedule = (run, delay) => Reflect.apply(timers.setTimeout, globalThis, [run, delay]);
  /** @param {any} handle */
  const cancel = (handle) => Reflect.apply(timers.clearTimeout, globalThis, [handle]);

  const backdrop = () => document.getElementById('kioskDeviceAuthBackdrop');

  /** @param {boolean} visible */
  function setVisible(visible) {
    const element = backdrop();
    if (element) element.style.display = visible ? 'flex' : 'none';
    element?.setAttribute?.('aria-hidden', visible ? 'false' : 'true');
  }

  /** @param {string} message */
  function setError(message) {
    const error = document.getElementById('kioskDeviceAuthError');
    if (error) error.textContent = message.slice(0, 180);
  }

  /** @param {string} message */
  function setStatus(message) {
    const status = document.getElementById('kioskDeviceAuthStatus');
    if (status) status.textContent = message;
  }

  /** @param {boolean} pending */
  function setPending(pending) {
    const submit = document.getElementById('kioskDeviceAuthSubmit');
    if (submit && 'disabled' in submit) submit.disabled = pending;
    setStatus(pending ? '正在驗證裝置身分…' : '');
  }

  function cancelScheduledRetry() {
    if (scheduledRetry === null) return;
    cancel(scheduledRetry);
    scheduledRetry = null;
  }

  /**
   * Resolve or reject within DEVICE_REQUEST_TIMEOUT_MS whatever the transport
   * does.  The abort signal is the polite path; the deadline is the guarantee.
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
          deadline = schedule(() => {
            controller.abort();
            reject(new Error('device request timed out'));
          }, DEVICE_REQUEST_TIMEOUT_MS);
        }),
      ]);
    } finally {
      if (deadline !== null) cancel(deadline);
    }
  }

  /** The device registration is not in question; the service has not answered. */
  function showServiceStarting() {
    setVisible(true);
    setError('');
    setStatus('服務啟動中，將自動重試；裝置設定不需要更動。');
    cancelScheduledRetry();
    const delay = retryDelayMs;
    retryDelayMs = Math.min(retryDelayMs * 2, RETRY_MAX_MS);
    scheduledRetry = schedule(() => {
      scheduledRetry = null;
      void bootstrap();
    }, delay);
  }

  async function bootstrap() {
    cancelScheduledRetry();
    /** @type {any} */
    let response;
    try {
      response = await fetchBounded(`${apiBaseUrl}/api/device/auth/session`, {
        credentials: 'same-origin',
      });
    } catch {
      showServiceStarting();
      return false;
    }

    if (!response?.ok) {
      setStatus('');
      setVisible(true);
      document.getElementById('kioskDeviceKeyId')?.focus?.();
      return false;
    }

    /** @type {any} */
    let body = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    if (body?.authenticated !== true || !body?.device_id) {
      setStatus('');
      setVisible(true);
      return false;
    }

    retryDelayMs = RETRY_BASE_MS;
    setError('');
    setStatus('');
    await onAuthenticated(body);
    setVisible(false);
    return true;
  }

  /** @param {SubmitEvent} event */
  async function provision(event) {
    event.preventDefault();
    const keyId = document.getElementById('kioskDeviceKeyId');
    const credential = document.getElementById('kioskDeviceCredential');
    if (!(keyId instanceof HTMLInputElement) || !(credential instanceof HTMLInputElement)) return;
    const normalizedKeyId = keyId.value.trim();
    if (!normalizedKeyId || !credential.value) {
      setError('請輸入 provisioning 檔案中的 key_id 與 credential。');
      return;
    }
    cancelScheduledRetry();
    setError('');
    setPending(true);
    let requestBody = JSON.stringify({ key_id: normalizedKeyId, credential: credential.value });
    credential.value = '';
    /** @type {any} */
    let response = null;
    try {
      response = await fetchBounded(`${apiBaseUrl}/api/device/auth/session`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: requestBody,
      });
    } catch {
      response = null;
    } finally {
      // The request is bounded, so the form is always handed back to the operator.
      requestBody = '';
      setPending(false);
    }
    if (!response?.ok) {
      setError(deviceProvisioningErrorMessage(response?.status || 0));
      return;
    }
    const body = await response.json();
    keyId.value = '';
    await onAuthenticated({ ...body, authenticated: true, auth_method: 'device_session' });
    setVisible(false);
  }

  function bind() {
    document.getElementById('kioskDeviceAuthForm')?.addEventListener('submit', provision);
    void bootstrap();
  }

  return { bind, bootstrap, provision };
}
