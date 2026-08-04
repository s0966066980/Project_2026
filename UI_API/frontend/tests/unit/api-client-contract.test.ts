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
});
