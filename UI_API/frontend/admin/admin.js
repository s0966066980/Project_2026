import { createRealtimeClient } from '../shared/realtimeClient.js';
import { createAvailabilityAdmin } from './modules/availabilityAdmin.js';
import { createHealthAdmin } from './modules/healthAdmin.js';
import { createRecommendationEventsAdmin } from './modules/recommendationEventsAdmin.js';
import { createCampaignAdmin } from './modules/campaignAdmin.js';
import { applyAdminNavigation } from './modules/adminNavigation.js';
import { adminHeaders, createAdminAuthController } from './features/auth/adminAuth.js';

const API = window.location.origin;
const CIRC = 2 * Math.PI * 49;
let adminPermissionSet = new Set();

function hasAdminPermission(permission) {
  return adminPermissionSet.has('*') || adminPermissionSet.has(permission);
}

const DEFAULT_PUSH_PROMPT =
  '你是麥當勞自助點餐機的 AI 推播助手。' +
  '只能從菜單白名單選 1 個餐點，不能發明不存在的餐點。' +
  '輸出純 JSON：{"recommendation_id":"MCDxxx","push_text":"繁體中文促購短句"}。';

// ── Menu cache (for name/image lookup) ──
let menuCache = {};
let menuLoadPromise = null;
let statsLoadPromise = null;

async function loadMenu() {
  if (Object.keys(menuCache).length) return menuCache;
  if (menuLoadPromise) return menuLoadPromise;
  menuLoadPromise = (async () => {
  try {
    const res = await fetch(`${API}/api/menu`);
    const items = await res.json();
    if (Array.isArray(items)) {
      const nextMenuCache = {};
      items.forEach(item => {
        if (item.id) nextMenuCache[item.id] = item;
      });
      menuCache = nextMenuCache;
    }
  } catch { /* 靜默失敗，用 ID fallback */ }
    return menuCache;
  })().finally(() => {
    menuLoadPromise = null;
  });
  return menuLoadPromise;
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

// ── Sidebar navigation ──
document.querySelectorAll('.nav-item[data-page]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-item[data-page]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const page = btn.dataset.page;
    document.querySelectorAll('[id^="page-"]').forEach(el => {
      el.style.display = el.id === `page-${page}` ? '' : 'none';
    });
    const titles  = { stats: '狀態統計', settings: '功能設定', recommendations: '推薦成效', promotions: '活動管理', availability: '供應狀態', health: '維運健康', rag: 'RAG 知識庫', emotion: 'Emotion-LLaMA', members: '會員管理', test: 'AI 問答測試' };
    const icons   = { stats: 'fa-chart-pie', settings: 'fa-sliders-h', recommendations: 'fa-bullseye', promotions: 'fa-ticket-alt', availability: 'fa-store', health: 'fa-heartbeat', rag: 'fa-database', emotion: 'fa-eye', members: 'fa-users', test: 'fa-flask' };
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
    if (page === 'recommendations') loadRecommendationEvents();
    if (page === 'promotions') loadCampaigns();
    if (page === 'availability') loadAvailability();
    if (page === 'health') loadAdminHealth();
    if (page === 'rag') { loadRagSettings(); loadRagHealth(); loadRagAlerts(); loadRagReviews(); loadRagDocs(); }
    if (page === 'emotion') { loadEmotionSettings(); loadEmotionLogs(); }
    if (page === 'members') loadMembers();
    if (page === 'test') { loadOllamaModels(); loadVoicePromptDefault(); }
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
  if (statsLoadPromise) return statsLoadPromise;
  statsLoadPromise = (async () => {
  try {
    const res = await fetch(`${API}/api/session_stats`, { headers: adminHeaders() });
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
  })().finally(() => {
    statsLoadPromise = null;
  });
  return statsLoadPromise;
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

    tbody.appendChild(tr);
  });
}

// ── Clear stats ──
async function clearStats() {
  const btn = document.getElementById('clearBtn');
  if (!confirm('確定清除所有點餐統計紀錄？此操作無法還原。')) return;
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`${API}/api/session_stats`, { method: 'DELETE', headers: adminHeaders() });
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

// ── Admin feature modules ──
const recommendationEventsAdmin = createRecommendationEventsAdmin({
  apiBaseUrl: API,
  adminHeaders,
  getElement: g,
  getValue: val,
  escapeHtml: escHtml,
  formatDate: fmtDate,
  loadMenu,
  menuName,
});

const campaignAdmin = createCampaignAdmin({
  apiBaseUrl: API,
  adminHeaders,
  getElement: g,
  loadMenu,
  getMenuItems: () => Object.values(menuCache),
  hasPermission: hasAdminPermission,
});

const availabilityAdmin = createAvailabilityAdmin({
  apiBaseUrl: API,
  adminHeaders,
  getElement: g,
  getValue: val,
  setValue: setVal,
  escapeHtml: escHtml,
});

const healthAdmin = createHealthAdmin({
  apiBaseUrl: API,
  adminHeaders,
  getElement: g,
  setText,
  escapeHtml: escHtml,
});

