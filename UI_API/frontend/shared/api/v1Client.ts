import type { ApiErrorEnvelope, ApiResponse } from '../contracts/api-v1';

export class ApiV1Error extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly requestId: string,
  ) {
    super(message);
    this.name = 'ApiV1Error';
  }
}

export interface ApiV1ClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  getBearerToken?: () => string;
  retryCount?: number;
  timeoutMs?: number;
}

function requestId(): string {
  const random = globalThis.crypto?.randomUUID?.().replaceAll('-', '') ?? Math.random().toString(16).slice(2);
  return `req_${random.slice(0, 24)}`;
}

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (!value || typeof value !== 'object' || !("error" in value)) return false;
  const error = (value as { error?: unknown }).error;
  return Boolean(error && typeof error === 'object' && 'code' in error && 'message' in error);
}

export function createApiV1Client(options: ApiV1ClientOptions = {}) {
  const fetchImpl = options.fetchImpl ?? fetch;
  const retryCount = Math.max(0, options.retryCount ?? 1);
  const timeoutMs = Math.max(100, options.timeoutMs ?? 8_000);
  const baseUrl = (options.baseUrl ?? '').replace(/\/$/, '');

  async function request<T>(path: string, init: RequestInit = {}): Promise<ApiResponse<T>> {
    const method = (init.method ?? 'GET').toUpperCase();
    const attempts = method === 'GET' ? retryCount + 1 : 1;
    let lastError: unknown;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      const headers = new Headers(init.headers);
      headers.set('Accept', 'application/json');
      headers.set('X-Request-Id', headers.get('X-Request-Id') ?? requestId());
      const bearer = options.getBearerToken?.().trim();
      if (bearer) headers.set('Authorization', `Bearer ${bearer}`);
      try {
        const response = await fetchImpl(`${baseUrl}/api/v1${path}`, {
          ...init,
          credentials: 'same-origin',
          headers,
          signal: controller.signal,
        });
        const payload: unknown = await response.json();
        if (response.ok) return payload as ApiResponse<T>;
        if (response.status >= 500 && attempt + 1 < attempts) continue;
        if (isErrorEnvelope(payload)) {
          throw new ApiV1Error(payload.error.message, response.status, payload.error.code, payload.error.request_id);
        }
        throw new ApiV1Error('The request could not be completed.', response.status, 'request_failed', '');
      } catch (error) {
        lastError = error;
        if (error instanceof ApiV1Error || attempt + 1 >= attempts) throw error;
      } finally {
        clearTimeout(timer);
      }
    }
    throw lastError;
  }

  return {
    get<T>(path: string): Promise<ApiResponse<T>> {
      return request<T>(path);
    },
    request,
  };
}
