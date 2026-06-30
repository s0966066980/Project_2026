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
  return token;
}

/**
 * @param {Record<string, string>} [extra]
 * @returns {Record<string, string>}
 */
function adminHeaders(extra = {}) {
  const token = demoToken();
  return token ? { ...extra, 'X-Admin-Token': token } : extra;
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
 * @param {FormData} formData
 * @returns {Promise<Record<string, unknown>>}
 */
export async function requestAiPushRecommendation(formData) {
  return postFormJson(`${API_BASE}/api/ai_push`, formData);
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
    resp = await fetch(`${API_BASE}/api/ask/stream`, { method: 'POST', body: formData });
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
  const requestOptions = { method: 'POST', body: formData };
  if (signal) requestOptions.signal = signal;
  return fetch(`${API_BASE}/api/checkout`, requestOptions);
}

/**
 * @param {InteractionEventPayload} payload
 * @returns {Promise<Record<string, unknown>>}
 */
export async function reportInteractionEvent(payload) {
  return postJson(`${API_BASE}/api/interaction_event`, payload);
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
  return postFormJson(`${API_BASE}/api/emotion/analyze_event`, formData);
}

/**
 * @param {string} sessionId
 * @returns {Promise<import('../types.d.ts').MenuItem[]>}
 */
export async function getAssistRecommendations(sessionId) {
  return fetchJson(`${API_BASE}/api/assist_recommend?session_id=${encodeURIComponent(sessionId)}`);
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
  return postFormJson(`${API_BASE}/api/passive_check`, formData);
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
  return postFormJson(`${API_BASE}/api/member/login`, formData);
}

/**
 * @param {string} sessionId
 * @param {string} phone
 * @param {string} nickname
 * @returns {Promise<Record<string, unknown>>}
 */
export async function memberRegister(sessionId, phone, nickname) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('phone', phone);
  formData.append('nickname', nickname || '');
  return postFormJson(`${API_BASE}/api/member/register`, formData);
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
  return postFormJson(`${API_BASE}/api/member/abandoned_order`, formData);
}
