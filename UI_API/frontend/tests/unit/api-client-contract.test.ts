import { describe, expect, it, vi } from 'vitest';

// Keep the contract suite pinned to the typed source; browser feature code uses
// the sibling `.js` entrypoint because Docker serves static modules directly.
import { ApiV1Error, createApiV1Client } from '../../shared/api/v1Client.ts';

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

/** Drives the client's own clock so a bounded wait can be observed without spending it. */
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
      for (const [handle, entry] of [...pending.entries()]) {
        if (entry.at > now) continue;
        pending.delete(handle);
        entry.run();
      }
      for (let tick = 0; tick < 8; tick += 1) await Promise.resolve();
    },
  };
}

describe('public API v1 client contract', () => {
  it('adds request metadata and bearer authentication to a request', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(ok({ data: { status: 'ok' }, meta: { request_id: 'r', timestamp: 't' } }));
    const client = createApiV1Client({
      baseUrl: 'http://api.example',
      fetchImpl,
      getBearerToken: () => 'token-1',
      retryCount: 0,
    });

    await client.get<{ status: string }>('/health');

    expect(fetchImpl).toHaveBeenCalledOnce();
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(url).toBe('http://api.example/api/v1/health');
    expect(headers.get('Authorization')).toBe('Bearer token-1');
    expect(headers.get('X-Request-Id')).toMatch(/^req_/);
  });

  it('merges capability headers and keeps validation details on typed errors', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: {
        code: 'validation_error',
        message: 'Invalid value',
        request_id: 'req-details',
        details: [{ location: ['body', 'name'], message: 'required', type: 'value_error' }],
      },
      meta: { request_id: 'req-details', timestamp: 't' },
    }), { status: 422 }));
    const client = createApiV1Client({
      fetchImpl,
      headers: () => ({ 'X-Kiosk-Token': 'kiosk-1', 'X-Optional': '' }),
      retryCount: 0,
    });

    await expect(client.get('/campaigns')).rejects.toMatchObject({
      code: 'validation_error',
      details: [{ location: ['body', 'name'] }],
      fieldErrors: [{ message: 'required' }],
    });
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get('X-Kiosk-Token')).toBe('kiosk-1');
    expect(new Headers(init.headers).get('X-Optional')).toBe('');
  });

  it('retries safe GET failures but surfaces the typed API error', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        error: { code: 'missing', message: 'Not found', request_id: 'req-2', details: [] },
        meta: { request_id: 'req-2', timestamp: 't' },
      }), { status: 404 }));
    const client = createApiV1Client({ fetchImpl, retryCount: 1 });

    await expect(client.get('/missing')).rejects.toMatchObject({
      status: 404,
      code: 'missing',
      requestId: 'req-2',
    });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  // Retrying a write could duplicate an order or a payment, so only GET is repeated.
  it('never retries a write, even on a server error', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{}', { status: 503 }));
    const client = createApiV1Client({ fetchImpl, retryCount: 3 });

    await expect(client.post('/orders', { item: 'burger' })).rejects.toBeInstanceOf(ApiV1Error);
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it('reports a typed error when the body is not an error envelope', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'nope' }), { status: 400 }));
    const client = createApiV1Client({ fetchImpl, retryCount: 0 });

    await expect(client.get('/bad')).rejects.toMatchObject({
      status: 400,
      code: 'request_failed',
      requestId: '',
    });
  });

  it.each([
    ['post', 'POST'],
    ['put', 'PUT'],
    ['patch', 'PATCH'],
  ] as const)('sends %s bodies as JSON', async (method, expectedMethod) => {
    const fetchImpl = vi.fn().mockResolvedValue(ok({ data: {}, meta: { request_id: 'r', timestamp: 't' } }));
    const client = createApiV1Client({ fetchImpl, retryCount: 0 });

    await client[method]('/thing', { name: 'value' });

    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe(expectedMethod);
    expect(init.body).toBe(JSON.stringify({ name: 'value' }));
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json');
  });

  it('omits the body when a write carries none', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(ok({ data: {}, meta: { request_id: 'r', timestamp: 't' } }));
    const client = createApiV1Client({ fetchImpl, retryCount: 0 });

    await client.post('/trigger');

    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(init.body).toBeUndefined();
  });

  it('keeps a caller-supplied request id so one trace spans the retry', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(ok({ data: {}, meta: { request_id: 'r', timestamp: 't' } }));
    const client = createApiV1Client({ fetchImpl, retryCount: 0 });

    await client.request('/thing', { headers: { 'X-Request-Id': 'caller-supplied' } });

    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get('X-Request-Id')).toBe('caller-supplied');
  });

  it('sends no Authorization header when the token is blank', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(ok({ data: {}, meta: { request_id: 'r', timestamp: 't' } }));
    const client = createApiV1Client({ fetchImpl, getBearerToken: () => '   ', retryCount: 0 });

    await client.get('/health');

    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).has('Authorization')).toBe(false);
  });

  it('strips a trailing slash from the base url', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(ok({ data: {}, meta: { request_id: 'r', timestamp: 't' } }));
    const client = createApiV1Client({ baseUrl: 'http://api.example/', fetchImpl, retryCount: 0 });

    await client.get('/health');

    expect(fetchImpl.mock.calls[0]?.[0]).toBe('http://api.example/api/v1/health');
  });

  it('surfaces a transport failure once the retries are spent', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error('network down'));
    const client = createApiV1Client({ fetchImpl, retryCount: 1 });

    await expect(client.get('/health')).rejects.toThrow('network down');
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('aborts a request that outlives its timeout', async () => {
    const fetchImpl = vi.fn((_url: string, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
    }));
    const client = createApiV1Client({ fetchImpl: fetchImpl as unknown as typeof fetch, retryCount: 0, timeoutMs: 100 });

    await expect(client.get('/slow')).rejects.toThrow('aborted');
  });

  it('times out when the response body never completes', async () => {
    vi.useFakeTimers();
    try {
      const fetchImpl = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => new Promise<never>(() => {}),
      });
      const client = createApiV1Client({ fetchImpl, retryCount: 0, timeoutMs: 100 });
      const pending = client.get('/slow-body');
      const settled = Promise.race([
        pending.then(() => true, () => true),
        new Promise<boolean>(resolve => setTimeout(() => resolve(false), 200)),
      ]);

      await vi.advanceTimersByTimeAsync(200);

      expect(await settled).toBe(true);
      await expect(pending).rejects.toThrow('timed out after 100ms');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('bounded request failures', () => {
  it('says the request timed out rather than that a signal was aborted', async () => {
    // The fetch rejection and the timeout rejection race. A bare
    // `controller.abort()` makes the fetch reject with a DOMException reading
    // "signal is aborted without reason", and that message is what reached
    // the operator.
    const abortReasons: unknown[] = [];
    const fetchImpl = vi.fn((_url: string, init: RequestInit) => new Promise<never>((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => {
        abortReasons.push((init.signal as AbortSignal).reason);
        reject((init.signal as AbortSignal).reason);
      });
    }));
    const client = createApiV1Client({ fetchImpl: fetchImpl as unknown as typeof fetch, retryCount: 0, timeoutMs: 100 });

    await expect(client.get('/slow')).rejects.toThrow('timed out after 100ms');
    expect(String(abortReasons[0])).toContain('timed out after 100ms');
    expect(String(abortReasons[0])).not.toContain('without reason');
  });
});

