// @ts-check

/**
 * @template ResponseBody
 * @param {Response} response
 * @returns {Promise<ResponseBody>}
 */
export async function readJson(response) {
  return response.json();
}

/**
 * 讀出後端錯誤回應中的可讀訊息；解析失敗時退回 HTTP 狀態碼。
 * @param {Response} response
 * @returns {Promise<string>}
 */
async function readErrorMessage(response) {
  try {
    const body = await response.json();
    const detail = body?.detail ?? body?.message ?? body?.error;
    if (typeof detail === 'string' && detail) return detail;
    if (detail && typeof detail === 'object') return JSON.stringify(detail);
  } catch {
    // 非 JSON 錯誤回應（例如反向代理的 HTML 頁面）只保留狀態碼。
  }
  return `HTTP ${response.status}`;
}

/**
 * 預設請求時限。連線被接受但伺服器不回應時，沒有時限的 fetch 永遠不 settle，
 * 呼叫端的 `finally` 也永遠不執行——暫時性的後端狀況會被放大成永久卡住的畫面。
 * 時間放寬到 15 秒是為了不誤殺正常的慢請求；真正需要更久的呼叫端自己指定。
 */
const DEFAULT_REQUEST_TIMEOUT_MS = 15000;

/** @typedef {RequestInit & {timeoutMs?: number}} BoundedRequestInit */

/**
 * 非 2xx 一律丟出例外。否則錯誤回應（例如 401 的 {"detail": ...}）會被當成
 * 正常結果傳給呼叫端，讓 AI 推播之類的功能靜默退回本地備援而看不到錯誤。
 *
 * 每個請求都有時限：abort signal 是有禮貌的路徑，deadline 才是保證——
 * 不論傳輸層是否理會 signal，這個 Promise 一定會 settle。
 *
 * @template ResponseBody
 * @param {string} url
 * @param {BoundedRequestInit} [options]
 * @returns {Promise<ResponseBody>}
 */
export async function fetchJson(url, options) {
  const { timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS, ...requestInit } = options || {};
  const controller = new AbortController();
  /** @type {any} */
  let deadline = null;
  /** @type {Response} */
  let response;
  try {
    response = /** @type {Response} */ (await Promise.race([
      fetch(url, { ...requestInit, signal: requestInit.signal || controller.signal }),
      new Promise((_resolve, reject) => {
        deadline = setTimeout(() => {
          controller.abort();
          reject(new Error(`request timed out after ${timeoutMs}ms: ${url}`));
        }, timeoutMs);
      }),
    ]));
  } finally {
    if (deadline !== null) clearTimeout(deadline);
  }
  if (!response.ok) throw new Error(await readErrorMessage(response));
  return readJson(response);
}

/**
 * @template ResponseBody
 * @param {string} url
 * @param {FormData} formData
 * @param {BoundedRequestInit} [options]
 * @returns {Promise<ResponseBody>}
 */
export function postFormJson(url, formData, options = {}) {
  return fetchJson(url, { ...options, method: 'POST', body: formData });
}

/**
 * @template ResponseBody
 * @param {string} url
 * @param {unknown} payload
 * @param {Record<string, string>} [headers]
 * @param {{timeoutMs?: number}} [options]
 * @returns {Promise<ResponseBody>}
 */
export function postJson(url, payload, headers = {}, options = {}) {
  return fetchJson(url, {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(payload || {}),
  });
}
