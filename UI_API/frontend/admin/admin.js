import { createRealtimeClient } from '../shared/realtimeClient.js';
import { createAvailabilityAdmin } from './modules/availabilityAdmin.js';
import { createHealthAdmin } from './modules/healthAdmin.js';
import { createRecommendationEventsAdmin } from './modules/recommendationEventsAdmin.js';
import { createCampaignAdmin } from './modules/campaignAdmin.js';
import { createSettingsAdmin } from './modules/settingsAdmin.js';
import { createMemberServiceDeskAdmin } from './modules/memberServiceDeskAdmin.js';
import { createRagAdmin } from './modules/ragAdmin.js';
import { createOperationsOverviewAdmin } from './modules/operationsOverviewAdmin.js';
import { applyAdminNavigation } from './modules/adminNavigation.js';
import { bindLayoutPreference, initZoom } from './modules/layoutPreference.js';
import { createCatalogClient } from '../shared/api/catalogClient.js';
import {
  createDiagnosticClient,
  createEmotionClient,
  createOperationsClient,
  createProjectBrainClient,
} from '../shared/api/capabilityClients.js';
import { adminHeaders, createAdminAuthController } from './features/auth/adminAuth.js';
import { llmTestErrorMessage } from './features/apiErrors.js';
import {
  classifyEmotionMediaError,
  createEmotionSectionLoader,
  describeEmotionApiError,
} from './modules/emotionConsoleAdmin.js';

