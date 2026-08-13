import type { ApiErrorEnvelope, ApiResponse } from '../contracts/api-v1';

export class ApiV1Error extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly requestId: string,
    readonly details: unknown[] = [],
  ) {
    super(message);
    this.name = 'ApiV1Error';
  }

  /** Campaign and knowledge forms use the same public validation detail shape. */
  get fieldErrors(): unknown[] {
    return this.details;
  }
}

export interface ApiV1ClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  getBearerToken?: () => string;
  headers?: () => Record<string, string>;
  retryCount?: number;
  timeoutMs?: number;
  timers?: Pick<typeof globalThis, 'setTimeout' | 'clearTimeout'>;
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
  const timers = options.timers ?? globalThis;

  async function request<T>(path: string, init: RequestInit = {}): Promise<ApiResponse<T>> {
    const method = (init.method ?? 'GET').toUpperCase();
    const attempts = method === 'GET' ? retryCount + 1 : 1;
    let lastError: unknown;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const controller = new AbortController();
      let timeoutHandle: ReturnType<typeof timers.setTimeout> | undefined;
      let bodyTimeoutHandle: ReturnType<typeof timers.setTimeout> | undefined;
      const headers = new Headers(init.headers);
      for (const [name, value] of Object.entries(options.headers?.() ?? {})) {
        if (value !== undefined && value !== null) headers.set(name, value);
      }
      headers.set('Accept', 'application/json');
      headers.set('X-Request-Id', headers.get('X-Request-Id') ?? requestId());
      const bearer = options.getBearerToken?.().trim();
      if (bearer) headers.set('Authorization', `Bearer ${bearer}`);
      try {
        const timeout = new Promise<never>((_resolve, reject) => {
          timeoutHandle = timers.setTimeout(() => {
            // Abort with the reason, not bare. Both the fetch rejection and
            // this one race to surface, and a bare abort rejects with
            // "signal is aborted without reason" — which is what an operator
            // saw instead of being told the request had hit its bound.
            controller.abort(new Error(`request timed out after ${timeoutMs}ms`));
            reject(new Error(`request timed out after ${timeoutMs}ms`));
          }, timeoutMs);
        });
        const response = await Promise.race([
          fetchImpl(`${baseUrl}/api/v1${path}`, {
            ...init,
            credentials: 'same-origin',
            headers,
            signal: controller.signal,
          }),
          timeout,
        ]);
        const payload: unknown = await Promise.race([
          response.json(),
          new Promise<never>((_resolve, reject) => {
            bodyTimeoutHandle = timers.setTimeout(() => {
              controller.abort(new Error(`response body timed out after ${timeoutMs}ms`));
              reject(new Error(`response body timed out after ${timeoutMs}ms`));
            }, timeoutMs);
          }),
        ]);
        if (response.ok) return payload as ApiResponse<T>;
        if (response.status >= 500 && attempt + 1 < attempts) continue;
        if (isErrorEnvelope(payload)) {
          throw new ApiV1Error(
            payload.error.message,
            response.status,
            payload.error.code,
            payload.error.request_id,
            payload.error.details,
          );
        }
        throw new ApiV1Error('The request could not be completed.', response.status, 'request_failed', '');
      } catch (error) {
        lastError = error;
        if (error instanceof ApiV1Error || attempt + 1 >= attempts) throw error;
      } finally {
        if (timeoutHandle !== undefined) timers.clearTimeout(timeoutHandle);
        if (bodyTimeoutHandle !== undefined) timers.clearTimeout(bodyTimeoutHandle);
      }
    }
    throw lastError;
  }

  return {
    get<T>(path: string): Promise<ApiResponse<T>> {
      return request<T>(path);
    },
    post<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
      const init: RequestInit = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      };
      if (body !== undefined) init.body = JSON.stringify(body);
      return request<T>(path, init);
    },
    put<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
      const init: RequestInit = {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
      };
      if (body !== undefined) init.body = JSON.stringify(body);
      return request<T>(path, init);
    },
    patch<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
      const init: RequestInit = {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
      };
      if (body !== undefined) init.body = JSON.stringify(body);
      return request<T>(path, init);
    },
    request,
  };
}
