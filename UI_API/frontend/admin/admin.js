import { createRealtimeClient } from '../shared/realtimeClient.js';
import { createAvailabilityAdmin } from './modules/availabilityAdmin.js';
import { createHealthAdmin } from './modules/healthAdmin.js';
import { createRecommendationEventsAdmin } from './modules/recommendationEventsAdmin.js';
import { createCampaignAdmin } from './modules/campaignAdmin.js';
import { createSettingsAdmin } from './modules/settingsAdmin.js';
import { createEmotionInfluenceAdmin } from './modules/emotionInfluenceAdmin.js';
import { createMemberServiceDeskAdmin } from './modules/memberServiceDeskAdmin.js';
import { createRagAdmin } from './modules/ragAdmin.js';
import { createOperationsOverviewAdmin } from './modules/operationsOverviewAdmin.js';
import { applyAdminNavigation } from './modules/adminNavigation.js';
import { bindLayoutPreference, initZoom } from './modules/layoutPreference.js';
import { adminHeaders, createAdminAuthController } from './features/auth/adminAuth.js';
import { llmTestErrorMessage } from './features/apiErrors.js';

const API = window.location.origin;

// 在任何畫面繪製前先套用個人的介面縮放偏好，避免先閃一下預設大小再跳動。
initZoom();
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
    document.querySelectorAll('.nav-item[data-page]').forEach(b => {
      const active = b === btn;
      b.classList.toggle('active', active);
      if (active) b.setAttribute('aria-current', 'page');
      else b.removeAttribute('aria-current');
    });
    const page = btn.dataset.page;
    document.querySelectorAll('[id^="page-"]').forEach(el => {
      el.style.display = el.id === `page-${page}` ? '' : 'none';
    });
    const titles  = { stats: '營運總覽', settings: '功能設定', recommendations: '推薦成效', promotions: '活動管理', availability: '供應狀態', health: '維運健康', rag: 'RAG 智慧工作室', emotion: '情緒分析', members: '會員管理' };
    const icons   = { stats: 'fa-chart-line', settings: 'fa-sliders-h', recommendations: 'fa-bullseye', promotions: 'fa-ticket-alt', availability: 'fa-store', health: 'fa-heartbeat', rag: 'fa-database', emotion: 'fa-eye', members: 'fa-users' };
    const titleEl = document.getElementById('page-title');
    const iconEl  = document.getElementById('topbar-icon');
    if (titleEl) titleEl.textContent = titles[page] || page;
    if (iconEl) {
      const ico = document.createElement('i');
      ico.className = `fas ${icons[page] || 'fa-circle'}`;
      iconEl.textContent = '';
      iconEl.appendChild(ico);
    }
    if (page === 'stats') loadOperationsOverview();
    if (page === 'settings') loadSettings();
    if (page === 'recommendations') loadRecommendationEvents();
    if (page === 'promotions') loadCampaigns();
    if (page === 'availability') loadAvailability();
    if (page === 'health') loadAdminHealth();
    if (page === 'rag') ragAdmin.loadPage();
    if (page === 'emotion') { loadEmotionSettings(); loadEmotionLogs(); }
    if (page === 'members') loadMembers();
    // 模型診斷與即時影音測試已併入功能設定／情緒分析頁，測試頁不再存在。
    if (page === 'settings') { loadOllamaModels(); loadVoicePromptDefault(); }
    if (page !== 'emotion') stopEmotionVideoDetection();
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
    setText('s-success',   String(success));

    const sessions = data.sessions || [];
    renderTop3(sessions);
    renderTable(sessions);

  } catch (error) {
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
function fmtDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-TW');
}

// ── Admin feature modules ──
const operationsOverviewAdmin = createOperationsOverviewAdmin({
  getElement: g,
  hasPermission: hasAdminPermission,
  loadOverview: async () => {
    const res = await fetch(`${API}/api/v1/operations/overview`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`營運總覽讀取失敗（${res.status}）`);
    return (await res.json()).data;
  },
});

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

const settingsAdmin = createSettingsAdmin({
  apiBaseUrl: API,
  adminHeaders,
  getElement: g,
  loadOllamaModels: () => loadOllamaModels(),
});

const availabilityAdmin = createAvailabilityAdmin({
  apiBaseUrl: API,
  adminHeaders,
  getElement: g,
  getValue: val,
  setValue: setVal,
  escapeHtml: escHtml,
  hasPermission: hasAdminPermission,
});

const healthAdmin = createHealthAdmin({
  apiBaseUrl: API,
  adminHeaders,
  getElement: g,
  setText,
  escapeHtml: escHtml,
  hasPermission: hasAdminPermission,
});

const memberServiceDeskAdmin = createMemberServiceDeskAdmin({
  apiBaseUrl: API,
  adminHeaders,
  getElement: g,
  escapeHtml: escHtml,
  hasPermission: hasAdminPermission,
});
memberServiceDeskAdmin.bind();

const ragAdmin = createRagAdmin({
  apiBaseUrl: API,
  adminHeaders,
  getElement: g,
  escapeHtml: escHtml,
  hasPermission: hasAdminPermission,
});

const emotionInfluenceAdmin = createEmotionInfluenceAdmin({
  getElement: g,
  escapeHtml: escHtml,
  emotionLabel: zhEmotion,
  intensityLabel: zhIntensity,
  providerLabel: value => EMOTION_RUNTIME_LABELS[value] || String(value || 'R1-Omni'),
});
let latestEmotionRoundId = '';