function loadRecommendationEvents() { return recommendationEventsAdmin.loadRecommendationEvents(); }
function loadCampaigns() { return campaignAdmin.loadCampaigns(); }
function clearRecommendationEvents() { return recommendationEventsAdmin.clearRecommendationEvents(); }
function renderRecommendationDashboard() { return recommendationEventsAdmin.renderRecommendationDashboard(); }
function loadAvailability() { return availabilityAdmin.loadAvailability(); }
function saveAvailability() { return availabilityAdmin.saveAvailability(); }
function renderAvailabilityRows() { return availabilityAdmin.renderAvailabilityRows(); }
function loadAdminHealth() { return healthAdmin.loadAdminHealth(); }

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

    // AI 提供者
    const provider = s.AI_PROVIDER || 'ollama';
    g('page-settings')?.querySelectorAll('.provider-tab[data-provider]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.provider === provider);
    });
    ['ollama', 'gemini', 'openai'].forEach(p => {
      g(`settings-fields-${p}`)?.classList.toggle('hidden', p !== provider);
    });
    // Gemini / OpenAI 文字欄
    setVal('inp-gemini-model',       s.GEMINI_MODEL_NAME      || 'gemini-2.0-flash');
    setVal('inp-gemini-voice-model', s.GEMINI_VOICE_MODEL     || 'gemini-2.0-flash');
    setVal('inp-openai-base-url',    s.OPENAI_API_BASE_URL    || '');
    setVal('inp-openai-model',       s.OPENAI_MODEL_NAME      || 'gpt-4o-mini');
    setVal('inp-openai-voice-model', s.OPENAI_VOICE_MODEL     || 'gpt-4o-mini');
    // Ollama 模型 select（需先載入清單）
    await loadOllamaModels();
    populateModelSelect('inp-model-name',  _ollamaModels, s.MODEL_NAME         || 'qwen3.5:4b');
    populateModelSelect('inp-voice-model', _ollamaModels, s.VOICE_ASSIST_MODEL || 'qwen3.5:4b');
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
    const kws = Array.isArray(s.PASSIVE_VOICE_KEYWORDS) ? s.PASSIVE_VOICE_KEYWORDS : [];
    setVal('inp-passive-keywords', kws.join('\n'));
    // 別名：{"MCDxxx": ["別名1","別名2"]} → "MCDxxx = 別名1, 別名2\n..."
    const aliasObj = (s.PASSIVE_VOICE_ALIASES && typeof s.PASSIVE_VOICE_ALIASES === 'object') ? s.PASSIVE_VOICE_ALIASES : {};
    setVal('inp-passive-aliases', Object.entries(aliasObj)
      .map(([id, arr]) => `${id} = ${Array.isArray(arr) ? arr.join(', ') : arr}`)
      .join('\n'));

    onSttProviderChange();
    onTtsProviderChange();
    if (s.MEMBER_ENABLED === false) {
      const tab = document.querySelector('.nav-item[data-page="members"]');
      if (tab) tab.style.display = 'none';
    }
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
    const activeProvider = g('page-settings')?.querySelector('.provider-tab.active[data-provider]')?.dataset.provider || 'ollama';
    const body = {
      AI_PROVIDER: activeProvider,
      // Ollama
      MODEL_NAME:                val('inp-model-name')      || 'qwen3.5:4b',
      VOICE_ASSIST_MODEL:        val('inp-voice-model')     || 'qwen3.5:4b',
      // Gemini
      GEMINI_MODEL_NAME:         val('inp-gemini-model')    || 'gemini-2.0-flash',
      GEMINI_VOICE_MODEL:        val('inp-gemini-voice-model') || 'gemini-2.0-flash',
      // OpenAI
      OPENAI_API_BASE_URL:       val('inp-openai-base-url'),
      OPENAI_MODEL_NAME:         val('inp-openai-model')    || 'gpt-4o-mini',
      OPENAI_VOICE_MODEL:        val('inp-openai-voice-model') || 'gpt-4o-mini',
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
      PASSIVE_VOICE_KEYWORDS: (val('inp-passive-keywords') || '')
        .split('\n').map(s => s.trim()).filter(Boolean),
      PASSIVE_VOICE_ALIASES: Object.fromEntries(
        (val('inp-passive-aliases') || '').split('\n')
          .map(l => l.trim()).filter(l => l.includes('='))
          .map(l => {
            const [id, rest] = l.split('=').map(p => p.trim());
            return [id, rest.split(',').map(a => a.trim()).filter(Boolean)];
          })
      ),
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
    setVal('inp-emotion-provider',            s.EMOTION_PROVIDER || 'emotion_llama');
    g('inp-emotion-enabled').checked        = Boolean(s.EMOTION_LLAMA_ENABLED);
    setVal('inp-emotion-clip-sec',            s.EMOTION_LLAMA_CLIP_SEC       ?? 2.0);
    setVal('inp-payment-emotion-clip-sec',    s.PAYMENT_EMOTION_CLIP_SEC     ?? 5.0);
    g('inp-emotion-quality-check').checked  = s.EMOTION_LLAMA_QUALITY_CHECK !== false;
    g('inp-emotion-affect-voice').checked   = Boolean(s.EMOTION_LLAMA_AFFECT_VOICE);
    g('inp-emotion-affect-barrier').checked = Boolean(s.EMOTION_LLAMA_AFFECT_BARRIER);
    g('inp-emotion-event-voice').checked        = Boolean(s.EMOTION_LLAMA_EVENT_VOICE);
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
      EMOTION_PROVIDER:             val('inp-emotion-provider') || 'emotion_llama',
      EMOTION_LLAMA_ENABLED:        g('inp-emotion-enabled').checked,
      EMOTION_LLAMA_CLIP_SEC:       parseFloat(val('inp-emotion-clip-sec') || '2.0'),
      PAYMENT_EMOTION_CLIP_SEC:     parseFloat(val('inp-payment-emotion-clip-sec') || '5.0'),
      EMOTION_LLAMA_QUALITY_CHECK:  g('inp-emotion-quality-check').checked,
      EMOTION_LLAMA_AFFECT_VOICE:   g('inp-emotion-affect-voice').checked,
      EMOTION_LLAMA_AFFECT_BARRIER: g('inp-emotion-affect-barrier').checked,
      EMOTION_LLAMA_EVENT_VOICE:        g('inp-emotion-event-voice').checked,
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

// Emotion-LLaMA 結構化欄位英→繁對照（emotion / intensity 為有限列舉）
const EMOTION_ZH = {
  neutral: '中性', happy: '開心', sad: '難過', angry: '生氣',
  frustrated: '沮喪', anxious: '焦慮', confused: '困惑', surprised: '驚訝',
  disgust: '厭惡', fear: '害怕', fearful: '害怕', excited: '興奮', bored: '無聊',
};
const INTENSITY_ZH = { low: '低', medium: '中', high: '高' };
// 情緒分析模型代碼 → 顯示名稱
const EMOTION_PROVIDER_LABELS = { emotion_llama: 'Emotion-LLaMA', r1_omni: 'R1-Omni' };

function zhEmotion(v) {
  if (!v) return '';
  return EMOTION_ZH[String(v).trim().toLowerCase()] || v;
}
function zhIntensity(v) {
  if (!v) return '';
  return INTENSITY_ZH[String(v).trim().toLowerCase()] || v;
}

async function loadEmotionLogs() {
  const tbody = g('emotion-logs-tbody');
  if (!tbody) return;
  const EMPTY_CELL = '<span style="color:var(--text2)">—</span>';
  tbody.innerHTML = `<tr><td colspan="7" style="padding:16px;color:var(--text2);text-align:center">載入中…</td></tr>`;
  try {
    const res = await fetch(`${API}/api/emotion/intervention_logs?limit=200`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const logs = (data.logs || []).slice().reverse();
    if (!logs.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="padding:16px;color:var(--text2);text-align:center">尚無紀錄</td></tr>`;
      return;
    }
    tbody.innerHTML = logs.map(r => {
      const time  = escHtml(r.timestamp ? r.timestamp.replace('T', ' ').slice(0, 19) : '—');
      // 優先使用後端已計算的 event_type_label，避免前後端 label 不同步
      const evt   = escHtml(r.event_type_label || r.event_type || '—');
      const prov  = r.provider ? escHtml(EMOTION_PROVIDER_LABELS[r.provider] || r.provider) : '—';

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
        const intens = r.intensity ? ` <span style="font-size:11px;color:var(--text2)">(${escHtml(zhIntensity(r.intensity))})</span>` : '';
        emoCell    = r.emotion  ? `<strong>${escHtml(zhEmotion(r.emotion))}</strong>${intens}` : EMPTY_CELL;
        facialCell = r.facial   ? escHtml(r.facial)   : EMPTY_CELL;
        vocalCell  = r.vocal    ? escHtml(r.vocal)    : EMPTY_CELL;
        descCell   = r.description
          ? `<details class="emo-desc"><summary></summary><div class="emo-desc-body">${escHtml(r.description)}</div></details>`
          : EMPTY_CELL;
      }

      return `<tr style="border-top:1px solid var(--border)">
        <td style="padding:7px 10px;white-space:nowrap;font-size:12px">${time}</td>
        <td style="padding:7px 10px;white-space:nowrap">${evt}</td>
        <td style="padding:7px 10px;white-space:nowrap;font-size:12px">${prov}</td>
        <td style="padding:7px 10px;white-space:nowrap">${emoCell}</td>
        <td style="padding:7px 10px;max-width:180px;overflow-wrap:break-word;font-size:12px">${facialCell}</td>
        <td style="padding:7px 10px;max-width:160px;overflow-wrap:break-word;font-size:12px">${vocalCell}</td>
        <td style="padding:7px 10px;max-width:240px;overflow-wrap:break-word;font-size:12px">${descCell}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="padding:16px;color:var(--danger)">載入失敗：${escHtml(e.message)}</td></tr>`;
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
  manual: '手動',
  policy: '政策/規則',
  faq: 'FAQ',
  menu_supplement: '菜單補充',
  promotion: '活動優惠',
  nutrition: '營養過敏原',
  customer_service: '客服知識',
};

const RAG_REVIEW_STATUS_LABELS = {
  draft: '草稿',
  approved: '已核准',
  published: '已發布',
  rejected: '已拒絕',
  archived: '已封存',
};

let ragReviewRows = [];
let ragAlertRows = [];

function ragNotice(msg, ok = true) {
  const el = document.getElementById('rag-notice');
  if (!el) return;
  el.textContent = msg;
  el.style.color = ok ? '#1db87a' : '#e84040';
  el.style.display = '';
  setTimeout(() => { el.style.display = 'none'; }, 3000);
}

function renderRagHealth(data = {}) {
  const box = g('rag-health-grid');
  if (!box) return;
  const chromaOk = data.collection_ok !== false && data.status !== 'degraded';
  const sourceOk = data.source_dir_exists && data.source_dir_readable;
  const writable = data.chroma_writable !== false;
  const lastRebuild = data.last_rebuild || {};
  const rows = [
    [chromaOk ? '正常' : '異常', 'Chroma 狀態'],
    [String(data.doc_count ?? '—'), 'Chroma 文件數'],
    [sourceOk ? '可讀取' : '需檢查', '來源文件目錄'],
    [writable ? '可寫入' : '不可寫入', 'Chroma 寫入權限'],
    [lastRebuild.status || '—', '最後重建狀態'],
    [lastRebuild.rebuild_at || lastRebuild.checked_at || '—', '最後檢查時間'],
  ];
  box.innerHTML = rows
    .map(([value, label]) => `<div class="rag-health-chip"><b>${escHtml(String(value))}</b><span>${escHtml(label)}</span></div>`)
    .join('');
}

async function loadRagHealth() {
  try {
    const res = await fetch(`${API}/api/rag/status`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    renderRagHealth(await res.json());
  } catch (e) {
    renderRagHealth({ status: 'degraded', collection_ok: false, collection_error: e.message });
  }
}

function ragAlertStatusLabel(status) {
  return {
    open: '未處理',
    acknowledged: '已知悉',
    resolved: '已解決',
  }[String(status || 'open')] || status;
}

function renderRagAlerts(rows = []) {
  ragAlertRows = Array.isArray(rows) ? rows : [];
  const box = g('rag-alert-list');
  if (!box) return;
  const visibleRows = ragAlertRows.filter(row => row.status !== 'resolved').slice(0, 5);
  box.textContent = '';
  if (!visibleRows.length) return;
  visibleRows.forEach(row => {
    const status = String(row.status || 'open');
    const severity = String(row.severity || 'error');
    const card = document.createElement('div');
    card.className = `rag-alert-card ${severity === 'warning' ? 'warning' : ''} ${status === 'resolved' ? 'resolved' : ''}`;
    const errors = Array.isArray(row.errors) ? row.errors : [];
    const errorText = errors.length ? `｜${errors.slice(0, 2).map(err => err.message || '').filter(Boolean).join('；')}` : '';
    const actions = [];
    const actionable = row.alert_id && row.alert_id !== 'local_load_error';
    if (actionable && status === 'open') {
      actions.push(`<button type="button" onclick="ackRagAlert('${escHtml(row.alert_id)}')">已知悉</button>`);
    }
    if (actionable && status !== 'resolved') {
      actions.push(`<button type="button" onclick="resolveRagAlert('${escHtml(row.alert_id)}')">標記解決</button>`);
    }
    card.innerHTML = `
      <div class="rag-alert-head">
        <div class="rag-alert-title">
          <b>${escHtml(row.message || 'RAG alert')}</b>
          <span>${escHtml(row.alert_type || '')}｜${escHtml(row.created_at || '')}${escHtml(errorText)}</span>
        </div>
        <span class="rag-alert-status ${escHtml(status)}">${escHtml(ragAlertStatusLabel(status))}</span>
      </div>
      <div class="rag-alert-actions">${actions.join('')}</div>
    `;
    box.appendChild(card);
  });
}

async function loadRagAlerts() {
  try {
    const res = await fetch(`${API}/api/rag/alerts?limit=20`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderRagAlerts(data.alerts || []);
  } catch (e) {
    renderRagAlerts([{
      alert_id: 'local_load_error',
      alert_type: 'rag_alert_load_failed',
      severity: 'warning',
      status: 'open',
      message: `RAG alert 載入失敗：${e.message}`,
      created_at: '',
    }]);
  }
}

async function mutateRagAlert(alertId, action, notice) {
  try {
    const res = await fetch(`${API}/api/rag/alerts/${encodeURIComponent(alertId)}/${action}`, {
      method: 'POST',
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.status === 'error') throw new Error((data.errors || []).join('、') || '操作失敗');
    ragNotice(notice || '✓ alert 已更新');
    await loadRagAlerts();
  } catch (e) {
    ragNotice(`alert 更新失敗：${e.message}`, false);
  }
}

function ackRagAlert(alertId) {
  mutateRagAlert(alertId, 'ack', '✓ 已標記知悉');
}

function resolveRagAlert(alertId) {
  mutateRagAlert(alertId, 'resolve', '✓ 已標記解決');
}

function renderRagValidation(data = {}) {
  const box = g('rag-validation-box');
  if (!box) return;
  const errors = Array.isArray(data.errors) ? data.errors : [];
  const warnings = Array.isArray(data.warnings) ? data.warnings : [];
  const ok = data.ok !== false && !errors.length;
  const issues = [...errors, ...warnings].slice(0, 30);
  const summary = [
    `檔案 ${Number(data.total_files || 0)}`,
    `文件 ${Number(data.total_documents || 0)}`,
    `錯誤 ${errors.length}`,
    `警告 ${warnings.length}`,
  ].join(' / ');
  const items = issues.length
    ? issues.map(issue => {
      const level = issue.level === 'error' ? 'error' : 'warning';
      const label = level === 'error' ? '錯誤' : '警告';
      const path = issue.path ? `${issue.path}：` : '';
      return `<div class="rag-validation-item ${level}"><b>${label}</b> ${escHtml(path + (issue.message || ''))}</div>`;
    }).join('')
    : `<div class="rag-validation-item ok">檢查通過，可安全重建 Chroma。</div>`;
  box.style.display = '';
  box.innerHTML = `<div class="rag-validation-head"><b>${ok ? 'RAG 文件檢查通過' : 'RAG 文件需要修正'}</b><span>${escHtml(summary)}</span></div>`
    + `<div class="rag-validation-list">${items}</div>`;
}

async function validateRagDocs(showNotice = true) {
  try {
    if (showNotice) ragNotice('檢查中，請稍候…');
    const res = await fetch(`${API}/api/rag/validate`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderRagValidation(data);
    if (showNotice) {
      const errors = Array.isArray(data.errors) ? data.errors.length : 0;
      const warnings = Array.isArray(data.warnings) ? data.warnings.length : 0;
      ragNotice(errors ? `檢查未通過：${errors} 個錯誤` : `檢查通過${warnings ? `，${warnings} 個警告` : ''}`, errors === 0);
    }
    return data;
  } catch (e) {
    ragNotice(`檢查失敗：${e.message}`, false);
    renderRagValidation({ ok: false, errors: [{ level: 'error', message: e.message }] });
    return { ok: false, errors: [{ message: e.message }] };
  }
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
      const tagClass = {
        manual: 'manual',
        policy: 'manual',
        faq: 'faq',
        menu_supplement: 'menu_supplement',
        promotion: 'promotion',
        nutrition: 'nutrition',
        customer_service: 'customer_service',
      };
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
  const editingReviewId = (document.getElementById('rag-review-editing-id')?.value || '').trim();
  const sourceId = (document.getElementById('rag-source-id')?.value || '').trim();
  const content = (document.getElementById('rag-content')?.value || '').trim();
  const type = document.getElementById('rag-type')?.value || 'manual';
  if (!content) { ragNotice('請輸入內容', false); return; }
  if (!sourceId) { ragNotice('請輸入文件 ID，發布後會以此建立 source file', false); return; }
  try {
    const url = editingReviewId
      ? `${API}/api/rag/reviews/${encodeURIComponent(editingReviewId)}`
      : `${API}/api/rag/reviews`;
    const res = await fetch(url, {
      method: editingReviewId ? 'PUT' : 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content,
        source_type: type,
        source_id: sourceId,
        title: sourceId,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.status === 'error') throw new Error((data.errors || []).join('、') || '儲存失敗');
    if (document.getElementById('rag-source-id')) document.getElementById('rag-source-id').value = '';
    if (document.getElementById('rag-content')) document.getElementById('rag-content').value = '';
    if (document.getElementById('rag-review-editing-id')) document.getElementById('rag-review-editing-id').value = '';
    const saveBtn = document.getElementById('rag-save-btn-label');
    if (saveBtn) saveBtn.textContent = '建立草稿';
    ragNotice(editingReviewId ? '✓ 草稿已更新，需重新核准發布' : '✓ 已建立草稿，核准發布後才會進入 RAG 文件');
    await loadRagReviews();
  } catch (e) {
    ragNotice(`儲存失敗：${e.message}`, false);
  }
}

function editRagReview(reviewId) {
  const row = ragReviewRows.find(item => item.review_id === reviewId);
  if (!row) return;
  const editingInput = document.getElementById('rag-review-editing-id');
  if (editingInput) editingInput.value = row.review_id;
  if (document.getElementById('rag-source-id')) document.getElementById('rag-source-id').value = row.source_id || '';
  if (document.getElementById('rag-type')) document.getElementById('rag-type').value = row.source_type || 'manual';
  if (document.getElementById('rag-content')) document.getElementById('rag-content').value = row.content || '';
  const saveBtn = document.getElementById('rag-save-btn-label');
  if (saveBtn) saveBtn.textContent = '更新草稿';
  ragNotice(`正在編輯：${row.source_id || row.review_id}`);
}

function cancelRagReviewEdit() {
  if (document.getElementById('rag-review-editing-id')) document.getElementById('rag-review-editing-id').value = '';
  if (document.getElementById('rag-source-id')) document.getElementById('rag-source-id').value = '';
  if (document.getElementById('rag-content')) document.getElementById('rag-content').value = '';
  const saveBtn = document.getElementById('rag-save-btn-label');
  if (saveBtn) saveBtn.textContent = '建立草稿';
}

function renderRagReviews(rows = []) {
  ragReviewRows = Array.isArray(rows) ? rows : [];
  const list = document.getElementById('rag-review-list');
  const count = document.getElementById('rag-review-count');
  if (count) count.textContent = ragReviewRows.length ? `(${ragReviewRows.length})` : '';
  if (!list) return;
  list.textContent = '';
  if (!ragReviewRows.length) {
    const empty = document.createElement('div');
    empty.style.cssText = 'color:#adb5c9;font-size:13px;padding:16px 0;text-align:center';
    empty.textContent = '目前沒有待審核 RAG 文本。';
    list.appendChild(empty);
    return;
  }

  ragReviewRows.forEach(row => {
    const card = document.createElement('div');
    card.className = 'rag-review-card';
    const status = row.status || 'draft';
    const publishedPath = row.published_path ? ` · ${row.published_path}` : '';
    const rejectedReason = row.rejection_reason ? `<div class="rag-review-reason">拒絕原因：${escHtml(row.rejection_reason)}</div>` : '';
    const actions = [];
    if (['draft', 'rejected'].includes(status)) {
      actions.push(`<button type="button" onclick="approveRagReview('${escHtml(row.review_id)}')">核准</button>`);
    }
    if (status === 'approved') {
      actions.push(`<button type="button" onclick="publishRagReview('${escHtml(row.review_id)}')">發布</button>`);
    }
    if (['draft', 'approved', 'rejected'].includes(status)) {
      actions.push(`<button type="button" onclick="editRagReview('${escHtml(row.review_id)}')">編輯</button>`);
    }
    if (['draft', 'approved'].includes(status)) {
      actions.push(`<button type="button" onclick="rejectRagReview('${escHtml(row.review_id)}')">拒絕</button>`);
    }
    if (status !== 'archived') {
      actions.push(`<button type="button" onclick="archiveRagReview('${escHtml(row.review_id)}')">封存</button>`);
    }

    card.innerHTML = `
      <div class="rag-review-head">
        <div class="rag-review-title">
          <b>${escHtml(row.title || row.source_id || row.review_id)}</b>
          <span>${escHtml(row.source_id || '')} · v${Number(row.version || 1)} · ${escHtml(RAG_TYPE_LABELS[row.source_type] || row.source_type || 'manual')}${escHtml(publishedPath)}</span>
        </div>
        <span class="rag-review-status ${escHtml(status)}">${escHtml(RAG_REVIEW_STATUS_LABELS[status] || status)}</span>
      </div>
      <div class="rag-review-text">${escHtml(row.content || '')}</div>
      ${rejectedReason}
      <div class="rag-review-actions">${actions.join('')}</div>
    `;
    list.appendChild(card);
  });
}

async function loadRagReviews() {
  try {
    const res = await fetch(`${API}/api/rag/reviews`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderRagReviews(data.reviews || []);
  } catch (e) {
    ragNotice(`載入審核清單失敗：${e.message}`, false);
  }
}

async function mutateRagReview(reviewId, action, options = {}) {
  try {
    const res = await fetch(`${API}/api/rag/reviews/${encodeURIComponent(reviewId)}/${action}`, {
      method: 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(options.body || {}),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.status === 'error') throw new Error((data.errors || []).join('、') || '操作失敗');
    ragNotice(options.notice || '✓ 操作完成');
    await loadRagReviews();
    await loadRagHealth();
  } catch (e) {
    ragNotice(`操作失敗：${e.message}`, false);
  }
}

function approveRagReview(reviewId) {
  mutateRagReview(reviewId, 'approve', { notice: '✓ 已核准，發布後才會寫入 rag_documents' });
}

function publishRagReview(reviewId) {
  if (!confirm('發布後會更新 rag_documents source file；仍需執行安全重建 Chroma 才會進入正式向量庫。確定發布？')) return;
  mutateRagReview(reviewId, 'publish', { notice: '✓ 已發布 source file，請執行安全重建 Chroma' });
}

function rejectRagReview(reviewId) {
  const reason = prompt('請輸入拒絕原因，可留空：') || '';
  mutateRagReview(reviewId, 'reject', { body: { reason }, notice: '✓ 已拒絕' });
}

function archiveRagReview(reviewId) {
  if (!confirm('確定封存這筆審核紀錄？')) return;
  mutateRagReview(reviewId, 'archive', { notice: '✓ 已封存' });
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
    await loadRagReviews();
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
    await loadRagReviews();
  } catch (e) {
    ragNotice(`清空失敗：${e.message}`, false);
  }
}

async function rebuildRagDocs() {
  if (!confirm('系統會先驗證 rag_documents；只有檢查通過才會清空並重建 Chroma。確定執行？')) return;
  try {
    ragNotice('驗證與重建中，請稍候…');
    const res = await fetch(`${API}/api/rag/rebuild`, {
      method: 'POST',
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderRagValidation(data.validated || data);
    const failed = Number(data.failed || 0);
    if (data.status === 'error') {
      ragNotice(`重建已停止：請先修正 ${failed} 個錯誤`, false);
      return;
    }
    ragNotice(`✓ 安全重建完成：匯入 ${data.imported || 0} 筆，清除 ${data.deleted || 0} 筆${failed ? `，失敗 ${failed} 筆` : ''}`, failed === 0);
    await loadRagHealth();
    await loadRagAlerts();
    await loadRagDocs();
    await loadRagReviews();
  } catch (e) {
    ragNotice(`重建失敗：${e.message}`, false);
  }
}

// ── Promotion management ──

let promotionRows = [];

function splitCsv(value) {
  return String(value || '').split(',').map(row => row.trim()).filter(Boolean);
}

function joinCsv(value) {
  if (Array.isArray(value)) return value.join(', ');
  return String(value || '');
}

function promotionNotice(message, ok = true) {
  const el = g('promotion-notice');
  if (!el) return;
  el.textContent = message;
  el.style.color = ok ? '#1db87a' : '#e84040';
  el.style.display = '';
  setTimeout(() => { el.style.display = 'none'; }, 5000);
}

function promotionStatusLabel(status) {
  const key = String(status || 'draft').toLowerCase();
  return { active: '啟用', draft: '草稿', inactive: '停用' }[key] || key;
}

function getPromotionPayload() {
  return {
    offer_id: val('promotion-offer-id'),
    title: val('promotion-title'),
    status: val('promotion-status') || 'draft',
    enabled: val('promotion-enabled') !== 'false',
    surface: val('promotion-surface') || 'recommendation',
    priority: parseInt(val('promotion-priority') || '0', 10),
    rotation_seconds: parseInt(val('promotion-rotation-seconds') || '6', 10),
    member_only: val('promotion-member-only') === 'true',
    valid_from: val('promotion-valid-from'),
    valid_until: val('promotion-valid-until'),
    start_at: val('promotion-valid-from'),
    end_at: val('promotion-valid-until'),
    timezone: val('promotion-timezone') || 'Asia/Taipei',
    item_ids: splitCsv(val('promotion-item-ids')),
    categories: splitCsv(val('promotion-categories')),
    required_cart_item_ids: splitCsv(val('promotion-required-items')),
    pricing: {
      type: 'add_on_fixed_price',
      original_price: val('promotion-original-price') ? parseInt(val('promotion-original-price'), 10) : null,
      promotion_price: val('promotion-promotion-price') ? parseInt(val('promotion-promotion-price'), 10) : null,
      currency: 'TWD',
    },
    original_price: val('promotion-original-price') ? parseInt(val('promotion-original-price'), 10) : null,
    promo_price: val('promotion-promotion-price') ? parseInt(val('promotion-promotion-price'), 10) : null,
    save_text: val('promotion-save-text'),
    ad: {
      headline: val('promotion-ad-headline'),
      copy: val('promotion-ad-copy'),
      cta: val('promotion-ad-cta') || '立即查看',
    },
    badge: val('promotion-ad-headline'),
    subtitle: val('promotion-ad-copy'),
    cta_text: val('promotion-ad-cta') || '立即查看',
    target_type: val('promotion-target-type') || 'none',
    target_value: val('promotion-target-value'),
    theme: val('promotion-theme') || 'gold',
    legal_text: val('promotion-legal-text'),
    score_boost: parseInt(val('promotion-score-boost') || '4', 10),
    category_score_boost: parseInt(val('promotion-category-score-boost') || '2', 10),
    content: val('promotion-content'),
  };
}

function setPromotionForm(row = {}) {
  const rawStatus = String(row.status || row.metadata?.status || 'draft').toLowerCase();
  const formStatus = ['active', 'draft', 'inactive'].includes(rawStatus) ? rawStatus : 'draft';
  setVal('promotion-editing-id', row.offer_id || '');
  setVal('promotion-offer-id', row.offer_id || '');
  setVal('promotion-title', row.title || row.name || '');
  setVal('promotion-status', formStatus);
  setVal('promotion-enabled', row.enabled === false ? 'false' : 'true');
  setVal('promotion-surface', row.surface || 'recommendation');
  setVal('promotion-priority', row.priority ?? 0);
  setVal('promotion-rotation-seconds', row.rotation_seconds ?? 6);
  setVal('promotion-member-only', row.member_only ? 'true' : 'false');
  setVal('promotion-valid-from', row.start_at || row.valid_from || row.starts_at || '');
  setVal('promotion-valid-until', row.end_at || row.valid_until || row.ends_at || '');
  setVal('promotion-timezone', row.timezone || 'Asia/Taipei');
  setVal('promotion-item-ids', joinCsv(row.item_ids || row.items));
  setVal('promotion-categories', joinCsv(row.categories || row.category));
  setVal('promotion-required-items', joinCsv(row.required_cart_item_ids || row.required_items));
  const pricing = row.pricing && typeof row.pricing === 'object' ? row.pricing : {};
  const ad = row.ad && typeof row.ad === 'object' ? row.ad : {};
  setVal('promotion-original-price', pricing.original_price ?? '');
  setVal('promotion-promotion-price', pricing.promotion_price ?? '');
  setVal('promotion-save-text', row.save_text || '');
  setVal('promotion-ad-headline', row.badge || ad.headline || '');
  setVal('promotion-ad-copy', row.subtitle || ad.copy || '');
  setVal('promotion-ad-cta', row.cta_text || ad.cta || '立即查看');
  setVal('promotion-target-type', row.target_type || 'none');
  setVal('promotion-target-value', row.target_value || '');
  setVal('promotion-theme', row.theme || 'gold');
  setVal('promotion-legal-text', row.legal_text || '');
  setVal('promotion-score-boost', row.score_boost ?? 4);
  setVal('promotion-category-score-boost', row.category_score_boost ?? 2);
  setVal('promotion-content', row.content || row.description || '');
  const offerInput = g('promotion-offer-id');
  if (offerInput) offerInput.disabled = Boolean(row.offer_id);
}

function resetPromotionForm() {
  setPromotionForm({});
  const offerInput = g('promotion-offer-id');
  if (offerInput) offerInput.disabled = false;
}

function appendCsvValue(inputId, value) {
  const input = g(inputId);
  const nextValue = String(value || '').trim();
  if (!input || !nextValue) return;
  const values = splitCsv(input.value);
  if (!values.includes(nextValue)) values.push(nextValue);
  input.value = values.join(', ');
}

function promotionCategoriesFromMenu() {
  return Array.from(new Set(
    Object.values(menuCache)
      .map(item => String(item.category || '').trim())
      .filter(Boolean)
  )).sort((a, b) => a.localeCompare(b, 'zh-Hant'));
}

function fillSelect(selectId, rows, valueOf, labelOf) {
  const select = g(selectId);
  if (!select) return;
  select.textContent = '';
  rows.forEach(row => {
    const option = document.createElement('option');
    option.value = valueOf(row);
    option.textContent = labelOf(row);
    select.appendChild(option);
  });
}

function fillPromotionTargetPicker() {
  const targetType = val('promotion-target-type') || 'none';
  if (targetType === 'category') {
    fillSelect('promotion-target-picker', promotionCategoriesFromMenu(), row => row, row => row);
    return;
  }
  if (targetType === 'item') {
    fillSelect(
      'promotion-target-picker',
      Object.values(menuCache),
      row => row.id || '',
      row => `${row.id || ''}｜${row.name || row.id || ''}`
    );
    return;
  }
  fillSelect('promotion-target-picker', [{ id: '', name: '此目標類型不需要 target_value' }], row => row.id, row => row.name);
}

async function preparePromotionPickers() {
  await loadMenu();
  const menuRows = Object.values(menuCache);
  fillSelect('promotion-item-picker', menuRows, row => row.id || '', row => `${row.id || ''}｜${row.name || row.id || ''}`);
  fillSelect('promotion-required-picker', menuRows, row => row.id || '', row => `${row.id || ''}｜${row.name || row.id || ''}`);
  fillSelect('promotion-category-picker', promotionCategoriesFromMenu(), row => row, row => row);
  fillPromotionTargetPicker();
}

function bindPromotionPickers() {
  document.querySelectorAll('[data-promotion-picker]').forEach(button => {
    button.addEventListener('click', async () => {
      await preparePromotionPickers();
      const key = button.getAttribute('data-promotion-picker') || '';
      document.querySelectorAll('.promotion-picker-panel').forEach(panel => panel.classList.remove('open'));
      g(`promotion-picker-${key}`)?.classList.add('open');
    });
  });
  document.querySelectorAll('[data-promotion-insert]').forEach(button => {
    button.addEventListener('click', () => {
      const key = button.getAttribute('data-promotion-insert') || '';
      const mappings = {
        items: ['promotion-item-picker', 'promotion-item-ids'],
        categories: ['promotion-category-picker', 'promotion-categories'],
        required: ['promotion-required-picker', 'promotion-required-items'],
        target: ['promotion-target-picker', 'promotion-target-value'],
      };
      const mapping = mappings[key];
      if (!mapping) return;
      const select = g(mapping[0]);
      const value = select?.value || '';
      if (key === 'target') {
        setVal(mapping[1], value);
      } else {
        appendCsvValue(mapping[1], value);
      }
    });
  });
  g('promotion-target-type')?.addEventListener('change', async () => {
    await preparePromotionPickers();
    g('promotion-picker-target')?.classList.add('open');
  });
}

function promotionScope(row) {
  const itemIds = Array.isArray(row.item_ids) ? row.item_ids : [];
  const categories = Array.isArray(row.categories) ? row.categories : [];
  const rows = [];
  if (itemIds.length) rows.push(`品項 ${itemIds.slice(0, 4).join(', ')}`);
  if (categories.length) rows.push(`分類 ${categories.slice(0, 4).join(', ')}`);
  return rows.join(' · ') || '未設定範圍';
}

async function loadPromotions() {
  const box = g('promotion-list');
  if (box) box.innerHTML = '<div class="adm-empty">載入中…</div>';
  try {
    const res = await fetch(`${API}/api/rag/promotions`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    promotionRows = Array.isArray(data.promotions) ? data.promotions : [];
    renderPromotionList();
  } catch (e) {
    promotionRows = [];
    if (box) box.innerHTML = `<div class="adm-empty" style="color:#e84040">載入失敗：${escHtml(e.message)}</div>`;
  }
}

function renderPromotionList() {
  const box = g('promotion-list');
  const count = g('promotion-count');
  if (count) count.textContent = `(${promotionRows.length})`;
  if (!box) return;
  if (!promotionRows.length) {
    box.innerHTML = '<div class="adm-empty">尚無結構化活動。</div>';
    return;
  }
  box.textContent = '';
  promotionRows
    .slice()
    .sort((a, b) => String(a.status || '').localeCompare(String(b.status || '')) || String(a.offer_id || '').localeCompare(String(b.offer_id || '')))
    .forEach(row => {
      const status = String(row.status || row.metadata?.status || 'draft').toLowerCase();
      const pricing = row.pricing && typeof row.pricing === 'object' ? row.pricing : {};
      const promoPrice = row.promo_price || pricing.promotion_price;
      const originalPrice = row.original_price || pricing.original_price;
      const priceText = promoPrice
        ? `優惠價 $${promoPrice}${originalPrice ? `（原價 $${originalPrice}）` : ''}`
        : '未設定加購價';
      const surfaceText = row.surface === 'pos_home_banner' ? `POS Banner｜優先級 ${row.priority || 0}` : '推薦 / RAG';
      const card = document.createElement('div');
      card.className = 'promotion-card';
      card.innerHTML = `<div class="promotion-card-head">`
        + `<div class="promotion-card-title"><b>${escHtml(row.title || row.offer_id || '未命名活動')}</b><span>${escHtml(row.offer_id || '')}</span></div>`
        + `<span class="promotion-status ${escHtml(status)}">${escHtml(promotionStatusLabel(status))}</span>`
        + `</div>`
        + `<div class="promotion-meta">`
        + `<span>${row.member_only ? '會員限定' : '一般活動'}</span>`
        + `<span>${escHtml(surfaceText)}</span>`
        + `<span>${escHtml(row.start_at || row.valid_from || '未設定')} - ${escHtml(row.end_at || row.valid_until || '未設定')}｜${escHtml(row.timezone || 'Asia/Taipei')}</span>`
        + `<span>${escHtml(promotionScope(row))}</span>`
        + `<span>${escHtml(priceText)}</span>`
        + `<span>${escHtml(row.badge || row.ad?.headline || '未設定 Banner 標籤')}</span>`
        + `</div>`
        + `<div class="promotion-actions"></div>`;
      const actions = card.querySelector('.promotion-actions');
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.textContent = '編輯';
      edit.addEventListener('click', () => setPromotionForm(row));
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.textContent = status === 'active' ? '停用' : '啟用';
      toggle.addEventListener('click', () => updatePromotionStatus(row.offer_id, status === 'active' ? 'inactive' : 'active'));
      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'danger';
      del.textContent = '刪除';
      del.addEventListener('click', () => deletePromotion(row.offer_id, row.title || ''));
      actions.append(edit, toggle, del);
      box.appendChild(card);
    });
}

async function savePromotion() {
  const editingId = val('promotion-editing-id');
  const payload = getPromotionPayload();
  if (!payload.title) {
    promotionNotice('儲存失敗：活動名稱不可為空', false);
    return;
  }
  if (payload.start_at && payload.end_at && payload.start_at > payload.end_at) {
    promotionNotice('儲存失敗：結束時間不可早於開始時間', false);
    return;
  }
  const url = editingId
    ? `${API}/api/rag/promotions/${encodeURIComponent(editingId)}`
    : `${API}/api/rag/promotions`;
  try {
    const res = await fetch(url, {
      method: editingId ? 'PUT' : 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.status !== 'ok') throw new Error((data.errors || [data.message || '儲存失敗']).join('；'));
    promotionNotice('✓ 活動已儲存');
    resetPromotionForm();
    await loadPromotions();
    await loadRagDocs();
    await loadRagReviews();
  } catch (e) {
    promotionNotice(`儲存失敗：${e.message}`, false);
  }
}

async function updatePromotionStatus(offerId, status) {
  if (!offerId) return;
  try {
    const res = await fetch(`${API}/api/rag/promotions/${encodeURIComponent(offerId)}/status`, {
      method: 'PATCH',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.status !== 'ok') throw new Error((data.errors || ['更新失敗']).join('；'));
    promotionNotice(`✓ 已${status === 'active' ? '啟用' : '停用'}活動`);
    await loadPromotions();
  } catch (e) {
    promotionNotice(`更新失敗：${e.message}`, false);
  }
}

async function deletePromotion(offerId, title) {
  if (!offerId) return;
  if (!confirm(`確定刪除活動「${title || offerId}」？此操作會刪除 promotion JSON。`)) return;
  try {
    const res = await fetch(`${API}/api/rag/promotions/${encodeURIComponent(offerId)}`, {
      method: 'DELETE',
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data.deleted) throw new Error('找不到活動');
    promotionNotice('✓ 活動已刪除');
    resetPromotionForm();
    await loadPromotions();
    await loadRagDocs();
    await loadRagReviews();
  } catch (e) {
    promotionNotice(`刪除失敗：${e.message}`, false);
  }
}

// ── Members ──

let memberFilter = 'all';
let selectedMemberRef = '';
let memberControlsBound = false;

async function loadMembers() {
  const rows = await fetch('/api/members', { headers: adminHeaders() }).then(r => r.json()).catch(() => []);
  window._memberRows = Array.isArray(rows) ? rows : [];
  bindMemberControls();
  renderMemberStats(window._memberRows);
  renderMemberTable(getFilteredMemberRows());
}

function bindMemberControls() {
  if (memberControlsBound) return;
  memberControlsBound = true;
  const search = document.getElementById('memberSearch');
  search?.addEventListener('input', () => renderMemberTable(getFilteredMemberRows()));
  document.getElementById('memberFilters')?.addEventListener('click', (event) => {
    const btn = event.target?.closest?.('.member-filter');
    if (!btn) return;
    memberFilter = btn.getAttribute('data-filter') || 'all';
    document.querySelectorAll('.member-filter').forEach(el => el.classList.toggle('active', el === btn));
    renderMemberTable(getFilteredMemberRows());
  });
  document.getElementById('memberExportBtn')?.addEventListener('click', exportMembersCsv);
}

function getMemberSearchText(row) {
  return [
    row.phone_masked,
    row.nickname,
    ...(Array.isArray(row.favorites) ? row.favorites : []),
  ].join(' ').toLowerCase();
}

function getMemberStatus(row) {
  const completed = Number(row.completed_order_count || 0);
  const incomplete = Number(row.incomplete_order_count || 0);
  const last = Date.parse(row.last_visit_at || '');
  const active = Number.isFinite(last) && last >= Date.now() - 7 * 864e5;
  if (!completed && !incomplete) return { key: 'new', label: '新會員' };
  if (incomplete > 0 && !completed) return { key: 'risk', label: '未完成' };
  if (active) return { key: 'active', label: '活躍' };
  return { key: 'dormant', label: '沉睡' };
}

function getFilteredMemberRows() {
  const rows = Array.isArray(window._memberRows) ? window._memberRows : [];
  const q = String(document.getElementById('memberSearch')?.value || '').trim().toLowerCase();
  const spendValues = rows.map(r => Number(r.completed_spend ?? r.total_spend ?? 0)).sort((a, b) => a - b);
  const highValueThreshold = spendValues.length ? spendValues[Math.max(0, Math.floor(spendValues.length * 0.75) - 1)] : 0;
  return rows.filter((row) => {
    if (q && !getMemberSearchText(row).includes(q)) return false;
    const status = getMemberStatus(row);
    if (memberFilter === 'active') {
      const last = Date.parse(row.last_visit_at || '');
      return Number.isFinite(last) && last >= Date.now() - 7 * 864e5;
    }
    if (memberFilter === 'incomplete') return Number(row.incomplete_order_count || 0) > 0;
    if (memberFilter === 'high_value') return Number(row.completed_spend ?? row.total_spend ?? 0) >= highValueThreshold && highValueThreshold > 0;
    if (memberFilter === 'new') return status.key === 'new';
    return true;
  });
}

function fmtMoney(value) {
  return `$${Number(value || 0).toLocaleString('zh-TW')}`;
}

function fmtDate(value, fallback = '—') {
  if (!value) return fallback;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 16).replace('T', ' ');
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function renderMemberStats(rows) {
  const total = rows.length;
  const weekAgo = Date.now() - 7 * 864e5;
  const active = rows.filter(r => Date.parse(r.last_visit_at || '') >= weekAgo).length;
  const completedOrders = rows.reduce((s, r) => s + Number(r.completed_order_count || 0), 0);
  const incompleteOrders = rows.reduce((s, r) => s + Number(r.incomplete_order_count || 0), 0);
  const spend = rows.reduce((s, r) => s + Number(r.completed_spend ?? r.total_spend ?? 0), 0);
  const avg = completedOrders ? Math.round(spend / completedOrders) : 0;
  const hitCount = rows.reduce((s, r) => s + Number(r.recommendation_hit_count || 0), 0);
  const hitRate = completedOrders ? Math.round((hitCount / completedOrders) * 100) : 0;
  const cards = [
    ['總會員數', total, '已註冊帳戶'],
    ['近 7 天活躍', active, `${total ? Math.round(active / total * 100) : 0}% 活躍率`],
    ['完成訂單', completedOrders, '會員完成交易'],
    ['未完成訂單', incompleteOrders, `${completedOrders + incompleteOrders ? Math.round(incompleteOrders / (completedOrders + incompleteOrders) * 100) : 0}% 未完成率`],
    ['會員營收', fmtMoney(spend), '只計完成訂單'],
    ['平均客單', fmtMoney(avg), `推播命中 ${hitRate}%`],
  ];
  document.getElementById('memberStatCards').innerHTML = cards
    .map(([label, val, sub]) => `<div class="member-stat"><b>${escHtml(String(val))}</b><span>${escHtml(label)}</span><small>${escHtml(sub)}</small></div>`)
    .join('');
}

function renderMemberTable(rows) {
  const body = document.getElementById('memberTableBody');
  body.innerHTML = '';
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#9aa4b1;padding:24px">沒有符合條件的會員</td></tr>';
    return;
  }
  rows.forEach((r) => {
    const tr = document.createElement('tr');
    const memberRef = r.member_ref || '';
    tr.classList.toggle('member-row-selected', selectedMemberRef && selectedMemberRef === memberRef);
    const status = getMemberStatus(r);
    const favs = (r.favorites || []).map(f => `<span class="fav-chip">${escHtml(f)}</span>`).join('');
    tr.innerHTML = `<td><div class="member-person"><b>${escHtml(r.nickname || '未命名會員')}</b><span>${escHtml(r.phone_masked || '')}</span></div></td>`
      + `<td><span class="member-status ${status.key}">${escHtml(status.label)}</span></td>`
      + `<td>${Number(r.completed_order_count || 0)} 筆</td>`
      + `<td>${Number(r.incomplete_order_count || 0)} 筆</td>`
      + `<td>${fmtMoney(r.completed_spend ?? r.total_spend ?? 0)}</td>`
      + `<td>${fmtMoney(r.avg_completed_spend ?? r.avg_spend ?? 0)}</td>`
      + `<td>${escHtml(fmtDate(r.last_visit_at, '—').slice(0, 10))}</td><td>${favs || '<span class="muted">—</span>'}</td>`
      + `<td><button class="view-btn" data-member-ref="${escHtml(memberRef)}">查看</button></td>`;
    body.appendChild(tr);
  });
  body.querySelectorAll('.view-btn').forEach(btn => {
    btn.addEventListener('click', () => loadMemberDetail(btn.getAttribute('data-member-ref')));
  });
}

async function loadMemberDetail(memberRef) {
  selectedMemberRef = memberRef || '';
  renderMemberTable(getFilteredMemberRows());
  const d = await fetch(`/api/members/${encodeURIComponent(memberRef)}`, { headers: adminHeaders() }).then(r => r.ok ? r.json() : null).catch(() => null);
  const panel = document.getElementById('memberDetailPanel');
  if (!d) {
    panel.classList.remove('hidden');
    panel.innerHTML = '<div class="member-detail-empty">找不到會員資料</div>';
    return;
  }
  const favRows = (d.favorites_ranked || []).map(f =>
    `<div class="fav-row"><span>${escHtml(f.name)}</span><b>×${f.count}</b></div>`).join('');
  const categoryRows = (d.categories_ranked || []).slice(0, 6).map(row =>
    `<div class="fav-row"><span>${escHtml(row.category || '未分類')}</span><b>×${Number(row.count || 0)}</b></div>`).join('');
  const pairRows = (d.pairs_ranked || []).slice(0, 5).map(row =>
    `<div class="fav-row"><span>${(row.names || []).map(escHtml).join(' + ')}</span><b>×${Number(row.count || 0)}</b></div>`).join('');
  const rec = d.recommendation_summary || {};
  const recRows = [
    ['曝光', rec.shown || 0],
    ['點擊', rec.clicked || 0],
    ['加購', rec.added_to_cart || 0],
    ['結帳命中', rec.checked_out || 0],
    ['忽略', rec.ignored || 0],
    ['接受率', `${Math.round(Number(rec.acceptance_rate || 0) * 100)}%`],
  ].map(([label, value]) => `<div><b>${escHtml(String(value))}</b><span>${escHtml(label)}</span></div>`).join('');
  const consentRows = [
    ['點餐紀錄', d.order_history_consent ? '已同意' : '未同意'],
    ['個人化推薦', d.personalization_consent ? '已同意' : '未同意'],
    ['同意版本', d.consent_version || '—'],
    ['隱私版本', d.privacy_version || '—'],
    ['同意時間', fmtDate(d.consent_accepted_at, '—')],
    ['最後登入', fmtDate(d.last_login_at, '—')],
    ['登入次數', Number(d.login_count || 0)],
    ['資料保留至', fmtDate(d.data_retention_until, '—').slice(0, 10)],
  ].map(([label, value]) => `<div><b>${escHtml(String(value))}</b><span>${escHtml(label)}</span></div>`).join('');
  const orderRows = (d.orders || []).map(o => {
    const completed = o.is_completed !== false && (o.order_status || 'completed') === 'completed';
    const status = completed
      ? '<span class="member-status active">已完成</span>'
      : '<span class="member-status risk">未完成</span>';
    const items = (o.items || []).map(it => `${escHtml(it.name || it.id || '')}${Number(it.count || 1) > 1 ? ` ×${Number(it.count || 1)}` : ''}`).join('、')
      || (o.cart_ids || []).map(escHtml).join('、');
    const hit = o.recommendation_success || o.is_success
      ? '<span class="hit">推播命中</span>'
      : '<span class="miss">推播未命中</span>';
    const reason = !completed && o.cancel_reason ? `<span class="miss">原因：${escHtml(o.cancel_reason)}</span>` : '';
    return `<div class="order-row"><div class="order-row-top"><div><div class="order-row-date">${escHtml(fmtDate(o.timestamp))}</div>${status}</div>`
      + `<b class="order-row-total">${fmtMoney(o.total || 0)}</b></div><div class="order-items">${items || '—'}</div>${hit}${reason}</div>`;
  }).join('');
  panel.classList.remove('hidden');
  panel.innerHTML = `<div class="member-detail-head"><div><h2>${escHtml(d.nickname || '未命名會員')}</h2><small>${escHtml(d.phone_masked || '')}</small></div><span class="member-status ${getMemberStatus(d).key}">${escHtml(getMemberStatus(d).label)}</span></div>`
    + `<div class="member-kpis"><div><b>${d.completed_order_count || 0}</b><span>完成訂單</span></div>`
    + `<div><b>${d.incomplete_order_count || 0}</b><span>未完成</span></div>`
    + `<div><b>${fmtMoney(d.completed_spend ?? d.total_spend ?? 0)}</b><span>完成營收</span></div>`
    + `<div><b>${fmtMoney(d.avg_completed_spend ?? d.avg_spend ?? 0)}</b><span>平均客單</span></div></div>`
    + `<div class="member-section-title">會員資料治理</div><div class="member-kpis">${consentRows}</div>`
    + `<div class="member-section-title">常點品項排行</div>${favRows || '<p class="muted">尚無紀錄</p>'}`
    + `<div class="member-section-title">分類偏好</div>${categoryRows || '<p class="muted">尚無分類偏好</p>'}`
    + `<div class="member-section-title">常見搭配</div>${pairRows || '<p class="muted">尚無搭配紀錄</p>'}`
    + `<div class="member-section-title">推薦成效</div><div class="member-kpis">${recRows}</div>`
    + `<div class="member-section-title">訂單時間線</div>${orderRows || '<p class="muted">尚無訂單</p>'}`
    + `<div class="member-danger">`
    + `<button class="member-clear-btn" type="button">刪除點餐紀錄</button>`
    + `<button class="member-delete-btn" type="button">刪除會員帳戶</button>`
    + `</div>`;
  panel.querySelector('.member-clear-btn')?.addEventListener('click', () => clearMemberRecords(d.member_ref || memberRef, d.nickname || '', d.phone_masked || ''));
  panel.querySelector('.member-delete-btn')?.addEventListener('click', () => deleteMember(d.member_ref || memberRef, d.nickname || '', d.phone_masked || ''));
}

async function clearMemberRecords(memberRef, nickname, phoneMasked) {
  if (!confirm(`確定要刪除「${nickname || phoneMasked || memberRef}」的所有點餐紀錄（訂單、常點、消費統計）嗎？\n帳戶會保留，但紀錄無法復原。`)) return;
  const result = await fetch(`/api/members/${encodeURIComponent(memberRef)}/records`, { method: 'DELETE', headers: adminHeaders() })
    .then(r => r.ok ? r.json() : null).catch(() => null);
  if (!result?.ok) { alert('刪除失敗'); return; }
  if (result.audit_id) alert(`已清除紀錄，Audit ID：${result.audit_id}`);
  await loadMembers();
  loadMemberDetail(memberRef);
}

async function deleteMember(memberRef, nickname, phoneMasked) {
  if (!confirm(`確定要刪除會員帳戶「${nickname || phoneMasked || memberRef}」嗎？\n此操作將永久移除該會員及其所有紀錄，無法復原。`)) return;
  const result = await fetch(`/api/members/${encodeURIComponent(memberRef)}`, { method: 'DELETE', headers: adminHeaders() })
    .then(r => r.ok ? r.json() : null).catch(() => null);
  if (!result?.ok) { alert('刪除失敗'); return; }
  if (result.audit_id) alert(`已刪除會員，Audit ID：${result.audit_id}`);
  document.getElementById('memberDetailPanel')?.classList.add('hidden');
  await loadMembers();
}

async function exportMembersCsv() {
  const res = await fetch('/api/members/export', { headers: adminHeaders() }).catch(() => null);
  if (!res || !res.ok) {
    alert('匯出失敗');
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'members_export.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  const auditId = res.headers.get('X-Admin-Audit-Id');
  if (auditId) alert(`已匯出會員 CSV，Audit ID：${auditId}`);
}

// ── 測試頁：載入預設語音 Prompt ──

async function loadVoicePromptDefault() {
  const ta = g('test-inp-system-prompt');
  if (!ta || ta.value.trim()) return;   // 使用者已手動填寫則不覆蓋
  try {
    const res = await fetch(`${API}/api/test/voice_prompt`, { headers: adminHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    if (data.prompt) ta.value = data.prompt;
  } catch { /* 靜默失敗 */ }
}

// ── Ollama 模型清單 ──

let _ollamaModels = [];

async function loadOllamaModels() {
  try {
    const res = await fetch(`${API}/api/ollama/models`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _ollamaModels = Array.isArray(data.models) ? data.models : [];
  } catch {
    _ollamaModels = [];
  }
  // 更新設定頁 select
  const mainCur  = val('inp-model-name');
  const voiceCur = val('inp-voice-model');
  populateModelSelect('inp-model-name',  _ollamaModels, mainCur  || 'qwen3.5:4b');
  populateModelSelect('inp-voice-model', _ollamaModels, voiceCur || 'qwen3.5:4b');
  // 更新測試頁 select
  const testCur = val('test-inp-model');
  populateModelSelect('test-inp-model', _ollamaModels, testCur || (_ollamaModels[0] || ''));
}

function populateModelSelect(selectId, models, currentValue) {
  const sel = g(selectId);
  if (!sel || sel.tagName !== 'SELECT') return;
  const prev = sel.value || currentValue;
  sel.textContent = '';
  if (!models.length) {
    const opt = document.createElement('option');
    opt.value = currentValue;
    opt.textContent = currentValue || '（無法取得模型清單）';
    sel.appendChild(opt);
    return;
  }
  let matched = false;
  models.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m;
    opt.textContent = m;
    if (m === prev) { opt.selected = true; matched = true; }
    sel.appendChild(opt);
  });
  // 若目前值不在清單中，插入一個自訂 option
  if (!matched && prev) {
    const opt = document.createElement('option');
    opt.value = prev;
    opt.textContent = `${prev}（自訂）`;
    opt.selected = true;
    sel.insertBefore(opt, sel.firstChild);
  }
}

// ── 設定頁：AI 提供者切換 ──

function onAiProviderChange(btn) {
  const provider = btn.dataset.provider;
  btn.closest('.provider-tabs').querySelectorAll('.provider-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  ['ollama', 'gemini', 'openai'].forEach(p => {
    g(`settings-fields-${p}`)?.classList.toggle('hidden', p !== provider);
  });
  if (provider === 'ollama' && !_ollamaModels.length) loadOllamaModels();
}

// ── 測試頁：提供者切換 ──

function onTestProviderChange(btn) {
  const provider = btn.dataset.provider;
  btn.closest('.provider-tabs').querySelectorAll('.provider-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  ['ollama', 'gemini', 'openai'].forEach(p => {
    g(`test-fields-${p}`)?.classList.toggle('hidden', p !== provider);
  });
}

function getTestProvider() {
  return g('page-test')?.querySelector('.provider-tab.active')?.dataset.provider || 'ollama';
}

function getTestModel() {
  const p = getTestProvider();
  if (p === 'gemini') return val('test-inp-gemini-model') || 'gemini-2.0-flash';
  if (p === 'openai') return val('test-inp-openai-model') || 'gpt-4o-mini';
  return val('test-inp-model') || (_ollamaModels[0] || '');
}

// ── 測試頁：對話 ──

const _testMessages = [];

function switchTestView(view, btn) {
  btn.closest('.test-view-tabs').querySelectorAll('.test-view-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  g('test-chat-view')?.classList.toggle('hidden', view !== 'chat');
  g('test-json-view')?.classList.toggle('hidden', view !== 'json');
}

function clearTestChat() {
  _testMessages.length = 0;
  const win = g('test-chat-view');
  if (win) {
    win.textContent = '';
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble ai';
    bubble.innerHTML = '<span class="bubble-label">AI 助理</span><div class="bubble-text">對話已清除，可繼續輸入測試。</div>';
    win.appendChild(bubble);
  }
  const raw = g('test-json-view');
  if (raw) raw.textContent = '// 對話已清除';
  g('test-stat-chips')?.style.setProperty('display', 'none');
}

function _appendBubble(role, text, meta = '') {
  const win = g('test-chat-view');
  if (!win) return null;
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${role}`;
  const label = document.createElement('span');
  label.className = 'bubble-label';
  label.textContent = meta || (role === 'user' ? '測試輸入' : 'AI 助理');
  const txt = document.createElement('div');
  txt.className = 'bubble-text';
  txt.textContent = text;
  bubble.append(label, txt);
  win.appendChild(bubble);
  win.scrollTop = win.scrollHeight;
  return bubble;
}

async function sendTestMsg() {
  const inputEl = g('test-input');
  const text = (inputEl?.value || '').trim();
  if (!text) return;

  const sendBtn = g('test-send-btn');
  if (sendBtn) sendBtn.disabled = true;
  inputEl.value = '';
  inputEl.style.height = '';

  _appendBubble('user', text);
  _testMessages.push({ role: 'user', content: text });

  const loadingBubble = _appendBubble('ai loading', '思考中…');
  if (loadingBubble) loadingBubble.classList.add('loading');

  const provider = getTestProvider();
  const model    = getTestModel();
  const systemPrompt = val('test-inp-system-prompt') || '';

  try {
    const res = await fetch(`${API}/api/test/ask`, {
      method: 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, model, system_prompt: systemPrompt, messages: [..._testMessages] }),
    });
    const data = await res.json();

    loadingBubble?.remove();

    if (data.error && !data.ai_response) {
      _appendBubble('ai', `❌ 錯誤：${data.error}`);
    } else {
      // 語音模式回傳 ai_response（JSON 結構）；備援 text（raw 模式）
      const responseText = data.ai_response || data.text || '';
      const cartActions  = Array.isArray(data.cart_actions) ? data.cart_actions : [];
      const mentionedIds = Array.isArray(data.mentioned_ids) ? data.mentioned_ids : [];

      const latency = data.latency_ms ?? '?';
      const providerLabel = `${data.provider || provider} / ${data.model || model}`;
      let meta = `AI 助理 · ${providerLabel} · ${latency}ms`;
      if (cartActions.length) meta += ` · 加購 ${cartActions.length} 項`;

      _appendBubble('ai', responseText, meta);
      _testMessages.push({ role: 'assistant', content: responseText });

      // cart_actions 加購提示
      if (cartActions.length) {
        const addedNames = cartActions.map(a => `${a.id}×${a.quantity ?? 1}`).join('、');
        const hint = document.createElement('div');
        hint.style.cssText = 'font-size:11.5px;color:#1db87a;padding:2px 0 4px 4px';
        hint.textContent = `🛒 加入購物車：${addedNames}`;
        g('test-chat-view')?.appendChild(hint);
      }

      // 原始 JSON 視窗（隱藏內部欄位以保持清晰）
      const raw = g('test-json-view');
      if (raw) {
        const display = {
          ai_response:   responseText,
          mentioned_ids: mentionedIds,
          cart_actions:  cartActions,
          _meta: { provider: data.provider || provider, model: data.model || model, latency_ms: latency },
        };
        raw.textContent = JSON.stringify(display, null, 2);
      }

      // 延遲 chip
      const chips = g('test-stat-chips');
      if (chips) {
        chips.style.display = 'flex';
        const latEl = g('test-stat-latency');
        if (latEl) latEl.textContent = `${latency}ms`;
      }
    }
  } catch (e) {
    loadingBubble?.remove();
    _appendBubble('ai', `❌ 請求失敗：${e.message}`);
  } finally {
    if (sendBtn) sendBtn.disabled = false;
  }
}

// ── expose to inline handlers
window.onSttProviderChange = onSttProviderChange;
window.onTtsProviderChange = onTtsProviderChange;
window.saveSettings    = saveSettings;
window.saveRagSettings = saveRagSettings;
window.loadRagHealth   = loadRagHealth;
window.loadRagAlerts   = loadRagAlerts;
window.ackRagAlert     = ackRagAlert;
window.resolveRagAlert = resolveRagAlert;
window.loadRagDocs     = loadRagDocs;
window.loadRagReviews  = loadRagReviews;
window.addRagDoc       = addRagDoc;
window.editRagReview   = editRagReview;
window.cancelRagReviewEdit = cancelRagReviewEdit;
window.approveRagReview = approveRagReview;
window.publishRagReview = publishRagReview;
window.rejectRagReview = rejectRagReview;
window.archiveRagReview = archiveRagReview;
window.validateRagDocs = validateRagDocs;
window.deleteRagDoc    = deleteRagDoc;
window.clearRagDocs    = clearRagDocs;
window.rebuildRagDocs  = rebuildRagDocs;
window.loadPromotions = loadPromotions;
window.savePromotion = savePromotion;
window.resetPromotionForm = resetPromotionForm;
window.loadAvailability = loadAvailability;
window.saveAvailability = saveAvailability;
window.saveEmotionSettings        = saveEmotionSettings;
window.clearEmotionLogs           = clearEmotionLogs;
window.updateEmotionPromptCounter = updateEmotionPromptCounter;
window.onAiProviderChange  = onAiProviderChange;
window.onTestProviderChange = onTestProviderChange;
window.sendTestMsg   = sendTestMsg;
window.clearTestChat = clearTestChat;
window.switchTestView = switchTestView;
window.loadOllamaModels = loadOllamaModels;
window.loadVoicePromptDefault = loadVoicePromptDefault;

// ── 測試頁：Enter 送出 / Shift+Enter 換行；自動撐高 ──
g('test-input')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendTestMsg();
  }
});
g('test-input')?.addEventListener('input', (e) => {
  e.target.style.height = 'auto';
  e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
});