const API = window.location.origin;
const adminCatalogClient = createCatalogClient({ baseUrl: API, headers: () => adminHeaders() });
const adminOperationsClient = createOperationsClient({ baseUrl: API, headers: () => adminHeaders() });
const adminEmotionClient = createEmotionClient({ baseUrl: API, headers: () => adminHeaders() });
const adminDiagnosticClient = createDiagnosticClient({ baseUrl: API, headers: () => adminHeaders() });
const adminProjectBrainClient = createProjectBrainClient({ baseUrl: API, headers: () => adminHeaders() });

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
    // Admin reads the catalog through the capability contract, so the item
    // names it shows cannot drift from what the server publishes.
    const { items } = await adminCatalogClient.listItems({ includeRetired: true });
    const nextMenuCache = {};
    items.forEach(item => {
      if (item.id) nextMenuCache[item.id] = item;
    });
    menuCache = nextMenuCache;
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
    if (page === 'stats') loadStatsPage();
    if (page === 'settings') loadSettings();
    if (page === 'recommendations') loadRecommendationEvents();
    if (page === 'promotions') loadCampaigns();
    if (page === 'availability') loadAvailability();
    if (page === 'health') loadAdminHealth();
    if (page === 'rag') ragAdmin.loadPage();
    if (page === 'emotion') { loadEmotionConsole(); }
    if (page === 'members') loadMembers();
    // 模型診斷與即時影音測試已併入功能設定／情緒分析頁，測試頁不再存在。
    if (page === 'settings') { loadOllamaModels(); loadVoicePromptDefault(); }
    if (page !== 'emotion') stopEmotionConsoleTest();
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
    const data = await adminOperationsClient.sessionStats();
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
    const data = await adminOperationsClient.clearSessionStats();
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
function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Admin feature modules ──
const operationsOverviewAdmin = createOperationsOverviewAdmin({
  getElement: g,
  hasPermission: hasAdminPermission,
  loadOverview: () => adminOperationsClient.overview(),
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

function loadRecommendationEvents() { return recommendationEventsAdmin.loadRecommendationEvents(); }
function loadOperationsOverview() { return operationsOverviewAdmin.refresh(); }

/**
 * The stats page carries three independently permissioned sections, so opening
 * it must fill every section the principal is allowed to see — not just the
 * overview.
 */
function loadStatsPage() {
  const tasks = [loadOperationsOverview()];
  if (hasAdminPermission('operations.read')) tasks.push(loadStats());
  if (hasAdminPermission('recommendations.effectiveness.read')) tasks.push(loadRecommendationEvents());
  return Promise.allSettled(tasks);
}

function loadCampaigns() { return campaignAdmin.loadCampaigns(); }
function renderRecommendationDashboard() { return recommendationEventsAdmin.renderRecommendationDashboard(); }
function loadAvailability() { return availabilityAdmin.loadAvailability(); }
function saveAvailability() { return availabilityAdmin.saveAvailability(); }
function renderAvailabilityRows() { return availabilityAdmin.renderAvailabilityRows(); }
function loadAdminHealth() { return healthAdmin.loadAdminHealth(); }
function loadMembers() { return memberServiceDeskAdmin.load(); }

function loadSettings() { return settingsAdmin.load(); }

// ── 情緒分析欄位英→繁對照 ──
const EMOTION_ZH = {
  neutral: "中性", happy: "開心", angry: "生氣", frustrated: "沮喪",
  anxious: "焦慮", confused: "困惑", undetermined: "未判定",
};
const INTENSITY_ZH = { low: "低", medium: "中", high: "高", undetermined: "未判定" };

function zhEmotion(value) {
  if (!value) return "";
  return EMOTION_ZH[String(value).trim().toLowerCase()] || value;
}
function zhIntensity(value) {
  if (!value) return "";
  return INTENSITY_ZH[String(value).trim().toLowerCase()] || value;
}

// ── 測試頁：載入預設語音 Prompt ──

async function loadVoicePromptDefault() {
  const ta = g('test-inp-system-prompt');
  if (!ta || ta.value.trim()) return;   // 使用者已手動填寫則不覆蓋
  try {
    const data = await adminDiagnosticClient.voicePrompt();
    if (data.prompt) ta.value = data.prompt;
  } catch { /* 靜默失敗 */ }
}

// ── Ollama 模型清單 ──

let _ollamaModels = [];

async function loadOllamaModels() {
  const status = g('test-model-status');
  if (status) status.textContent = '正在讀取 Ollama 模型清單…';
  try {
    const data = await adminDiagnosticClient.models();
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
    const data = await adminDiagnosticClient.ask({ provider, model, system_prompt: systemPrompt, messages: [..._testMessages] });
    loadingBubble?.remove();

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

// ── Single-pass emotion console ────────────────────────────────
let emotionConsoleProfiles = null;
let emotionConsoleDefaultPrompt = '';
let emotionConsoleStream = null;
let emotionConsoleRecorder = null;
let emotionConsoleTimer = null;
let emotionConsoleCancelled = false;
let emotionConsoleSelectedProfile = 'r1_omni';

function emotionDuration(id) {
  return Math.max(2, Math.min(30, Number(val(id) || 5)));
}

function selectedEmotionProfile() {
  return emotionConsoleProfiles?.profiles?.find(row => row.id === val('emotion2-model'));
}

function updateEmotionModelState() {
  const profile = selectedEmotionProfile();
  setText(
    'emotion2-model-status',
    profile?.ready
      ? `模型已就緒；能力：${(profile.capabilities || []).join('、')}`
      : (profile?.message || '模型尚未就緒；設定仍可儲存，顧客擷取會自動暫停。'),
  );
  const start = g('emotion2-start');
  if (start && !emotionConsoleRecorder) start.disabled = !profile?.ready;
}

function renderEmotionConsoleProfiles(data) {
  emotionConsoleProfiles = data;
  emotionConsoleDefaultPrompt = String(data.default_prompt || '');
  const select = g('emotion2-model');
  if (select) {
    select.textContent = '';
    (data.profiles || []).forEach(profile => {
      const option = document.createElement('option');
      option.value = profile.id;
      option.textContent = `${profile.label}${profile.ready ? '（就緒）' : '（未就緒）'}`;
      select.appendChild(option);
    });
    const requested = emotionConsoleSelectedProfile || data.default_profile || 'r1_omni';
    select.value = [...select.options].some(option => option.value === requested)
      ? requested
      : (data.default_profile || 'r1_omni');
  }
  updateEmotionModelState();
  if (!val('emotion2-prompt')) setVal('emotion2-prompt', emotionConsoleDefaultPrompt);
}

function renderEmotionConsoleSettings(settings) {
  setVal('emotion2-mode', settings.EMOTION_CAPTURE_MODE || 'off');
  emotionConsoleSelectedProfile = settings.EMOTION_MODEL_PROFILE || 'r1_omni';
  setVal('emotion2-model', emotionConsoleSelectedProfile);
  setVal('emotion2-clip', settings.EMOTION_CLIP_SEC ?? 5);
  updateEmotionModelState();
}

function renderEmotionConsoleRecords(data) {
  const body = g('emotion2-records');
  if (!body) return;
  const rows = data.records || [];
  body.innerHTML = rows.length ? rows.map(row => `<tr style="border-top:1px solid var(--border)">
    <td>${escHtml(fmtDate(row.timestamp))}</td><td>${escHtml(row.event)}</td><td>${escHtml(row.model)}</td>
    <td>${escHtml(zhEmotion(row.emotion))}</td><td>${escHtml(zhIntensity(row.intensity))}</td>
    <td>${escHtml(row.expression)}</td><td>${escHtml(row.voice)}</td><td>${escHtml(row.description)}</td></tr>`).join('')
    : '<tr><td colspan="8">尚無紀錄</td></tr>';
}

function updateEmotionSection(section, state) {
  const status = g(`emotion2-${section}-load-status`);
  const retry = g(`emotion2-${section}-retry`);
  if (retry) retry.hidden = state.status !== 'error';
  if (status) {
    status.classList?.toggle('error', state.status === 'error');
    status.textContent = state.status === 'loading'
      ? '載入中…'
      : state.status === 'error'
        ? state.message
        : '已更新';
  }
  if (state.status !== 'ready') return;
  if (section === 'settings') renderEmotionConsoleSettings(state.data);
  if (section === 'model') renderEmotionConsoleProfiles(state.data);
  if (section === 'records') renderEmotionConsoleRecords(state.data);
}

const emotionSectionLoader = createEmotionSectionLoader({
  requests: {
    settings: () => adminOperationsClient.settings().then(data => data.values || data),
    model: () => adminEmotionClient.profiles(),
    records: () => adminEmotionClient.records(200),
  },
  onState: updateEmotionSection,
});

async function loadEmotionConsole() {
  await emotionSectionLoader.refreshAll();
}

async function saveEmotionConsoleSettings() {
  const mode = val('emotion2-mode') || 'off';
  setText('emotion2-settings-status', '儲存中…');
  try {
    await adminOperationsClient.patchSettings({
      EMOTION_CAPTURE_MODE: mode,
      EMOTION_MODEL_PROFILE: val('emotion2-model') || 'r1_omni',
      EMOTION_CLIP_SEC: emotionDuration('emotion2-clip'),
    });
    setText('emotion2-settings-status', '設定已儲存；模型未就緒時顧客擷取會自動暫停。');
  } catch (error) {
    setText('emotion2-settings-status', `儲存失敗：${describeEmotionApiError(error)}`);
  }
}

function resetEmotionConsolePrompt() {
  setVal('emotion2-prompt', emotionConsoleDefaultPrompt);
}

function renderEmotionConsoleResult(data) {
  const record = { ...(data?.record || data || {}), emotion: data?.emotion || data?.record?.emotion };
  document.querySelectorAll('[data-emotion-field]').forEach(node => {
    const key = node.dataset.emotionField;
    node.textContent = record[key] || '—';
  });
}

async function submitEmotionConsoleClip(blob) {
  if (!blob?.size) throw Object.assign(new Error('empty media'), { name: 'EmptyMediaError' });
  const form = new FormData();
  form.append('media', blob, 'admin_emotion_test.webm');
  form.append('model_profile', val('emotion2-model') || 'r1_omni');
  form.append('prompt', val('emotion2-prompt'));
  const data = await adminEmotionClient.analyzeMediaTest(form);
  renderEmotionConsoleResult(data);
  setText(
    'emotion2-test-status',
    data.status === 'ok'
      ? '分析完成。原始影音已刪除。'
      // The reason alone ("analysis_failed") tells an operator nothing; the
      // detail names which part of the provider path actually broke.
      : `分析未完成：${data.reason || '服務拒絕'}${data.detail ? `（${data.detail}）` : ''}`,
  );
  await emotionSectionLoader.refresh('records');
}

async function startEmotionConsoleTest() {
  if (emotionConsoleRecorder) return;
  const profile = emotionConsoleProfiles?.profiles?.find(row => row.id === val('emotion2-model'));
  if (!profile?.ready) {
    setText('emotion2-test-status', '選定模型尚未就緒，無法測試。');
    return;
  }
  emotionConsoleCancelled = false;
  try {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      throw Object.assign(new Error('unsupported recorder'), { name: 'NotSupportedError', source: 'recorder' });
    }
    let cameraStream;
    let microphoneStream;
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      if (!cameraStream.getVideoTracks().length) throw Object.assign(new Error('camera not found'), { name: 'NotFoundError' });
    } catch (error) {
      throw Object.assign(error, { source: 'camera' });
    }
    try {
      microphoneStream = await navigator.mediaDevices.getUserMedia({ video: false, audio: true });
      if (!microphoneStream.getAudioTracks().length) throw Object.assign(new Error('microphone not found'), { name: 'NotFoundError' });
    } catch (error) {
      cameraStream.getTracks().forEach(track => track.stop());
      throw Object.assign(error, { source: 'microphone' });
    }
    emotionConsoleStream = new MediaStream([...cameraStream.getTracks(), ...microphoneStream.getTracks()]);
    g('emotion2-video').srcObject = emotionConsoleStream;
    const chunks = [];
    const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp8,opus') ? 'video/webm;codecs=vp8,opus' : 'video/webm';
    if (!MediaRecorder.isTypeSupported(mimeType)) throw Object.assign(new Error('unsupported recorder'), { name: 'NotSupportedError', source: 'recorder' });
    emotionConsoleRecorder = new MediaRecorder(emotionConsoleStream, { mimeType });
    emotionConsoleRecorder.ondataavailable = event => { if (event.data?.size) chunks.push(event.data); };
    emotionConsoleRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: 'video/webm' });
      emotionConsoleStream?.getTracks().forEach(track => track.stop());
      emotionConsoleStream = null;
      emotionConsoleRecorder = null;
      g('emotion2-video').srcObject = null;
      updateEmotionModelState();
      g('emotion2-cancel').disabled = true;
      if (!emotionConsoleCancelled) {
        try {
          setText('emotion2-test-status', '正在分析影音…');
          await submitEmotionConsoleClip(blob);
        } catch (error) {
          setText(
            'emotion2-test-status',
            error?.name === 'EmptyMediaError'
              ? classifyEmotionMediaError(error, 'media')
              : `分析未完成：${describeEmotionApiError(error)}`,
          );
        }
      }
    };
    emotionConsoleRecorder.start(500);
    g('emotion2-start').disabled = true;
    g('emotion2-cancel').disabled = false;
    const seconds = emotionDuration('emotion2-duration');
    setText('emotion2-test-status', `錄製中，${seconds} 秒後自動送出…`);
    emotionConsoleTimer = setTimeout(() => emotionConsoleRecorder?.stop(), seconds * 1000);
  } catch (error) {
    setText('emotion2-test-status', classifyEmotionMediaError(error, error?.source || 'media'));
    stopEmotionConsoleTest();
  }
}

