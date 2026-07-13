import { describe, expect, it, vi } from 'vitest';

import { ApiV1Error, createApiV1Client } from '../../shared/api/v1Client';

const ok = (data: unknown) => new Response(JSON.stringify({ data, meta: { request_id: 'req_server', timestamp: '2026-07-13T12:00:00Z' } }), {
  status: 200,
  headers: { 'Content-Type': 'application/json' },
});

describe('API v1 client', () => {
  it('centralizes same-origin auth, request correlation and typed data', async () => {
    const fetchImpl = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(init?.credentials).toBe('same-origin');
      expect(headers.get('Authorization')).toBe('Bearer test-session');
      expect(headers.get('X-Request-Id')).toMatch(/^req_/);
      return ok({ user_id: 'admin-id' });
    });
    const client = createApiV1Client({ fetchImpl, getBearerToken: () => 'test-session' });
    await expect(client.get<{ user_id: string }>('/auth/me')).resolves.toMatchObject({ data: { user_id: 'admin-id' } });
  });

  it('retries safe reads but not unsafe writes', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 503 }))
      .mockResolvedValueOnce(ok({ healthy: true }));
    const client = createApiV1Client({ fetchImpl, retryCount: 1 });
    await expect(client.get('/commercial-context')).resolves.toMatchObject({ data: { healthy: true } });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('maps safe server errors without leaking credentials', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({
      error: { code: 'forbidden', message: 'The action is not allowed.', request_id: 'req_denied', details: [] },
      meta: { request_id: 'req_denied', timestamp: '2026-07-13T12:00:00Z' },
    }), { status: 403 }));
    const client = createApiV1Client({ fetchImpl, getBearerToken: () => 'never-echo' });
    const error = await client.get('/members').catch(value => value);
    expect(error).toBeInstanceOf(ApiV1Error);
    expect(String(error)).not.toContain('never-echo');
    expect(error).toMatchObject({ status: 403, code: 'forbidden', requestId: 'req_denied' });
  });
});
