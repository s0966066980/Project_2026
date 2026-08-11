import { afterEach, describe, expect, it, vi } from 'vitest';

/**
 * Ordering entry, cart and checkout reads keep their own error vocabulary and
 * so do not route through `httpClient`. They still must end: a connection that
 * is accepted and then goes quiet would otherwise hang forever, and the
 * recovery states the domain already defines — Guest Ordering Start Failure,
 * Menu Initialization Failure — never get the chance to happen.
 */

const emptyStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
};

Object.assign(globalThis, {
  window: {
    location: { protocol: 'http:', pathname: '/kiosk', hash: '', search: '', origin: 'http://api' },
  },
  history: { replaceState: () => {} },
  sessionStorage: emptyStorage,
  localStorage: emptyStorage,
});

const api = await import('../../shared/apiClient.js');

const neverAnswers = () => new Promise<never>(() => {});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** Runs the call against a service that never answers, without spending the wait. */
async function expectBounded(call: () => Promise<unknown>) {
  vi.useFakeTimers();
  const pending = call();
  const assertion = expect(pending).rejects.toThrow(/timed out/);
  await vi.advanceTimersByTimeAsync(20000);
  await assertion;
}

describe('kiosk critical path requests are bounded', () => {
  it.each([
    ['ordering entry start', () => api.startEntryFlow({})],
    ['ordering entry command', () => api.commandEntryFlow('flow-1', 1, 'choose_guest', {})],
    ['checkout prepare', () => api.prepareCheckout('session-1')],
    ['checkout outcome', () => api.getCheckoutOutcome('quote-1', 'key-1')],
    ['cart sync', () => api.syncCart('session-1', [])],
  ])('%s ends instead of hanging when the service never answers', async (_name, call) => {
    vi.stubGlobal('fetch', vi.fn(neverAnswers));

    await expectBounded(call);
  });

  it('aborts the request it gave up on', async () => {
    let seenSignal: AbortSignal | undefined;
    vi.stubGlobal('fetch', vi.fn((_url: string, options: RequestInit) => {
      seenSignal = options.signal ?? undefined;
      return neverAnswers();
    }));

    await expectBounded(() => api.startEntryFlow({}));

    expect(seenSignal?.aborted).toBe(true);
  });

  it('keeps its own failure vocabulary for an answered rejection', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 409, json: async () => ({}) })));

    await expect(api.startEntryFlow({})).rejects.toThrow('entry_flow_start_failed:409');
  });
});
