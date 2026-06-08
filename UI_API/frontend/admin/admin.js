const API = window.location.origin;
const CIRC = 2 * Math.PI * 49;

const MOOD_BAR_COLORS = { '1':'#ef9a9a','2':'#ffcc80','3':'#fff176','4':'#a5d6a7','5':'#81d4fa' };
const MOOD_BAR_LABELS = { '1':'★ 很差','2':'★★ 普通','3':'★★★ 還不錯','4':'★★★★ 很開心','5':'★★★★★ 超棒' };
const MOOD_CHIP_STYLES = {
  0: 'background:#f0f0f0;color:#aaa',
  1: 'background:#ffebee;color:#c62828',
  2: 'background:#fff8e1;color:#f57f17',
  3: 'background:#fffde7;color:#827717',
  4: 'background:#e8f5e9;color:#2e7d32',
  5: 'background:#e3f2fd;color:#0d47a1',
};

const DEFAULT_PUSH_PROMPT =
  '你是麥當勞自助點餐機的 AI 推播助手。' +
  '只能從菜單白名單選 1 個餐點，不能發明不存在的餐點。' +
  '輸出純 JSON：{"recommendation_id":"MCDxxx","push_text":"繁體中文促購短句"}。';

// ── Menu cache (for name/image lookup) ──
let menuCache = {};

async function loadMenu() {
  try {
    const res = await fetch(`${API}/api/menu`);
    const items = await res.json();
    if (Array.isArray(items)) {
      items.forEach(item => {
        if (item.id) menuCache[item.id] = item;
      });
    }
  } catch { /* 靜默失敗，用 ID fallback */ }
}

function menuName(id)  { return menuCache[id]?.name  || id; }
function menuImage(id) { return menuCache[id]?.image || ''; }

// ── Date in topbar ──
const dateTextEl = document.getElementById('topbar-date-text');
if (dateTextEl) {
  dateTextEl.textContent = new Date().toLocaleDateString('zh-TW', {
    year: 'numeric', month: '2-digit', day: '2-digit',
  });
}

// ── Admin token helper ──
function adminToken() {
  const params = new URLSearchParams(window.location.search);
  const t = params.get('token') || params.get('admin_token') || sessionStorage.getItem('admin_demo_token') || '';
  if (t) sessionStorage.setItem('admin_demo_token', t);
  return t;
}
function adminHeaders(extra = {}) {
  const t = adminToken();
  return t ? { ...extra, 'X-Admin-Token': t } : extra;
}

// ── Sidebar navigation ──
document.querySelectorAll('.nav-item[data-page]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-item[data-page]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const page = btn.dataset.page;
    document.querySelectorAll('[id^="page-"]').forEach(el => {
      el.style.display = el.id === `page-${page}` ? '' : 'none';
    });
    const titles  = { stats: '狀態統計', settings: '功能設定', rag: 'RAG 知識庫', emotion: 'Emotion-LLaMA' };
    const icons   = { stats: 'fa-chart-pie', settings: 'fa-sliders-h', rag: 'fa-database', emotion: 'fa-eye' };
    const titleEl = document.getElementById('page-title');
    const iconEl  = document.getElementById('topbar-icon');
    if (titleEl) titleEl.textContent = titles[page] || page;
    if (iconEl) {
      const ico = document.createElement('i');
      ico.className = `fas ${icons[page] || 'fa-circle'}`;
      iconEl.textContent = '';
      iconEl.appendChild(ico);
    }
    if (page === 'stats') loadStats();
    if (page === 'settings') loadSettings();
    if (page === 'rag') { loadRagSettings(); loadRagDocs(); }
    if (page === 'emotion') { loadEmotionSettings(); loadEmotionLogs(); }
  });
});

// ── Helpers ──
function setText(id, v) {
  const el = document.getElementById(id);
  if (el) el.textContent = v;
}

const SOURCE_LABELS = {
  ai_push:          'AI推播',
  choice_hesitation:'猶豫視窗',
  voice_assist:     '語音點餐',
  manual:           '手動',
  menu_card:        '手動',
};

function sourceLabel(src) {
  return SOURCE_LABELS[src] || '手動';
}

