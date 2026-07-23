import { afterEach, describe, expect, it, vi } from 'vitest';

import { adminHeaders, createAdminAuthController } from '../../admin/features/auth/adminAuth.js';
import {
  buildKioskSessionId,
  loadKioskFeatures,
  resolveKioskAppMode,
  saveKioskFeatures,
} from '../../kiosk/features/bootstrap/runtimePreferences.js';

class MemoryStorage implements Storage {
  private values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

afterEach(() => vi.unstubAllGlobals());

describe('Kiosk bootstrap preferences', () => {
  it('resolves application mode and sanitizes a requested session', () => {
    const location = { pathname: '/kiosk', port: '9000', search: '?session_id=safe_ID%21' } as Location;
    expect(resolveKioskAppMode(location)).toBe('kiosk');
    expect(buildKioskSessionId(location)).toBe('safe_ID');
    expect(resolveKioskAppMode({ ...location, pathname: '/admin' } as Location)).toBe('admin');
    expect(resolveKioskAppMode({ ...location, pathname: '/', port: '9001' } as Location)).toBe('admin');
    expect(buildKioskSessionId({ ...location, search: '' } as Location)).toMatch(/^kiosk_[a-z0-9]+$/);
  });

  it('persists versioned preferences and preserves explicit choices', () => {
    const storage = new MemoryStorage();
    saveKioskFeatures(storage, { voiceAssist: false });
    expect(loadKioskFeatures(storage, false)).toEqual({ voiceAssist: false, recommend: true, multiLang: true });
    storage.setItem('kiosk_feat', '{invalid');
    expect(loadKioskFeatures(storage, false)).toMatchObject({ voiceAssist: true, recommend: true });
    storage.clear();
    expect(loadKioskFeatures(storage, true)).toMatchObject({
      voiceAssist: true,
      recommend: true,
      multiLang: true,
    });
  });
});

describe('Admin auth feature', () => {
  it('builds compatibility headers only from session storage', () => {
    const storage = new MemoryStorage();
    vi.stubGlobal('sessionStorage', storage);
    expect(adminHeaders()).toEqual({});
    storage.setItem('admin_demo_token', 'compat-token');
    expect(adminHeaders({ Accept: 'application/json' })).toMatchObject({
      Accept: 'application/json',
      Authorization: 'Bearer compat-token',
    });
  });

  it('shows the gate on failure and loads the dashboard after authentication', async () => {
    const storage = new MemoryStorage();
    const backdrop = { style: { display: '' } };
    vi.stubGlobal('sessionStorage', storage);
    vi.stubGlobal('document', { getElementById: () => backdrop });
    const onAuthenticated = vi.fn(async () => undefined);
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));
    const controller = createAdminAuthController({ apiBaseUrl: '', onAuthenticated, fetchImpl });
    await controller.bootstrap();
    expect(backdrop.style.display).toBe('flex');
    await controller.bootstrap();
    expect(backdrop.style.display).toBe('none');
    expect(onAuthenticated).toHaveBeenCalledOnce();
  });

  it('binds a safe login submit and clears password state', async () => {
    class FakeInput {
      value = '';
    }
    const storage = new MemoryStorage();
    const backdrop = { style: { display: '' } };
    const identity = new FakeInput();
    identity.value = 'e2e-admin';
    const password = new FakeInput();
    password.value = 'temporary-password';
    const error = { textContent: 'old error' };
    let submit: ((event: { preventDefault(): void }) => Promise<void>) | undefined;
    const form = {
      addEventListener: (_type: string, handler: typeof submit) => { submit = handler; },
    };
    const elements: Record<string, unknown> = {
      adminAuthBackdrop: backdrop,
      adminAuthForm: form,
      adminLoginIdentity: identity,
      adminLoginPassword: password,
      adminAuthError: error,
    };
    vi.stubGlobal('sessionStorage', storage);
    vi.stubGlobal('HTMLInputElement', FakeInput);
    vi.stubGlobal('document', { getElementById: (id: string) => elements[id] ?? null });
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));
    const onAuthenticated = vi.fn(async () => undefined);
    createAdminAuthController({ apiBaseUrl: '', onAuthenticated, fetchImpl }).bind();
    await vi.waitFor(() => expect(backdrop.style.display).toBe('flex'));
    expect(submit).toBeTypeOf('function');
    await submit?.({ preventDefault: vi.fn() });
    expect(password.value).toBe('');
    expect(error.textContent).toBe('');
    expect(backdrop.style.display).toBe('none');
    expect(onAuthenticated).toHaveBeenCalledOnce();
  });

  it('shows a bounded message when login is rejected', async () => {
    class FakeInput { value = 'input'; }
    const backdrop = { style: { display: '' } };
    const identity = new FakeInput();
    const password = new FakeInput();
    const error = { textContent: '' };
    let submit: ((event: { preventDefault(): void }) => Promise<void>) | undefined;
    const elements: Record<string, unknown> = {
      adminAuthBackdrop: backdrop,
      adminAuthForm: { addEventListener: (_type: string, handler: typeof submit) => { submit = handler; } },
      adminLoginIdentity: identity,
      adminLoginPassword: password,
      adminAuthError: error,
    };
    vi.stubGlobal('sessionStorage', new MemoryStorage());
    vi.stubGlobal('HTMLInputElement', FakeInput);
    vi.stubGlobal('document', { getElementById: (id: string) => elements[id] ?? null });
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockResolvedValueOnce(new Response('{}', { status: 403 }));
    createAdminAuthController({ apiBaseUrl: '', onAuthenticated: vi.fn(), fetchImpl }).bind();
    await vi.waitFor(() => expect(backdrop.style.display).toBe('flex'));
    await submit?.({ preventDefault: vi.fn() });
    expect(error.textContent).toContain('登入失敗');
    expect(password.value).toBe('');
  });
});