function loadRecommendationEvents() { return recommendationEventsAdmin.loadRecommendationEvents(); }
function loadOperationsOverview() { return operationsOverviewAdmin.refresh(); }
function loadCampaigns() { return campaignAdmin.loadCampaigns(); }
function renderRecommendationDashboard() { return recommendationEventsAdmin.renderRecommendationDashboard(); }
function loadAvailability() { return availabilityAdmin.loadAvailability(); }
function saveAvailability() { return availabilityAdmin.saveAvailability(); }
function renderAvailabilityRows() { return availabilityAdmin.renderAvailabilityRows(); }
function loadAdminHealth() { return healthAdmin.loadAdminHealth(); }
function loadMembers() { return memberServiceDeskAdmin.load(); }

function loadSettings() { return settingsAdmin.load(); }

// ── 情緒分析頁分頁 ──

function showEmotionTab(tab) {
  document.querySelectorAll('[data-emotion-tab]').forEach(node => {
    const selected = node.dataset.emotionTab === tab;
    node.classList.toggle('active', selected);
    node.setAttribute('aria-selected', String(selected));
  });
  document.querySelectorAll('[data-emotion-panel]').forEach(node => {
    const selected = node.dataset.emotionPanel === tab;
    node.hidden = !selected;
    node.classList.toggle('active', selected);
  });
  // 攝影機只在「即時客人分析」分頁需要；離開分頁就收掉，避免鏡頭在背景持續開著。
  if (tab !== 'live') stopEmotionVideoDetection();
}

function bindEmotionTabs() {
  document.querySelectorAll('[data-emotion-tab]').forEach(node => {
    node.addEventListener('click', () => showEmotionTab(node.dataset.emotionTab || 'config'));
  });
}

// ── R1-Omni emotion settings ──

