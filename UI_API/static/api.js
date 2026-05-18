export const API_BASE = (
  window.location.hostname &&
  window.location.hostname !== 'localhost' &&
  window.location.hostname !== '127.0.0.1' &&
  window.location.protocol !== 'file:'
) ? '' : 'http://127.0.0.1:8000';

async function asJson(response) {
  return response.json();
}

export async function getSettings() {
  return asJson(await fetch(`${API_BASE}/api/settings`));
}

export async function saveSettings(settings) {
  return asJson(await fetch(`${API_BASE}/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings)
  }));
}

export async function getMenu() {
  return asJson(await fetch(`${API_BASE}/api/menu`));
}

export async function saveMenu(menu) {
  return asJson(await fetch(`${API_BASE}/api/menu`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(menu)
  }));
}

export async function detectPersonFrame(formData) {
  return asJson(await fetch(`${API_BASE}/api/person_detect_frame`, { method: 'POST', body: formData }));
}

export async function pingState(formData) {
  return asJson(await fetch(`${API_BASE}/api/ping_state`, { method: 'POST', body: formData }));
}

export async function autoRecommend(formData) {
  return asJson(await fetch(`${API_BASE}/api/auto_recommend`, { method: 'POST', body: formData }));
}

export async function ask(formData) {
  return asJson(await fetch(`${API_BASE}/api/ask`, { method: 'POST', body: formData }));
}

export async function customerService(formData) {
  return asJson(await fetch(`${API_BASE}/api/customer_service`, { method: 'POST', body: formData }));
}

export async function checkout(formData, signal) {
  return fetch(`${API_BASE}/api/checkout`, { method: 'POST', body: formData, signal });
}

export async function getLogs() {
  return asJson(await fetch(`${API_BASE}/api/logs`));
}

export async function clearLogs() {
  return asJson(await fetch(`${API_BASE}/api/logs`, { method: 'DELETE' }));
}

export async function deleteLog(index) {
  return asJson(await fetch(`${API_BASE}/api/logs/${encodeURIComponent(index)}`, { method: 'DELETE' }));
}

export async function clearRagDocs() {
  return asJson(await fetch(`${API_BASE}/api/rag_docs`, { method: 'DELETE' }));
}

export async function uploadRagPdf(formData) {
  return asJson(await fetch(`${API_BASE}/api/rag_pdf`, { method: 'POST', body: formData }));
}

export async function getEmotionClips(sessionId) {
  return asJson(await fetch(`${API_BASE}/api/emotion_clips/${encodeURIComponent(sessionId)}`));
}

export async function clearEmotionClips(sessionId) {
  return asJson(await fetch(`${API_BASE}/api/emotion_clips/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }));
}

export async function getRagDocs() {
  return asJson(await fetch(`${API_BASE}/api/rag_docs`));
}

export async function addRagDoc(payload) {
  return asJson(await fetch(`${API_BASE}/api/rag_docs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }));
}

export async function deleteRagDoc(docId) {
  return asJson(await fetch(`${API_BASE}/api/rag_docs/${encodeURIComponent(docId)}`, { method: 'DELETE' }));
}

export async function deleteRagReviewLog(index) {
  return asJson(await fetch(`${API_BASE}/api/rag_review_logs/${encodeURIComponent(index)}`, { method: 'DELETE' }));
}

export async function getCustomerServiceLogs() {
  return asJson(await fetch(`${API_BASE}/api/customer_service_logs`));
}

export async function sendHumanReply(sourceId, payload) {
  return asJson(await fetch(`${API_BASE}/api/customer_service_logs/${encodeURIComponent(sourceId)}/human_reply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }));
}
