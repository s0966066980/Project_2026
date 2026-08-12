// @ts-check

import { createCatalogClient } from './api/catalogClient.js';
import {
  createEmotionClient,
  createInteractionClient,
  createKioskCapabilityClient,
  createMemberClient,
  createOrderingClient,
  createOperationsClient,
  createPromotionBannerClient,
  createRecommendationAssistClient,
  createRecommendationEventClient,
  createVoiceClient,
} from './api/capabilityClients.js';

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

/**
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

const catalogClient = createCatalogClient({ baseUrl: API_BASE, headers: () => kioskHeaders() });
const kioskOperationsClient = createOperationsClient({ baseUrl: API_BASE, headers: () => kioskHeaders() });
const kioskCapabilityClient = createKioskCapabilityClient({ baseUrl: API_BASE, headers: () => kioskHeaders() });
const orderingClient = createOrderingClient({ baseUrl: API_BASE, headers: () => kioskHeaders() });
const voiceClient = createVoiceClient({ baseUrl: API_BASE, headers: () => kioskHeaders() });
const emotionClient = createEmotionClient({ baseUrl: API_BASE, headers: () => kioskHeaders() });
const interactionClient = createInteractionClient({ baseUrl: API_BASE, headers: () => kioskHeaders() });
const recommendationEventClient = createRecommendationEventClient({ baseUrl: API_BASE, headers: () => kioskHeaders() });
const recommendationAssistClient = createRecommendationAssistClient({ baseUrl: API_BASE, headers: () => kioskHeaders() });
const promotionBannerClient = createPromotionBannerClient({ baseUrl: API_BASE, headers: () => kioskHeaders() });
const memberKioskClient = createMemberClient({ baseUrl: API_BASE, headers: () => kioskHeaders() });

/**
 * @param {() => Promise<any>} call
 * @param {string} failureCode
 * @returns {Promise<any>}
 */
async function versionedKioskCall(call, failureCode) {
  try {
    return await call();
  } catch (error) {
    const detail = /** @type {any} */ (error);
    const status = Number(detail?.status || 0);
    if (status) throw new Error(`${failureCode}:${status}`);
    throw error;
  }
}

/** @returns {Promise<Record<string, unknown>>} */
export async function getPublicSettings() {
  if (!publicSettingsRequest) {
    publicSettingsRequest = kioskOperationsClient.publicSettings()
      .catch(error => {
        publicSettingsRequest = null;
        throw error;
      });
  }
  return publicSettingsRequest;
}

/** @returns {Promise<Record<string, unknown>>} */
export async function getSettings() {
  return kioskOperationsClient.settings();
}

