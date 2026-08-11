import { beforeEach, describe, expect, it, vi } from 'vitest';

import { adminHeaders, createAdminAuthController } from '../../admin/features/auth/adminAuth.js';

class StubElement {
  textContent = '';
  disabled = false;
  readonly style: Record<string, string> = {};
  private readonly listeners = new Map<string, Array<(event: unknown) => unknown>>();

  addEventListener(type: string, listener: (event: unknown) => unknown) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  async dispatch(type: string, event: unknown = {}) {
    for (const listener of this.listeners.get(type) ?? []) await listener(event);
  }
}

const elements = new Map<string, StubElement>();

function element(id: string): StubElement {
  const existing = elements.get(id);
  if (existing) return existing;
  const created = new StubElement();
  elements.set(id, created);
  return created;
}

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, headers: { get: () => '' }, json: async () => body };
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
    /** Fire everything due within `ms`, letting each callback settle. */
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

function controllerWith(fetchImpl: unknown, overrides: Record<string, unknown> = {}) {
  return createAdminAuthController({
    apiBaseUrl: 'http://api',
    onAuthenticated: vi.fn(async () => {}),
    onPrincipal: vi.fn(),
    fetchImpl: fetchImpl as typeof fetch,
    ...overrides,
  });
}

beforeEach(() => {
  elements.clear();
  Object.assign(globalThis, {
    document: { getElementById: (id: string) => element(id) },
  });
});

describe('device-authenticated Admin access', () => {
  it('adds no alternate credential to requests', () => {
    expect(adminHeaders()).toEqual({});
    expect(adminHeaders({ 'X-Trace': 'abc' })).toEqual({ 'X-Trace': 'abc' });
  });

  it('uses only the device-backed /me endpoint and opens Admin directly', async () => {
    const onAuthenticated = vi.fn(async () => {});
    const onPrincipal = vi.fn();
    const fetchImpl = vi.fn(async (_url: string, _options?: RequestInit) => jsonResponse({
      principal: { user_id: 'device-admin', permissions: ['*'], auth_method: 'device_admin' },
      access: 'device_admin',
    }));

    await controllerWith(fetchImpl, { onAuthenticated, onPrincipal }).bootstrap();

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const firstCall = fetchImpl.mock.calls[0];
    expect(firstCall).toBeDefined();
    if (!firstCall) throw new Error('missing Admin bootstrap request');
    expect(String(firstCall[0])).toBe('http://api/api/admin/auth/me');
    expect(firstCall[1]).toMatchObject({ credentials: 'same-origin' });
    expect(onPrincipal).toHaveBeenCalledWith(expect.objectContaining({ permissions: ['*'] }));
    expect(onAuthenticated).toHaveBeenCalledTimes(1);
    expect(element('adminAuthBackdrop').style.display).toBe('none');
    expect(element('adminAccessStatus').textContent).toBe('裝置已驗證');
  });

  it('shows a recoverable device-verification error without a password prompt', async () => {
    const onAuthenticated = vi.fn(async () => {});
    const onPrincipal = vi.fn();
    const fetchImpl = vi.fn(async (_url: string, _options?: RequestInit) => jsonResponse({}, false, 401));

    await controllerWith(fetchImpl, { onAuthenticated, onPrincipal }).bootstrap();

    expect(onAuthenticated).not.toHaveBeenCalled();
    expect(onPrincipal).toHaveBeenCalledWith(null);
    expect(element('adminAuthBackdrop').style.display).toBe('flex');
    expect(element('adminAuthMessage').textContent).toContain('裝置尚未完成驗證');
    expect(element('adminAccessStatus').textContent).toBe('裝置未驗證');
  });

  it('reaches a bounded outcome when the service accepts the connection but never answers', async () => {
    const onPrincipal = vi.fn();
    const timers = createTestTimers();
    const fetchImpl = vi.fn(() => new Promise<never>(() => {}));
    const controller = controllerWith(fetchImpl, { onPrincipal, timers: timers.timers });

    const settled = controller.bootstrap();
    await timers.advance(5000);
    await timers.advance(5000);
    await settled;

    expect(element('adminAccessStatus').textContent).toBe('服務啟動中');
    expect(element('adminAuthRetry').disabled).toBe(false);
    expect(timers.scheduled).toBeGreaterThan(0);
    expect(onPrincipal).toHaveBeenCalledWith(null);
  });

  it('never reports a starting service as an unauthorised device', async () => {
    const timers = createTestTimers();
    const fetchImpl = vi.fn(() => new Promise<never>(() => {}));
    const controller = controllerWith(fetchImpl, { timers: timers.timers });

    const settled = controller.bootstrap();
    await timers.advance(5000);
    await timers.advance(5000);
    await settled;

    const message = element('adminAuthMessage').textContent;
    expect(message).toContain('自動重試');
    expect(message).not.toContain('重新註冊');
    expect(element('adminAccessStatus').textContent).not.toBe('裝置未驗證');
  });

  it('recovers on its own once the service starts answering', async () => {
    let meAttempts = 0;
    const onAuthenticated = vi.fn(async () => {});
    const timers = createTestTimers();
    const fetchImpl = vi.fn((url: string) => {
      if (String(url).endsWith('/ready')) return new Promise<never>(() => {});
      meAttempts += 1;
      if (meAttempts === 1) return new Promise<never>(() => {});
      return Promise.resolve(jsonResponse({
        principal: { permissions: ['*'], auth_method: 'device_admin' },
      }));
    });
    const controller = controllerWith(fetchImpl, { onAuthenticated, timers: timers.timers });

    const settled = controller.bootstrap();
    await timers.advance(5000);
    await timers.advance(5000);
    await settled;
    await timers.advance(1000);

    expect(meAttempts).toBe(2);
    expect(onAuthenticated).toHaveBeenCalledTimes(1);
    expect(element('adminAccessStatus').textContent).toBe('裝置已驗證');
    expect(element('adminAuthBackdrop').style.display).toBe('none');
  });

  it('keeps an unauthorised device terminal instead of retrying it forever', async () => {
    const timers = createTestTimers();
    const fetchImpl = vi.fn(async () => jsonResponse({}, false, 403));
    const controller = controllerWith(fetchImpl, { timers: timers.timers });

    await controller.bootstrap();

    expect(element('adminAccessStatus').textContent).toBe('裝置未驗證');
    expect(element('adminAuthMessage').textContent).toContain('沒有管理後台權限');
    expect(element('adminAuthRetry').disabled).toBe(false);
    expect(timers.scheduled).toBe(0);
  });

  it('retries device verification from the blocking state', async () => {
    let attempts = 0;
    const onAuthenticated = vi.fn(async () => {});
    const fetchImpl = vi.fn(async (_url: string, _options?: RequestInit) => {
      attempts += 1;
      if (attempts === 1) return jsonResponse({}, false, 401);
      return jsonResponse({ principal: { permissions: ['*'], auth_method: 'device_admin' } });
    });
    const controller = controllerWith(fetchImpl, { onAuthenticated });
    controller.bind();
    await Promise.resolve();
    await Promise.resolve();

    await element('adminAuthRetry').dispatch('click');

    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(onAuthenticated).toHaveBeenCalledTimes(1);
    expect(element('adminAuthBackdrop').style.display).toBe('none');
  });
});
