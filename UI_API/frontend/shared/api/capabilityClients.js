// @ts-nocheck

// These small adapters are the generated-client seam: the canonical request
// and response types live in v1Client.ts; this JS layer only names operations
// for legacy feature modules and is intentionally kept free of business logic.

import { createApiV1Client } from './v1Client.js';
import { fetchResponse } from '../httpClient.js';

/**
 * The only browser-facing owners of versioned capability paths. Feature modules
 * receive domain operations instead of assembling URLs or response envelopes.
 */
function v1(options = {}) {
  return createApiV1Client({
    baseUrl: options.baseUrl,
    headers: options.headers,
    // Resolve the global at request time so kiosk tests and embedders can
    // replace fetch after the client factory has been created.
    fetchImpl: options.fetchImpl ?? ((...args) => fetch(...args)),
    timeoutMs: options.timeoutMs,
    timers: options.timers,
    retryCount: options.retryCount,
  });
}

const payload = response => response?.data ?? response;

/** @param {{baseUrl?: string, headers?: () => Record<string, string>}} [options] */
export function createCampaignClient(options = {}) {
  const client = v1(options);
  const data = response => response.data;
  return {
    list: () => client.get('/campaigns').then(data),
    get: campaignId => client.get(`/campaigns/${encodeURIComponent(campaignId)}`).then(data),
    preview: payload => client.post('/campaigns/preview', payload).then(data),
    createDraft: payload => client.post('/campaigns', payload).then(data),
    reviseDraft: (campaignId, payload) => client.put(`/campaigns/${encodeURIComponent(campaignId)}/draft`, payload).then(data),
    publish: payload => client.post('/campaigns/publish', payload).then(data),
    transition: (campaignId, payload) => client.post(`/campaigns/${encodeURIComponent(campaignId)}/transition`, payload).then(data),
  };
}

/** @param {{baseUrl?: string, headers?: () => Record<string, string>}} [options] */
export function createKnowledgeClient(options = {}) {
  const client = v1(options);
  const data = response => response.data;
  return {
    list: () => client.get('/rag/knowledge').then(data),
    create: payload => client.post('/rag/knowledge', payload).then(data),
    revise: (itemId, payload) => client.put(`/rag/knowledge/${encodeURIComponent(itemId)}`, payload).then(data),
    publish: payload => client.post('/rag/knowledge/publish', payload).then(data),
    resumePublication: attemptId => client.post(`/rag/knowledge/publication-attempts/${encodeURIComponent(attemptId)}/resume`).then(data),
    retire: (itemId, expectedRowRevision) => client.post(`/rag/knowledge/${encodeURIComponent(itemId)}/retire`, { expected_row_revision: expectedRowRevision }).then(data),
    remove: (itemId, expectedRowRevision) => client.request(
      `/rag/knowledge/${encodeURIComponent(itemId)}?expected_row_revision=${encodeURIComponent(expectedRowRevision)}`,
      { method: 'DELETE' },
    ).then(data),
    retrievalTest: payload => client.post('/rag/retrieval/test', payload).then(data),
    confirmRetrieval: checkId => client.post(`/rag/retrieval/checks/${encodeURIComponent(checkId)}/confirm`).then(data),
    configurations: () => client.get('/rag/retrieval/configurations').then(data),
    publishConfiguration: payload => client.post('/rag/retrieval/configurations', payload).then(data),
    removeConfiguration: version => client.request(`/rag/retrieval/configurations/${encodeURIComponent(version)}`, { method: 'DELETE' }).then(data),
    job: attemptId => client.get(`/rag/knowledge/publication-attempts/${encodeURIComponent(attemptId)}`).then(data),
  };
}