function emptyRow(tbody, msg, color) {
  tbody.textContent = '';
  const tr = document.createElement('tr');
  const td = document.createElement('td');
  td.colSpan = 6;
  td.className = 'adm-empty';
  if (color) td.style.color = color;
  td.textContent = msg;
  tr.appendChild(td);
  tbody.appendChild(tr);
}

// ── Stats loader ──
async function loadStats() {
  try {
    const res = await fetch(`${API}/api/session_stats`);
    const data = await res.json();
    if (data.status !== 'success') throw new Error('api error');

    const total   = data.total_sessions ?? 0;
    const clicks  = data.total_ai_push_cart_clicks ?? 0;
    const success = data.success_sessions ?? 0;
    const fail    = data.failure_sessions ?? 0;
    const rate    = data.success_rate ?? 0;
    const score   = data.cumulative_score ?? 0;
    const failRate = total > 0 ? Math.round((fail / total) * 100) : 0;

    // Donut
    const pct = Math.round(rate * 100);
    setText('d-rate', pct + '%');
    setText('d-success', String(success));
    setText('d-fail', String(fail));
    setText('d-score', (score >= 0 ? '+' : '') + score);
    const fill = document.getElementById('donut-fill');
    if (fill) fill.setAttribute('stroke-dasharray', `${(pct / 100) * CIRC} ${CIRC}`);

    // Stat cards
    setText('s-total',     String(total));
    setText('s-clicks',    String(clicks));
    setText('s-fail',      String(fail));
    setText('s-fail-rate', failRate + '%');

    const sessions = data.sessions || [];
    renderTop3(sessions);
    renderTable(sessions);

  } catch {
    const tbody = document.getElementById('s-tbody');
    if (tbody) emptyRow(tbody, '載入失敗，請重新整理。', '#e84040');
  }
}


function renderTop3(sessions) {
  const box = document.getElementById('top3-list');
  if (!box) return;

  // 統計所有 session 購物車各品項出現頻率（含手動、語音、AI推播）
  const freq = {};
  sessions.forEach(s => {
    if (Array.isArray(s.final_cart_ids)) {
      s.final_cart_ids.forEach(id => { freq[id] = (freq[id] || 0) + 1; });
    }
  });

  const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 3);
  box.textContent = '';

  if (!sorted.length) {
    const empty = document.createElement('div');
    empty.style.cssText = 'color:#adb5c9;font-size:12px';
    empty.textContent = '尚無點餐紀錄。';
    box.appendChild(empty);
    return;
  }

  const maxCount = sorted[0][1];
  const rankClass = ['r1', 'r2', 'r3'];

  sorted.forEach(([id, count], i) => {
    const item = document.createElement('div');
    item.className = 'top3-item';

    const rank = document.createElement('div');
    rank.className = `top3-rank ${rankClass[i] || 'r3'}`;
    rank.textContent = String(i + 1);

    const imgUrl = menuImage(id);
    if (imgUrl) {
      const img = document.createElement('img');
      img.className = 'top3-img';
      img.alt = menuName(id);
      img.src = imgUrl;
      img.onerror = () => { img.style.display = 'none'; };
      item.appendChild(rank);
      item.appendChild(img);
    } else {
      item.appendChild(rank);
    }

    const info = document.createElement('div');
    info.className = 'top3-bar-wrap';

    const name = document.createElement('div');
    name.className = 'top3-name';
    name.textContent = menuName(id);

    const cnt = document.createElement('div');
    cnt.className = 'top3-count';
    cnt.textContent = `出現 ${count} 次`;

    const track = document.createElement('div');
    track.className = 'top3-bar-track';
    const barFill = document.createElement('div');
    barFill.className = 'top3-bar-fill';
    barFill.style.width = Math.round((count / maxCount) * 100) + '%';
    track.appendChild(barFill);

    info.append(name, cnt, track);
    item.appendChild(info);
    box.appendChild(item);
  });
}

