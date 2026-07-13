// @ts-check

import { fetchJson, postFormJson, postJson } from './httpClient.js';

/** @typedef {import('../types.d.ts').InteractionEventPayload} InteractionEventPayload */
/** @typedef {import('../types.d.ts').VoiceStreamAudioChunk} VoiceStreamAudioChunk */
/** @typedef {import('../types.d.ts').VoiceStreamChunk} VoiceStreamChunk */
/** @typedef {import('../types.d.ts').VoiceStreamHandlers} VoiceStreamHandlers */

export const API_BASE = (
  window.location.protocol === 'file:'
) ? 'http://127.0.0.1:9000' : '';

/** @type {Promise<Record<string, unknown>> | null} */
let publicSettingsRequest = null;
/** @type {Promise<import('../types.d.ts').MenuItem[]> | null} */
let menuRequest = null;
/** @type {Map<string, Promise<Record<string, unknown>>>} */
const posPromotionBannersRequests = new Map();

/** @param {URLSearchParams} params */
function stripSensitiveTokenParams(params) {
  const sensitiveKeys = ['token', 'admin_token', 'kiosk_token', 'pos_token', 'ws_token'];
  if (!sensitiveKeys.some(key => params.has(key))) return;
  sensitiveKeys.forEach(key => params.delete(key));
  const query = params.toString();
  history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
}

/**
 * @param {unknown} value
 * @returns {value is Record<string, unknown>}
 */
function isObjectRecord(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/**
 * @param {unknown} value
 * @returns {VoiceStreamChunk | null}
 */
function parseVoiceStreamChunk(value) {
  if (!isObjectRecord(value) || typeof value.type !== 'string') return null;
  if (value.type === 'audio' && typeof value.data === 'string') {
    /** @type {VoiceStreamAudioChunk} */
    const audioChunk = {
      type: 'audio',
      data: value.data,
    };
    return typeof value.format === 'string'
      ? { ...audioChunk, format: value.format }
      : audioChunk;
  }
  if (value.type === 'done') {
    return { ...value, type: 'done' };
  }
  return null;
}

/** @returns {string} */
function demoToken() {
  const params = new URLSearchParams(window.location.search || '');
  const token = params.get('token') || params.get('admin_token') || sessionStorage.getItem('admin_demo_token') || '';
  if (token) sessionStorage.setItem('admin_demo_token', token);
  stripSensitiveTokenParams(params);
  return token;
}

/**
 * @param {Record<string, string>} [extra]
 * @returns {Record<string, string>}
 */
function adminHeaders(extra = {}) {
  const token = demoToken();
  return token ? { ...extra, 'X-Admin-Token': token, Authorization: `Bearer ${token}` } : extra;
}

/** @returns {string} */
function kioskToken() {
  const params = new URLSearchParams(window.location.search || '');
  const token = (
    params.get('kiosk_token') ||
    params.get('pos_token') ||
    params.get('token') ||
    sessionStorage.getItem('pos_demo_token') ||
    sessionStorage.getItem('kiosk_device_token') ||
    ''
  );
  if (token) {
    sessionStorage.setItem('pos_demo_token', token);
    sessionStorage.setItem('kiosk_device_token', token);
  }
  stripSensitiveTokenParams(params);
  return token;
}

/**
 * @param {Record<string, string>} [extra]
 * @returns {Record<string, string>}
 */
function kioskHeaders(extra = {}) {
  const token = kioskToken();
  return token ? { ...extra, 'X-Kiosk-Token': token } : extra;
}

/** @returns {Promise<Record<string, unknown>>} */
export async function getPublicSettings() {
  if (!publicSettingsRequest) {
    publicSettingsRequest = fetchJson(`${API_BASE}/api/public_settings`)
      .catch(error => {
        publicSettingsRequest = null;
        throw error;
      });
  }
  return publicSettingsRequest;
}

/** @returns {Promise<Record<string, unknown>>} */
export async function getSettings() {
  return fetchJson(`${API_BASE}/api/settings`, { headers: adminHeaders() });
}

/** @returns {Promise<import('../types.d.ts').MenuItem[]>} */
export async function getMenu() {
  if (!menuRequest) {
    menuRequest = fetchJson(`${API_BASE}/api/menu`)
      .catch(error => {
        menuRequest = null;
        throw error;
      });
  }
  return menuRequest;
}

/**
 * @param {string} [surface]
 * @returns {Promise<Record<string, unknown>>}
 */
export async function getPosPromotionBanners(surface = 'pos_home_banner') {
  const cacheKey = String(surface || 'pos_home_banner');
  if (!posPromotionBannersRequests.has(cacheKey)) {
    const params = new URLSearchParams({ surface });
    posPromotionBannersRequests.set(cacheKey, fetchJson(`${API_BASE}/api/promotions/pos-banner?${params.toString()}`, { headers: kioskHeaders() })
      .catch(error => {
        posPromotionBannersRequests.delete(cacheKey);
        throw error;
      }));
  }
  return /** @type {Promise<Record<string, unknown>>} */ (posPromotionBannersRequests.get(cacheKey));
}

/**
 * @param {FormData} formData
 * @returns {Promise<Record<string, unknown>>}
 */
export async function requestAiPushRecommendation(formData) {
  return postFormJson(`${API_BASE}/api/ai_push`, formData, { headers: kioskHeaders() });
}

/**
 * 串流版語音請求。每個 NDJSON chunk 以 callback 回調：
 * @param {FormData} formData
 * @param {VoiceStreamHandlers} handlers
 * @returns {Promise<void>}
 */
export async function streamVoiceAssistantResponse(formData, { onAudio, onDone, onError }) {
  let resp;
  try {
    resp = await fetch(`${API_BASE}/api/ask/stream`, { method: 'POST', body: formData, headers: kioskHeaders() });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  } catch (e) {
    onError(String(e));
    return;
  }
  if (!resp.body) {
    onError('Empty streaming response body');
    return;
  }
  const reader  = resp.body.getReader();
  const decoder = new TextDecoder();
  let leftover  = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const text  = leftover + decoder.decode(value, { stream: true });
      const lines = text.split('\n');
      leftover    = lines.pop() || '';          // 可能不完整的最後一行
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          /** @type {unknown} */
          const parsedJson = JSON.parse(line);
          const parsedChunk = parseVoiceStreamChunk(parsedJson);
          if (!parsedChunk) continue;
          if (
            parsedChunk.type === 'audio'
          ) {
            onAudio(parsedChunk.data, parsedChunk.format || 'wav');
          } else if (parsedChunk.type === 'done') {
            onDone(parsedChunk);
          }
        } catch { /* 忽略格式異常的行 */ }
      }
    }
  } catch (e) {
    onError(String(e));
  }
}

