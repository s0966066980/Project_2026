import { describe, expect, it, vi } from 'vitest';

import { ApiV1Error, createApiV1Client } from '../../shared/api/v1Client';

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

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
});