/** @param {{baseUrl?: string, headers?: () => Record<string, string>, fetchImpl?: typeof fetch, timeoutMs?: number, timers?: any, retryCount?: number}} [options] */
export function createOperationsClient(options = {}) {
  const client = v1(options);
  const data = response => response.data;
  return {
    publicSettings: () => client.get('/public-settings').then(data),
    settings: () => client.get('/settings').then(response => data(response)?.values ?? data(response)),
    patchSettings: values => client.patch('/settings', { values }).then(response => data(response)?.values ?? data(response)),
    sessionStats: () => client.get('/operations/session-stats').then(payload),
    clearSessionStats: () => client.request('/operations/session-stats', { method: 'DELETE' }).then(payload),
    logs: () => client.get('/operations/logs').then(payload),
    clearLogs: () => client.request('/operations/logs', { method: 'DELETE' }).then(payload),
    deleteLog: index => client.request(`/operations/logs/${encodeURIComponent(index)}`, { method: 'DELETE' }).then(payload),
    llmRouting: () => client.get('/settings/llm-routing').then(payload),
    llmTraffic: () => client.get('/settings/llm-traffic').then(payload),
    llmConnectivityTest: () => client.post('/settings/llm-connectivity-test', {}).then(payload),
    settingsVersions: () => client.get('/settings/versions').then(payload),
    rollbackSettingsVersion: version => client.post(`/settings/versions/${encodeURIComponent(version)}/rollback`, {}).then(payload),
    serviceHealth: () => client.get('/operations/service-health').then(data),
    overview: (days = 1) => client.get(`/operations/overview?days=${encodeURIComponent(days)}`).then(data),
    effectiveness: params => {
      const query = new URLSearchParams(params || {});
      return client.get(`/recommendation-effectiveness?${query.toString()}`).then(data);
    },
    recommendations: params => {
      const query = new URLSearchParams(params || {});
      return client.get(`/recommendations?${query.toString()}`).then(data);
    },
    members: params => {
      const query = new URLSearchParams(params || {});
      return client.get(`/members?${query.toString()}`);
    },
  };
}

/** @param {{baseUrl?: string, headers?: () => Record<string, string>}} [options] */
export function createRecommendationClient(options = {}) {
  const operations = createOperationsClient(options);
  return {
    effectiveness: operations.effectiveness,
    list: operations.recommendations,
  };
}

