import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createDeviceIdentityController,
  deviceProvisioningErrorMessage,
} from '../../kiosk/features/bootstrap/deviceIdentity.js';

class StubElement {
  textContent = '';
  disabled = false;
  readonly style: Record<string, string> = {};
  private readonly attributes = new Map<string, string>();
  private readonly listeners = new Map<string, Array<(event: unknown) => unknown>>();
  focus = vi.fn();

  setAttribute(name: string, value: string) { this.attributes.set(name, value); }
  getAttribute(name: string) { return this.attributes.get(name) ?? null; }

  addEventListener(type: string, listener: (event: unknown) => unknown) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  async dispatch(type: string, event: unknown) {
    for (const listener of this.listeners.get(type) ?? []) await listener(event);
  }
}

class StubInput extends StubElement {
  value = '';
}

const elements = new Map<string, StubElement>();

function element(id: string): StubElement {
  const existing = elements.get(id);
  if (existing) return existing;
  const created = id === 'kioskDeviceKeyId' || id === 'kioskDeviceCredential' ? new StubInput() : new StubElement();
  elements.set(id, created);
  return created;
}

function input(id: string): StubInput {
  return element(id) as StubInput;
}

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body };
}

/**
 * Drives the controller's own clock so a bounded wait can be observed without
 * spending it.  Every pending deadline fires in schedule order.
 */
function createTestTimers() {
  let sequence = 0;
  const pending = new Map<number, { at: number; run: () => void }>();
  let now = 0;
  return {
    timers: {
      setTimeout: ((run: () => void, delay = 0) => {
        const handle = ++sequence;
        pending.set(handle, { at: now + delay, run });
        return handle as unknown as ReturnType<typeof setTimeout>;
      }) as unknown as typeof setTimeout,
      clearTimeout: ((handle: unknown) => {
        pending.delete(handle as number);
      }) as unknown as typeof clearTimeout,
    },
    async advance(ms: number) {
      now += ms;
      for (let guard = 0; guard < 50; guard += 1) {
        const due = [...pending.entries()]
          .filter(([, entry]) => entry.at <= now)
          .sort((left, right) => left[1].at - right[1].at);
        if (due.length === 0) break;
        for (const [handle, entry] of due) {
          pending.delete(handle);
          entry.run();
        }
        for (let tick = 0; tick < 8; tick += 1) await Promise.resolve();
      }
    },
    get scheduled() {
      return pending.size;
    },
  };
}

beforeEach(() => {
  elements.clear();
  Object.assign(globalThis, {
    document: { getElementById: (id: string) => element(id) },
    // provision() narrows with `instanceof HTMLInputElement`, so the stub inputs must
    // satisfy that check for the happy path to be reachable at all.
    HTMLInputElement: StubInput,
  });
});

describe('device provisioning error messages', () => {
  it('names the cause the operator can act on', () => {
    expect(deviceProvisioningErrorMessage(0)).toContain('無法連線');
    expect(deviceProvisioningErrorMessage(401)).toContain('金鑰或憑證不正確');
    expect(deviceProvisioningErrorMessage(403)).toContain('已停用');
    expect(deviceProvisioningErrorMessage(429)).toContain('嘗試次數過多');
  });

  it('falls back to a provisioning hint for unexpected statuses', () => {
    expect(deviceProvisioningErrorMessage(500)).toContain('有效期限');
  });
});

