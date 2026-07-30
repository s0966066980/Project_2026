import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createDeviceIdentityController,
  deviceProvisioningErrorMessage,
} from '../../kiosk/features/bootstrap/deviceIdentity.js';

class FakeInput {
  value = '';
  disabled = false;
  focus = vi.fn();
}

afterEach(() => vi.unstubAllGlobals());

function fixture() {
  const backdrop = { style: { display: '' }, setAttribute: vi.fn() };
  const keyId = new FakeInput();
  const credential = new FakeInput();
  const error = { textContent: '' };
  const status = { textContent: '' };
  const submitButton = new FakeInput();
  let submit: ((event: { preventDefault(): void }) => Promise<void>) | undefined;
  const form = {
    addEventListener: (_type: string, handler: typeof submit) => { submit = handler; },
  };
  const elements: Record<string, unknown> = {
    kioskDeviceAuthBackdrop: backdrop,
    kioskDeviceAuthForm: form,
    kioskDeviceKeyId: keyId,
    kioskDeviceCredential: credential,
    kioskDeviceAuthError: error,
    kioskDeviceAuthStatus: status,
    kioskDeviceAuthSubmit: submitButton,
  };
  vi.stubGlobal('HTMLInputElement', FakeInput);
  vi.stubGlobal('document', { getElementById: (id: string) => elements[id] ?? null });
  return { backdrop, keyId, credential, error, submitButton, getSubmit: () => submit };
}

describe('Kiosk device identity bootstrap', () => {
  it('keeps the Kiosk locked until a current database-owned session exists', async () => {
    const dom = fixture();
    const onAuthenticated = vi.fn(async () => undefined);
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response('{"detail":"device authentication required"}', { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        authenticated: true,
        device_id: 'device-1',
        store_id: 'store-1',
        tenant_id: 'tenant-1',
      }), { status: 200 }));
    const controller = createDeviceIdentityController({ apiBaseUrl: '', onAuthenticated, fetchImpl });

    expect(await controller.bootstrap()).toBe(false);
    expect(dom.backdrop.style.display).toBe('flex');
    expect(onAuthenticated).not.toHaveBeenCalled();
    expect(await controller.bootstrap()).toBe(true);
    expect(dom.backdrop.style.display).toBe('none');
    expect(onAuthenticated).toHaveBeenCalledOnce();
  });

  it('exchanges the one-time credential for a cookie session and clears both inputs', async () => {
    const dom = fixture();
    dom.keyId.value = 'dev_key';
    dom.credential.value = 'one-time-device-secret';
    const onAuthenticated = vi.fn(async () => undefined);
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      device_id: 'device-1', store_id: 'store-1', tenant_id: 'tenant-1', expires_at: 'later',
    }), { status: 200 }));
    const controller = createDeviceIdentityController({ apiBaseUrl: '', onAuthenticated, fetchImpl });

    await controller.provision({ preventDefault: vi.fn() } as unknown as SubmitEvent);

    expect(fetchImpl).toHaveBeenCalledWith('/api/device/auth/session', expect.objectContaining({
      method: 'POST',
      credentials: 'same-origin',
      body: JSON.stringify({ key_id: 'dev_key', credential: 'one-time-device-secret' }),
    }));
    expect(dom.keyId.value).toBe('');
    expect(dom.credential.value).toBe('');
    expect(dom.backdrop.style.display).toBe('none');
    expect(onAuthenticated).toHaveBeenCalledOnce();
  });

  it('uses bounded operator-facing errors without retaining the credential', async () => {
    const dom = fixture();
    dom.keyId.value = 'dev_key';
    dom.credential.value = 'invalid-device-secret';
    const controller = createDeviceIdentityController({
      apiBaseUrl: '',
      onAuthenticated: vi.fn(),
      fetchImpl: vi.fn().mockResolvedValue(new Response('{}', { status: 401 })),
    });

    await controller.provision({ preventDefault: vi.fn() } as unknown as SubmitEvent);

    expect(dom.credential.value).toBe('');
    expect(dom.error.textContent).toBe(deviceProvisioningErrorMessage(401));
  });
});