/**
 * @param {FormData} formData
 * @param {AbortSignal} [signal]
 * @returns {Promise<Response>}
 */
export async function submitCheckout(formData, signal) {
  /** @type {RequestInit} */
  const requestOptions = { method: 'POST', body: formData, headers: kioskHeaders() };
  if (signal) requestOptions.signal = signal;
  return fetch(`${API_BASE}/api/checkout`, requestOptions);
}

/**
 * @param {InteractionEventPayload} payload
 * @returns {Promise<Record<string, unknown>>}
 */
export async function reportInteractionEvent(payload) {
  return postJson(`${API_BASE}/api/interaction_event`, payload, kioskHeaders());
}

/**
 * @param {Record<string, unknown>} payload
 * @returns {Promise<Record<string, unknown>>}
 */
export async function reportRecommendationEvent(payload) {
  return postJson(`${API_BASE}/api/recommendation_events`, payload, kioskHeaders());
}

/**
 * @param {string} sessionId
 * @param {string} eventType
 * @param {Blob} mediaBlob
 * @returns {Promise<Record<string, unknown>>}
 */
export async function analyzeEmotionEvent(sessionId, eventType, mediaBlob) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('event_type', eventType);
  formData.append('media', mediaBlob, 'emotion_clip.webm');
  return postFormJson(`${API_BASE}/api/emotion/analyze_event`, formData, { headers: kioskHeaders() });
}

/**
 * @param {string} sessionId
 * @param {string[]} cartIds
 * @returns {Promise<import('../types.d.ts').MenuItem[]>}
 */
export async function getAssistRecommendations(sessionId, cartIds = []) {
  const params = new URLSearchParams({
    session_id: sessionId,
    cart_ids: JSON.stringify(cartIds),
  });
  return fetchJson(`${API_BASE}/api/assist_recommend?${params.toString()}`, { headers: kioskHeaders() });
}

/**
 * @param {string} sessionId
 * @param {Blob} audioBlob
 * @returns {Promise<Record<string, unknown>>}
 */
export async function checkPassiveVoice(sessionId, audioBlob) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('media', audioBlob, 'passive.webm');
  return postFormJson(`${API_BASE}/api/passive_check`, formData, { headers: kioskHeaders() });
}

/**
 * @param {string} sessionId
 * @param {string} phone
 * @returns {Promise<Record<string, unknown>>}
 */
export async function memberLogin(sessionId, phone) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('phone', phone);
  return postFormJson(`${API_BASE}/api/member/login`, formData, { headers: kioskHeaders() });
}

/**
 * @param {string} sessionId
 * @param {string} phone
 * @param {string} nickname
 * @param {{orderHistoryConsent?: boolean, personalizationConsent?: boolean}} [options]
 * @returns {Promise<Record<string, unknown>>}
 */
export async function memberRegister(sessionId, phone, nickname, options = {}) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('phone', phone);
  formData.append('nickname', nickname || '');
  formData.append('order_history_consent', String(options.orderHistoryConsent !== false));
  formData.append('personalization_consent', String(options.personalizationConsent !== false));
  return postFormJson(`${API_BASE}/api/member/register`, formData, { headers: kioskHeaders() });
}

/**
 * @param {string} sessionId
 * @param {string[]} cartIds
 * @param {number} cartTotal
 * @param {string} reason
 * @returns {Promise<Record<string, unknown>>}
 */
export async function recordAbandonedOrder(sessionId, cartIds, cartTotal, reason) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('cart_ids', JSON.stringify(Array.isArray(cartIds) ? cartIds : []));
  formData.append('cart_total', String(Number(cartTotal || 0)));
  formData.append('reason', reason || '');
  return postFormJson(`${API_BASE}/api/member/abandoned_order`, formData, { headers: kioskHeaders() });
}