async function loadEmotionSettings() {
  try {
    const res = await fetch(`${API}/api/settings`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const s = await res.json();
    g('inp-emotion-enabled').checked        = Boolean(s.EMOTION_ENABLED);
    setVal('inp-emotion-clip-sec',            s.EMOTION_CLIP_SEC       ?? 2.0);
    g('inp-emotion-quality-check').checked  = s.EMOTION_QUALITY_CHECK !== false;
    g('inp-emotion-affect-voice').checked   = Boolean(s.EMOTION_AFFECT_VOICE);
    const assistanceMode = s.EMOTION_ASSISTANCE_MODE || 'shadow';
    setVal('inp-emotion-assistance-mode', assistanceMode);
    setVal('inp-emotion-confidence-threshold', s.EMOTION_ASSISTANCE_CONFIDENCE_THRESHOLD ?? 0.7);
    setVal('inp-emotion-rollout-percent', s.EMOTION_ASSISTANCE_ROLLOUT_PERCENT ?? 0);
    g('inp-emotion-affect-voice').checked = assistanceMode === 'active';
    g('inp-emotion-event-voice').checked    = s.EMOTION_EVENT_VOICE !== false;
    const analysisMode = s.EMOTION_ANALYSIS_MODE
      || (s.EMOTION_INCLUDE_STT === false ? 'media_only' : 'media_plus_stt');
    setVal('inp-emotion-analysis-mode', analysisMode);
    g('inp-emotion-include-stt').checked = analysisMode !== 'media_only';
    setVal('inp-emotion-prompt',              s.EMOTION_PROMPT || '');
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
    const analysisMode = val('inp-emotion-analysis-mode') || 'media_plus_stt';
    const assistanceMode = val('inp-emotion-assistance-mode') || 'shadow';
    const body = {
      EMOTION_ENABLED:        g('inp-emotion-enabled').checked,
      EMOTION_CLIP_SEC:       parseFloat(val('inp-emotion-clip-sec') || '2.0'),
      EMOTION_QUALITY_CHECK:  g('inp-emotion-quality-check').checked,
      EMOTION_AFFECT_VOICE:   assistanceMode === 'active',
      EMOTION_ASSISTANCE_MODE:      assistanceMode,
      EMOTION_ASSISTANCE_CONFIDENCE_THRESHOLD: Math.min(1, Math.max(0,
        parseFloat(val('inp-emotion-confidence-threshold') || '0.7'))),
      EMOTION_ASSISTANCE_ROLLOUT_PERCENT: parseInt(val('inp-emotion-rollout-percent') || '0', 10),
      EMOTION_EVENT_VOICE:    g('inp-emotion-event-voice').checked,
      EMOTION_ANALYSIS_MODE:  analysisMode,
      EMOTION_INCLUDE_STT:    analysisMode !== 'media_only',
      EMOTION_PROMPT:         val('inp-emotion-prompt'),
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

// R1-Omni 結構化欄位英→繁對照（emotion / intensity 為有限列舉）
const EMOTION_ZH = {
  neutral: '中性', happy: '開心', sad: '難過', angry: '生氣',
  frustrated: '沮喪', anxious: '焦慮', confused: '困惑', surprise: '驚訝', surprised: '驚訝',
  disgust: '厭惡', fear: '害怕', fearful: '害怕', excited: '興奮', bored: '無聊',
};
const INTENSITY_ZH = { low: '低', medium: '中', high: '高' };
// 情緒分析模型代碼 → 顯示名稱
const EMOTION_RUNTIME_LABELS = { r1_omni: 'R1-Omni' };

function zhEmotion(v) {
  if (!v) return '';
  return EMOTION_ZH[String(v).trim().toLowerCase()] || v;
}
function zhIntensity(v) {
  if (!v) return '';
  return INTENSITY_ZH[String(v).trim().toLowerCase()] || v;
}

let emotionVideoStream = null;
let emotionVideoRecorder = null;
let emotionVideoRunning = false;
let emotionVideoGeneration = 0;
let emotionVideoAbortController = null;
let emotionTestCapabilities = null;

function setEmotionVideoStatus(message, tone = 'info', icon = 'fa-circle-info') {
  const status = g('emotion-video-status');
  if (!status) return;
  status.classList.toggle('is-error', tone === 'error');
  status.innerHTML = `<i class="fas ${escHtml(icon)}" aria-hidden="true"></i><span>${escHtml(message)}</span>`;
}

async function loadEmotionTestCapabilities() {
  const pill = g('emotion-test-provider-pill');
  if (pill) {
    pill.className = 'emotion-test-pill is-checking';
    pill.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> 檢查模型';
  }
  try {
    const response = await fetch(`${API}/api/emotion/test_capabilities`, { headers: adminHeaders() });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    emotionTestCapabilities = data;
    const provider = data.provider || {};
    const label = EMOTION_RUNTIME_LABELS[provider.provider] || provider.provider || 'R1-Omni';
    const capabilities = Array.isArray(provider.capabilities) ? provider.capabilities : [];
    const ready = data.enabled && provider.status === 'ready' && provider.model_loaded === true && capabilities.includes('video_audio');
    if (pill) {
      pill.className = `emotion-test-pill ${ready ? 'is-ready' : 'is-error'}`;
      pill.innerHTML = `<i class="fas ${ready ? 'fa-circle-check' : 'fa-triangle-exclamation'}"></i> ${escHtml(label)}${ready ? ' 已就緒' : ' 未就緒'}`;
      pill.title = ready
        ? `模型已載入；影音能力已確認；健康檢查 ${provider.latency_ms || 0}ms`
        : (provider.message || '模型尚未載入，或未宣告影音分析能力');
    }
    if (!ready) setEmotionVideoStatus(provider.message || '情緒模型尚未就緒，請使用對應啟動腳本。', 'error', 'fa-triangle-exclamation');
    return ready;
  } catch (error) {
    emotionTestCapabilities = null;
    if (pill) {
      pill.className = 'emotion-test-pill is-error';
      pill.innerHTML = '<i class="fas fa-triangle-exclamation"></i> 無法檢查模型';
    }
    setEmotionVideoStatus(`模型狀態檢查失敗：${error.message}`, 'error', 'fa-triangle-exclamation');
    return false;
  }
}

function emotionVideoRecorderOptions() {
  if (typeof MediaRecorder === 'undefined') return {};
  if (MediaRecorder.isTypeSupported('video/webm;codecs=vp8')) {
    return { mimeType: 'video/webm;codecs=vp8', videoBitsPerSecond: 240000 };
  }
  return MediaRecorder.isTypeSupported('video/webm')
    ? { mimeType: 'video/webm', videoBitsPerSecond: 240000 }
    : {};
}

function captureEmotionVideoClip(stream, { minMs = 1500, silenceMs = 900, noSpeechMs = 2500, maxMs = 8000 } = {}) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let recorder;
    let animationFrame = 0;
    let audioContext = null;
    let audioSource = null;
    let analyser = null;
    let noSpeechTimer = 0;
    try {
      recorder = new MediaRecorder(stream, emotionVideoRecorderOptions());
    } catch (error) {
      reject(error);
      return;
    }
    emotionVideoRecorder = recorder;
    const stopRecorder = () => {
      if (recorder.state !== 'inactive') recorder.stop();
    };
    const deadline = window.setTimeout(stopRecorder, maxMs);
    const cleanup = () => {
      window.clearTimeout(deadline);
      window.clearTimeout(noSpeechTimer);
      if (animationFrame) cancelAnimationFrame(animationFrame);
      audioSource?.disconnect();
      analyser?.disconnect();
      if (audioContext) void audioContext.close().catch(() => {});
    };
    const AudioContextClass = globalThis.AudioContext;
    if (AudioContextClass && stream.getAudioTracks().length) {
      try {
        audioContext = new AudioContextClass();
        audioSource = audioContext.createMediaStreamSource(stream);
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 512;
        audioSource.connect(analyser);
        const levels = new Uint8Array(analyser.fftSize);
        const startedAt = performance.now();
        let speechSeen = false;
        let lastSpeechAt = startedAt;
        noSpeechTimer = window.setTimeout(stopRecorder, noSpeechMs);
        const sample = () => {
          if (!analyser || recorder.state === 'inactive') return;
          analyser.getByteTimeDomainData(levels);
          const rms = Math.sqrt(levels.reduce((total, level) => total + ((level - 128) / 128) ** 2, 0) / levels.length);
          const now = performance.now();
          if (rms >= 0.025) {
            speechSeen = true;
            lastSpeechAt = now;
            window.clearTimeout(noSpeechTimer);
          }
          if (speechSeen && now - startedAt >= minMs && now - lastSpeechAt >= silenceMs) {
            stopRecorder();
            return;
          }
          animationFrame = requestAnimationFrame(sample);
        };
        animationFrame = requestAnimationFrame(sample);
      } catch {
        noSpeechTimer = window.setTimeout(stopRecorder, noSpeechMs);
      }
    } else {
      noSpeechTimer = window.setTimeout(stopRecorder, noSpeechMs);
    }
    recorder.ondataavailable = event => {
      if (event.data?.size > 0) chunks.push(event.data);
    };
    recorder.onerror = event => {
      cleanup();
      if (emotionVideoRecorder === recorder) emotionVideoRecorder = null;
      reject(event.error || new Error('瀏覽器無法錄製影像片段'));
    };
    recorder.onstop = () => {
      cleanup();
      if (emotionVideoRecorder === recorder) emotionVideoRecorder = null;
      const type = recorder.mimeType || 'video/webm';
      resolve(new Blob(chunks, { type }));
    };
    recorder.start();
  });
}

function renderEmotionVideoResult(data, batchLatencyMs = 0) {
  const result = g('emotion-video-result');
  if (!result) return;
  const rows = [data];
  result.classList.add('is-single');
  result.innerHTML = rows.map(row => {
    const provider = EMOTION_RUNTIME_LABELS[row.provider] || row.provider || 'R1-Omni';
    const model = row.model_version && row.model_version !== 'unknown' ? `${provider} · ${row.model_version}` : provider;
    const emotion = zhEmotion(row.emotion) || '—';
    const intensity = zhIntensity(row.intensity);
    const confidence = row.confidence == null ? Number.NaN : Number(row.confidence);
    const transcriptStatus = row.transcript_status === 'available'
      ? `同片段 STT 完成（${Number(row.transcript_character_count || 0)} 字）`
      : row.transcript_status === 'no_speech'
        ? '同片段未偵測到語音'
        : '同片段 STT 無法完成（未補入手填文字）';
    const failed = row.status === 'error';
    return `<article class="emotion-result-card${failed ? ' is-error' : ''}">
      <header><b>單次影音擷取</b><span>${escHtml(failed ? '失敗' : (row.status || '完成'))}</span></header>
      <dl>
        <div class="emotion-result-wide"><dt>權威情緒模型</dt><dd>${escHtml(model)}</dd></div>
        <div><dt>主要情緒／強度</dt><dd>${escHtml(`${emotion}${intensity ? `／${intensity}` : ''}`)}</dd></div>
        <div><dt>信心</dt><dd>${Number.isFinite(confidence) ? `${Math.round(confidence * 100)}%` : '—'}</dd></div>
        <div><dt>模型耗時</dt><dd>${Number.isFinite(Number(row.evidence_latency_ms)) ? `${Math.round(Number(row.evidence_latency_ms))}ms` : '—'}</dd></div>
        <div><dt>證據品質</dt><dd>${escHtml(row.quality_skipped ? '品質快篩跳過' : (row.evidence_quality || row.status || '—'))}</dd></div>
        <div class="emotion-result-wide"><dt>同片段 STT 狀態</dt><dd>${escHtml(transcriptStatus)}</dd></div>
        <div class="emotion-result-wide"><dt>表情線索</dt><dd>${escHtml(row.facial || '—')}</dd></div>
        <div class="emotion-result-wide"><dt>聲音線索</dt><dd>${escHtml(row.vocal || '未觀察到')}</dd></div>
        <div class="emotion-result-wide"><dt>${failed ? '失敗原因與復原方式' : '情緒模型分析內容'}</dt><dd>${escHtml(failed ? (row.failure_message || '請檢查模型服務後重試。') : (row.description || '—'))}</dd></div>
        <div class="emotion-result-wide"><dt>情緒觀察解說（不改分類）</dt><dd>${escHtml(row.emotion_observation_explanation || '—')}</dd></div>
      </dl>
    </article>`;
  }).join('');
  setText('emotion-video-result-pair', '單次擷取');
  setText('emotion-video-last-completed', new Date().toLocaleTimeString('zh-TW', { hour12: false }));
  setText('emotion-video-batch-latency', `${Math.round(batchLatencyMs)}ms`);
}

async function runEmotionVideoDetection(generation) {
  if (emotionVideoRunning && generation === emotionVideoGeneration && emotionVideoStream) {
    try {
      setEmotionVideoStatus('正在單次自適應擷取；說完並停頓後會自動送出，最長 8 秒。', 'info', 'fa-video');
      g('emotion-video-capture-badge')?.removeAttribute('hidden');
      const blob = await captureEmotionVideoClip(emotionVideoStream);
      g('emotion-video-capture-badge')?.setAttribute('hidden', '');
      if (!emotionVideoRunning || generation !== emotionVideoGeneration) return;
      if (!blob.size) throw new Error('沒有取得可分析的影像片段');

      setEmotionVideoStatus('同一片段正交由情緒模型與 STT 處理；STT 不接受手填替代文字。', 'info', 'fa-circle-notch fa-spin');
      setText('emotion-video-inflight', '1');
      const formData = new FormData();
      formData.append('media', blob, 'admin_emotion_test.webm');
      emotionVideoAbortController = new AbortController();
      const batchStarted = performance.now();
      const response = await fetch(`${API}/api/emotion/analyze_media_test`, {
        method: 'POST',
        headers: adminHeaders(),
        body: formData,
        signal: emotionVideoAbortController.signal,
      });
      const data = await response.json();
      emotionVideoAbortController = null;
      setText('emotion-video-inflight', '0');
      if (!response.ok) throw new Error(data.message || data.detail || `HTTP ${response.status}`);
      if (data.status === 'disabled') {
        setEmotionVideoStatus('情緒分析尚未啟用，請先到情緒分析頁開啟。', 'error', 'fa-triangle-exclamation');
        stopEmotionVideoDetection({ preserveStatus: true });
        return;
      }
      const batchLatency = performance.now() - batchStarted;
      renderEmotionVideoResult(data, batchLatency);
      if (data.status === 'error') {
        const reason = data.failure_message || '模型沒有產生可用結果。';
        setEmotionVideoStatus(`${reason} 單次診斷已停止。`, 'error', 'fa-triangle-exclamation');
        stopEmotionVideoDetection({ preserveStatus: true });
        return;
      }
      setEmotionVideoStatus('單次診斷完成；原始影音與逐字稿已丟棄，可再次開始新的擷取。', 'info', 'fa-circle-check');
      stopEmotionVideoDetection({ preserveStatus: true });
    } catch (error) {
      emotionVideoAbortController = null;
      setText('emotion-video-inflight', '0');
      g('emotion-video-capture-badge')?.setAttribute('hidden', '');
      if (error?.name === 'AbortError' || generation !== emotionVideoGeneration) return;
      setEmotionVideoStatus(`即時偵測停止：${error.message}`, 'error', 'fa-triangle-exclamation');
      stopEmotionVideoDetection({ preserveStatus: true });
      return;
    }
  }
}

async function startEmotionVideoDetection() {
  if (emotionVideoRunning) return;
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    setEmotionVideoStatus('此瀏覽器不支援攝影機或 MediaRecorder。', 'error', 'fa-triangle-exclamation');
    return;
  }
  try {
    const providerReady = await loadEmotionTestCapabilities();
    if (!providerReady) return;
    setEmotionVideoStatus('正在請求攝影機與麥克風權限…', 'info', 'fa-video');
    emotionVideoStream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 480, max: 640 },
        height: { ideal: 360, max: 480 },
        frameRate: { ideal: 10, max: 15 },
      },
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const video = g('emotion-video');
    if (video) video.srcObject = emotionVideoStream;
    g('emotion-video-preview')?.classList.add('is-active');
    emotionVideoRunning = true;
    emotionVideoGeneration += 1;
    g('emotion-video-start-btn')?.setAttribute('disabled', '');
    g('emotion-video-stop-btn')?.removeAttribute('disabled');
    void runEmotionVideoDetection(emotionVideoGeneration);
  } catch (error) {
    stopEmotionVideoDetection({ preserveStatus: true });
    setEmotionVideoStatus(`無法啟用攝影機或麥克風：${error.message}`, 'error', 'fa-triangle-exclamation');
  }
}

