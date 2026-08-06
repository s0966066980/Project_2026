// @ts-check

import { fetchJson, postFormJson, postJson } from './httpClient.js';

/** @typedef {import('../types.d.ts').InteractionEventPayload} InteractionEventPayload */
/** @typedef {import('../types.d.ts').VoiceStreamAudioChunk} VoiceStreamAudioChunk */
/** @typedef {import('../types.d.ts').VoiceStreamChunk} VoiceStreamChunk */
/** @typedef {import('../types.d.ts').VoiceStreamHandlers} VoiceStreamHandlers */
/** @typedef {import('../types.d.ts').VoiceTurnEventCandidate} VoiceTurnEventCandidate */
/** @typedef {import('../types.d.ts').VoiceTurnEventPayload} VoiceTurnEventPayload */

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
  if (value.type === 'transcript' && typeof value.user_text === 'string') {
    return {
      type: 'transcript',
      user_text: value.user_text,
    };
  }
  if (value.type === 'assistant_text' && typeof value.ai_response === 'string') {
    return {
      type: 'assistant_text',
      ai_response: value.ai_response,
      ...(typeof value.user_text === 'string' ? { user_text: value.user_text } : {}),
    };
  }
  if (value.type === 'done') {
    return { ...value, type: 'done' };
  }
  return null;
}

/**
 * @param {Record<string, string>} [extra]
 * @returns {Record<string, string>}
 */
function adminHeaders(extra = {}) {
  return extra;
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
 * @param {string[]} [cartItemIds]
 * @param {string} [sessionId]
 * @returns {Promise<import('../types.d.ts').MenuPriceProjection[]>}
 */
export async function getMenuPriceProjections(cartItemIds = [], sessionId = '') {
  const envelope = await postJson(
    `${API_BASE}/api/v1/menu/price-projection`,
    { cart_item_ids: cartItemIds, session_id: sessionId },
    kioskHeaders(),
  );
  return Array.isArray(envelope?.data) ? envelope.data : [];
}

/**
 * @param {import('../types.d.ts').CartItem[]} cartItems
 * @param {string} [sessionId]
 * @returns {Promise<import('../types.d.ts').CartQuote>}
 */
export async function quoteCart(cartItems, sessionId = '') {
  const requestItems = cartItems.map(item => ({
    id: item.id,
    quantity: Number(item.quantity || 1),
    options: Array.isArray(item.options) ? item.options : [],
    applied_offer_id: item.applied_offer_id || '',
  }));
  const envelope = await postJson(
    `${API_BASE}/api/v1/cart/quote`,
    { cart_items: requestItems, session_id: sessionId },
    kioskHeaders(),
  );
  return envelope.data;
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
export async function streamVoiceAssistantResponse(formData, { onEvent, onAudio, onTranscript, onAssistantText, onDone, onError }) {
  const voiceTurnId = String(formData.get('voice_turn_id') || '');
  let lastSequence = 0;
  let terminal = false;

  /** @param {string} line */
  function consumeLine(line) {
    if (!line.trim()) return;
    const event = /** @type {VoiceTurnEventCandidate} */ (JSON.parse(line));
    onEvent?.(event);
    lastSequence = Number(event.sequence || lastSequence);
    terminal = Boolean(event.terminal);
    if (!isObjectRecord(event.payload)) throw new Error('invalid_voice_turn_event_payload');
    const payload = /** @type {VoiceTurnEventPayload} */ (event.payload);
    if (event.type === 'transcript') onTranscript?.(payload);
    if (event.type === 'assistant_result') onAssistantText?.(payload);
    if (event.type === 'completed') {
      if (payload.audio_base64) onAudio?.(payload.audio_base64, payload.audio_format || 'wav');
      onDone(payload);
    }
    if (event.type === 'transcription_failed' || event.type === 'assistant_failed' || event.type === 'playback_failed') {
      onDone(payload);
    }
  }

  /** @param {Response} response */
  async function consumeResponse(response) {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    if (!response.body) throw new Error('Empty streaming response body');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let leftover = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const lines = (leftover + decoder.decode(value, { stream: true })).split('\n');
      leftover = lines.pop() || '';
      lines.forEach(consumeLine);
    }
    consumeLine(leftover + decoder.decode());
  }

  try {
    await consumeResponse(await fetch(`${API_BASE}/api/ask/stream`, {
      method: 'POST', body: formData, headers: kioskHeaders(),
    }));
  } catch (e) {
    if (!voiceTurnId || lastSequence === 0) {
      onError(String(e));
      throw e;
    }
  }

  for (let reconnect = 0; !terminal && reconnect < 3; reconnect += 1) {
    try {
      await new Promise(resolve => setTimeout(resolve, 150 * (2 ** reconnect)));
      const params = new URLSearchParams({ after_sequence: String(lastSequence) });
      await consumeResponse(await fetch(
        `${API_BASE}/api/ask/stream/${encodeURIComponent(voiceTurnId)}?${params}`,
        { headers: kioskHeaders() },
      ));
    } catch (error) {
      if (reconnect === 2) {
        onError(String(error));
        throw error;
      }
    }
  }
  if (!terminal) {
    const error = new Error('voice_turn_eof_before_terminal');
    onError(String(error));
    throw error;
  }
}

/**
 * @param {string} sessionId
 * @param {import('../types.d.ts').CartItem[]} cartItems
 * @returns {Promise<Record<string, unknown>>}
 */
export async function syncCart(sessionId, cartItems) {
  const currentResponse = await fetch(`${API_BASE}/api/cart/${encodeURIComponent(sessionId)}`, { headers: kioskHeaders() });
  if (!currentResponse.ok) throw new Error(`cart_read_failed:${currentResponse.status}`);
  const current = await currentResponse.json();
  const response = await fetch(`${API_BASE}/api/cart/${encodeURIComponent(sessionId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...kioskHeaders() },
    body: JSON.stringify({
      expected_revision: Number(current.revision || 0),
      lines: cartItems.map(item => ({ item_id: item.id, quantity: Number(item.quantity || 1), options: item.options || [], applied_offer_id: item.applied_offer_id || '' })),
    }),
  });
  if (!response.ok) throw new Error(`cart_write_failed:${response.status}`);
  return response.json();
}

/** @param {string} sessionId @returns {Promise<Record<string, unknown>>} */
export async function prepareCheckout(sessionId) {
  const response = await fetch(`${API_BASE}/api/checkout/prepare`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...kioskHeaders() }, body: JSON.stringify({ session_id: sessionId }),
  });
  if (!response.ok) throw new Error(`checkout_prepare_failed:${response.status}`);
  return response.json();
}

/**
 * @param {string} quoteId
 * @param {string} idempotencyKey
 * @param {AbortSignal | undefined} signal
 * @returns {Promise<Response>}
 */
export async function confirmCheckout(quoteId, idempotencyKey, signal) {
  const headers = { ...kioskHeaders(), 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey };
  return fetch(`${API_BASE}/api/checkout/confirm`, {
    method: 'POST', headers, body: JSON.stringify({ quote_id: quoteId }), ...(signal ? { signal } : {}),
  });
}

/**
 * @param {string} quoteId
 * @param {string} idempotencyKey
 * @returns {Promise<Record<string, unknown>>}
 */
export async function getCheckoutOutcome(quoteId, idempotencyKey) {
  const params = new URLSearchParams({ idempotency_key: idempotencyKey });
  const response = await fetch(`${API_BASE}/api/checkout/outcome/${encodeURIComponent(quoteId)}?${params}`, { headers: kioskHeaders() });
  if (!response.ok) throw new Error(`checkout_outcome_failed:${response.status}`);
  return response.json();
}

/** @param {Record<string, unknown>} [payload] @returns {Promise<Record<string, unknown>>} */
export async function startEntryFlow(payload = {}) {
  const response = await fetch(`${API_BASE}/api/entry-flow/start`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...kioskHeaders() }, body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`entry_flow_start_failed:${response.status}`);
  return response.json();
}

/**
 * @param {string} entryFlowId
 * @param {number} phaseRevision
 * @param {string} command
 * @param {Record<string, unknown>} [payload]
 * @returns {Promise<Record<string, unknown>>}
 */
export async function commandEntryFlow(entryFlowId, phaseRevision, command, payload = {}) {
  const response = await fetch(`${API_BASE}/api/entry-flow/${encodeURIComponent(entryFlowId)}/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...kioskHeaders() },
    body: JSON.stringify({ phase_revision: phaseRevision, command, payload }),
  });
  if (!response.ok) throw new Error(`entry_flow_command_failed:${response.status}`);
  return response.json();
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
 * @param {Record<string, unknown>} payload
 * @returns {Promise<Record<string, unknown>>}
 */