function renderTable(sessions) {
  const tbody = document.getElementById('s-tbody');
  if (!tbody) return;
  if (!sessions.length) { emptyRow(tbody, '尚無點餐紀錄。'); return; }

  tbody.textContent = '';
  sessions.forEach(s => {
    const tr = document.createElement('tr');

    const tdTs = document.createElement('td');
    tdTs.textContent = s.timestamp
      ? new Date(s.timestamp).toLocaleString('zh-TW', {
          month: '2-digit', day: '2-digit',
          hour: '2-digit', minute: '2-digit',
        })
      : '—';

    const tdSid = document.createElement('td');
    tdSid.style.cssText = 'font-family:monospace;color:#8494b0';
    tdSid.textContent = '…' + String(s.session_id || '').slice(-8);

    const tdClicks = document.createElement('td');
    tdClicks.style.cssText = 'font-weight:700;text-align:center';
    tdClicks.textContent = String(s.ai_push_cart_count ?? 0);

    const tdResult = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = s.ai_push_success ? 'badge-ok' : 'badge-no';
    badge.textContent = s.ai_push_success ? '✓ 成功' : '✗ 未加購';
    tdResult.appendChild(badge);

    const tdCart = document.createElement('td');
    tdCart.style.cssText = 'color:#6b7a99;font-size:11px';
    const names = (s.final_cart_ids || []).map(id => menuName(id));
    tdCart.textContent = names.join('、') || '—';

    // 加入方式欄：聚合每個品項的來源
    const tdSource = document.createElement('td');
    tdSource.style.cssText = 'font-size:11px';
    const sources = s.cart_sources || [];
    if (sources.length) {
      const sourceMap = {};
      sources.forEach(({ id, source }) => {
        if (!id) return;
        if (!sourceMap[id]) sourceMap[id] = new Set();
        sourceMap[id].add(sourceLabel(source));
      });
      const parts = (s.final_cart_ids || []).map(id => {
        const labels = sourceMap[id] ? [...sourceMap[id]].join('/') : '手動';
        return `${menuName(id)}（${labels}）`;
      });
      tdSource.style.color = '#4b5679';
      tdSource.textContent = parts.join('、') || '—';
    } else {
      tdSource.style.color = '#adb5c9';
      tdSource.textContent = '—';
    }

    // 語音對話欄
    const tdVoice = document.createElement('td');
    const turns = s.voice_turns || [];
    if (turns.length) {
      const badge = document.createElement('button');
      badge.className = 'voice-badge';
      const badgeIcon = document.createElement('i');
      badgeIcon.className = 'fas fa-microphone';
      const badgeText = document.createTextNode(` ${turns.length} 輪 ▾`);
      badge.append(badgeIcon, badgeText);
      badge.addEventListener('click', () => {
        const next = tr.nextElementSibling;
        if (next && next.classList.contains('voice-expand-row')) {
          next.remove();
          badgeText.textContent = ` ${turns.length} 輪 ▾`;
        } else {
          const expandRow = document.createElement('tr');
          expandRow.className = 'voice-expand-row';
          const expandTd = document.createElement('td');
          expandTd.colSpan = 8;
          const inner = document.createElement('div');
          inner.className = 'voice-expand-inner';
          turns.forEach(t => {
            const turn = document.createElement('div');
            turn.className = 'voice-turn';
            if (t.user) {
              const u = document.createElement('div');
              u.className = 'voice-bubble-user';
              u.textContent = t.user;
              turn.appendChild(u);
            }
            if (t.ai) {
              const a = document.createElement('div');
              a.className = 'voice-bubble-ai';
              a.textContent = t.ai;
              turn.appendChild(a);
            }
            inner.appendChild(turn);
          });
          expandTd.appendChild(inner);
          expandRow.appendChild(expandTd);
          tr.after(expandRow);
          badgeText.textContent = ` ${turns.length} 輪 ▴`;
        }
      });
      tdVoice.appendChild(badge);
    } else {
      tdVoice.style.cssText = 'color:#bbb;font-size:12px';
      tdVoice.textContent = '—';
    }

    tr.append(tdTs, tdSid, tdClicks, tdResult, tdCart, tdSource, tdVoice);

    // 心情欄
    const tdMood = document.createElement('td');
    const score = s.mood_score ?? 0;
    if (score > 0) {
      const chip = document.createElement('span');
      chip.style.cssText = `display:inline-block;padding:3px 8px;border-radius:12px;font-size:11px;font-weight:700;${MOOD_CHIP_STYLES[score] || ''}`;
      chip.textContent = `${'★'.repeat(score)} ${['','很差','普通','還不錯','很開心','超棒'][score]}`;
      tdMood.appendChild(chip);
    } else {
      tdMood.style.cssText = 'color:#bbb;font-size:12px';
      tdMood.textContent = '—';
    }
    tr.appendChild(tdMood);

    tbody.appendChild(tr);
  });
}

