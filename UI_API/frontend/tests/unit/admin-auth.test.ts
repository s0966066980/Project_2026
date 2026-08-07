import { beforeEach, describe, expect, it, vi } from 'vitest';

import { adminHeaders, createAdminAuthController } from '../../admin/features/auth/adminAuth.js';

class StubElement {
  textContent = '';
  readonly style: Record<string, string> = {};
  private readonly flags = new Set<string>();
  private readonly listeners = new Map<string, Array<(event: unknown) => unknown>>();
  focus = vi.fn();

  toggleAttribute(name: string, force?: boolean) {
    const next = force ?? !this.flags.has(name);
    if (next) this.flags.add(name);
    else this.flags.delete(name);
    return next;
  }

  hasAttribute(name: string) { return this.flags.has(name); }

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
const documentListeners: string[] = [];

function element(id: string): StubElement {
  const existing = elements.get(id);
  if (existing) return existing;
  const created = id === 'adminLoginPassword' ? new StubInput() : new StubElement();
  elements.set(id, created);
  return created;
}

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body };
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
  documentListeners.length = 0;
  Object.assign(globalThis, {
    document: {
      getElementById: (id: string) => element(id),
      addEventListener: (type: string) => { documentListeners.push(type); },
    },
    HTMLInputElement: StubInput,
  });
});

describe('admin headers', () => {
  // Session cookies carry admin identity; a header helper that invents one would be a
  // second, weaker authentication path.
  it('adds nothing of its own to the request', () => {
    expect(adminHeaders()).toEqual({});
    expect(adminHeaders({ 'X-Trace': 'abc' })).toEqual({ 'X-Trace': 'abc' });
  });
});

describe('admin auth bootstrap', () => {
  it('admits a manager session and hides the login prompt', async () => {
    const onAuthenticated = vi.fn(async () => {});
    const onPrincipal = vi.fn();
    const fetchImpl = vi.fn(async (url: string) => (
      url.endsWith('/ui-config')
        ? jsonResponse({ manager_login_identity: 'manager', manager_idle_timeout_sec: 60 })
        : jsonResponse({ principal: { id: 'admin-1' }, manager: true })
    ));

    await controllerWith(fetchImpl, { onAuthenticated, onPrincipal }).bootstrap();

    expect(onPrincipal).toHaveBeenCalledWith({ id: 'admin-1' });
    expect(onAuthenticated).toHaveBeenCalledWith({ id: 'admin-1' });
    expect(element('adminAuthBackdrop').style.display).toBe('none');
    expect(element('managerAccessStatus').textContent).toBe('已登入');
    expect(element('managerLockBtn').hasAttribute('hidden')).toBe(false);
  });

  // Without a manager session the backend still issues a staff principal, and the page
  // has to stay usable rather than dead-ending on a login prompt.
  it('keeps a staff principal usable while showing manager as locked', async () => {
    const onAuthenticated = vi.fn(async () => {});
    const fetchImpl = vi.fn(async (url: string) => (
      url.endsWith('/ui-config')
        ? jsonResponse({})
        : jsonResponse({ principal: { id: 'staff-1' }, manager: false })
    ));

    await controllerWith(fetchImpl, { onAuthenticated }).bootstrap();

    expect(onAuthenticated).toHaveBeenCalledWith({ id: 'staff-1' });
    expect(element('adminAuthBackdrop').style.display).toBe('none');
    expect(element('managerAccessStatus').textContent).toBe('未登入');
    expect(element('managerUnlockBtn').hasAttribute('hidden')).toBe(false);
  });

  it('requires login when the session check is refused', async () => {
    const onAuthenticated = vi.fn(async () => {});
    const onPrincipal = vi.fn();
    const fetchImpl = vi.fn(async (url: string) => (
      url.endsWith('/ui-config') ? jsonResponse({}) : jsonResponse({}, false, 401)
    ));

    await controllerWith(fetchImpl, { onAuthenticated, onPrincipal }).bootstrap();

    expect(onAuthenticated).not.toHaveBeenCalled();
    expect(onPrincipal).toHaveBeenCalledWith(null);
    expect(element('adminAuthBackdrop').style.display).toBe('flex');
    expect(element('adminLoginPassword').focus).toHaveBeenCalled();
  });

  it('still checks the session when ui-config is unavailable', async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      if (url.endsWith('/ui-config')) throw new Error('offline');
      return jsonResponse({ principal: null, manager: false });
    });

    await controllerWith(fetchImpl).bootstrap();

    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
});

describe('manager login', () => {
  const submitEvent = () => ({ preventDefault: vi.fn() });

  it('sends the identity from ui-config and clears the password field', async () => {
    const calls: Array<Record<string, unknown>> = [];
    const fetchImpl = vi.fn(async (url: string, init?: Record<string, unknown>) => {
      calls.push({ url, ...(init ?? {}) });
      if (url.endsWith('/ui-config')) return jsonResponse({ manager_login_identity: 'store-manager' });
      if (url.endsWith('/login')) return jsonResponse({});
      return jsonResponse({ principal: { id: 'admin-1' }, manager: true });
    });
    const controller = controllerWith(fetchImpl);
    await controller.bootstrap();

    controller.bind();
    (element('adminLoginPassword') as StubInput).value = 'secret';
    await element('adminAuthForm').dispatch('submit', submitEvent());

    const login = calls.find((call) => String(call.url).endsWith('/login'));
    expect(JSON.parse(String(login?.body))).toEqual({ login_identity: 'store-manager', password: 'secret' });
    expect((element('adminLoginPassword') as StubInput).value).toBe('');
  });

  it('reports a rejected password without leaving it in the field', async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      if (url.endsWith('/ui-config')) return jsonResponse({});
      if (url.endsWith('/login')) return jsonResponse({}, false, 401);
      return jsonResponse({}, false, 401);
    });
    const controller = controllerWith(fetchImpl);
    controller.bind();
    (element('adminLoginPassword') as StubInput).value = 'wrong';

    await element('adminAuthForm').dispatch('submit', submitEvent());

    expect((element('adminLoginPassword') as StubInput).value).toBe('');
    expect(element('adminAuthError').textContent).not.toBe('');
  });

  it('opens and closes the manager prompt on demand', async () => {
    const controller = controllerWith(vi.fn(async () => jsonResponse({}, false, 401)));
    controller.bind();

    controller.openManagerLogin();
    expect(element('adminAuthBackdrop').style.display).toBe('flex');

    await element('adminAuthCancel').dispatch('click', {});
    expect(element('adminAuthBackdrop').style.display).toBe('none');
  });

  it('logs the manager out and falls back to staff rather than locking the page', async () => {
    const seen: string[] = [];
    const fetchImpl = vi.fn(async (url: string) => {
      seen.push(new URL(url).pathname);
      if (url.endsWith('/ui-config')) return jsonResponse({});
      if (url.endsWith('/logout')) return jsonResponse({});
      return jsonResponse({ principal: { id: 'staff-1' }, manager: false });
    });

    await controllerWith(fetchImpl).lockManager();

    expect(seen).toContain('/api/admin/auth/logout');
    expect(element('managerAccessStatus').textContent).toBe('未登入');
    expect(element('adminAuthBackdrop').style.display).toBe('none');
  });

  it('binds idle activity listeners so a manager session can time out', () => {
    controllerWith(vi.fn(async () => jsonResponse({}, false, 401))).bind();

    expect(documentListeners).toEqual(['pointerdown', 'keydown']);
  });
});