describe('daily diagnostic workbench client contract', () => {
  it('keeps question, diagnosis, and candidate operations under the versioned optimization surface', async () => {
    const fetchImpl = vi.fn().mockImplementation(async () => ok({ data: { questions: [], profiles: [], report: null, candidate: null } }));
    const { createOptimizationClient } = await import('../../shared/api/capabilityClients.js');
    const client = createOptimizationClient({ baseUrl: 'http://api.example', fetchImpl, retryCount: 0 });

    await client.questions();
    await client.updateQuestion('question/1', { display_name: '名稱', prompt: 'Prompt' });
    await client.simulate({ store_date: '2026-08-13' });
    await client.confirmCandidate('candidate/1');

    expect(fetchImpl.mock.calls.map(call => [call[0], (call[1] as RequestInit).method])).toEqual([
      ['http://api.example/api/v1/optimization/questions', undefined],
      ['http://api.example/api/v1/optimization/questions/question%2F1', 'PUT'],
      ['http://api.example/api/v1/optimization/simulations', 'POST'],
      ['http://api.example/api/v1/optimization/candidate/candidate%2F1/confirm', 'POST'],
    ]);
  });
});

describe('voice evidence client contract', () => {
  it('keeps metadata search under the versioned voice evidence surface', async () => {
    const fetchImpl = vi.fn().mockImplementation(async () => ok({ data: { records: [], page: {} } }));
    const { createVoiceEvidenceClient } = await import('../../shared/api/capabilityClients.js');
    const client = createVoiceEvidenceClient({ baseUrl: 'http://api.example', fetchImpl, retryCount: 0 });

    await client.list({
      observed_from: '2026-08-14T00:00:00+08:00',
      observed_to: '2026-08-15T00:00:00+08:00',
      terminal_status: 'completed',
      limit: 50,
    });

    expect(fetchImpl.mock.calls[0]?.[0]).toContain('http://api.example/api/v1/voice-evidence?');
    expect(fetchImpl.mock.calls[0]?.[0]).toContain('terminal_status=completed');
    expect(fetchImpl.mock.calls[0]?.[0]).not.toContain('transcript');
  });
});