function stopEmotionVideoDetection({ preserveStatus = false } = {}) {
  const wasActive = emotionVideoRunning || Boolean(emotionVideoStream);
  emotionVideoRunning = false;
  emotionVideoGeneration += 1;
  emotionVideoAbortController?.abort();
  emotionVideoAbortController = null;
  if (emotionVideoRecorder?.state && emotionVideoRecorder.state !== 'inactive') {
    emotionVideoRecorder.stop();
  }
  emotionVideoRecorder = null;
  emotionVideoStream?.getTracks().forEach(track => track.stop());
  emotionVideoStream = null;
  const video = g('emotion-video');
  if (video) video.srcObject = null;
  g('emotion-video-preview')?.classList.remove('is-active');
  g('emotion-video-capture-badge')?.setAttribute('hidden', '');
  setText('emotion-video-inflight', '0');
  g('emotion-video-start-btn')?.removeAttribute('disabled');
  g('emotion-video-stop-btn')?.setAttribute('disabled', '');
  if (wasActive && !preserveStatus) setEmotionVideoStatus('擷取已取消，攝影機與麥克風已關閉。', 'info', 'fa-circle-stop');
}

async function loadEmotionLogs() {
  const tbody = g('emotion-logs-tbody');
  if (!tbody) return;
  const EMPTY_CELL = '<span style="color:var(--text2)">—</span>';
  tbody.innerHTML = `<tr><td colspan="8" style="padding:16px;color:var(--text2);text-align:center">載入中…</td></tr>`;
  emotionInfluenceAdmin.renderLoading();
  try {
    const res = await fetch(`${API}/api/emotion/intervention_logs?limit=200`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const logs = (data.logs || []).slice().reverse();
    await loadEmotionAssistanceSummary();
    const emotionView = emotionInfluenceAdmin.render(logs);
    latestEmotionRoundId = String(emotionView.latestRound?.id || '');
    const analysisLogs = logs.filter(r => !['voice_llm_influence', 'assistance_outcome', 'human_evaluation'].includes(r.event_type));
    if (!analysisLogs.length) {
      tbody.innerHTML = `<tr><td colspan="8" style="padding:16px;color:var(--text2);text-align:center">尚無紀錄</td></tr>`;
      return;
    }
    tbody.innerHTML = analysisLogs.map(r => {
      const time  = escHtml(r.timestamp ? r.timestamp.replace('T', ' ').slice(0, 19) : '—');
      // 優先使用後端已計算的 event_type_label，避免前後端 label 不同步
      const evt   = escHtml(r.event_type_label || r.event_type || '—');
      const prov  = r.provider ? escHtml(EMOTION_RUNTIME_LABELS[r.provider] || r.provider) : '—';

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
      const evaluationCell = r.event_id && r.status === 'ok'
        ? `<div style="display:flex;gap:4px"><button class="btn" style="font-size:11px;padding:3px 7px" type="button" onclick="labelEmotionEvent('${escHtml(r.event_id)}','${encodeURIComponent(String(r.emotion || ''))}',true)">符合</button><button class="btn" style="font-size:11px;padding:3px 7px" type="button" onclick="labelEmotionEvent('${escHtml(r.event_id)}','${encodeURIComponent(String(r.emotion || ''))}',false)">修正</button></div>`
        : EMPTY_CELL;

      return `<tr style="border-top:1px solid var(--border)">
        <td style="padding:7px 10px;white-space:nowrap;font-size:12px">${time}</td>
        <td style="padding:7px 10px;white-space:nowrap">${evt}</td>
        <td style="padding:7px 10px;white-space:nowrap;font-size:12px">${prov}</td>
        <td style="padding:7px 10px;white-space:nowrap">${emoCell}</td>
        <td style="padding:7px 10px;max-width:180px;overflow-wrap:break-word;font-size:12px">${facialCell}</td>
        <td style="padding:7px 10px;max-width:160px;overflow-wrap:break-word;font-size:12px">${vocalCell}</td>
        <td style="padding:7px 10px;max-width:240px;overflow-wrap:break-word;font-size:12px">${descCell}</td>
        <td style="padding:7px 10px;white-space:nowrap">${evaluationCell}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    emotionInfluenceAdmin.renderError(e);
    tbody.innerHTML = `<tr><td colspan="8" style="padding:16px;color:var(--danger)">載入失敗：${escHtml(e.message)}</td></tr>`;
  }
}

async function loadEmotionAssistanceSummary() {
  const box = g('emotion-assistance-summary');
  const assessment = g('emotion-assistance-assessment');
  if (!box) return;
  try {
    const response = await fetch(`${API}/api/emotion/assistance_summary`, { headers: adminHeaders() });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    const agreement = data.exact_label_agreement == null
      ? '資料不足'
      : `${Math.round(Number(data.exact_label_agreement) * 100)}%`;
    const treatment = data.groups?.treatment || {};
    const control = data.groups?.control || {};
    const cards = [
      [String(data.annotated_samples || 0), '人工標註', `${data.usable_samples || 0} 筆可用`],
      [agreement, '情緒標籤一致率', '模型標籤 vs 人工觀察'],
      [String(data.shadow_turns || 0), 'Shadow 回合', '只記錄、不影響顧客回覆'],
      [`${treatment.sessions || 0} / ${control.sessions || 0}`, '實驗／對照 session', `完成率 ${Math.round(Number(treatment.checkout_rate || 0) * 100)}% / ${Math.round(Number(control.checkout_rate || 0) * 100)}%`],
    ];
    box.innerHTML = cards.map(([value, label, hint]) => `<article class="emotion-influence-kpi"><b>${escHtml(value)}</b><span>${escHtml(label)}</span><small>${escHtml(hint)}</small></article>`).join('');
    if (assessment) {
      const accuracy = data.accuracy_assessment === 'measured' ? '人工標註樣本已達可評估門檻' : '人工標註不足，暫不能判定偵測準確性';
      const outcome = data.outcome_assessment === 'measured' ? '分流樣本已達可比較門檻' : '實驗／對照樣本不足，暫不能宣稱提升回覆成效';
      assessment.textContent = `${accuracy}；${outcome}。`;
    }
  } catch (error) {
    box.innerHTML = `<div class="emotion-influence-empty error">成效證據載入失敗：${escHtml(error.message)}</div>`;
  }
}

async function labelEmotionEvent(eventId, encodedModelEmotion, matches) {
  const modelEmotion = decodeURIComponent(String(encodedModelEmotion || ''));
  let observedEmotion = modelEmotion;
  if (!matches) {
    observedEmotion = prompt('請輸入人工觀察的情緒標籤（例如 neutral、confused、frustrated）', modelEmotion) || '';
  }
  if (!observedEmotion.trim()) return;
  const response = await fetch(`${API}/api/emotion/human_evaluations`, {
    method: 'POST',
    headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      evidence_event_id: eventId,
      observed_emotion: observedEmotion.trim(),
      usable: true,
      notes: matches ? 'admin_confirmed' : 'admin_corrected',
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(`標註失敗：${data.detail || response.status}`);
    return;
  }
  await loadEmotionAssistanceSummary();
}

async function analyzeEmotionCustomer() {
  const button = g('emotion-customer-analyze-btn');
  const status = g('emotion-customer-analysis-status');
  const result = g('emotion-customer-analysis-result');
  if (!latestEmotionRoundId) {
    if (status) status.textContent = '目前沒有可分析的本輪情緒紀錄。';
    return;
  }
  if (button) button.disabled = true;
  if (result) result.hidden = true;
  if (status) status.textContent = 'LLM 正在分析本輪客戶情況…';
  try {
    const response = await fetch(`${API}/api/emotion/analyze_ordering_round`, {
      method: 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ emotion_round_id: latestEmotionRoundId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`);
    setText('emotion-customer-current-situation', data.current_situation || '—');
    setText('emotion-customer-ordering-need', data.ordering_need || '—');
    setText('emotion-customer-response-focus', data.response_focus || '—');
    setText('emotion-customer-caution', data.caution || '—');
    if (result) result.hidden = false;
    if (status) status.textContent = `分析完成；採用 ${Number(data.evidence_count || 0)} 筆五欄完整情緒證據。`;
  } catch (error) {
    if (status) status.textContent = `客人分析失敗：${error instanceof Error ? error.message : String(error)}`;
  } finally {
    if (button) button.disabled = false;
  }
}

async function clearEmotionLogs() {
  if (!confirm('確定清除所有 R1-Omni 分析紀錄？')) return;
  try {
    const res = await fetch(`${API}/api/emotion/intervention_logs`, { method: 'DELETE', headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    loadEmotionLogs();
  } catch (e) {
    console.error('clearEmotionLogs failed', e);
  }
}

// ── 測試頁：載入預設語音 Prompt ──

async function loadVoicePromptDefault() {
  const ta = g('test-inp-system-prompt');
  if (!ta || ta.value.trim()) return;   // 使用者已手動填寫則不覆蓋
  try {
    const res = await fetch(`${API}/api/diagnostics/voice_prompt`, { headers: adminHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    if (data.prompt) ta.value = data.prompt;
  } catch { /* 靜默失敗 */ }
}

// ── Ollama 模型清單 ──

let _ollamaModels = [];

async function loadOllamaModels() {
  const status = g('test-model-status');
  if (status) status.textContent = '正在讀取 Ollama 模型清單…';
  try {
    const res = await fetch(`${API}/api/ollama/models`, { headers: adminHeaders() });
    if (!res.ok) {
      _ollamaModels = [];
      if (status) status.textContent = llmTestErrorMessage(res.status);
      return;
    }
    const data = await res.json();
    _ollamaModels = Array.isArray(data.models) ? data.models : [];
    if (status) {
      status.textContent = _ollamaModels.length
        ? `已讀取 ${_ollamaModels.length} 個 Ollama 模型。`
        : 'Ollama 已連線，但目前沒有可用模型。';
    }
  } catch {
    _ollamaModels = [];
    if (status) status.textContent = llmTestErrorMessage(0);
  } finally {
    // 更新設定頁 select
    const mainCur  = val('inp-model-name');
    const voiceCur = val('inp-voice-model');
    populateModelSelect('inp-model-name',  _ollamaModels, mainCur  || 'qwen3.5:4b');
    populateModelSelect('inp-voice-model', _ollamaModels, voiceCur || 'qwen3.5:4b');
    // 更新測試頁 select
    const testCur = val('test-inp-model');
    populateModelSelect('test-inp-model', _ollamaModels, testCur || (_ollamaModels[0] || ''));
  }
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

// ── 測試頁：提供者切換 ──

// Diagnostic Provider Override: the half of the provider chain this one prompt will exercise.
// Held here rather than read back out of the DOM, so moving the diagnostic panel to another
// page cannot silently strand the lookup and send every prompt to the local runtime.
let _testProvider = 'ollama';

function onTestProviderChange(btn) {
  _testProvider = btn.dataset.provider;
  btn.closest('.provider-tabs').querySelectorAll('.provider-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  ['ollama', 'nvidia_nim'].forEach(p => {
    g(`test-fields-${p}`)?.classList.toggle('hidden', p !== _testProvider);
  });
}

function getTestProvider() {
  return _testProvider;
}

// Sentinel option that swaps the NIM catalog dropdown for a free-text model id. The typed id
// is a Diagnostic Provider Override: it is sent with this one prompt and never persisted, so
// a model can be tried without first committing it to the settings document.
const TEST_NIM_CUSTOM_MODEL = '__custom__';

function onTestNimModelChange() {
  const custom = g('test-inp-nim-model-custom');
  if (!custom) return;
  custom.hidden = val('test-inp-nim-model') !== TEST_NIM_CUSTOM_MODEL;
  if (!custom.hidden) custom.focus();
}

function getTestModel() {
  const p = getTestProvider();
  if (p !== 'nvidia_nim') return val('test-inp-model') || (_ollamaModels[0] || '');
  const chosen = val('test-inp-nim-model');
  if (chosen === TEST_NIM_CUSTOM_MODEL) return val('test-inp-nim-model-custom');
  return chosen || 'meta/llama-3.1-8b-instruct';
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

  // Sending with an empty custom id would fall back to the configured model server-side, so the
  // reply would come from a model the operator did not ask for — the one thing a diagnostic
  // must never do. Refuse instead, and keep their prompt in the box.
  if (getTestProvider() === 'nvidia_nim' && !getTestModel()) {
    _appendBubble('ai', '❌ 請先輸入要測試的 NIM 模型 ID。');
    g('test-inp-nim-model-custom')?.focus();
    return;
  }

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
    const res = await fetch(`${API}/api/diagnostics/ask`, {
      method: 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, model, system_prompt: systemPrompt, messages: [..._testMessages] }),
    });
    loadingBubble?.remove();
    if (!res.ok) {
      // 400 is the diagnostic rejecting the request parameters; its detail names which one,
      // and the fixed copy ("請稍後再試") would be actively wrong advice for it.
      let detail = '';
      if (res.status === 400) {
        detail = String((await res.json().catch(() => ({})))?.detail || '');
      }
      _appendBubble('ai', `❌ ${detail || llmTestErrorMessage(res.status)}`);
      return;
    }

    let data;
    try {
      data = await res.json();
    } catch {
      _appendBubble('ai', '❌ API 回傳了無法解析的內容，請重新啟動後端後再試。');
      return;
    }

    if (data.error && !data.ai_response) {
      _appendBubble('ai', `❌ 模型執行失敗：${data.error}`);
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
  } catch {
    loadingBubble?.remove();
    _appendBubble('ai', `❌ ${llmTestErrorMessage(0)}`);
  } finally {
    if (sendBtn) sendBtn.disabled = false;
  }
}

// ── expose to inline handlers
window.saveRagSettings = ragAdmin.saveSettings;
window.updateRagStrategyHelp = ragAdmin.updateStrategyHelp;
window.testRagKnowledge = ragAdmin.testKnowledge;
window.saveRagKnowledge = ragAdmin.saveKnowledge;
window.loadRagKnowledge = ragAdmin.loadKnowledge;
window.editRagKnowledge = ragAdmin.editKnowledge;
window.cancelRagKnowledgeEdit = ragAdmin.cancelEdit;
window.retryRagKnowledge = ragAdmin.retryKnowledge;
window.deleteRagKnowledge = ragAdmin.deleteKnowledge;
window.loadRagHealth   = ragAdmin.loadHealth;
window.loadRagAlerts   = ragAdmin.loadAlerts;
window.loadAvailability = loadAvailability;
window.saveAvailability = saveAvailability;
window.saveEmotionSettings        = saveEmotionSettings;
window.analyzeEmotionCustomer     = analyzeEmotionCustomer;
window.startEmotionVideoDetection = startEmotionVideoDetection;
window.stopEmotionVideoDetection  = stopEmotionVideoDetection;
window.clearEmotionLogs           = clearEmotionLogs;
window.labelEmotionEvent          = labelEmotionEvent;
window.updateEmotionPromptCounter = updateEmotionPromptCounter;
window.onTestProviderChange = onTestProviderChange;
window.onTestNimModelChange = onTestNimModelChange;
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
g('emotion-test-provider-refresh')?.addEventListener('click', loadEmotionTestCapabilities);
window.addEventListener('beforeunload', () => stopEmotionVideoDetection({ preserveStatus: true }));

// ── Init ──
document.getElementById('refreshBtn')?.addEventListener('click', loadOperationsOverview);
document.getElementById('clearBtn')?.addEventListener('click', clearStats);
document.getElementById('availabilityRefreshBtn')?.addEventListener('click', loadAvailability);
document.getElementById('availabilitySaveBtn')?.addEventListener('click', saveAvailability);
document.getElementById('availabilitySearch')?.addEventListener('input', renderAvailabilityRows);
document.getElementById('availabilityStatusFilter')?.addEventListener('change', renderAvailabilityRows);
document.getElementById('healthRefreshBtn')?.addEventListener('click', loadAdminHealth);
campaignAdmin.bind();
settingsAdmin.bind();
bindEmotionTabs();
bindLayoutPreference(g);
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
    g('statsOverviewSection')?.toggleAttribute(
      'hidden',
      !hasAdminPermission('operations.read'),
    );
    g('recommendationOverviewSection')?.toggleAttribute('hidden', !hasAdminPermission('recommendations.effectiveness.read'));
    g('clearBtn')?.toggleAttribute('hidden', !hasAdminPermission('operations.write'));
    operationsOverviewAdmin.render();
  },
  onAuthenticated: async () => {
    await loadMenu();
    await loadOperationsOverview();
    if (hasAdminPermission('system.debug')) await loadEmotionTestCapabilities();
  },
}).bind();
// 只在統計頁可見時才自動重整
setInterval(() => {
  const statsPage = document.getElementById('page-stats');
  if (statsPage && statsPage.style.display !== 'none') loadOperationsOverview();
}, 15000);

// ── Admin WebSocket（接收 Kiosk 通知）────────────────────────────
function handleStaffNotify(event) {
  const p = event.payload || {};
  const kiosk = p.kiosk_name || '';

  const kioskEl   = document.getElementById('staffNotifyKiosk');
  const reasonEl  = document.getElementById('staffNotifyReason');
  const backdrop  = document.getElementById('staffNotifyBackdrop');

  if (kioskEl)  kioskEl.textContent  = kiosk;
  if (reasonEl) reasonEl.textContent = '人員協助付款';

  if (backdrop) backdrop.style.display = 'flex';
}

function handleRagAlert(event) {
  ragAdmin.handleAlert(event);
}

window.dismissStaffNotify = function () {
  const backdrop = document.getElementById('staffNotifyBackdrop');
  if (backdrop) backdrop.style.display = 'none';
};

createRealtimeClient('admin', 'admin', {
  staff_notify: handleStaffNotify,
  rag_alert: handleRagAlert,
});
