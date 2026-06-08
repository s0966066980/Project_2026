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




export async function aiPush(formData) {
  return asJson(await fetch(`${API_BASE}/api/ai_push`, { method: 'POST', body: formData }));
}

export async function ask(formData) {
  return asJson(await fetch(`${API_BASE}/api/ask`, { method: 'POST', body: formData }));
}

/**
 * 串流版語音請求。每個 NDJSON chunk 以 callback 回調：
 *   onAudio(base64: string, format: string) — 每段語音
 *   onDone(data: object)                    — 最終結果（含 cart_actions）
 *   onError(msg: string)                    — 發生錯誤
 */
export async function askStream(formData, { onAudio, onDone, onError }) {
  let resp;
  try {
    resp = await fetch(`${API_BASE}/api/ask/stream`, { method: 'POST', body: formData });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  } catch (e) {
    onError(String(e));
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
      leftover    = lines.pop();          // 可能不完整的最後一行
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const chunk = JSON.parse(line);
          if (chunk.type === 'audio') onAudio(chunk.data, chunk.format || 'wav');
          else if (chunk.type === 'done') onDone(chunk);
        } catch { /* 忽略格式異常的行 */ }
      }
    }
  } catch (e) {
    onError(String(e));
  }
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

export async function reportInteractionEvent(payload) {
  return asJson(await fetch(`${API_BASE}/api/interaction_event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  }));
}

export async function analyzeEmotionEvent(sessionId, eventType, mediaBlob) {
  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('event_type', eventType);
  fd.append('media', mediaBlob, 'emotion_clip.webm');
  return asJson(await fetch(`${API_BASE}/api/emotion/analyze_event`, { method: 'POST', body: fd }));
}

export async function getEmotionInterventionLogs(limit = 200) {
  return asJson(await fetch(`${API_BASE}/api/emotion/intervention_logs?limit=${limit}`, { headers: adminHeaders() }));
}

export async function assistRecommend(sessionId) {
  return asJson(await fetch(`${API_BASE}/api/assist_recommend?session_id=${encodeURIComponent(sessionId)}`));
}