export async function reportCommercialTouch(payload) {
  return postJson(`${API_BASE}/api/v1/commercial-touches`, payload, kioskHeaders());
}

/**
 * @param {string} sessionId
 * @param {'voice_mode_started' | 'voice_mode_ended'} phase
 * @param {Blob} mediaBlob
 * @param {{emotionRoundId: string, voiceTurnId: string, voiceTurnIndex: number, observedAtMs: number, speechText?: string}} context
 * @returns {Promise<Record<string, unknown>>}
 */
export async function analyzeVoiceEmotionEvent(sessionId, phase, mediaBlob, context) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('event_type', phase);
  formData.append('emotion_round_id', context.emotionRoundId);
  formData.append('voice_turn_id', context.voiceTurnId);
  formData.append('voice_turn_index', String(context.voiceTurnIndex));
  formData.append('observed_at_ms', String(context.observedAtMs));
  if (context.speechText) formData.append('speech_text', context.speechText.slice(0, 500));
  formData.append('media', mediaBlob, `voice_emotion_${phase}.webm`);
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
  const response = await postFormJson(`${API_BASE}/api/member/login`, formData, { headers: kioskHeaders() });
  if (!isObjectRecord(response) || typeof response.found !== 'boolean') {
    throw new Error('member login returned an invalid response');
  }
  return response;
}

/**
 * @param {string} sessionId
 * @param {string} phone
 * @param {string} nickname
 * @param {{necessaryTermsAccepted?: boolean, orderHistoryConsent?: boolean, personalizationConsent?: boolean}} [options]
 * @returns {Promise<Record<string, unknown>>}
 */
export async function memberRegister(sessionId, phone, nickname, options = {}) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('phone', phone);
  formData.append('nickname', nickname || '');
  formData.append('necessary_terms_accepted', String(options.necessaryTermsAccepted === true));
  formData.append('order_history_consent', String(options.orderHistoryConsent === true));
  formData.append('personalization_consent', String(options.personalizationConsent === true));
  const response = await postFormJson(`${API_BASE}/api/member/register`, formData, { headers: kioskHeaders() });
  if (!isObjectRecord(response) || typeof response.ok !== 'boolean') {
    throw new Error('member registration returned an invalid response');
  }
  return response;
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