/** @returns {Promise<import('../types.d.ts').MenuItem[]>} */
export async function getMenu() {
  if (!menuRequest) {
    // The kiosk reads the catalog through the capability's published contract
    // rather than the legacy menu route, so a field it depends on
    // cannot change without failing the generated-contract drift gate.
    menuRequest = catalogClient
      .listItems()
      .then(list => list.items)
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
  const data = await kioskCapabilityClient.priceProjection(cartItemIds, sessionId);
  return Array.isArray(data) ? data : [];
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
  return kioskCapabilityClient.quoteCart({ cart_items: requestItems, session_id: sessionId });
}

/**
 * @param {string} [surface]
 * @returns {Promise<Record<string, unknown>>}
 */
export async function getPosPromotionBanners(surface = 'pos_home_banner') {
  const cacheKey = String(surface || 'pos_home_banner');
  if (!posPromotionBannersRequests.has(cacheKey)) {
    posPromotionBannersRequests.set(cacheKey, promotionBannerClient.list(surface)
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
  return recommendationAssistClient.push(formData);
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

  /**
   * A refusal carries the reason the service gave. Collapsing it into
   * `HTTP 503` would leave the kiosk unable to tell a capability that is
   * still starting from one that failed, which are different things to a
   * customer standing at the machine.
   *
   * @param {Response} response
   */
  async function consumeResponse(response) {
    if (!response.ok) {
      let code = '';
      try {
        const body = await response.json();
        code = String(body?.detail?.code || body?.code || '');
      } catch {
        code = '';
      }
      const failure = new Error(code ? `HTTP ${response.status} ${code}` : `HTTP ${response.status}`);
      Object.assign(failure, { status: response.status, code });
      throw failure;
    }
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

  /** @param {unknown} error @returns {{status: number, code: string}} */
  function refusal(error) {
    const detail = /** @type {any} */ (error);
    return { status: Number(detail?.status || 0), code: String(detail?.code || '') };
  }

  try {
    await consumeResponse(await fetch(voiceClient.streamUrl, {
      method: 'POST', body: formData, headers: voiceClient.headers(),
    }));
  } catch (e) {
    if (!voiceTurnId || lastSequence === 0) {
      onError(String(e), refusal(e));
      throw e;
    }
  }

  for (let reconnect = 0; !terminal && reconnect < 3; reconnect += 1) {
    try {
      await new Promise(resolve => setTimeout(resolve, 150 * (2 ** reconnect)));
      const params = new URLSearchParams({ after_sequence: String(lastSequence) });
      await consumeResponse(await fetch(
        `${voiceClient.replayUrl(voiceTurnId)}?${params}`,
        { headers: voiceClient.headers() },
      ));
    } catch (error) {
      if (reconnect === 2) {
        onError(String(error), refusal(error));
        throw error;
      }
    }
  }
  if (!terminal) {
    const error = new Error('voice_turn_eof_before_terminal');
    onError(String(error), refusal(error));
    throw error;
  }
}

/**
 * @param {string} sessionId
 * @param {import('../types.d.ts').CartItem[]} cartItems
 * @returns {Promise<Record<string, unknown>>}
 */
export async function syncCart(sessionId, cartItems) {
  const current = await versionedKioskCall(() => orderingClient.getCart(sessionId), 'cart_read_failed');
  return versionedKioskCall(() => orderingClient.replaceCart(sessionId, {
    expected_revision: Number(current.revision || 0),
    lines: cartItems.map(item => ({ item_id: item.id, quantity: Number(item.quantity || 1), options: item.options || [], applied_offer_id: item.applied_offer_id || '' })),
  }), 'cart_write_failed');
}

/** @param {string} sessionId @returns {Promise<Record<string, unknown>>} */
export async function prepareCheckout(sessionId) {
  return versionedKioskCall(() => orderingClient.prepareCheckout({ session_id: sessionId }), 'checkout_prepare_failed');
}

/**
 * @param {string} quoteId
 * @param {string} idempotencyKey
 * @param {AbortSignal | undefined} signal
 * @returns {Promise<Response>}
 */
export async function confirmCheckout(quoteId, idempotencyKey, signal) {
  const result = await orderingClient.confirmCheckout({ quote_id: quoteId }, idempotencyKey, signal);
  return new Response(JSON.stringify(result), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

/**
 * @param {string} quoteId
 * @param {string} idempotencyKey
 * @returns {Promise<Record<string, unknown>>}
 */
export async function getCheckoutOutcome(quoteId, idempotencyKey) {
  return versionedKioskCall(() => orderingClient.checkoutOutcome(quoteId, idempotencyKey), 'checkout_outcome_failed');
}

/** @param {Record<string, unknown>} [payload] @returns {Promise<Record<string, unknown>>} */
export async function startEntryFlow(payload = {}) {
  return versionedKioskCall(() => orderingClient.startEntryFlow(payload), 'entry_flow_start_failed');
}

/**
 * @param {string} entryFlowId
 * @param {number} phaseRevision
 * @param {string} command
 * @param {Record<string, unknown>} [payload]
 * @returns {Promise<Record<string, unknown>>}
 */
export async function commandEntryFlow(entryFlowId, phaseRevision, command, payload = {}) {
  return versionedKioskCall(
    () => orderingClient.commandEntryFlow(entryFlowId, { phase_revision: phaseRevision, command, payload }),
    'entry_flow_command_failed',
  );
}

/**
 * @param {InteractionEventPayload} payload
 * @returns {Promise<Record<string, unknown>>}
 */
export async function reportInteractionEvent(payload) {
  return interactionClient.report(payload);
}

/**
 * @param {Record<string, unknown>} payload
 * @returns {Promise<Record<string, unknown>>}
 */
export async function reportRecommendationEvent(payload) {
  return recommendationEventClient.report(payload);
}

/**
 * @param {Record<string, unknown>} payload
 * @returns {Promise<Record<string, unknown>>}
 */
export async function reportCommercialTouch(payload) {
  return kioskCapabilityClient.commercialTouch(payload);
}

/**
 * @param {string} sessionId
 * @param {'voice_mode_ended' | 'ordering_periodic'} phase
 * @param {Blob} mediaBlob
 * @returns {Promise<Record<string, unknown>>}
 */
export async function analyzeVoiceEmotionEvent(sessionId, phase, mediaBlob) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('event_type', phase);
  formData.append('media', mediaBlob, `voice_emotion_${phase}.webm`);
  // Emotion inference runs a model over a clip of up to thirty seconds, so it
  // needs a budget of its own rather than the default request deadline. It is
  // still bounded: an enrichment that never returns must not hold a request
  // open for the rest of the ordering session.
  return emotionClient.analyzeEvent(formData);
}

/**
 * Check the selected emotion provider before Kiosk requests a camera or records
 * a customer clip.
 * @returns {Promise<{ready: boolean, status: string, provider?: Record<string, unknown>}>}
 */
export async function getEmotionReadiness() {
  return emotionClient.readiness();
}

/**
 * @param {string} sessionId
 * @param {string[]} cartIds
 * @returns {Promise<import('../types.d.ts').MenuItem[]>}
 */
export async function getAssistRecommendations(sessionId, cartIds = []) {
  return recommendationAssistClient.assist(sessionId, cartIds);
}

/**
 * @param {string} sessionId
 * @param {string} phone
 * @returns {Promise<Record<string, unknown>>}
 */
export async function memberLogin(sessionId, phone) {
  const response = await memberKioskClient.login(sessionId, phone);
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
  const response = await memberKioskClient.register(sessionId, phone, nickname, options);
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
  return memberKioskClient.abandonedOrder(sessionId, cartIds, cartTotal, reason);
}