/** @param {{baseUrl?: string, headers?: () => Record<string, string>}} [options] */
export function createMemberClient(options = {}) {
  const baseUrl = (options.baseUrl || '').replace(/\/$/, '');
  const headers = options.headers || (() => ({}));
  const operations = createOperationsClient(options);
  const client = v1(options);
  const data = response => response.data;
  return {
    list: params => operations.members(params).then(response => response),
    detail: memberRef => client.get(`/members/${encodeURIComponent(memberRef)}`).then(data),
    saveVerifiedPreferences: (memberRef, payload) => client.put(`/members/${encodeURIComponent(memberRef)}/verified-preferences`, payload).then(data),
    clearRecords: memberRef => client.request(`/members/${encodeURIComponent(memberRef)}/records`, { method: 'DELETE' }).then(data),
    remove: memberRef => client.request(`/members/${encodeURIComponent(memberRef)}`, { method: 'DELETE' }).then(data),
    exportCsv: async () => {
      const response = await fetchResponse(`${baseUrl}/api/v1/members/export`, { headers: { ...headers(), Accept: 'text/csv' } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.blob();
    },
    login: (sessionId, phone) => {
      const body = new FormData();
      body.append('session_id', sessionId);
      body.append('phone', phone);
      return client.request('/member/login', { method: 'POST', body }).then(payload);
    },
    register: (sessionId, phone, nickname, consent = {}) => {
      const body = new FormData();
      body.append('session_id', sessionId);
      body.append('phone', phone);
      body.append('nickname', nickname || '');
      body.append('necessary_terms_accepted', String(consent.necessaryTermsAccepted === true));
      body.append('order_history_consent', String(consent.orderHistoryConsent === true));
      body.append('personalization_consent', String(consent.personalizationConsent === true));
      return client.request('/member/register', { method: 'POST', body }).then(payload);
    },
    abandonedOrder: (sessionId, cartIds, cartTotal, reason) => {
      const body = new FormData();
      body.append('session_id', sessionId);
      body.append('cart_ids', JSON.stringify(Array.isArray(cartIds) ? cartIds : []));
      body.append('cart_total', String(Number(cartTotal || 0)));
      body.append('reason', reason || '');
      return client.request('/member/abandoned_order', { method: 'POST', body }).then(payload);
    },
  };
}

/** @param {{baseUrl?: string, headers?: () => Record<string, string>, timeoutMs?: number}} [options] */
export function createKioskCapabilityClient(options = {}) {
  const client = v1({ ...options, timeoutMs: options.timeoutMs ?? 15_000 });
  return {
    priceProjection: (cartItemIds, sessionId) => client.post('/menu/price-projection', {
      cart_item_ids: cartItemIds,
      session_id: sessionId,
    }).then(response => response.data),
    quoteCart: payload => client.post('/cart/quote', payload).then(response => response.data),
    commercialTouch: payload => client.post('/commercial-touches', payload).then(response => response.data),
  };
}

/** Versioned Ordering Entry, Cart, and Checkout operations. */
export function createOrderingClient(options = {}) {
  const client = v1({ ...options, timeoutMs: options.timeoutMs ?? 15_000, retryCount: options.retryCount ?? 0 });
  return {
    startEntryFlow: body => client.post('/entry-flow/start', body).then(payload),
    commandEntryFlow: (entryFlowId, body) => client.post(`/entry-flow/${encodeURIComponent(entryFlowId)}/command`, body).then(payload),
    getEntryFlow: entryFlowId => client.get(`/entry-flow/${encodeURIComponent(entryFlowId)}`).then(payload),
    getCart: sessionId => client.get(`/cart/${encodeURIComponent(sessionId)}`).then(payload),
    replaceCart: (sessionId, body) => client.put(`/cart/${encodeURIComponent(sessionId)}`, body).then(payload),
    prepareCheckout: body => client.post('/checkout/prepare', body).then(payload),
    confirmCheckout: (body, idempotencyKey, signal) => client.request('/checkout/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(body),
      ...(signal ? { signal } : {}),
    }).then(payload),
    checkoutOutcome: (quoteId, idempotencyKey) => client.get(
      `/checkout/outcome/${encodeURIComponent(quoteId)}?${new URLSearchParams({ idempotency_key: idempotencyKey })}`,
    ).then(payload),
  };
}

/** Versioned Voice streaming URL and durable replay operations. */
export function createVoiceClient(options = {}) {
  const baseUrl = (options.baseUrl || '').replace(/\/$/, '');
  const headers = options.headers || (() => ({}));
  return {
    streamUrl: `${baseUrl}/api/v1/ask/stream`,
    replayUrl: voiceTurnId => `${baseUrl}/api/v1/ask/stream/${encodeURIComponent(voiceTurnId)}`,
    headers,
  };
}

/** Versioned Emotion Diagnostics operations. */
export function createEmotionClient(options = {}) {
  const client = v1({ ...options, timeoutMs: options.timeoutMs ?? 90_000 });
  return {
    profiles: () => client.get('/emotion/profiles').then(payload),
    readiness: () => client.get('/emotion/readiness').then(payload),
    analyzeEvent: formData => client.request('/emotion/analyze_event', { method: 'POST', body: formData }).then(payload),
    analyzeMediaTest: formData => client.request('/emotion/analyze_media_test', { method: 'POST', body: formData }).then(payload),
    records: limit => client.get(`/emotion/records?limit=${encodeURIComponent(limit ?? 200)}`).then(payload),
    clearRecords: () => client.request('/emotion/records', { method: 'DELETE' }).then(payload),
  };
}

/** Versioned interaction and recommendation event operations. */
export function createInteractionClient(options = {}) {
  const client = v1(options);
  return {
    report: body => client.post('/interaction_event', body).then(payload),
    events: (sessionId, limit = 200) => client.get(`/interaction_events/${encodeURIComponent(sessionId)}?limit=${encodeURIComponent(limit)}`).then(payload),
    barrierState: body => client.post('/barrier_state', body).then(payload),
    interventionResult: body => client.post('/intervention_result', body).then(payload),
  };
}

export function createRecommendationEventClient(options = {}) {
  const client = v1(options);
  return {
    report: body => client.post('/recommendation_events', body).then(payload),
    list: (sessionId = '', limit = 200) => client.get(`/recommendation_events?${new URLSearchParams({ session_id: sessionId, limit: String(limit) })}`).then(payload),
    // The cutoff is explicit on the wire. The server defaults to keeping 30
    // days because the operations overview reads the same rows.
    clear: ({ olderThanDays = 30 } = {}) =>
      client
        .request(`/recommendation_events?older_than_days=${encodeURIComponent(String(olderThanDays))}`, {
          method: 'DELETE',
        })
        .then(payload),
  };
}

/** Versioned recommendation assistance and promotion banner operations. */
export function createRecommendationAssistClient(options = {}) {
  const client = v1(options);
  return {
    push: formData => client.request('/ai_push', { method: 'POST', body: formData }).then(payload),
    assist: (sessionId, cartIds = []) => client.get(`/assist_recommend?${new URLSearchParams({ session_id: sessionId, cart_ids: JSON.stringify(cartIds) })}`).then(payload),
  };
}

export function createPromotionBannerClient(options = {}) {
  const client = v1(options);
  return {
    list: (surface = 'pos_home_banner') => client.get(`/promotions/pos-banner?${new URLSearchParams({ surface })}`).then(payload),
  };
}

/** Versioned local diagnostics (Ollama and voice prompt probes). */
export function createDiagnosticClient(options = {}) {
  const client = v1(options);
  return {
    models: () => client.get('/diagnostics/ollama-models').then(payload),
    voicePrompt: () => client.get('/diagnostics/voice-prompt').then(payload),
    ask: body => client.post('/diagnostics/ask', body).then(payload),
  };
}

/** Versioned authoring surface for operator-reviewed push copy. */
export function createPushCopyClient(options = {}) {
  const client = v1(options);
  return {
    list: () => client.get('/push-copy').then(payload),
    batch: () => client.get('/push-copy/batch').then(payload),
    startBatch: body => client.post('/push-copy/batch', body).then(payload),
    generate: (itemId, body) => client.post(`/push-copy/${encodeURIComponent(itemId)}/generate`, body).then(payload),
    save: (itemId, body) => client.post(`/push-copy/${encodeURIComponent(itemId)}`, body).then(payload),
  };
}


/** Versioned Daily Operations Diagnostic Workbench surface. */
export function createOptimizationClient(options = {}) {
  const client = v1(options);
  return {
    questions: () => client.get('/optimization/questions').then(payload),
    createQuestion: body => client.post('/optimization/questions', body).then(payload),
    updateQuestion: (questionId, body) => client.put(`/optimization/questions/${encodeURIComponent(questionId)}`, body).then(payload),
    deleteQuestion: questionId => client.request(`/optimization/questions/${encodeURIComponent(questionId)}`, { method: 'DELETE' }).then(payload),
    profiles: () => client.get('/optimization/profiles').then(payload),
    latest: () => client.get('/optimization/latest').then(payload),
    candidate: () => client.get('/optimization/candidate').then(payload),
    simulate: body => client.post('/optimization/simulations', body).then(payload),
    abandonCandidate: candidateId => client.post(`/optimization/candidate/${encodeURIComponent(candidateId)}/abandon`).then(payload),
    editCandidate: (candidateId, body) => client.put(`/optimization/candidate/${encodeURIComponent(candidateId)}`, body).then(payload),
    confirmCandidate: candidateId => client.post(`/optimization/candidate/${encodeURIComponent(candidateId)}/confirm`).then(payload),
  };
}

/** Versioned read-only Voice Evidence metadata surface. */
export function createVoiceEvidenceClient(options = {}) {
  const client = v1(options);
  return {
    list: params => {
      const query = new URLSearchParams(params || {});
      return client.get(`/voice-evidence?${query.toString()}`).then(payload);
    },
  };
}
