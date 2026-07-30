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
 * 非 2xx 一律丟出例外。否則錯誤回應（例如 401 的 {"detail": ...}）會被當成
 * 正常結果傳給呼叫端，讓 AI 推播之類的功能靜默退回本地備援而看不到錯誤。
 * @template ResponseBody
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<ResponseBody>}
 */
export async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(await readErrorMessage(response));
  return readJson(response);
}

/**
 * @template ResponseBody
 * @param {string} url
 * @param {FormData} formData
 * @param {RequestInit} [options]
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
 * @returns {Promise<ResponseBody>}
 */
export function postJson(url, payload, headers = {}) {
  return fetchJson(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(payload || {}),
  });
}
