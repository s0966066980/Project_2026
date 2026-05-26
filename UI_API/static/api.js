export const API_BASE = (
  window.location.protocol === 'file:'
) ? 'http://127.0.0.1:8000' : '';

async function asJson(response) {
  return response.json();
}

function demoToken() {
  const params = new URLSearchParams(window.location.search || '');
  const token = params.get('token') || params.get('admin_token') || sessionStorage.getItem('admin_demo_token') || '';
  if (token) sessionStorage.setItem('admin_demo_token', token);
  return token;
}

function adminHeaders(extra = {}) {
  const token = demoToken();
  return token ? { ...extra, 'X-Admin-Token': token } : extra;
}

export function adminQuerySuffix(prefix = '?') {
  const token = demoToken();
  if (!token) return '';
  return `${prefix}token=${encodeURIComponent(token)}`;
}

export async function getPublicSettings() {
  return asJson(await fetch(`${API_BASE}/api/public_settings`));
}

export async function getSettings() {
  return asJson(await fetch(`${API_BASE}/api/settings`, { headers: adminHeaders() }));
}

export async function saveSettings(settings) {
  return asJson(await fetch(`${API_BASE}/api/settings`, {
    method: 'POST',
    headers: adminHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(settings)
  }));
}

export async function getMenu() {
  return asJson(await fetch(`${API_BASE}/api/menu`));
}

export async function saveMenu(menu) {
  return asJson(await fetch(`${API_BASE}/api/menu`, {
    method: 'POST',
    headers: adminHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(menu)
  }));
}

export async function detectPersonFrame(formData) {
  return asJson(await fetch(`${API_BASE}/api/person_detect_frame`, { method: 'POST', body: formData }));
}

export async function pingState(formData) {
  return asJson(await fetch(`${API_BASE}/api/ping_state`, { method: 'POST', body: formData }));
}

export async function triggeredMultimodalAnalysis(formData) {
  return asJson(await fetch(`${API_BASE}/api/triggered_multimodal_analysis`, {
    method: 'POST',
    body: formData
  }));
}

export async function autoRecommend(formData) {
  return asJson(await fetch(`${API_BASE}/api/auto_recommend`, { method: 'POST', body: formData }));
}

export async function ask(formData) {
  return asJson(await fetch(`${API_BASE}/api/ask`, { method: 'POST', body: formData }));
}

export async function checkout(formData, signal) {
  return fetch(`${API_BASE}/api/checkout`, { method: 'POST', body: formData, signal });
}

export async function getLogs() {
  return asJson(await fetch(`${API_BASE}/api/logs`, { headers: adminHeaders() }));
}

export async function clearLogs() {
  return asJson(await fetch(`${API_BASE}/api/logs`, { method: 'DELETE', headers: adminHeaders() }));
}

export async function deleteLog(index) {
  return asJson(await fetch(`${API_BASE}/api/logs/${encodeURIComponent(index)}`, { method: 'DELETE', headers: adminHeaders() }));
}

export async function clearRagDocs() {
  return asJson(await fetch(`${API_BASE}/api/rag_docs`, { method: 'DELETE', headers: adminHeaders() }));
}

export async function uploadRagPdf(formData) {
  return asJson(await fetch(`${API_BASE}/api/rag_pdf`, { method: 'POST', headers: adminHeaders(), body: formData }));
}

export async function getEmotionClips(sessionId) {
  return asJson(await fetch(`${API_BASE}/api/emotion_clips/${encodeURIComponent(sessionId)}`, { headers: adminHeaders() }));
}

export async function getEmotionStatus() {
  return asJson(await fetch(`${API_BASE}/api/emotion_status`, { headers: adminHeaders() }));
}

export async function clearEmotionClips(sessionId) {
  return asJson(await fetch(`${API_BASE}/api/emotion_clips/${encodeURIComponent(sessionId)}`, { method: 'DELETE', headers: adminHeaders() }));
}

export async function getRagDocs() {
  return asJson(await fetch(`${API_BASE}/api/rag_docs`, { headers: adminHeaders() }));
}

export async function getRagStatus() {
  return asJson(await fetch(`${API_BASE}/api/rag_status`, { headers: adminHeaders() }));
}

export async function getOllamaModels() {
  return asJson(await fetch(`${API_BASE}/api/ollama_models`, { headers: adminHeaders() }));
}

export async function reviewAllRagDocs(payload = {}) {
  return asJson(await fetch(`${API_BASE}/api/rag_docs/review_all`, {
    method: 'POST',
    headers: adminHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload)
  }));
}

export async function addRagDoc(payload) {
  return asJson(await fetch(`${API_BASE}/api/rag_docs`, {
    method: 'POST',
    headers: adminHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload)
  }));
}

export async function deleteRagDoc(docId) {
  return asJson(await fetch(`${API_BASE}/api/rag_docs/${encodeURIComponent(docId)}`, { method: 'DELETE', headers: adminHeaders() }));
}

export async function deleteRagReviewLog(index) {
  return asJson(await fetch(`${API_BASE}/api/rag_review_logs/${encodeURIComponent(index)}`, { method: 'DELETE', headers: adminHeaders() }));
}

export async function reportInteractionEvent(payload) {
  return asJson(await fetch(`${API_BASE}/api/interaction_event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  }));
}

export async function barrierState(payload) {
  return asJson(await fetch(`${API_BASE}/api/barrier_state`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  }));
}

export async function getInterventionStats() {
  return asJson(await fetch(`${API_BASE}/api/intervention_stats`, { headers: adminHeaders() }));
}

export async function clearInterventionLogs() {
  return asJson(await fetch(`${API_BASE}/api/intervention_logs`, { method: 'DELETE', headers: adminHeaders() }));
}

export async function startEmotionLlama() {
  return asJson(await fetch(`${API_BASE}/api/emotion_llama/start`, { method: 'POST', headers: adminHeaders() }));
}

export async function stopEmotionLlama() {
  return asJson(await fetch(`${API_BASE}/api/emotion_llama/stop`, { method: 'POST', headers: adminHeaders() }));
}