function stopEmotionConsoleTest() {
  clearTimeout(emotionConsoleTimer);
  emotionConsoleTimer = null;
  emotionConsoleCancelled = true;
  if (emotionConsoleRecorder?.state && emotionConsoleRecorder.state !== 'inactive') emotionConsoleRecorder.stop();
  emotionConsoleStream?.getTracks().forEach(track => track.stop());
  emotionConsoleStream = null;
  const video = g('emotion2-video');
  if (video) video.srcObject = null;
  if (!emotionConsoleRecorder) {
    const start = g('emotion2-start');
    const cancel = g('emotion2-cancel');
    if (start) start.disabled = !selectedEmotionProfile()?.ready;
    if (cancel) cancel.disabled = true;
  }
}

async function loadEmotionConsoleRecords() {
  await emotionSectionLoader.refresh('records');
}

async function clearEmotionConsoleRecords() {
  if (!confirm('確定清除目前的情緒分析紀錄？')) return;
  try {
    await adminEmotionClient.clearRecords();
    await loadEmotionConsoleRecords();
  } catch (error) {
    updateEmotionSection('records', { status: 'error', message: describeEmotionApiError(error) });
  }
}

g('emotion2-model')?.addEventListener('change', () => {
  emotionConsoleSelectedProfile = val('emotion2-model');
  updateEmotionModelState();
});
['settings', 'model', 'records'].forEach(section => {
  g(`emotion2-${section}-retry`)?.addEventListener('click', () => emotionSectionLoader.refresh(section));
});