// ── Init ──
document.getElementById('refreshBtn')?.addEventListener('click', loadStats);
document.getElementById('clearBtn')?.addEventListener('click', clearStats);
document.getElementById('recommendationRefreshBtn')?.addEventListener('click', loadRecommendationEvents);
document.getElementById('recommendationClearBtn')?.addEventListener('click', clearRecommendationEvents);
document.getElementById('availabilityRefreshBtn')?.addEventListener('click', loadAvailability);
document.getElementById('availabilitySaveBtn')?.addEventListener('click', saveAvailability);
document.getElementById('availabilitySearch')?.addEventListener('input', renderAvailabilityRows);
document.getElementById('availabilityStatusFilter')?.addEventListener('change', renderAvailabilityRows);
document.getElementById('healthRefreshBtn')?.addEventListener('click', loadAdminHealth);
bindPromotionPickers();
campaignAdmin.bind();
[
  'recommendationEventTypeFilter',
  'recommendationSurfaceFilter',
  'recommendationAudienceFilter',
  'recommendationSince',
  'recommendationUntil',
  'recommendationLimit',
].forEach(id => {
  document.getElementById(id)?.addEventListener('change', () => {
    if (['recommendationLimit', 'recommendationSurfaceFilter', 'recommendationAudienceFilter', 'recommendationSince', 'recommendationUntil'].includes(id)) loadRecommendationEvents();
    else renderRecommendationDashboard();
  });
});
document.getElementById('recommendationSessionFilter')?.addEventListener('input', renderRecommendationDashboard);

