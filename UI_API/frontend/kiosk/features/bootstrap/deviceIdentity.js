// @ts-check

/** @param {number} status */
export function deviceProvisioningErrorMessage(status) {
  if (status === 0) return '無法連線到本機 API，請確認服務已啟動。';
  if (status === 401) return '裝置金鑰或憑證不正確，請重新輸入。';
  if (status === 403) return '此裝置憑證已停用，請由主管重新配置。';
  if (status === 429) return '嘗試次數過多，請稍後再試。';
  return '裝置設定失敗，請確認 provisioning 檔案仍在有效期限內。';
}

/**
 * @param {{
 *   apiBaseUrl: string,
 *   onAuthenticated: (principal?: any) => Promise<void>,
 *   fetchImpl?: typeof fetch,
 * }} options
 */
export function createDeviceIdentityController({
  apiBaseUrl,
  onAuthenticated,
  fetchImpl = fetch,
}) {
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

  /** @param {boolean} pending */
  function setPending(pending) {
    const submit = document.getElementById('kioskDeviceAuthSubmit');
    if (submit && 'disabled' in submit) submit.disabled = pending;
    const status = document.getElementById('kioskDeviceAuthStatus');
    if (status) status.textContent = pending ? '正在驗證裝置身分…' : '';
  }

  async function bootstrap() {
    const response = await fetchImpl(`${apiBaseUrl}/api/device/auth/session`, {
      credentials: 'same-origin',
    }).catch(() => null);
    if (!response?.ok) {
      setVisible(true);
      document.getElementById('kioskDeviceKeyId')?.focus?.();
      return false;
    }
    const body = await response.json();
    if (body?.authenticated !== true || !body?.device_id) {
      setVisible(true);
      return false;
    }
    setError('');
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
    setError('');
    setPending(true);
    let requestBody = JSON.stringify({ key_id: normalizedKeyId, credential: credential.value });
    credential.value = '';
    const response = await fetchImpl(`${apiBaseUrl}/api/device/auth/session`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: requestBody,
    }).catch(() => null);
    requestBody = '';
    setPending(false);
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