describe('device identity bootstrap', () => {
  it('invokes browser timers with the global receiver', async () => {
    let sequence = 0;
    const timers = {
      setTimeout: (function(this: unknown, _run: TimerHandler, _delay?: number, ..._args: unknown[]) {
        expect(this).toBe(globalThis);
        return ++sequence as unknown as ReturnType<typeof setTimeout>;
      }) as unknown as typeof setTimeout,
      clearTimeout: (function(this: unknown, _handle: unknown) {
        expect(this).toBe(globalThis);
      }) as unknown as typeof clearTimeout,
    };
    const controller = createDeviceIdentityController({
      apiBaseUrl: 'http://api',
      onAuthenticated: vi.fn(async () => {}),
      fetchImpl: (async () => jsonResponse({ authenticated: true, device_id: 'device-browser' })) as unknown as typeof fetch,
      timers,
    });

    await expect(controller.bootstrap()).resolves.toBe(true);
  });

  it('authenticates and hides the prompt when the session is valid', async () => {
    const onAuthenticated = vi.fn(async () => {});
    const fetchImpl = vi.fn(async () => jsonResponse({ authenticated: true, device_id: 'device-1' }));
    const controller = createDeviceIdentityController({
      apiBaseUrl: 'http://api',
      onAuthenticated,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await expect(controller.bootstrap()).resolves.toBe(true);
    expect(onAuthenticated).toHaveBeenCalledWith({ authenticated: true, device_id: 'device-1' });
    expect(element('kioskDeviceAuthBackdrop').style.display).toBe('none');
  });

  // An unreachable service says nothing about whether this device is registered,
  // so it must not send staff to the provisioning field.
  it('treats an unreachable service as starting rather than a credential problem', async () => {
    const timers = createTestTimers();
    const controller = createDeviceIdentityController({
      apiBaseUrl: 'http://api',
      onAuthenticated: vi.fn(async () => {}),
      fetchImpl: (async () => { throw new Error('offline'); }) as unknown as typeof fetch,
      timers: timers.timers,
    });

    await expect(controller.bootstrap()).resolves.toBe(false);
    expect(element('kioskDeviceAuthBackdrop').style.display).toBe('flex');
    expect(element('kioskDeviceAuthStatus').textContent).toContain('服務啟動中');
    expect(element('kioskDeviceKeyId').focus).not.toHaveBeenCalled();
    expect(timers.scheduled).toBeGreaterThan(0);
  });

  it('reaches a bounded outcome when the service accepts the connection but never answers', async () => {
    const timers = createTestTimers();
    const controller = createDeviceIdentityController({
      apiBaseUrl: 'http://api',
      onAuthenticated: vi.fn(async () => {}),
      fetchImpl: (() => new Promise<never>(() => {})) as unknown as typeof fetch,
      timers: timers.timers,
    });

    const settled = controller.bootstrap();
    await timers.advance(5000);

    await expect(settled).resolves.toBe(false);
    expect(element('kioskDeviceAuthStatus').textContent).toContain('服務啟動中');
    expect(timers.scheduled).toBeGreaterThan(0);
  });

  it('recovers on its own once the service starts answering', async () => {
    let attempts = 0;
    const onAuthenticated = vi.fn(async () => {});
    const timers = createTestTimers();
    const controller = createDeviceIdentityController({
      apiBaseUrl: 'http://api',
      onAuthenticated,
      fetchImpl: (() => {
        attempts += 1;
        if (attempts === 1) return new Promise<never>(() => {});
        return Promise.resolve(jsonResponse({ authenticated: true, device_id: 'device-9' }));
      }) as unknown as typeof fetch,
      timers: timers.timers,
    });

    const settled = controller.bootstrap();
    await timers.advance(5000);
    await settled;
    await timers.advance(1000);

    expect(attempts).toBe(2);
    expect(onAuthenticated).toHaveBeenCalledTimes(1);
    expect(element('kioskDeviceAuthBackdrop').style.display).toBe('none');
  });

  // A 200 that does not actually authenticate must not be treated as a session.
  it('prompts when the response is not an authenticated device', async () => {
    const onAuthenticated = vi.fn(async () => {});
    const controller = createDeviceIdentityController({
      apiBaseUrl: 'http://api',
      onAuthenticated,
      fetchImpl: (async () => jsonResponse({ authenticated: false })) as unknown as typeof fetch,
    });

    await expect(controller.bootstrap()).resolves.toBe(false);
    expect(onAuthenticated).not.toHaveBeenCalled();
    expect(element('kioskDeviceAuthBackdrop').style.display).toBe('flex');
  });
});

describe('device provisioning', () => {
  const submitEvent = () => ({ preventDefault: vi.fn() });

  it('refuses to send an incomplete provisioning pair', async () => {
    const fetchImpl = vi.fn();
    const controller = createDeviceIdentityController({
      apiBaseUrl: 'http://api',
      onAuthenticated: vi.fn(async () => {}),
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    input('kioskDeviceKeyId').value = '   ';
    input('kioskDeviceCredential').value = 'secret';

    await controller.provision(submitEvent() as unknown as SubmitEvent);

    expect(fetchImpl).not.toHaveBeenCalled();
    expect(element('kioskDeviceAuthError').textContent).toContain('key_id');
  });

  it('clears the credential from the field before the request resolves', async () => {
    let credentialDuringRequest = 'unset';
    const fetchImpl = vi.fn(async () => {
      credentialDuringRequest = input('kioskDeviceCredential').value;
      return jsonResponse({ device_id: 'device-2' });
    });
    const controller = createDeviceIdentityController({
      apiBaseUrl: 'http://api',
      onAuthenticated: vi.fn(async () => {}),
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    input('kioskDeviceKeyId').value = 'key-1';
    input('kioskDeviceCredential').value = 'secret';

    await controller.provision(submitEvent() as unknown as SubmitEvent);

    expect(credentialDuringRequest).toBe('');
  });

  it('authenticates and clears both fields on success', async () => {
    const onAuthenticated = vi.fn(async () => {});
    const controller = createDeviceIdentityController({
      apiBaseUrl: 'http://api',
      onAuthenticated,
      fetchImpl: (async () => jsonResponse({ device_id: 'device-2' })) as unknown as typeof fetch,
    });
    input('kioskDeviceKeyId').value = 'key-1';
    input('kioskDeviceCredential').value = 'secret';

    await controller.provision(submitEvent() as unknown as SubmitEvent);

    expect(onAuthenticated).toHaveBeenCalledWith({
      device_id: 'device-2',
      authenticated: true,
      auth_method: 'device_session',
    });
    expect(input('kioskDeviceKeyId').value).toBe('');
    expect(element('kioskDeviceAuthBackdrop').style.display).toBe('none');
    expect(element('kioskDeviceAuthSubmit').disabled).toBe(false);
  });

  it('reports the rejection reason and re-enables the form', async () => {
    const controller = createDeviceIdentityController({
      apiBaseUrl: 'http://api',
      onAuthenticated: vi.fn(async () => {}),
      fetchImpl: (async () => jsonResponse({}, false, 401)) as unknown as typeof fetch,
    });
    input('kioskDeviceKeyId').value = 'key-1';
    input('kioskDeviceCredential').value = 'wrong';

    await controller.provision(submitEvent() as unknown as SubmitEvent);

    expect(element('kioskDeviceAuthError').textContent).toBe(deviceProvisioningErrorMessage(401));
    expect(element('kioskDeviceAuthSubmit').disabled).toBe(false);
    expect(element('kioskDeviceAuthStatus').textContent).toBe('');
  });

  it('binds the form so a submit provisions the device', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ authenticated: true, device_id: 'device-3' }));
    const controller = createDeviceIdentityController({
      apiBaseUrl: 'http://api',
      onAuthenticated: vi.fn(async () => {}),
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    controller.bind();
    input('kioskDeviceKeyId').value = 'key-1';
    input('kioskDeviceCredential').value = 'secret';
    await element('kioskDeviceAuthForm').dispatch('submit', submitEvent());

    expect(fetchImpl).toHaveBeenCalledWith(
      'http://api/api/device/auth/session',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
