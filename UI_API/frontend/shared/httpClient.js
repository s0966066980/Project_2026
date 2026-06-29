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
 * @template ResponseBody
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<ResponseBody>}
 */
export async function fetchJson(url, options) {
  return readJson(await fetch(url, options));
}

/**
 * @template ResponseBody
 * @param {string} url
 * @param {FormData} formData
 * @returns {Promise<ResponseBody>}
 */
export function postFormJson(url, formData) {
  return fetchJson(url, { method: 'POST', body: formData });
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