createAdminAuthController({
  apiBaseUrl: API,
  onPrincipal: principal => {
    adminPermissionSet = new Set(principal?.permissions || []);
    applyAdminNavigation(principal);
  },
  onAuthenticated: async () => {
    await loadMenu();
    await loadStats();
  },
}).bind();
// 只在統計頁可見時才自動重整
setInterval(() => {
  const statsPage = document.getElementById('page-stats');
  if (statsPage && statsPage.style.display !== 'none') loadStats();
  const recommendationsPage = document.getElementById('page-recommendations');
  if (recommendationsPage && recommendationsPage.style.display !== 'none') loadRecommendationEvents();
}, 15000);

function toggleVoiceWaitMode() {
  const row = document.getElementById('voice-wait-mode-row');
  if (!row) return;
  const checked = g('inp-emotion-event-voice')?.checked;
  row.style.display = checked ? 'flex' : 'none';
}
window.toggleVoiceWaitMode = toggleVoiceWaitMode;

// ── Admin WebSocket（接收 Kiosk 通知）────────────────────────────
function handleStaffNotify(event) {
  const p = event.payload || {};
  const kiosk          = p.kiosk_name     || '';
  const assist_response = p.assist_response || '';
  const emotion        = p.emotion && typeof p.emotion === 'object' ? p.emotion : null;

  const kioskEl   = document.getElementById('staffNotifyKiosk');
  const reasonEl  = document.getElementById('staffNotifyReason');
  const emotionEl = document.getElementById('staffNotifyEmotion');
  const labelEl   = document.getElementById('staffNotifyEmotionLabel');
  const descEl    = document.getElementById('staffNotifyEmotionDesc');
  const backdrop  = document.getElementById('staffNotifyBackdrop');

  if (kioskEl)  kioskEl.textContent  = kiosk;
  if (reasonEl) reasonEl.textContent = '人員協助付款';

  if (emotionEl && labelEl && descEl) {
    if (assist_response) {
      // Ollama 生成的中文情緒摘要：給員工直接閱讀
      labelEl.textContent = assist_response;
      descEl.textContent  = emotion?.emotion
        ? `情緒：${emotion.emotion}${emotion.intensity ? '（' + emotion.intensity + '）' : ''}`
        : '';
    } else if (emotion && emotion.emotion) {
      // fallback：沒有 assist_response 時顯示原始情緒欄位
      const intensity = emotion.intensity ? `（${emotion.intensity}）` : '';
      labelEl.textContent = `${emotion.emotion}${intensity}`;
      descEl.textContent  = emotion.description || '';
    } else {
      labelEl.textContent = '情緒分析尚未完成';
      descEl.textContent  = '';
    }
    emotionEl.style.display = 'block';
  }

  if (backdrop) backdrop.style.display = 'flex';
}

function handleRagAlert(event) {
  const alert = event.payload?.alert;
  if (alert?.message) {
    ragNotice(`RAG 警示：${alert.message}`, false);
  }
  loadRagHealth();
  loadRagAlerts();
}

window.dismissStaffNotify = function () {
  const backdrop = document.getElementById('staffNotifyBackdrop');
  if (backdrop) backdrop.style.display = 'none';
};

createRealtimeClient('admin', 'admin', {
  staff_notify: handleStaffNotify,
  rag_alert: handleRagAlert,
});
