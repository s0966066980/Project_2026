// The static Docker runtime serves source modules directly (without Vite's
// TypeScript resolver). Keep this browser entrypoint in lockstep with
// `v1Client.ts`, which is the typed source used by tests and build tooling.

export class ApiV1Error extends Error {
  constructor(message, status, code, requestId, details = []) {
    super(message);
    this.name = 'ApiV1Error';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }

  get fieldErrors() {
    return this.details;
  }
}

function requestId() {
  const random = globalThis.crypto?.randomUUID?.().replaceAll('-', '') ?? Math.random().toString(16).slice(2);
  return `req_${random.slice(0, 24)}`;
}

function isErrorEnvelope(value) {
  if (!value || typeof value !== 'object' || !('error' in value)) return false;
  const error = value.error;
  return Boolean(error && typeof error === 'object' && 'code' in error && 'message' in error);
}

export function createApiV1Client(options = {}) {
  const fetchImpl = options.fetchImpl ?? fetch;
  const retryCount = Math.max(0, options.retryCount ?? 1);
  const timeoutMs = Math.max(100, options.timeoutMs ?? 8_000);
  const baseUrl = (options.baseUrl ?? '').replace(/\/$/, '');
  const timers = options.timers ?? globalThis;

  async function request(path, init = {}) {
    const method = (init.method ?? 'GET').toUpperCase();
    const attempts = method === 'GET' ? retryCount + 1 : 1;
    let lastError;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const controller = new AbortController();
      let timeoutHandle;
      let bodyTimeoutHandle;
      const headers = new Headers(init.headers);
      for (const [name, value] of Object.entries(options.headers?.() ?? {})) {
        if (value !== undefined && value !== null) headers.set(name, value);
      }
      headers.set('Accept', 'application/json');
      headers.set('X-Request-Id', headers.get('X-Request-Id') ?? requestId());
      const bearer = options.getBearerToken?.().trim();
      if (bearer) headers.set('Authorization', `Bearer ${bearer}`);
      try {
        const timeout = new Promise((resolve, reject) => {
          timeoutHandle = timers.setTimeout(() => {
            controller.abort();
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
        const payload = await Promise.race([
          response.json(),
          new Promise((_resolve, reject) => {
            bodyTimeoutHandle = timers.setTimeout(() => {
              controller.abort();
              reject(new Error(`response body timed out after ${timeoutMs}ms`));
            }, timeoutMs);
          }),
        ]);
        if (response.ok) return payload;
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
    get: path => request(path),
    post: (path, body) => request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
    put: (path, body) => request(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
    patch: (path, body) => request(path, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
    request,
  };
}