// The report is now the sidecar's structured result: findings and the evidence
// they cite. Model reasoning and CLI output are never persisted (ADR-0038), so
// there is no prose blob to render — and a stale report says so, because a
// failed rescan that still looks current is the failure nobody notices.
function renderProjectBrainReport(report) {
  const target = g('projectBrainReport');
  if (!target) return;
  if (!report) { target.textContent = '尚無報告；按「重新分析專案」才會建立。'; return; }

  const result = report.result || {};
  const stale = report.status === 'stale'
    ? `⚠ 這份報告已過期（${fmtDate(report.stale_since)}）：${report.stale_reason || '重新分析失敗'}\n\n`
    : '';
  const findings = (result.findings || []).length
    ? (result.findings || []).map(finding => {
        const cited = (finding.evidence_paths || []).join('、');
        return `[${finding.severity}] ${finding.title}${finding.detail ? `\n  ${finding.detail}` : ''}${cited ? `\n  依據：${cited}` : ''}`;
      }).join('\n\n')
    : '—';

  target.textContent =
    `${stale}時間：${fmtDate(report.recorded_at)}\n分析設定檔：${result.profile || '—'}\n版本：${result.git_revision || '—'}\n\n${findings}`;
}

async function loadProjectBrain() {
  let data;
  try { data = await adminProjectBrainClient.status(); }
  catch (error) { setText('projectBrainModelStatus', `讀取失敗（${error.status || 0}）`); return; }
  const select = g('projectBrainModel');
  const profiles = data.models || [];
  if (select) {
    const previous = select.value;
    select.textContent = '';
    // Only ready profiles are selectable, and no profile is ever chosen for the
    // operator: an analysis names the provider that produced it (ADR-0037).
    profiles.filter(profile => profile.ready).forEach(profile => {
      const option = document.createElement('option');
      option.value = profile.id;
      option.textContent = `${profile.id}${profile.version ? ` ${profile.version}` : ''}`;
      select.appendChild(option);
    });
    if (previous && [...select.options].some(option => option.value === previous)) select.value = previous;
  }

  const ready = profiles.filter(profile => profile.ready);
  // An unready profile is shown with its reason rather than hidden. An empty
  // selector tells an operator nothing; `credential_missing` tells them what to do.
  const blocked = profiles.filter(profile => !profile.ready)
    .map(profile => `${profile.id || '未知'}：${profile.reason || '未就緒'}`).join('；');
  setText(
    'projectBrainModelStatus',
    ready.length
      ? `就緒設定檔 ${ready.length} 個；不會自動切換。${blocked ? ` 未就緒 — ${blocked}` : ''}`
      : `目前沒有就緒的分析設定檔。${blocked ? ` 原因 — ${blocked}` : ''}`,
  );
  renderProjectBrainReport(data.latest);
}

