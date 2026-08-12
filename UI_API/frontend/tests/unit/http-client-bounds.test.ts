import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchJson, postFormJson } from '../../shared/httpClient.js';

/**
 * A connection that is accepted and then goes quiet is the one failure a client
 * cannot tell from a slow answer. Without a deadline the promise never settles,
 * the caller's `finally` never runs, and a temporary backend condition becomes a
 * permanently stuck surface.
 */

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('bounded JSON requests', () => {
  it('rejects when the service accepts the connection but never answers', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<never>(() => {})));

    await expect(fetchJson('http://api/slow', { timeoutMs: 20 })).rejects.toThrow(/timed out/);
  });

  it('aborts the request it gave up on', async () => {
    let seenSignal: AbortSignal | undefined;
    vi.stubGlobal('fetch', vi.fn((_url: string, options: RequestInit) => {
      seenSignal = options.signal ?? undefined;
      return new Promise<never>(() => {});
    }));

    await expect(fetchJson('http://api/slow', { timeoutMs: 20 })).rejects.toThrow(/timed out/);
    expect(seenSignal?.aborted).toBe(true);
  });

  it('rejects when the response body never completes', async () => {
    vi.useFakeTimers();
    try {
      vi.stubGlobal('fetch', vi.fn(async () => ({
        ok: true,
        status: 200,
        json: () => new Promise<never>(() => {}),
      })));
      const pending = fetchJson('http://api/slow-body', { timeoutMs: 20 });
      const settled = Promise.race([
        pending.then(() => true, () => true),
        new Promise<boolean>(resolve => setTimeout(() => resolve(false), 30)),
      ]);

      await vi.advanceTimersByTimeAsync(30);

      expect(await settled).toBe(true);
      await expect(pending).rejects.toThrow(/timed out/);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not send the deadline to the transport as a request field', async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ ok: 1 }) }));
    vi.stubGlobal('fetch', fetchImpl);

    await fetchJson('http://api/fast', { timeoutMs: 5000 });

    const [, options] = fetchImpl.mock.calls[0] as unknown as [string, Record<string, unknown>];
    expect(options).not.toHaveProperty('timeoutMs');
    expect(options.signal).toBeDefined();
  });

  it('lets a caller buy a longer budget for genuinely slow work', async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ ok: 1 }) }));
    vi.stubGlobal('fetch', fetchImpl);

    await expect(
      postFormJson('http://api/inference', new FormData(), { timeoutMs: 90000 }),
    ).resolves.toEqual({ ok: 1 });
  });

  it('still surfaces a non-2xx body as an error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 409,
      json: async () => ({ detail: 'conflicting revision' }),
    })));

    await expect(fetchJson('http://api/conflict')).rejects.toThrow('conflicting revision');
  });
});