// ── Clear stats ──
async function clearStats() {
  const btn = document.getElementById('clearBtn');
  if (!confirm('確定清除所有點餐統計紀錄？此操作無法還原。')) return;
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`${API}/api/session_stats`, { method: 'DELETE' });
    const data = await res.json();
    if (data.status === 'success') await loadStats();
  } catch {
    alert('清除失敗，請重試。');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── Settings ──

function g(id) { return document.getElementById(id); }
function val(id) { return g(id)?.value?.trim() || ''; }
function setVal(id, v) { if (g(id)) g(id).value = v ?? ''; }
function showRow(id, visible) { g(id)?.classList.toggle('hidden', !visible); }

function onSttProviderChange() {
  const isApi = val('inp-stt-provider') === 'openai_compatible';
  showRow('row-stt-model', !isApi);
  showRow('row-stt-api',   isApi);
  showRow('row-stt-key',   isApi);
}

function onTtsProviderChange() {
  const p = val('inp-tts-provider');
  showRow('row-tts-edge-zh', p === 'edge');
  showRow('row-tts-edge-en', p === 'edge');
  showRow('row-tts-api',     p === 'openai_compatible');
  showRow('row-tts-key',     p === 'openai_compatible');
  showRow('row-tts-voice',   p === 'openai_compatible');
}

async function loadSettings() {
  try {
    const res = await fetch(`${API}/api/settings`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const s = await res.json();

    // Ollama
    setVal('inp-model-name',    s.MODEL_NAME          || 'qwen3.5:4b');
    setVal('inp-voice-model',   s.VOICE_ASSIST_MODEL  || 'qwen3.5:4b');
    setVal('inp-temperature',   s.OLLAMA_TEMPERATURE  ?? 0.8);
    setVal('inp-num-predict',   s.OLLAMA_NUM_PREDICT  ?? 2048);
    // Prompts
    setVal('inp-voice-prompt-zh', s.VOICE_ASSIST_SYSTEM_PROMPT    || '');
    setVal('inp-voice-prompt-en', s.VOICE_ASSIST_SYSTEM_PROMPT_EN || '');
    setVal('inp-push-prompt',     s.AI_PUSH_SYSTEM_PROMPT         || DEFAULT_PUSH_PROMPT);
    setVal('inp-push-text-min',   s.AI_PUSH_TEXT_MIN ?? 18);
    setVal('inp-push-text-max',   s.AI_PUSH_TEXT_MAX ?? 34);
    // STT
    setVal('inp-stt-provider',  s.STT_PROVIDER        || 'faster_whisper');
    setVal('inp-stt-model',     s.STT_MODEL           || 'small');
    setVal('inp-stt-api-url',   s.STT_API_URL         || '');
    setVal('inp-stt-api-key',   s.STT_API_KEY         || '');
    // TTS
    setVal('inp-tts-provider',  s.TTS_PROVIDER        || 'edge');
    setVal('inp-tts-voice-zh',  s.EDGE_TTS_VOICE      || 'zh-TW-HsiaoChenNeural');
    setVal('inp-tts-voice-en',  s.EDGE_TTS_VOICE_EN   || 'en-US-JennyNeural');
    setVal('inp-tts-api-url',   s.TTS_API_URL         || '');
    setVal('inp-tts-api-key',   s.TTS_API_KEY         || '');
    setVal('inp-tts-voice',     s.TTS_VOICE           || 'alloy');
    // 付款逾時協助 Prompt
    setVal('inp-payment-assist-prompt', s.PAYMENT_ASSIST_PROMPT || '');
    // 心情 Prompt
    [1,2,3,4,5].forEach(n => setVal(`inp-mood-ctx-${n}`, s[`MOOD_CONTEXT_${n}`] || ''));

    onSttProviderChange();
    onTtsProviderChange();
  } catch (e) {
    console.error('loadSettings failed', e);
  }
}

async function saveSettings() {
  const btn = g('saveSettingsBtn');
  const notice = g('settings-notice');
  if (btn) btn.disabled = true;
  if (notice) { notice.style.display = 'none'; }
  try {
    const body = {
      // Ollama
      MODEL_NAME:                val('inp-model-name')      || 'qwen3.5:4b',
      VOICE_ASSIST_MODEL:        val('inp-voice-model')     || 'qwen3.5:4b',
      OLLAMA_TEMPERATURE:        parseFloat(val('inp-temperature') || '0.8'),
      OLLAMA_NUM_PREDICT:        parseInt(val('inp-num-predict') || '2048', 10),
      // Prompts
      VOICE_ASSIST_SYSTEM_PROMPT:    val('inp-voice-prompt-zh'),
      VOICE_ASSIST_SYSTEM_PROMPT_EN: val('inp-voice-prompt-en'),
      AI_PUSH_SYSTEM_PROMPT:         val('inp-push-prompt') === DEFAULT_PUSH_PROMPT ? '' : val('inp-push-prompt'),
      PAYMENT_ASSIST_PROMPT:         val('inp-payment-assist-prompt'),
      AI_PUSH_TEXT_MIN:              parseInt(val('inp-push-text-min') || '18', 10),
      AI_PUSH_TEXT_MAX:              parseInt(val('inp-push-text-max') || '34', 10),
      // STT
      STT_PROVIDER:        val('inp-stt-provider')  || 'faster_whisper',
      STT_MODEL:           val('inp-stt-model')     || 'small',
      STT_API_URL:         val('inp-stt-api-url'),
      STT_API_KEY:         val('inp-stt-api-key'),
      // TTS
      TTS_PROVIDER:        val('inp-tts-provider')  || 'edge',
      EDGE_TTS_VOICE:      val('inp-tts-voice-zh')  || 'zh-TW-HsiaoChenNeural',
      EDGE_TTS_VOICE_EN:   val('inp-tts-voice-en')  || 'en-US-JennyNeural',
      TTS_API_URL:         val('inp-tts-api-url'),
      TTS_API_KEY:         val('inp-tts-api-key'),
      TTS_VOICE:           val('inp-tts-voice')     || 'alloy',
      // 心情 Prompt（空白 = 保留系統預設，交由後端 config fallback 處理）
      ...Object.fromEntries([1,2,3,4,5].map(n => [`MOOD_CONTEXT_${n}`, val(`inp-mood-ctx-${n}`)])),
    };
    const res = await fetch(`${API}/api/settings`, {
      method: 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (notice) {
      notice.textContent = '✓ 儲存成功';
      notice.style.color = '#1db87a';
      notice.style.display = '';
      setTimeout(() => { notice.style.display = 'none'; }, 3000);
    }
  } catch (e) {
    if (notice) {
      notice.textContent = `✗ 儲存失敗：${e.message}`;
      notice.style.color = '#e84040';
      notice.style.display = '';
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── Emotion-LLaMA settings ──

async function loadEmotionSettings() {
  try {
    const res = await fetch(`${API}/api/settings`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const s = await res.json();
    g('inp-emotion-enabled').checked        = Boolean(s.EMOTION_LLAMA_ENABLED);
    setVal('inp-emotion-clip-sec',            s.EMOTION_LLAMA_CLIP_SEC    ?? 2.0);
    g('inp-emotion-quality-check').checked  = s.EMOTION_LLAMA_QUALITY_CHECK !== false;
    g('inp-emotion-affect-voice').checked   = Boolean(s.EMOTION_LLAMA_AFFECT_VOICE);
    g('inp-emotion-affect-barrier').checked = Boolean(s.EMOTION_LLAMA_AFFECT_BARRIER);
    g('inp-emotion-event-tutorial').checked     = s.EMOTION_LLAMA_EVENT_TUTORIAL !== false;
    g('inp-emotion-event-voice').checked        = Boolean(s.EMOTION_LLAMA_EVENT_VOICE);
    g('inp-emotion-event-cancel-guide').checked = Boolean(s.EMOTION_LLAMA_EVENT_CANCEL_GUIDE);
    g('inp-emotion-event-payment-timeout').checked = s.EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT !== false;
    const waitMode = s.EMOTION_LLAMA_VOICE_WAIT_MODE || 'speed';
    const modeEl = g(waitMode === 'analysis' ? 'inp-emotion-voice-analysis' : 'inp-emotion-voice-speed');
    if (modeEl) modeEl.checked = true;
    toggleVoiceWaitMode();
    setVal('inp-emotion-prompt',              s.EMOTION_LLAMA_PROMPT || '');
    updateEmotionPromptCounter();
  } catch (e) {
    console.error('loadEmotionSettings failed', e);
  }
}

function updateEmotionPromptCounter() {
  const ta      = g('inp-emotion-prompt');
  const counter = g('emotion-prompt-counter');
  const warn    = g('emotion-prompt-warn');
  if (!ta || !counter) return;
  const len = (ta.value || '').length;
  counter.textContent = `${len} 字`;
  const over = len > 800;
  counter.style.color = over ? 'var(--danger)' : 'var(--text2)';
  if (warn) warn.style.display = over ? 'inline' : 'none';
}

async function saveEmotionSettings() {
  const notice = g('emotion-settings-notice');
  if (notice) notice.style.display = 'none';
  try {
    const body = {
      EMOTION_LLAMA_ENABLED:        g('inp-emotion-enabled').checked,
      EMOTION_LLAMA_CLIP_SEC:       parseFloat(val('inp-emotion-clip-sec') || '2.0'),
      EMOTION_LLAMA_QUALITY_CHECK:  g('inp-emotion-quality-check').checked,
      EMOTION_LLAMA_AFFECT_VOICE:   g('inp-emotion-affect-voice').checked,
      EMOTION_LLAMA_AFFECT_BARRIER: g('inp-emotion-affect-barrier').checked,
      EMOTION_LLAMA_EVENT_TUTORIAL:     g('inp-emotion-event-tutorial').checked,
      EMOTION_LLAMA_EVENT_VOICE:        g('inp-emotion-event-voice').checked,
      EMOTION_LLAMA_EVENT_CANCEL_GUIDE: g('inp-emotion-event-cancel-guide').checked,
      EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT: g('inp-emotion-event-payment-timeout').checked,
      EMOTION_LLAMA_VOICE_WAIT_MODE:    g('inp-emotion-voice-analysis')?.checked ? 'analysis' : 'speed',
      EMOTION_LLAMA_PROMPT:         val('inp-emotion-prompt'),
    };
    const res = await fetch(`${API}/api/settings`, {
      method: 'POST', headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (notice) {
      notice.textContent = '✓ 儲存成功';
      notice.style.color = '#1db87a';
      notice.style.display = 'inline';
      setTimeout(() => { notice.style.display = 'none'; }, 2000);
    }
  } catch (e) {
    console.error('saveEmotionSettings failed', e);
    if (notice) {
      notice.textContent = '✗ 儲存失敗';
      notice.style.color = '#e84040';
      notice.style.display = 'inline';
    }
  }
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function loadEmotionLogs() {
  const tbody = g('emotion-logs-tbody');
  if (!tbody) return;
  const EMPTY_CELL = '<span style="color:var(--text2)">—</span>';
  tbody.innerHTML = `<tr><td colspan="6" style="padding:16px;color:var(--text2);text-align:center">載入中…</td></tr>`;
  try {
    const res = await fetch(`${API}/api/emotion/intervention_logs?limit=200`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const logs = (data.logs || []).slice().reverse();
    if (!logs.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="padding:16px;color:var(--text2);text-align:center">尚無紀錄</td></tr>`;
      return;
    }
    tbody.innerHTML = logs.map(r => {
      const time  = escHtml(r.timestamp ? r.timestamp.replace('T', ' ').slice(0, 19) : '—');
      // 優先使用後端已計算的 event_type_label，避免前後端 label 不同步
      const evt   = escHtml(r.event_type_label || r.event_type || '—');

      let emoCell, facialCell, vocalCell, descCell;
      if (r.quality_skipped) {
        emoCell    = `<span style="color:var(--text2)">品質快篩跳過</span>`;
        facialCell = EMPTY_CELL;
        vocalCell  = EMPTY_CELL;
        descCell   = EMPTY_CELL;
      } else if (r.status === 'error') {
        emoCell    = `<span style="color:var(--danger)">分析失敗</span>`;
        facialCell = EMPTY_CELL;
        vocalCell  = EMPTY_CELL;
        descCell   = EMPTY_CELL;
      } else {
        const intens = r.intensity ? ` <span style="font-size:11px;color:var(--text2)">(${escHtml(r.intensity)})</span>` : '';
        emoCell    = r.emotion  ? `<strong>${escHtml(r.emotion)}</strong>${intens}` : EMPTY_CELL;
        facialCell = r.facial   ? escHtml(r.facial)   : EMPTY_CELL;
        vocalCell  = r.vocal    ? escHtml(r.vocal)    : EMPTY_CELL;
        descCell   = r.description ? escHtml(r.description) : EMPTY_CELL;
      }

      return `<tr style="border-top:1px solid var(--border)">
        <td style="padding:7px 10px;white-space:nowrap;font-size:12px">${time}</td>
        <td style="padding:7px 10px;white-space:nowrap">${evt}</td>
        <td style="padding:7px 10px;white-space:nowrap">${emoCell}</td>
        <td style="padding:7px 10px;max-width:180px;overflow-wrap:break-word;font-size:12px">${facialCell}</td>
        <td style="padding:7px 10px;max-width:160px;overflow-wrap:break-word;font-size:12px">${vocalCell}</td>
        <td style="padding:7px 10px;max-width:240px;overflow-wrap:break-word;font-size:12px">${descCell}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" style="padding:16px;color:var(--danger)">載入失敗：${escHtml(e.message)}</td></tr>`;
  }
}

async function clearEmotionLogs() {
  if (!confirm('確定清除所有 Emotion-LLaMA 介入紀錄？')) return;
  try {
    const res = await fetch(`${API}/api/emotion/intervention_logs`, { method: 'DELETE', headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    loadEmotionLogs();
  } catch (e) {
    console.error('clearEmotionLogs failed', e);
  }
}

// ── RAG settings ──

async function loadRagSettings() {
  try {
    const res = await fetch(`${API}/api/settings`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const s = await res.json();
    setVal('inp-rag-enabled',   String(s.RAG_ENABLED  ?? false));
    setVal('inp-rag-threshold', s.RAG_SCORE_THRESHOLD ?? 0.5);
    setVal('inp-rag-top-k',     s.RAG_TOP_K           ?? 3);
  } catch (e) {
    console.error('loadRagSettings failed', e);
  }
}

async function saveRagSettings() {
  const notice = g('rag-settings-notice');
  try {
    const res = await fetch(`${API}/api/settings`, {
      method: 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        RAG_ENABLED:         val('inp-rag-enabled') === 'true',
        RAG_SCORE_THRESHOLD: parseFloat(val('inp-rag-threshold') || '0.5'),
        RAG_TOP_K:           parseInt(val('inp-rag-top-k') || '3', 10),
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (notice) {
      notice.textContent = '✓ 儲存成功';
      notice.style.color = '#1db87a';
      notice.style.display = '';
      setTimeout(() => { notice.style.display = 'none'; }, 3000);
    }
  } catch (e) {
    if (notice) {
      notice.textContent = `✗ 儲存失敗：${e.message}`;
      notice.style.color = '#e84040';
      notice.style.display = '';
    }
  }
}

// ── RAG docs ──

const RAG_TYPE_LABELS = {
  manual: '政策/規則', faq: 'FAQ', menu_supplement: '菜單補充',
};

function ragNotice(msg, ok = true) {
  const el = document.getElementById('rag-notice');
  if (!el) return;
  el.textContent = msg;
  el.style.color = ok ? '#1db87a' : '#e84040';
  el.style.display = '';
  setTimeout(() => { el.style.display = 'none'; }, 3000);
}

async function loadRagDocs() {
  const list = document.getElementById('rag-list');
  if (!list) return;
  try {
    const res = await fetch(`${API}/api/rag/docs`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const docs = data.docs || [];

    const countEl = document.getElementById('rag-count');
    if (countEl) countEl.textContent = docs.length ? `(${docs.length})` : '';

    list.textContent = '';
    if (!docs.length) {
      const empty = document.createElement('div');
      empty.style.cssText = 'color:#adb5c9;font-size:13px;padding:20px 0;text-align:center';
      empty.textContent = '尚無知識文件。';
      list.appendChild(empty);
      return;
    }

    docs.forEach(doc => {
      const card = document.createElement('div');
      card.className = 'rag-doc-card';

      const body = document.createElement('div');
      body.className = 'rag-doc-body';

      const tag = document.createElement('span');
      const tagClass = { manual: 'manual', faq: 'faq', menu_supplement: 'menu_supplement' };
      tag.className = `rag-doc-tag ${tagClass[doc.source_type] || 'manual'}`;
      tag.textContent = RAG_TYPE_LABELS[doc.source_type] || doc.source_type;

      const text = document.createElement('div');
      text.className = 'rag-doc-text';
      text.textContent = doc.content;

      body.append(tag, text);

      const del = document.createElement('button');
      del.className = 'rag-del-btn';
      del.title = '刪除';
      const icon = document.createElement('i');
      icon.className = 'fas fa-trash';
      del.appendChild(icon);
      del.onclick = () => deleteRagDoc(doc.id);

      card.append(body, del);
      list.appendChild(card);
    });
  } catch (e) {
    ragNotice(`載入失敗：${e.message}`, false);
  }
}

async function addRagDoc() {
  const content = (document.getElementById('rag-content')?.value || '').trim();
  const type = document.getElementById('rag-type')?.value || 'manual';
  if (!content) { ragNotice('請輸入內容', false); return; }
  try {
    const res = await fetch(`${API}/api/rag/docs`, {
      method: 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, source_type: type }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (document.getElementById('rag-content')) document.getElementById('rag-content').value = '';
    ragNotice('✓ 新增成功');
    await loadRagDocs();
  } catch (e) {
    ragNotice(`新增失敗：${e.message}`, false);
  }
}

async function deleteRagDoc(id) {
  if (!confirm('確定刪除這筆文件？')) return;
  try {
    const res = await fetch(`${API}/api/rag/docs/${encodeURIComponent(id)}`, {
      method: 'DELETE', headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    ragNotice('✓ 已刪除');
    await loadRagDocs();
  } catch (e) {
    ragNotice(`刪除失敗：${e.message}`, false);
  }
}

async function clearRagDocs() {
  if (!confirm('確定清空全部 RAG 文件？此操作無法還原。')) return;
  try {
    const res = await fetch(`${API}/api/rag/docs`, {
      method: 'DELETE', headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    ragNotice('✓ 已清空');
    await loadRagDocs();
  } catch (e) {
    ragNotice(`清空失敗：${e.message}`, false);
  }
}

// expose to inline handlers
window.onSttProviderChange = onSttProviderChange;
window.onTtsProviderChange = onTtsProviderChange;
window.saveSettings    = saveSettings;
window.saveRagSettings = saveRagSettings;
window.loadRagDocs     = loadRagDocs;
window.addRagDoc       = addRagDoc;
window.deleteRagDoc    = deleteRagDoc;
window.clearRagDocs    = clearRagDocs;
window.saveEmotionSettings        = saveEmotionSettings;
window.clearEmotionLogs           = clearEmotionLogs;
window.updateEmotionPromptCounter = updateEmotionPromptCounter;

// ── Init ──
document.getElementById('refreshBtn')?.addEventListener('click', loadStats);
document.getElementById('clearBtn')?.addEventListener('click', clearStats);

// 先載入菜單對照表，再載入統計
loadMenu().then(loadStats);
// 只在統計頁可見時才自動重整
setInterval(() => {
  const statsPage = document.getElementById('page-stats');
  if (statsPage && statsPage.style.display !== 'none') loadStats();
}, 15000);

function toggleVoiceWaitMode() {
  const row = document.getElementById('voice-wait-mode-row');
  if (!row) return;
  const checked = g('inp-emotion-event-voice')?.checked;
  row.style.display = checked ? 'flex' : 'none';
}
window.toggleVoiceWaitMode = toggleVoiceWaitMode;