async function analyzeProjectBrain() {
  const button = g('projectBrainAnalyze');
  if (button) button.disabled = true;
  setText('projectBrainReport', '正在建立唯讀快照並分析…');
  try {
    const data = await adminProjectBrainClient.analyze(val('projectBrainModel'));
    renderProjectBrainReport(data);
  } catch (error) {
    setText('projectBrainReport', `分析失敗：${error.message}`);
    // A failed rescan leaves the previous report in place and marked stale, so
    // reload rather than leaving the surface showing only the error.
    loadProjectBrain().catch(() => {});
  }
  finally { if (button) button.disabled = false; }
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
window.loadAvailability = loadAvailability;
window.saveAvailability = saveAvailability;
window.loadEmotionConsole = loadEmotionConsole;
window.saveEmotionConsoleSettings = saveEmotionConsoleSettings;
window.resetEmotionConsolePrompt = resetEmotionConsolePrompt;
window.startEmotionConsoleTest = startEmotionConsoleTest;
window.stopEmotionConsoleTest = stopEmotionConsoleTest;
window.clearEmotionConsoleRecords = clearEmotionConsoleRecords;
window.loadProjectBrain = loadProjectBrain;
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
window.addEventListener('beforeunload', stopEmotionConsoleTest);

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
g('projectBrainAnalyze')?.addEventListener('click', analyzeProjectBrain);
g('projectBrainRefresh')?.addEventListener('click', loadProjectBrain);
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
    await loadStatsPage();
    if (hasAdminPermission('system.debug')) await emotionSectionLoader.refresh('model');
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

window.dismissStaffNotify = function () {
  const backdrop = document.getElementById('staffNotifyBackdrop');
  if (backdrop) backdrop.style.display = 'none';
};

createRealtimeClient('admin', 'admin', {
  staff_notify: handleStaffNotify,
});
