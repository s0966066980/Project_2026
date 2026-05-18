import * as api from './api.js?v=intervention-dashboard-20260518';
import { API_BASE } from './api.js?v=intervention-dashboard-20260518';
import {
  ui,
  escapeHTML,
  switchMainView as switchMainViewUI,
  switchAdminTab as switchAdminTabUI,
  updateEmotionCameraPanel as updateEmotionCameraPanelUI,
  updateEmotionDetectionOverlay as updateEmotionDetectionOverlayUI
} from './ui.js?v=intervention-dashboard-20260518';
import {
  ensureMediaTracks as ensureMediaTracksCore,
  createVideoRecorder,
  createAudioRecorder,
  captureVideoFrameBlob
} from './media.js?v=intervention-dashboard-20260518';
import { createCartManager } from './cart.js?v=intervention-dashboard-20260518';
import { createRecommendationManager } from './recommendation.js?v=intervention-dashboard-20260518';

// =========================================================
// Controller 狀態
// =========================================================

const sessionId = 'pos_' + Math.random().toString(36).substr(2, 9);
let stream, askRecorder;
let serviceRecorder = null;
let serviceChunks = [];
let adminServiceRecorder = null;
let adminServiceChunks = [];
let adminServiceOllamaDirect = true;
let isSystemRunning = false;
let orderCompleted = false;
let menuData = [];
let sessionPushedIds = new Set();
let sessionPushedVariants = { A: new Set(), B: new Set(), single: new Set() };
let recommendPending = false;
let voiceBubbleTimer = null;
let emotionCardTimer = null;
let emotionLoopId = null;
let detectionLoopId = null;
let detectionInFlight = false;
let recommendLoopId = null;
let lastVoiceText = '';
let lastEmotionStructured = null;
let lastMediaSignals = {};
let promotionPausedUntil = 0;
let barrierCheckInFlight = false;
let lastBarrierCheckAt = 0;
let interactionModalTimer = null;
let pageDwellTimer = null;
const interactionState = {
  pageId: 'startup',
  pageEnteredAt: Date.now(),
  lastActivityAt: Date.now(),
  backCount: 0,
  invalidTouchCount: 0,
  paymentFailCount: 0,
  couponErrorCount: 0,
  cartEditCount: 0,
  lastReportedDwellPage: '',
};
let runtimeSettings = {
  PERFORMANCE_MODE: 'balanced',
  EMOTION_PING_INTERVAL_SEC: 15,
  EMOTION_RECORD_MS: 900,
  YOLO_FRAME_INTERVAL_MS: 650,
  RECOMMEND_INTERVAL_SEC: 30,
  RECOMMEND_AFTER_ASK_DELAY_MS: 1200,
  AUTO_RECOMMEND_MIN_GAP_SEC: 20,
  OLLAMA_NUM_PREDICT: 220,
  RAG_TOP_K: 3,
  AB_SINGLE_CALL: true,
  ENABLE_TTS_CACHE: true,
  ENABLE_RECOMMEND_CACHE: true
};

function perfValue(key) {
  return runtimeSettings[key];
}

async function loadRuntimeSettings() {
  try {
    runtimeSettings = { ...runtimeSettings, ...await api.getSettings() };
  } catch { }
}

function restartLoops() {
  if (emotionLoopId) clearInterval(emotionLoopId);
  if (detectionLoopId) clearInterval(detectionLoopId);
  if (recommendLoopId) clearInterval(recommendLoopId);
  emotionLoopId = null;
  detectionLoopId = null;
  recommendLoopId = null;
  if (isSystemRunning) {
    startEmotionLoop();
    startDetectionLoop();
    startRecommendLoop();
  }
}

// =========================================================
// 功能模組狀態
// =========================================================
const FEAT_DEFAULTS = { emotion: true, voiceAsk: false, recommend: true, emotionBackend: true, emotionChat: false, emotionCamera: false, abTest: false, multiLang: true };

function getFeatures() {
  try { return { ...FEAT_DEFAULTS, ...JSON.parse(localStorage.getItem('kiosk_feat') || '{}') }; }
  catch { return { ...FEAT_DEFAULTS }; }
}
function saveFeatures(f) { localStorage.setItem('kiosk_feat', JSON.stringify(f)); }

function toggleFeature(key, el) {
  const f = getFeatures();
  f[key] = !f[key];
  saveFeatures(f);
  el.classList.toggle('on', f[key]);
  if (key === 'voiceAsk' && !f.voiceAsk && askRecorder?.state === 'recording') askRecorder.stop();
  applyFeaturesToPOS();
  if (isSystemRunning && (key === 'voiceAsk' || key === 'emotion' || key === 'emotionBackend' || key === 'emotionCamera')) {
    ensureMediaTracks({
      video: f.emotion || f.emotionBackend || f.emotionCamera,
      audio: true
    }).then(ok => {
      if (ok) setupAskRecorder();
      if (ok) {
        updateEmotionCameraPanel();
        if (key === 'emotionBackend' && f.emotionBackend) startEmotionLoop();
        if (key === 'emotionCamera' && f.emotionCamera) startDetectionLoop();
      }
    });
  }
  if (key === 'abTest') clearAllPushCards();
}

function applyFeaturesToPOS() {
  const f = getFeatures();
  const center = document.getElementById('centerPanel');
  // 攝影機作為背景感測來源保留，不在 POS 版面中顯示欄位
  const cam = document.getElementById('mod-camera');
  if (cam) cam.style.display = 'none';
  // 語音按鈕
  const voice = document.getElementById('mod-voice');
  if (voice) voice.style.display = '';
  // 感測區永遠不佔版面，避免功能關閉後留下空白 UI 欄位
  if (center) center.style.display = 'none';
  // 語音回覆氣泡（關閉語音模組時隱藏）
  if (!f.voiceAsk) closeVoiceBubble();
  // 推播（關閉時清除現有浮動卡）
  if (!f.recommend) clearAllPushCards();
  if (!f.emotionChat) clearEmotionCards();
  if (!f.emotionCamera && detectionLoopId) {
    clearInterval(detectionLoopId);
    detectionLoopId = null;
  }
  updateEmotionCameraPanel();
}

function isPosActive() {
  return isSystemRunning && !orderCompleted && ui.posView && !ui.posView.classList.contains('hidden');
}

function clearPOSFloatingUI() {
  clearAllPushCards();
  clearEmotionCards();
  closeVoiceBubble();
  if (ui.emotionCameraPanel) ui.emotionCameraPanel.classList.add('hidden');
  if (ui.serviceWindow) ui.serviceWindow.classList.remove('open');
}

function initAdminToggles() {
  const f = getFeatures();
  Object.keys(FEAT_DEFAULTS).forEach(key => {
    const el = document.getElementById('tog-' + key);
    if (el) el.classList.toggle('on', f[key]);
  });
}

function updateEmotionCameraPanel() {
  updateEmotionCameraPanelUI({ features: getFeatures(), isPosActive: isPosActive(), stream });
}

function updateEmotionDetectionOverlay(personCheck = {}) {
  updateEmotionDetectionOverlayUI(personCheck, { features: getFeatures(), isPosActive: isPosActive(), stream });
}

function switchMainView(view) {
  switchMainViewUI(view, { clearPOSFloatingUI, loadAdminData, initAdminToggles, applyFeaturesToPOS, loadMenu });
  setInteractionPage(view === 'admin' ? 'admin_page' : 'menu_page', { source: 'switch_main_view' });
}

function switchAdminTab(id) {
  switchAdminTabUI(id, { loadEmotionClips });
}

function findMenuItems(ids = []) {
  return ids
    .map(id => String(id || '').replace(/[^a-zA-Z0-9]/g, ''))
    .map(cleanId => menuData.find(m => m.id === cleanId || m.id.includes(cleanId)))
    .filter(Boolean);
}

const cartManager = createCartManager({ ui, escapeHTML, findMenuItems });

function trackedAddToCart(item, metadata = {}) {
  cartManager.addToCart(item);
  trackInteractionEvent({
    event_type: 'cart_edit',
    button_id: item?.id ? `menu_${item.id}` : 'add_to_cart',
    cart_edit_count: 1,
    metadata: { action: 'add', item_id: item?.id || '', ...metadata }
  });
}

function trackedUpdateCartQty(id, delta) {
  cartManager.updateCartQty(id, delta);
  trackInteractionEvent({
    event_type: 'cart_edit',
    button_id: `cart_qty_${id}`,
    cart_edit_count: 1,
    metadata: { action: 'qty', item_id: id, delta }
  });
}

function trackedDeleteCartItem(id) {
  cartManager.deleteCartItem(id);
  trackInteractionEvent({
    event_type: 'cart_edit',
    button_id: `cart_delete_${id}`,
    cart_edit_count: 1,
    metadata: { action: 'delete', item_id: id }
  });
}

const recommendationManager = createRecommendationManager({
  ui,
  escapeHTML,
  isPosActive,
  getFeatures,
  findMenuItems,
  addToCart: item => trackedAddToCart(item, { source: 'recommendation' }),
  sessionPushedIds,
  sessionPushedVariants
});

const {
  clearAllPushCards,
  displayRecommendation,
  showPushNotice
} = recommendationManager;

// =========================================================
// 菜單
// =========================================================
async function loadMenu() {
  try {
    menuData = await api.getMenu();
  } catch {
    menuData = [
      { id: 'M01', name: '測試餐點一號', price: 100, description: '後端未連線，這是預設測試資料。' },
      { id: 'M02', name: '測試餐點二號', price: 150, description: '請確認 http://127.0.0.1:8000 已啟動。' }
    ];
  }
  renderMenu();
}

function renderMenu() {
  ui.menuGrid.innerHTML = '';
  menuData.forEach(item => {
    const visual = getMenuVisual(item);
    const prepMinutes = item.prep_time_minutes || item.prep_minutes || '';
    const d = document.createElement('div');
    d.id = `menu-${item.id}`;
    d.className = 'menu-card min-h-[252px]';
    d.onclick = () => trackedAddToCart(item, { source: 'menu_card' });
    d.innerHTML = `
      <div class="menu-photo">
        <img src="${visual.image}" alt="${escapeHTML(item.name)}" onerror="this.style.display='none';this.nextElementSibling.style.display='block'">
        <span class="menu-photo-fallback">${visual.emoji}</span>
      </div>
      <div class="min-w-0 flex flex-col h-full justify-between">
        <div>
          <span class="menu-tag mb-5"><i class="${visual.icon}"></i>${visual.tag}</span>
          <h3 class="font-extrabold text-2xl leading-snug mb-3" style="color:var(--text)">${escapeHTML(item.name)}</h3>
          <p class="text-base leading-relaxed line-clamp-3" style="color:var(--text2)">${escapeHTML(item.description)}</p>
          ${prepMinutes ? `<p class="text-sm mt-3 font-semibold" style="color:var(--accent2)"><i class="fas fa-clock mr-1"></i>約 ${escapeHTML(prepMinutes)} 分鐘</p>` : ''}
        </div>
        <div class="flex items-center justify-between mt-5">
          <span class="menu-price">$${escapeHTML(item.price)}</span>
          <button class="menu-add flex items-center justify-center" type="button" aria-label="加入購物車">
            <i class="fas fa-plus"></i>
          </button>
        </div>
      </div>`;
    ui.menuGrid.appendChild(d);
  });
}

// =========================================================
// POS 互動障礙事件追蹤
// =========================================================
function currentPageId() {
  if (ui.adminView && !ui.adminView.classList.contains('hidden')) return 'admin_page';
  if (orderCompleted) return 'completed_page';
  if (ui.orderConfirmModal && !ui.orderConfirmModal.classList.contains('hidden')) return 'payment_page';
  if (ui.posView && !ui.posView.classList.contains('hidden')) return 'menu_page';
  return interactionState.pageId || 'unknown';
}

function getDwellTimeSec() {
  return Math.max(0, Math.round((Date.now() - interactionState.pageEnteredAt) / 1000));
}

function getIdleTimeSec() {
  return Math.max(0, Math.round((Date.now() - interactionState.lastActivityAt) / 1000));
}

function buildUIContext(extra = {}) {
  return {
    page_id: currentPageId(),
    cart_count: cartManager.getCartIds().length,
    cart_total: cartManager.getCartTotal(),
    voice_ask_enabled: Boolean(getFeatures().voiceAsk),
    recommend_enabled: Boolean(getFeatures().recommend),
    promotion_paused: Date.now() < promotionPausedUntil,
    service_open: Boolean(ui.serviceWindow?.classList.contains('open')),
    ...extra,
  };
}

function setInteractionPage(pageId, metadata = {}) {
  const nextPage = pageId || currentPageId();
  if (interactionState.pageId === nextPage) return;
  interactionState.pageId = nextPage;
  interactionState.pageEnteredAt = Date.now();
  interactionState.lastReportedDwellPage = '';
  if (nextPage === 'menu_page') {
    trackInteractionEvent({ event_type: 'enter_menu_page', button_id: 'startSystemBtn', metadata });
  }
}

function normalizeInteractionPayload(event = {}) {
  const metadata = event.metadata && typeof event.metadata === 'object' ? event.metadata : {};
  return {
    session_id: sessionId,
    page_id: event.page_id || currentPageId(),
    event_type: event.event_type || 'unknown',
    button_id: event.button_id || '',
    dwell_time_sec: Number(event.dwell_time_sec ?? getDwellTimeSec()) || 0,
    back_count: Number(event.back_count ?? interactionState.backCount) || 0,
    invalid_touch_count: Number(event.invalid_touch_count ?? interactionState.invalidTouchCount) || 0,
    payment_fail_count: Number(event.payment_fail_count ?? interactionState.paymentFailCount) || 0,
    coupon_error_count: Number(event.coupon_error_count ?? interactionState.couponErrorCount) || 0,
    cart_edit_count: Number(event.cart_edit_count ?? interactionState.cartEditCount) || 0,
    idle_time_sec: Number(event.idle_time_sec ?? getIdleTimeSec()) || 0,
    metadata,
    ui_context: buildUIContext(metadata.ui_context || {}),
  };
}

function applyIntervention(intervention = {}, barrierResult = {}) {
  if (!intervention || intervention.action === 'none') return;
  console.log('[interaction intervention]', { intervention, barrierResult });

  if (intervention.ui_patch?.disable_promotion) {
    promotionPausedUntil = Date.now() + 45000;
    clearAllPushCards();
  }

  if (intervention.staff_notify) {
    showPushNotice('建議店員協助');
  }

  const modalName = intervention.ui_patch?.show_modal || '';
  if (!modalName) return;
  let box = document.getElementById('interactionInterventionBox');
  if (!box) {
    box = document.createElement('div');
    box.id = 'interactionInterventionBox';
    box.style.cssText = [
      'position:fixed',
      'left:24px',
      'bottom:24px',
      'z-index:80',
      'max-width:360px',
      'background:var(--surface)',
      'border:1.5px solid var(--border)',
      'box-shadow:var(--shadow)',
      'border-radius:16px',
      'padding:18px',
      'color:var(--text)'
    ].join(';');
    document.body.appendChild(box);
  }
  const titleMap = {
    payment_guide: '付款協助',
    coupon_guide: '優惠券協助',
    operation_hint: '操作協助',
  };
  box.innerHTML = `
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-sm font-bold mb-1" style="color:var(--accent2)">${escapeHTML(titleMap[modalName] || '操作提示')}</p>
        <p class="text-sm leading-relaxed">${escapeHTML(intervention.tts_text || intervention.reason || '需要協助時可通知店員。')}</p>
        ${intervention.staff_notify ? '<p class="text-xs mt-2 font-bold" style="color:var(--danger)">建議店員協助</p>' : ''}
      </div>
      <button type="button" data-close-intervention style="color:var(--text2)"><i class="fas fa-times"></i></button>
    </div>`;
  box.querySelector('[data-close-intervention]').onclick = () => box.remove();
  if (interactionModalTimer) clearTimeout(interactionModalTimer);
  interactionModalTimer = setTimeout(() => box.remove(), 10000);
}

async function maybeCheckBarrierState(riskResult = {}) {
  if (!riskResult.triggered || barrierCheckInFlight) return;
  if (Date.now() - lastBarrierCheckAt < 10000) return;
  barrierCheckInFlight = true;
  lastBarrierCheckAt = Date.now();
  try {
    const data = await api.barrierState({
      session_id: sessionId,
      speech_text: lastVoiceText,
      emotion_structured: lastEmotionStructured || {},
      ui_context: buildUIContext(),
      media_signals: lastMediaSignals || {},
    });
    if (data.status === 'success') {
      applyIntervention(data.intervention, data.barrier_result);
    }
  } catch (err) {
    console.warn('[interaction barrier_state failed]', err);
  } finally {
    barrierCheckInFlight = false;
  }
}

async function reportInteractionEvent(payload) {
  try {
    const response = await api.reportInteractionEvent(payload);
    if (response?.risk_result?.triggered) {
      await maybeCheckBarrierState(response.risk_result);
    }
    return response;
  } catch (err) {
    console.warn('[interaction_event failed]', err);
    return null;
  }
}

function trackInteractionEvent(event = {}) {
  interactionState.lastActivityAt = Date.now();
  if (event.event_type === 'back_navigation') interactionState.backCount += 1;
  if (event.event_type === 'invalid_touch') interactionState.invalidTouchCount += 1;
  if (event.event_type === 'payment_failed') interactionState.paymentFailCount += 1;
  if (event.event_type === 'checkout_error') interactionState.paymentFailCount += 1;
  if (event.event_type === 'coupon_error') interactionState.couponErrorCount += 1;
  if (event.event_type === 'cart_edit') interactionState.cartEditCount += 1;
  const payload = normalizeInteractionPayload(event);
  reportInteractionEvent(payload);
}

function startPageDwellWatcher() {
  if (pageDwellTimer) clearInterval(pageDwellTimer);
  pageDwellTimer = setInterval(() => {
    if (!isSystemRunning || !isPosActive()) return;
    const pageId = currentPageId();
    if (pageId !== interactionState.pageId) setInteractionPage(pageId);
    if (getDwellTimeSec() > 30 && interactionState.lastReportedDwellPage !== pageId) {
      interactionState.lastReportedDwellPage = pageId;
      trackInteractionEvent({
        event_type: 'page_dwell_timeout',
        button_id: 'page_timer',
        dwell_time_sec: getDwellTimeSec(),
        metadata: { reason: 'same_page_over_30_sec' }
      });
    }
  }, 5000);
}

function getMenuVisual(item) {
  const id = String(item.id || '').toUpperCase();
  const presets = {
    M01: { tag: '人氣推薦', icon: 'fas fa-fire', emoji: '🍗' },
    M02: { tag: '招牌必點', icon: 'fas fa-star', emoji: '🍤' },
    M03: { tag: '清爽首選', icon: 'fas fa-leaf', emoji: '🥗' },
    M04: { tag: '飲品推薦', icon: 'fas fa-mug-hot', emoji: '☕' }
  };
  const fallback = { tag: '精選餐點', icon: 'fas fa-utensils', emoji: '🍽️' };
  const visual = presets[id] || fallback;
  return { ...visual, image: `/static/menu_${id}.png` };
}

// =========================================================
// 情緒格式化
// =========================================================
function formatEmotion(t) {
  if (!t) return "分析中";
  const map = [["未偵測到顧客", "未偵測到顧客"], ["沒有明確人臉", "未偵測到顧客"],
  ["平靜", "平靜"], ["開心", "開心"], ["微笑", "開心"], ["疲憊", "疲憊"],
  ["累", "疲憊"], ["猶豫", "猶豫"], ["思考", "猶豫"], ["困惑", "困惑"],
  ["焦躁", "焦躁"], ["驚訝", "驚訝"], ["生氣", "生氣"], ["憤怒", "生氣"],
  ["難過", "難過"], ["悲傷", "難過"], ["無法判斷", "無法判斷"]];
  for (const [k, v] of map) if (t.includes(k)) return v;
  return t.length > 12 ? t.slice(0, 12) + '...' : t;
}

async function ensureMediaTracks({ video = false, audio = false } = {}) {
  try {
    stream = await ensureMediaTracksCore(stream, ui, { video, audio });
    return true;
  } catch {
    alert("無法取得需要的攝影機或麥克風權限。");
    return false;
  }
}

// =========================================================
// 啟動
// =========================================================
ui.startBtn.onclick = async () => {
  try {
    await loadRuntimeSettings();
    const f = getFeatures();
    const needVideo = f.emotion || f.emotionBackend || f.emotionCamera;
    const needAudio = true;
    const mediaReady = await ensureMediaTracks({ video: needVideo, audio: needAudio });
    if (!mediaReady && (needVideo || needAudio)) return;
    await loadMenu();
    applyFeaturesToPOS();
    ui.serviceFab.style.display = 'flex';
    ui.overlay.style.opacity = '0';
    setTimeout(() => { ui.overlay.classList.add('hidden'); }, 500);
    isSystemRunning = true;
    updateEmotionCameraPanel();
    startPageDwellWatcher();
    setInteractionPage('menu_page', { source: 'start_system' });
    startEmotionLoop();
    startDetectionLoop();
    startRecommendLoop();
    setupAskRecorder();
  } catch { alert("無法存取攝影機與麥克風。"); }
};

function startDetectionLoop() {
  if (detectionLoopId) return;
  detectionLoopId = setInterval(captureDetectionFrame, Math.max(250, Number(perfValue('YOLO_FRAME_INTERVAL_MS')) || 650));
}

function captureDetectionFrame() {
  const f = getFeatures();
  if (!isPosActive() || !f.emotionCamera) return;
  if (document.hidden || detectionInFlight) return;
  const video = ui.emotionCameraVideo || ui.webcam;
  detectionInFlight = true;
  captureVideoFrameBlob(video).then(async blob => {
    if (!blob) {
      detectionInFlight = false;
      return;
    }
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('frame', blob, 'frame.jpg');
    try {
      const data = await api.detectPersonFrame(fd);
      if (data.status === 'success' && data.person_check) updateEmotionDetectionOverlay(data.person_check);
    } catch { }
    finally {
      detectionInFlight = false;
    }
  });
}

// =========================================================
// 情緒 Loop
// =========================================================
function startEmotionLoop() {
  if (emotionLoopId) return;
  emotionLoopId = setInterval(() => {
    const f = getFeatures();
    if (!isPosActive() || !f.emotionBackend) return;
    if (document.hidden) return;
    if (!stream || !stream.getVideoTracks().length) return;
    const rec = createVideoRecorder(stream);
    let chunks = [];
    rec.ondataavailable = e => chunks.push(e.data);
    rec.onstop = async () => {
      ui.pingInd.style.opacity = '1';
      const fd = new FormData();
      fd.append('session_id', sessionId);
      fd.append('video', new Blob(chunks, { type: 'video/webm' }));
      try {
        const d = await api.pingState(fd);
        if (d.person_check) updateEmotionDetectionOverlay(d.person_check);
        if ((d.status === 'success' || d.status === 'not_executed') && d.emotion) {
          lastEmotionStructured = d.emotion_structured || d;
          lastMediaSignals = d.media_signals || d.emotion_structured?.media_signals || lastMediaSignals || {};
          ui.emotionBadge.classList.remove('hidden');
          ui.emotionText.textContent = formatEmotion(d.emotion);
          showEmotionCard(d.emotion_structured || d);
        }
      } catch { }
      setTimeout(() => ui.pingInd.style.opacity = '0', 600);
    };
    rec.start();
    setTimeout(() => { if (rec.state === 'recording') rec.stop(); }, Number(perfValue('EMOTION_RECORD_MS')) || 900);
  }, Math.max(5, Number(perfValue('EMOTION_PING_INTERVAL_SEC')) || 15) * 1000);
}

function clearEmotionCards() {
  if (emotionCardTimer) clearTimeout(emotionCardTimer);
  emotionCardTimer = null;
  if (ui.emotionFeed) ui.emotionFeed.innerHTML = '';
}

function renderDistributionBars(distribution = {}) {
  const rows = Object.entries(distribution || {})
    .filter(([, value]) => Number(value) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 5);
  if (!rows.length) return '';
  return `<div class="emotion-bars">${rows.map(([label, value]) => `
    <div class="emotion-bar-row">
      <span>${escapeHTML(label)}</span>
      <div><i style="width:${Math.max(4, Math.min(100, Number(value) || 0))}%"></i></div>
      <b>${escapeHTML(value)}%</b>
    </div>`).join('')}</div>`;
}

function showEmotionCard(emotionData) {
  if (!getFeatures().emotionChat || !ui.emotionFeed || !isPosActive()) return;
  const data = typeof emotionData === 'string'
    ? { emotion_display: emotionData }
    : (emotionData || {});
  lastEmotionStructured = data;
  lastMediaSignals = data.media_signals || lastMediaSignals || {};
  const display = data.emotion_display || data.emotion || '尚未取得情緒分析。';
  const evidence = data.emotion_evidence || data.evidence || '';
  const distribution = data.emotion_distribution || {};
  let card = ui.emotionFeed.querySelector('.emotion-card');
  if (!card) {
    card = document.createElement('div');
    card.className = 'emotion-card';
    card.innerHTML = `
      <div class="emotion-title"><i class="fas fa-brain"></i><span>Emotion-LLaMA</span></div>
      <div class="emotion-text"></div>
      <div class="emotion-evidence"></div>
      <div class="emotion-dist"></div>`;
    ui.emotionFeed.appendChild(card);
  }
  card.classList.remove('fade-out');
  card.querySelector('.emotion-text').textContent = display;
  const evidenceEl = card.querySelector('.emotion-evidence');
  evidenceEl.textContent = evidence ? `判斷依據：${evidence}` : '';
  card.querySelector('.emotion-dist').innerHTML = renderDistributionBars(distribution);
  if (emotionCardTimer) clearTimeout(emotionCardTimer);
  emotionCardTimer = setTimeout(() => {
    card.classList.add('fade-out');
    const target = card;
    setTimeout(() => {
      if (target.classList.contains('fade-out')) target.remove();
    }, 1800);
  }, 12000);
}

async function fetchAndDisplayRecommend() {
  const f = getFeatures();
  if (!f.recommend) return;
  if (Date.now() < promotionPausedUntil) return;
  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('ab_mode', f.abTest ? 'ab' : 'single');
  try {
    const data = await api.autoRecommend(fd);
    if (data.status === 'success') displayRecommendation(data);
  } catch { }
}

function startRecommendLoop() {
  if (recommendLoopId) return;
  recommendLoopId = setInterval(async () => {
    if (!isPosActive() || recommendPending) return;
    if (document.hidden) return;
    await fetchAndDisplayRecommend();
  }, Math.max(10, Number(perfValue('RECOMMEND_INTERVAL_SEC')) || 30) * 1000);
}

// =========================================================
// 語音問答（問題3: 回覆綁定浮動氣泡，問題5: 語言偵測）
// =========================================================
function closeVoiceBubble(stopAudio = true) {
  if (voiceBubbleTimer) clearTimeout(voiceBubbleTimer);
  voiceBubbleTimer = null;
  ui.voiceBubble.style.display = 'none';
  if (stopAudio) {
    ui.audio.pause();
    ui.audio.currentTime = 0;
  }
}

function showVoiceBubble(data) {
  if (!isPosActive() || !getFeatures().voiceAsk) return;
  const lang = data.detected_lang || 'zh';
  const dialogue = data.dialogue || {
    zh: { user_text: lang === 'zh' ? data.user_text : '', ai_response: lang === 'zh' ? data.ai_response : '' },
    en: { user_text: lang === 'en' ? data.user_text : '', ai_response: lang === 'en' ? data.ai_response : '' }
  };
  const d = dialogue[lang] || { user_text: data.user_text || '', ai_response: data.ai_response || '' };
  ui.voiceDialogueGrid.innerHTML = `
    <div class="dialogue-lane active">
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs font-bold" style="color:var(--accent2)">${lang === 'en' ? 'English' : '繁體中文'}</span>
        <i class="fas fa-volume-up text-xs" style="color:var(--accent2)"></i>
      </div>
      <p class="text-xs mb-1 truncate" style="color:var(--text2)">${escapeHTML(d.user_text || data.user_text || '-')}</p>
      <p class="text-sm font-medium leading-snug" style="color:var(--text)">${escapeHTML(d.ai_response || data.ai_response || '-')}</p>
    </div>`;
  ui.voiceLangBadge.textContent = lang === 'en' ? 'English output' : '繁體中文輸出';
  ui.voiceBubble.style.display = 'block';
  if (voiceBubbleTimer) clearTimeout(voiceBubbleTimer);
  voiceBubbleTimer = setTimeout(() => closeVoiceBubble(false), 12000);
}

function setupAskRecorder() {
  if (askRecorder) return; // 避免重複設定
  if (!stream || !stream.getAudioTracks().length) return;

  askRecorder = createAudioRecorder(stream);
  let chunks = [];
  askRecorder.ondataavailable = e => chunks.push(e.data);
  askRecorder.onstop = async () => {
    const blob = new Blob(chunks, { type: 'audio/webm' });
    chunks = [];
    if (blob.size < 1500) {
      trackInteractionEvent({
        event_type: 'voice_order_failed',
        button_id: 'askBtn',
        metadata: { reason: 'audio_too_short' }
      });
      ui.askText.textContent = "長按語音點餐";
      return;
    }

    const voiceAskEnabled = getFeatures().voiceAsk;
    ui.askText.textContent = voiceAskEnabled ? "AI 思考中..." : "辨識餐點中...";
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('audio', blob);
    fd.append('multi_lang', String(getFeatures().multiLang));
    fd.append('use_ollama', String(voiceAskEnabled));
    try {
      const data = await api.ask(fd);
      if (data.status === 'success') {
        lastVoiceText = data.user_text || lastVoiceText;
        if (voiceAskEnabled) {
          playVoice(data.audio_base64);
          showVoiceBubble(data);
        }
        const appliedOrders = cartManager.applyCartActions(data.cart_actions || []);
        if (appliedOrders.length) {
          trackInteractionEvent({
            event_type: 'cart_edit',
            button_id: 'askBtn',
            cart_edit_count: appliedOrders.length,
            metadata: { source: 'voice_order', items: appliedOrders }
          });
          showPushNotice(`已加入購物車：${appliedOrders.join('、')}`);
        } else if (!voiceAskEnabled) {
          showPushNotice(data.ai_response || '沒有在菜單中找到可加入購物車的餐點。');
        }

        if (voiceAskEnabled && data.trigger_recommend && getFeatures().recommend) {
          recommendPending = true;
          setTimeout(async () => {
            await fetchAndDisplayRecommend();
            recommendPending = false;
          }, Number(perfValue('RECOMMEND_AFTER_ASK_DELAY_MS')) || 1200);
        }
        if (data.mentioned_ids) data.mentioned_ids.forEach(id => sessionPushedIds.add(id));
      }
    } catch {
      trackInteractionEvent({
        event_type: 'voice_order_failed',
        button_id: 'askBtn',
        metadata: { reason: 'api_error', voice_ask_enabled: getFeatures().voiceAsk }
      });
      if (getFeatures().voiceAsk) {
        showVoiceBubble({
          detected_lang: 'zh',
          dialogue: { zh: { user_text: '', ai_response: '網路連線失敗，請稍後再試。' } }
        });
      } else {
        showPushNotice('語音點餐失敗，請稍後再試。');
      }
    }
    ui.askText.textContent = "長按語音點餐";
  };
}

ui.askBtn.onmousedown = ui.askBtn.ontouchstart = (e) => {
  e.preventDefault();
  if (askRecorder && askRecorder.state === 'inactive') {
    trackInteractionEvent({
      event_type: getFeatures().voiceAsk ? 'voice_ask_started' : 'voice_order_started',
      button_id: 'askBtn',
      metadata: { voice_ask_enabled: getFeatures().voiceAsk }
    });
    askRecorder.start();
    ui.askBtn.classList.add('recording');
    ui.askText.textContent = getFeatures().voiceAsk ? "聆聽發問中..." : "聆聽點餐中...";
  }
};
ui.askBtn.onmouseup = ui.askBtn.ontouchend = (e) => {
  e.preventDefault();
  if (askRecorder && askRecorder.state === 'recording') {
    askRecorder.stop();
    ui.askBtn.classList.remove('recording');
  }
};

window.addEventListener('beforeunload', () => {
  try {
    if (askRecorder?.state === 'recording') askRecorder.stop();
    if (serviceRecorder?.state === 'recording') serviceRecorder.stop();
    if (adminServiceRecorder?.state === 'recording') adminServiceRecorder.stop();
  } catch { }
  if (emotionLoopId) clearInterval(emotionLoopId);
  if (detectionLoopId) clearInterval(detectionLoopId);
  if (recommendLoopId) clearInterval(recommendLoopId);
  if (pageDwellTimer) clearInterval(pageDwellTimer);
});

function playVoice(b64) {
  if (!b64) return;
  ui.audio.src = `data:audio/mp3;base64,${b64}`;
  ui.audio.play();
}

// =========================================================
// POS 內建客服
// =========================================================
function setServiceResult(html) {
  ui.serviceResult.innerHTML = html;
}

function renderServiceResponse(targetEl, data) {
  const langLabel = data.detected_lang === 'en' ? 'English' : '繁體中文';
  targetEl.innerHTML = `
    <div class="flex flex-wrap gap-2 mb-3">
      <span class="text-xs px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">語系 ${escapeHTML(langLabel)}</span>
      <span class="text-xs px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">情緒 ${escapeHTML(formatEmotion(data.emotion || '-'))}</span>
      <span class="text-xs px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">優先級 ${escapeHTML(data.priority || '-')}</span>
    </div>
    <p class="text-xs mb-1" style="color:var(--text2)">顧客</p>
    <p class="mb-2 font-medium" style="color:var(--text)">${escapeHTML(data.user_text || '')}</p>
    <p class="text-xs mb-1" style="color:var(--text2)">客服回覆</p>
    <p class="font-semibold" style="color:var(--text)">${escapeHTML(data.customer_reply || '')}</p>
  `;
}

function resetServiceButton() {
  ui.serviceRecord.classList.remove('recording');
  ui.serviceRecordText.textContent = '開始收音';
}

async function startServiceRecording() {
  const ok = await ensureMediaTracks({ video: true, audio: true });
  if (!ok || !stream || !stream.getAudioTracks().length) return;
  serviceChunks = [];
  serviceRecorder = createVideoRecorder(stream);
  serviceRecorder.ondataavailable = e => { if (e.data.size) serviceChunks.push(e.data); };
  serviceRecorder.onstop = submitServiceRecording;
  serviceRecorder.start();
  ui.serviceRecord.classList.add('recording');
  ui.serviceRecordText.textContent = '停止並送出';
  setServiceResult('正在收音，停止後會通知客服並分析語系與情緒。');
}

function stopServiceRecording() {
  if (serviceRecorder && serviceRecorder.state === 'recording') serviceRecorder.stop();
}

async function submitServiceRecording() {
  const blob = new Blob(serviceChunks, { type: 'video/webm' });
  serviceChunks = [];
  resetServiceButton();
  if (blob.size < 1500) {
    trackInteractionEvent({
      event_type: 'customer_service_failed',
      button_id: 'posServiceRecord',
      metadata: { reason: 'media_too_short' }
    });
    setServiceResult('收音時間過短，請重新操作。');
    return;
  }

  setServiceResult('正在分析客服語音，請稍候。');
  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('media', blob, 'pos_customer_service.webm');
  fd.append('use_ollama', 'true');
  fd.append('multi_lang', String(getFeatures().multiLang));
  try {
    const data = await api.customerService(fd);
    if (data.status !== 'success') throw new Error(data.message || '客服流程失敗');
    renderServiceResponse(ui.serviceResult, data);
    if (data.audio_base64) playVoice(data.audio_base64);
  } catch (err) {
    trackInteractionEvent({
      event_type: 'customer_service_failed',
      button_id: 'posServiceRecord',
      metadata: { reason: err.message || 'customer_service_error' }
    });
    setServiceResult(escapeHTML(err.message || '客服流程失敗。'));
  }
}

function resetAdminServiceButton() {
  ui.adminServiceRecord?.classList.remove('recording');
  if (ui.adminServiceRecordText) ui.adminServiceRecordText.textContent = '開始收音';
}

async function startAdminServiceRecording() {
  const ok = await ensureMediaTracks({ video: true, audio: true });
  if (!ok || !stream || !stream.getAudioTracks().length) return;
  adminServiceChunks = [];
  adminServiceRecorder = createVideoRecorder(stream);
  adminServiceRecorder.ondataavailable = e => { if (e.data.size) adminServiceChunks.push(e.data); };
  adminServiceRecorder.onstop = submitAdminServiceRecording;
  adminServiceRecorder.start();
  ui.adminServiceRecord.classList.add('recording');
  ui.adminServiceRecordText.textContent = '停止並送出';
  ui.adminServiceResult.textContent = '正在收音，停止後會分析語系與情緒。';
}

function stopAdminServiceRecording() {
  if (adminServiceRecorder && adminServiceRecorder.state === 'recording') adminServiceRecorder.stop();
}

async function submitAdminServiceRecording() {
  const blob = new Blob(adminServiceChunks, { type: 'video/webm' });
  adminServiceChunks = [];
  resetAdminServiceButton();
  if (blob.size < 1500) {
    ui.adminServiceResult.textContent = '收音時間過短，請重新操作。';
    return;
  }

  ui.adminServiceResult.textContent = '正在分析客服語音，請稍候。';
  const fd = new FormData();
  fd.append('session_id', `${sessionId}_admin_service`);
  fd.append('media', blob, 'admin_customer_service.webm');
  fd.append('use_ollama', String(adminServiceOllamaDirect));
  fd.append('multi_lang', String(getFeatures().multiLang));
  try {
    const data = await api.customerService(fd);
    if (data.status !== 'success') throw new Error(data.message || '客服流程失敗');
    renderServiceResponse(ui.adminServiceResult, data);
    await loadCustomerServiceData();
    if (data.audio_base64) playVoice(data.audio_base64);
  } catch (err) {
    ui.adminServiceResult.textContent = err.message || '客服流程失敗。';
  }
}

ui.serviceFab.onclick = () => {
  trackInteractionEvent({
    event_type: 'customer_service_clicked',
    button_id: 'posServiceFab',
    metadata: { opening: !ui.serviceWindow.classList.contains('open') }
  });
  ui.serviceWindow.classList.toggle('open');
};
ui.serviceClose.onclick = () => {
  ui.serviceWindow.classList.remove('open');
  stopServiceRecording();
};
ui.serviceRecord.onclick = async () => {
  if (serviceRecorder && serviceRecorder.state === 'recording') {
    stopServiceRecording();
  } else {
    trackInteractionEvent({
      event_type: 'customer_service_record_started',
      button_id: 'posServiceRecord'
    });
    await startServiceRecording();
  }
};
document.addEventListener('pointerdown', (event) => {
  const target = event.target;
  const interactive = target?.closest?.(
    'button,a,input,textarea,select,[onclick],[data-fulfillment],[data-payment],.menu-card,.cart-item,#posServiceWindow,#posServiceFab,#voiceReplyBubble'
  );
  if (isSystemRunning && isPosActive() && !interactive) {
    trackInteractionEvent({
      event_type: 'invalid_touch',
      button_id: 'document',
      metadata: { tag: target?.tagName || '' }
    });
  }
  if (!ui.serviceWindow.classList.contains('open')) return;
  if (ui.serviceWindow.contains(target) || ui.serviceFab.contains(target)) return;
  ui.serviceWindow.classList.remove('open');
  stopServiceRecording();
});
if (ui.adminServiceToggle) {
  ui.adminServiceToggle.onclick = () => {
    adminServiceOllamaDirect = !adminServiceOllamaDirect;
    ui.adminServiceToggle.classList.toggle('on', adminServiceOllamaDirect);
  };
}
if (ui.adminServiceRecord) {
  ui.adminServiceRecord.onclick = async () => {
    if (adminServiceRecorder && adminServiceRecorder.state === 'recording') {
      stopAdminServiceRecording();
    } else {
      await startAdminServiceRecording();
    }
  };
}

function applyPerformancePreset(mode) {
  const presets = {
    eco: { emotion: 30, record: 700, recommend: 60, gap: 45, tokens: 160, rag: 2 },
    balanced: { emotion: 15, record: 900, recommend: 30, gap: 20, tokens: 220, rag: 3 },
    quality: { emotion: 8, record: 1500, recommend: 18, gap: 12, tokens: 360, rag: 4 }
  };
  const p = presets[mode] || presets.balanced;
  document.getElementById('inp-emotion-interval').value = p.emotion;
  document.getElementById('inp-emotion-record-ms').value = p.record;
  document.getElementById('inp-recommend-interval').value = p.recommend;
  document.getElementById('inp-recommend-gap').value = p.gap;
  document.getElementById('inp-num-predict').value = p.tokens;
  document.getElementById('inp-rag-top-k').value = p.rag;
}

// =========================================================
// 結帳
// =========================================================
let selectedFulfillment = 'takeout';
let selectedPayment = 'credit-card';

function getOrderNumber() {
  const numeric = Array.from(sessionId).reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % 900;
  return `#A${String(numeric + 100).padStart(3, '0')}`;
}

function getOrderTotals() {
  const subtotal = cartManager.getCartTotal();
  const serviceFee = Math.round(subtotal * 0.1);
  return { subtotal, serviceFee, total: subtotal + serviceFee };
}

function updateChoiceGroup(selector, selectedValue) {
  document.querySelectorAll(selector).forEach(button => {
    const value = button.dataset.fulfillment || button.dataset.payment;
    button.classList.toggle('selected', value === selectedValue);
    if (value === selectedValue && !button.querySelector('b')) {
      button.insertAdjacentHTML('beforeend', '<b><i class="fas fa-check"></i></b>');
    }
  });
}

function renderOrderConfirm() {
  const items = cartManager.getCartItems();
  const prepMinutes = Math.max(0, ...items.map(item => Number(item.prep_time_minutes || item.prep_minutes || 0)));
  const totals = getOrderTotals();

  if (ui.confirmSubtotalPrice) ui.confirmSubtotalPrice.textContent = `$${totals.subtotal}`;
  if (ui.confirmServiceFee) ui.confirmServiceFee.textContent = `$${totals.serviceFee}`;
  if (ui.confirmTotalPrice) ui.confirmTotalPrice.textContent = `$${totals.total}`;
  if (ui.confirmOrderNumber) ui.confirmOrderNumber.textContent = getOrderNumber();
  if (ui.confirmPrepTime) ui.confirmPrepTime.textContent = `約 ${prepMinutes || 5} 分鐘`;
  if (ui.confirmPayBtn) ui.confirmPayBtn.disabled = !items.length;

  if (!ui.confirmOrderList) return;
  if (!items.length) {
    ui.confirmOrderList.innerHTML = `
      <div class="order-empty">
        <i class="fas fa-shopping-bag"></i>
        <p>目前沒有選擇任何餐點。</p>
      </div>`;
    return;
  }

  ui.confirmOrderList.innerHTML = items.map(item => {
    const quantity = Number(item.quantity || 0);
    const price = Number(item.price || 0);
    const visual = getMenuVisual(item);
    return `
      <div class="order-summary-item">
        <div class="order-summary-photo">
          <img src="${visual.image}" alt="${escapeHTML(item.name)}" onerror="this.style.display='none';this.parentElement.innerHTML='${visual.emoji}'">
        </div>
        <div class="order-summary-name">${escapeHTML(item.name)}</div>
        <div class="order-summary-meta">
          <span class="order-summary-qty">× ${quantity}</span>
          <strong class="order-summary-price">$${price * quantity}</strong>
        </div>
      </div>
    `;
  }).join('');
}

async function writeCheckoutLog(cartIds = []) {
  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('pushed_ids', JSON.stringify(Array.from(sessionPushedIds)));
  fd.append('cart_ids', JSON.stringify(cartIds));
  fd.append('pushed_variants', JSON.stringify({
    A: Array.from(sessionPushedVariants.A),
    B: Array.from(sessionPushedVariants.B),
    single: Array.from(sessionPushedVariants.single)
  }));
  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), 4000);
  try { await api.checkout(fd, ctrl.signal); }
  catch (err) {
    trackInteractionEvent({
      event_type: 'payment_failed',
      button_id: 'confirmPayBtn',
      payment_fail_count: 1,
      metadata: { reason: err?.message || 'checkout_log_failed' }
    });
  }
  finally { clearTimeout(tid); }
}

function setConfirmButtonsDisabled(disabled) {
  [
    ui.orderConfirmCloseBtn,
    ui.confirmBackBtn,
    ui.confirmPayBtn,
    ui.checkoutBtn,
    ...document.querySelectorAll('[data-fulfillment], [data-payment]')
  ]
    .filter(Boolean)
    .forEach(button => { button.disabled = disabled; });
}

function showCompletionOverlay(title, subtitle) {
  switchMainView('pos');
  closeOrderConfirmModal();
  const titleEl = ui.checkoutOverlay?.querySelector('h1');
  const subtitleEl = ui.checkoutOverlay?.querySelector('p');
  if (titleEl) titleEl.textContent = title;
  if (subtitleEl) subtitleEl.textContent = subtitle;
  ui.checkoutOverlay.classList.remove('hidden');
  requestAnimationFrame(() => ui.checkoutOverlay.classList.remove('opacity-0'));
  updateEmotionCameraPanel();
  setTimeout(() => location.reload(), 3500);
}

async function finishOrder(cartIds, button, loadingText, doneTitle) {
  orderCompleted = true;
  clearPOSFloatingUI();
  recommendPending = false;
  const originalHTML = button?.innerHTML || '';
  setConfirmButtonsDisabled(true);
  if (button) button.innerHTML = `<i class="fas fa-spinner fa-spin mr-2"></i>${loadingText}`;
  await writeCheckoutLog(cartIds);
  if (button) button.innerHTML = originalHTML;
  showCompletionOverlay(doneTitle, '感謝您的使用 · Thank you');
}

function openOrderConfirmModal() {
  renderOrderConfirm();
  updateChoiceGroup('[data-fulfillment]', selectedFulfillment);
  updateChoiceGroup('[data-payment]', selectedPayment);
  ui.orderConfirmModal?.classList.remove('hidden');
  ui.orderConfirmModal?.setAttribute('aria-hidden', 'false');
  setInteractionPage('payment_page', { source: 'checkout_button' });
  clearPOSFloatingUI();
}

function closeOrderConfirmModal() {
  ui.orderConfirmModal?.classList.add('hidden');
  ui.orderConfirmModal?.setAttribute('aria-hidden', 'true');
  if (!orderCompleted) setInteractionPage('menu_page', { source: 'close_order_confirm' });
}

ui.checkoutBtn.onclick = () => {
  if (!cartManager.getCartIds().length) return;
  trackInteractionEvent({
    event_type: 'enter_payment_page',
    button_id: 'checkoutBtn',
    metadata: { cart_ids: cartManager.getCartIds() }
  });
  openOrderConfirmModal();
};

function leaveOrderConfirm(buttonId) {
  trackInteractionEvent({
    event_type: 'back_navigation',
    button_id: buttonId,
    back_count: 1,
    metadata: { from: 'payment_page', to: 'menu_page' }
  });
  closeOrderConfirmModal();
}

ui.orderConfirmCloseBtn?.addEventListener('click', () => leaveOrderConfirm('orderConfirmCloseBtn'));
ui.confirmBackBtn?.addEventListener('click', () => leaveOrderConfirm('confirmBackBtn'));
ui.orderConfirmModal?.addEventListener('click', event => {
  if (event.target?.classList?.contains('order-modal-backdrop')) leaveOrderConfirm('orderModalBackdrop');
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !ui.orderConfirmModal?.classList.contains('hidden')) leaveOrderConfirm('escapeKey');
});
document.querySelectorAll('[data-fulfillment]').forEach(button => {
  button.addEventListener('click', () => {
    selectedFulfillment = button.dataset.fulfillment || selectedFulfillment;
    updateChoiceGroup('[data-fulfillment]', selectedFulfillment);
  });
});
document.querySelectorAll('[data-payment]').forEach(button => {
  button.addEventListener('click', () => {
    selectedPayment = button.dataset.payment || selectedPayment;
    updateChoiceGroup('[data-payment]', selectedPayment);
  });
});
ui.confirmPayBtn?.addEventListener('click', () => {
  const cartIds = cartManager.getCartIds();
  if (!cartIds.length) return;
  trackInteractionEvent({
    event_type: 'payment_attempt',
    button_id: 'confirmPayBtn',
    metadata: { payment: selectedPayment, fulfillment: selectedFulfillment, cart_ids: cartIds }
  });
  finishOrder(cartIds, ui.confirmPayBtn, '結帳中...', '點餐完成！');
});

// =========================================================
// 後台
// =========================================================
function loadAdminData() {
  loadLogs();
  loadInterventionStats();
  loadSettings();
  loadAdminMenu();
  loadRagData();
  loadCustomerServiceData();
  loadEmotionClips();
}

function topCountLabel(counts = {}) {
  const entries = Object.entries(counts || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
  if (!entries.length) return '-';
  return `${entries[0][0]} (${entries[0][1]})`;
}

function renderCountList(containerId, counts = {}) {
  const box = document.getElementById(containerId);
  if (!box) return;
  const entries = Object.entries(counts || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
  if (!entries.length) {
    box.innerHTML = `<p class="text-sm" style="color:var(--text2)">尚無資料。</p>`;
    return;
  }
  const max = Math.max(...entries.map(([, count]) => Number(count) || 0), 1);
  box.innerHTML = entries.slice(0, 8).map(([label, count]) => {
    const value = Number(count) || 0;
    const width = Math.max(6, Math.round((value / max) * 100));
    return `
      <div>
        <div class="flex justify-between gap-3 mb-1">
          <span class="truncate" style="color:var(--text)">${escapeHTML(label)}</span>
          <b style="color:var(--accent2)">${value}</b>
        </div>
        <div class="h-2 rounded-full overflow-hidden" style="background:var(--surface2)">
          <i class="block h-full rounded-full" style="width:${width}%;background:var(--accent)"></i>
        </div>
      </div>`;
  }).join('');
}

async function loadInterventionStats() {
  try {
    const data = await api.getInterventionStats();
    if (data.status !== 'success') throw new Error(data.message || 'stats failed');
    const total = Number(data.total_interventions || 0);
    const successRate = Math.round(Number(data.success_rate || 0) * 100);
    document.getElementById('intervention-total').textContent = total;
    document.getElementById('intervention-success-rate').textContent = `${successRate}%`;
    document.getElementById('intervention-top-state').textContent = topCountLabel(data.barrier_state_counts);
    document.getElementById('intervention-top-action').textContent = topCountLabel(data.action_counts);
    renderCountList('barrierStateCounts', data.barrier_state_counts);
    renderCountList('interventionActionCounts', data.action_counts);
    renderCountList('pageIssueCounts', data.page_issue_counts);

    const tbody = document.getElementById('interventionLogsBody');
    if (!tbody) return;
    const logs = Array.isArray(data.recent_logs) ? data.recent_logs : [];
    tbody.innerHTML = '';
    logs.forEach(log => {
      const barrier = log.barrier_result || {};
      const intervention = log.intervention || {};
      const uiContext = log.ui_context || {};
      const result = log.result || {};
      const success = Boolean(result.checkout_success || result.payment_success);
      const resultBadge = success
        ? `<span class="text-xs font-bold px-2 py-0.5 rounded-full" style="background:#dcf5e7;color:var(--success)">完成</span>`
        : `<span class="text-xs font-bold px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">待觀察</span>`;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="p-3 text-xs" style="color:var(--text2)">${log.timestamp ? new Date(log.timestamp).toLocaleString() : '-'}</td>
        <td class="p-3 text-xs" style="color:var(--text)">${escapeHTML(uiContext.page_id || '-')}</td>
        <td class="p-3 text-xs font-mono" style="color:var(--accent2)">${escapeHTML(barrier.barrier_state || '-')}</td>
        <td class="p-3 text-xs font-mono" style="color:var(--info)">${escapeHTML(intervention.action || '-')}</td>
        <td class="p-3 text-center">${resultBadge}</td>`;
      tbody.appendChild(tr);
    });
    if (!logs.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="p-4 text-center text-sm" style="color:var(--text2)">尚無介入紀錄。</td></tr>`;
    }

    const eventsBody = document.getElementById('interactionEventsBody');
    if (!eventsBody) return;
    const events = Array.isArray(data.recent_events) ? data.recent_events : [];
    eventsBody.innerHTML = '';
    events.forEach(event => {
      const metadata = event.metadata || {};
      const source = event.button_id || metadata.source || metadata.reason || '-';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="p-3 text-xs" style="color:var(--text2)">${event.timestamp ? new Date(event.timestamp).toLocaleString() : '-'}</td>
        <td class="p-3 text-xs" style="color:var(--text)">${escapeHTML(event.page_id || '-')}</td>
        <td class="p-3 text-xs font-mono" style="color:var(--accent2)">${escapeHTML(event.event_type || '-')}</td>
        <td class="p-3 text-xs" style="color:var(--text2)">${escapeHTML(source)}</td>`;
      eventsBody.appendChild(tr);
    });
    if (!events.length) {
      eventsBody.innerHTML = `<tr><td colspan="4" class="p-4 text-center text-sm" style="color:var(--text2)">尚無 POS 操作事件。</td></tr>`;
    }
  } catch {
    renderCountList('barrierStateCounts', {});
    renderCountList('interventionActionCounts', {});
    renderCountList('pageIssueCounts', {});
  }
}

async function loadLogs() {
  try {
    const data = await api.getLogs();
    document.getElementById('stat-total').textContent = data.total;
    document.getElementById('stat-rate').textContent = data.success_rate + '%';
    document.getElementById('stat-success').textContent = data.success_count ?? data.logs.filter(l => l.is_success).length;
    const ab = data.ab_stats || {};
    const a = ab.A || { impressions: 0, successes: 0, success_rate: 0 };
    const b = ab.B || { impressions: 0, successes: 0, success_rate: 0 };
    document.getElementById('stat-ab-a').textContent = a.success_rate + '%';
    document.getElementById('stat-ab-a-detail').textContent = `${a.successes} / ${a.impressions}`;
    document.getElementById('stat-ab-b').textContent = b.success_rate + '%';
    document.getElementById('stat-ab-b-detail').textContent = `${b.successes} / ${b.impressions}`;
    const tbody = document.getElementById('logsTableBody');
    tbody.innerHTML = '';
    [...data.logs].reverse().forEach(log => {
      const badge = log.is_success
        ? `<span class="text-xs font-bold px-2 py-0.5 rounded-full" style="background:#dcf5e7;color:var(--success)">✓ 成功</span>`
        : `<span class="text-xs font-bold px-2 py-0.5 rounded-full" style="background:#fdecea;color:#c0392b">✗ 未命中</span>`;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="p-3 text-xs" style="color:var(--text2)">${new Date(log.timestamp).toLocaleString()}</td>
        <td class="p-3 text-xs" style="color:var(--text)">${escapeHTML(log.emotions_summary || '-')}</td>
        <td class="p-3 font-mono text-xs" style="color:var(--info)">[${escapeHTML((log.pushed_ids || []).join(','))}]</td>
        <td class="p-3 font-mono text-xs" style="color:var(--text)">[${escapeHTML((log.final_cart_ids || []).join(','))}]</td>
        <td class="p-3 text-center">${badge}</td>
        <td class="p-3 text-center">
          <button class="text-xs px-2 py-1 rounded-xl" style="color:var(--danger);border:1px solid var(--border)" data-delete-log="${escapeHTML(log._index)}">
            <i class="fas fa-trash"></i>
          </button>
        </td>`;
      tr.querySelector('[data-delete-log]').onclick = async () => {
        if (!confirm('確定刪除這筆推播成效資料？')) return;
        await api.deleteLog(log._index);
        await loadLogs();
      };
      tbody.appendChild(tr);
    });
  } catch { }
}

async function clearPushLogs() {
  if (!confirm('確定清空全部推播成效資料？')) return;
  await api.clearLogs();
  await loadLogs();
}

async function clearAllRagDocs() {
  if (!confirm('確定清空全部 RAG 文本、審查紀錄與向量庫？菜單資料會重新建立為基礎 RAG。')) return;
  const data = await api.clearRagDocs().catch(() => ({}));
  if (data.status !== 'success') {
    alert(data.message || '清空 RAG 失敗。');
    return;
  }
  await loadRagData();
  alert('RAG 已清空並重建菜單基礎資料。');
}

async function uploadRagPdf() {
  const input = document.getElementById('ragPdfFile');
  const file = input?.files?.[0];
  if (!file) return alert('請先選擇 PDF。');
  const fd = new FormData();
  fd.append('pdf', file);
  fd.append('review', document.getElementById('ragPdfReview')?.checked ? 'true' : 'false');
  const data = await api.uploadRagPdf(fd).catch(() => ({}));
  if (data.status !== 'success') {
    alert(data.message || 'PDF 匯入失敗。');
    return;
  }
  input.value = '';
  await loadRagData();
  alert(`PDF 已匯入 ${data.chunks || 0} 個 chunk。`);
}

async function loadEmotionClips() {
  const box = document.getElementById('emotionClipList');
  if (!box) return;
  box.innerHTML = '<p class="text-sm" style="color:var(--text2)">載入影像片段中...</p>';
  try {
    const data = await api.getEmotionClips(sessionId);
    const clips = data.clips || [];
    if (!clips.length) {
      box.innerHTML = '<p class="text-sm" style="color:var(--text2)">目前這筆訂單尚無情緒影像片段。</p>';
      return;
    }
    box.innerHTML = '';
    [...clips].reverse().forEach((clip, idx) => {
      const item = document.createElement('div');
      item.className = 'emotion-clip-item';
      const url = `${API_BASE}${clip.url}`;
      const personLabel = clip.person_detected ? '偵測到人物' : '未偵測到人物';
      const hitCount = clip.person_hits ?? clip.face_hits ?? 0;
      const signals = clip.media_signals || {};
      const signalText = signals.motion_level
        ? `音量 ${signals.audio_mean_db ?? '-'} dB / 動作 ${signals.motion_level}`
        : '';
      item.innerHTML = `
        <video controls muted playsinline preload="metadata" src="${escapeHTML(url)}"></video>
        <div class="clip-meta">
          <div class="font-bold" style="color:var(--text)">片段 ${clips.length - idx}</div>
          <div style="color:var(--text2)">${escapeHTML(new Date(clip.created_at).toLocaleString())}</div>
          <div style="color:var(--text)">${escapeHTML(clip.emotion_display || clip.emotion || '-')}</div>
          ${clip.speech_text ? `<div style="color:var(--text2)">語音：${escapeHTML(clip.speech_text)}</div>` : ''}
          ${clip.emotion_evidence ? `<div style="color:var(--text2)">依據：${escapeHTML(clip.emotion_evidence)}</div>` : ''}
          ${signalText ? `<div style="color:var(--text2)">訊號：${escapeHTML(signalText)}</div>` : ''}
          ${renderDistributionBars(clip.emotion_distribution || {})}
          <div class="clip-badges">
            <span>${escapeHTML(personLabel)}</span>
            <span>${escapeHTML(clip.detector || 'detector')}</span>
            <span>person ${escapeHTML(hitCount)} / ${escapeHTML(clip.frames_checked ?? 0)}</span>
          </div>
        </div>`;
      box.appendChild(item);
    });
  } catch {
    box.innerHTML = '<p class="text-sm" style="color:var(--danger)">影像片段讀取失敗。</p>';
  }
}

async function clearEmotionClips() {
  if (!confirm('確定清除目前這筆訂單的情緒影像片段？')) return;
  await api.clearEmotionClips(sessionId);
  await loadEmotionClips();
}

let fullSettings = {};
async function loadSettings() {
  try {
    fullSettings = await api.getSettings();
    runtimeSettings = { ...runtimeSettings, ...fullSettings };
    const modelName = fullSettings.MODEL_NAME || 'llama3.2';
    document.getElementById('inp-ai-provider').value = fullSettings.QA_AI_PROVIDER || fullSettings.AI_PROVIDER || 'ollama';
    document.getElementById('inp-model-name').value = modelName;
    document.getElementById('inp-ask-model-name').value = modelName;
    document.getElementById('inp-gemini-model-name').value = fullSettings.GEMINI_MODEL_NAME || 'gemini-3-flash-preview';
    document.getElementById('inp-gemini-fallback').checked = fullSettings.GEMINI_FALLBACK_TO_OLLAMA !== false;
    document.getElementById('inp-gemini-cooldown').value = fullSettings.GEMINI_COOLDOWN_SEC || 60;
    document.getElementById('inp-temp').value = fullSettings.OLLAMA_TEMPERATURE || 0.8;
    document.getElementById('inp-performance-mode').value = fullSettings.PERFORMANCE_MODE || 'balanced';
    document.getElementById('inp-num-predict').value = fullSettings.OLLAMA_NUM_PREDICT || 220;
    document.getElementById('inp-rag-top-k').value = fullSettings.RAG_TOP_K || 3;
    const rag = fullSettings.rag || {};
    document.getElementById('inp-rag-multi-query').checked = rag.use_multi_query !== false;
    document.getElementById('inp-rag-hybrid-search').checked = rag.use_hybrid_search !== false;
    document.getElementById('inp-rag-reranker').checked = rag.use_reranker !== false;
    document.getElementById('inp-rag-compression').checked = rag.use_context_compression !== false;
    document.getElementById('inp-rag-evaluation').checked = rag.use_answer_evaluation !== false;
    document.getElementById('inp-rag-top-k-vector').value = rag.top_k_vector || 10;
    document.getElementById('inp-rag-top-k-keyword').value = rag.top_k_keyword || 10;
    document.getElementById('inp-rag-top-k-final').value = rag.top_k_final || 5;
    document.getElementById('inp-rag-context-max').value = rag.context_max_chars || 2600;
    document.getElementById('inp-rag-embedding-provider').value = rag.embedding_provider || 'ollama';
    document.getElementById('inp-rag-embedding-model').value = rag.embedding_model || 'nomic-embed-text';
    document.getElementById('inp-rag-reranker-model').value = rag.reranker_model || 'cross-encoder/ms-marco-MiniLM-L-6-v2';
    document.getElementById('inp-emotion-interval').value = fullSettings.EMOTION_PING_INTERVAL_SEC || 15;
    document.getElementById('inp-emotion-record-ms').value = fullSettings.EMOTION_RECORD_MS || 900;
    document.getElementById('inp-recommend-interval').value = fullSettings.RECOMMEND_INTERVAL_SEC || 30;
    document.getElementById('inp-recommend-gap').value = fullSettings.AUTO_RECOMMEND_MIN_GAP_SEC || 20;
    document.getElementById('inp-ab-single-call').checked = fullSettings.AB_SINGLE_CALL !== false;
    document.getElementById('inp-tts-cache').checked = fullSettings.ENABLE_TTS_CACHE !== false;
    document.getElementById('inp-recommend-cache').checked = fullSettings.ENABLE_RECOMMEND_CACHE !== false;
    document.getElementById('inp-emotion-prompt').value = fullSettings.EMOTION_LLAMA_PROMPT || '';
    document.getElementById('inp-recommend-prompt').value = fullSettings.RECOMMEND_SYSTEM_PROMPT || '';
    document.getElementById('inp-recommend-prompt-b').value = fullSettings.RECOMMEND_SYSTEM_PROMPT_B || '';
    document.getElementById('inp-ask-prompt').value = fullSettings.ASK_SYSTEM_PROMPT || '';
    document.getElementById('inp-ask-prompt-en').value = fullSettings.ASK_SYSTEM_PROMPT_EN || '';
  } catch { }
}

async function saveSettings() {
  const selectedModel = document.getElementById('inp-model-name').value || 'llama3.2';
  fullSettings.AI_PROVIDER = 'ollama';
  fullSettings.QA_AI_PROVIDER = document.getElementById('inp-ai-provider').value || 'ollama';
  fullSettings.MODEL_NAME = selectedModel;
  fullSettings.ASK_MODEL_NAME = selectedModel;
  fullSettings.GEMINI_MODEL_NAME = document.getElementById('inp-gemini-model-name').value.trim() || 'gemini-3-flash-preview';
  fullSettings.GEMINI_FALLBACK_TO_OLLAMA = document.getElementById('inp-gemini-fallback').checked;
  fullSettings.GEMINI_COOLDOWN_SEC = parseInt(document.getElementById('inp-gemini-cooldown').value || '60', 10);
  fullSettings.OLLAMA_TEMPERATURE = parseFloat(document.getElementById('inp-temp').value);
  fullSettings.PERFORMANCE_MODE = document.getElementById('inp-performance-mode').value;
  fullSettings.OLLAMA_NUM_PREDICT = parseInt(document.getElementById('inp-num-predict').value || '220', 10);
  fullSettings.RAG_TOP_K = parseInt(document.getElementById('inp-rag-top-k').value || '3', 10);
  fullSettings.rag = {
    ...(fullSettings.rag || {}),
    use_multi_query: document.getElementById('inp-rag-multi-query').checked,
    use_hybrid_search: document.getElementById('inp-rag-hybrid-search').checked,
    use_reranker: document.getElementById('inp-rag-reranker').checked,
    use_context_compression: document.getElementById('inp-rag-compression').checked,
    use_answer_evaluation: document.getElementById('inp-rag-evaluation').checked,
    top_k_vector: parseInt(document.getElementById('inp-rag-top-k-vector').value || '10', 10),
    top_k_keyword: parseInt(document.getElementById('inp-rag-top-k-keyword').value || '10', 10),
    top_k_final: parseInt(document.getElementById('inp-rag-top-k-final').value || '5', 10),
    context_max_chars: parseInt(document.getElementById('inp-rag-context-max').value || '2600', 10),
    embedding_provider: document.getElementById('inp-rag-embedding-provider').value || 'ollama',
    embedding_model: document.getElementById('inp-rag-embedding-model').value.trim() || 'nomic-embed-text',
    reranker_model: document.getElementById('inp-rag-reranker-model').value.trim() || 'cross-encoder/ms-marco-MiniLM-L-6-v2'
  };
  fullSettings.EMOTION_PING_INTERVAL_SEC = parseFloat(document.getElementById('inp-emotion-interval').value || '15');
  fullSettings.EMOTION_RECORD_MS = parseInt(document.getElementById('inp-emotion-record-ms').value || '900', 10);
  fullSettings.RECOMMEND_INTERVAL_SEC = parseFloat(document.getElementById('inp-recommend-interval').value || '30');
  fullSettings.AUTO_RECOMMEND_MIN_GAP_SEC = parseFloat(document.getElementById('inp-recommend-gap').value || '20');
  fullSettings.AB_SINGLE_CALL = document.getElementById('inp-ab-single-call').checked;
  fullSettings.ENABLE_TTS_CACHE = document.getElementById('inp-tts-cache').checked;
  fullSettings.ENABLE_RECOMMEND_CACHE = document.getElementById('inp-recommend-cache').checked;
  fullSettings.EMOTION_LLAMA_PROMPT = document.getElementById('inp-emotion-prompt').value;
  fullSettings.RECOMMEND_SYSTEM_PROMPT = document.getElementById('inp-recommend-prompt').value;
  fullSettings.RECOMMEND_SYSTEM_PROMPT_B = document.getElementById('inp-recommend-prompt-b').value;
  fullSettings.ASK_SYSTEM_PROMPT = document.getElementById('inp-ask-prompt').value;
  fullSettings.ASK_SYSTEM_PROMPT_EN = document.getElementById('inp-ask-prompt-en').value;
  try {
    await api.saveSettings(fullSettings);
    runtimeSettings = { ...runtimeSettings, ...fullSettings };
    restartLoops();
    alert('設定儲存成功！');
  } catch { alert('儲存失敗！'); }
}

async function loadAdminMenu() {
  try {
    document.getElementById('menuEditor').value = JSON.stringify(await api.getMenu(), null, 4);
  } catch { document.getElementById('menuEditor').value = '[]'; }
}

async function saveMenu() {
  try {
    const data = JSON.parse(document.getElementById('menuEditor').value);
    await api.saveMenu(data);
    alert('菜單已儲存並更新 RAG！');
  } catch { alert('JSON 格式錯誤！'); }
}

async function loadRagData() {
  try {
    const data = await api.getRagDocs();
    const docs = data.docs || [];
    const logs = data.review_logs || [];
    const docsBox = document.getElementById('ragDocsList');
    const logsBox = document.getElementById('ragLogsList');
    if (docsBox) {
      docsBox.innerHTML = '';
      docs.filter(doc => !doc.deleted).reverse().forEach(doc => {
        const row = document.createElement('div');
        row.className = 'p-3 rounded-xl';
        row.style.border = '1.5px solid var(--border)';
        row.style.background = 'var(--surface)';
        row.innerHTML = `
          <div class="flex justify-between gap-3 mb-2">
            <div class="min-w-0">
              <p class="font-bold text-sm truncate" style="color:var(--text)">${escapeHTML(doc.source_type)} / ${escapeHTML(doc.source_id || doc.id)}</p>
              <p class="text-xs" style="color:var(--text2)">${escapeHTML(doc.review_status || '-')} · ${escapeHTML(doc.updated_at || '')}</p>
            </div>
            <button class="text-xs px-2 py-1 rounded-xl" style="color:var(--danger);border:1px solid var(--border)" data-delete-rag="${escapeHTML(doc.id)}"><i class="fas fa-trash mr-1"></i>刪除</button>
          </div>
          <p class="text-xs font-semibold mb-1" style="color:var(--accent2)">審查後文本</p>
          <pre class="text-xs whitespace-pre-wrap break-words max-h-36 overflow-y-auto" style="color:var(--text)">${escapeHTML(doc.reviewed_text || '')}</pre>
          ${doc.review_notes ? `<p class="text-xs mt-2" style="color:var(--text2)">審查備註：${escapeHTML(doc.review_notes)}</p>` : ''}`;
        row.innerHTML += `
          <details class="text-xs mt-2">
            <summary class="cursor-pointer" style="color:var(--accent2)">查看原始文本</summary>
            <pre class="mt-2 p-2 whitespace-pre-wrap break-words rounded-xl max-h-32 overflow-y-auto" style="background:var(--surface2);color:var(--text2)">${escapeHTML(doc.source_text || '')}</pre>
          </details>`;
        row.querySelector('[data-delete-rag]').onclick = async () => {
          if (!confirm('確定刪除這段 RAG 文本並重建向量庫？')) return;
          await api.deleteRagDoc(doc.id);
          await loadRagData();
        };
        docsBox.appendChild(row);
      });
      if (!docsBox.innerHTML) docsBox.innerHTML = `<p class="text-sm" style="color:var(--text2)">目前沒有 RAG 文本。</p>`;
    }
    if (logsBox) {
      logsBox.innerHTML = '';
      logs.slice().reverse().forEach(log => {
        const row = document.createElement('div');
        row.className = 'p-3 rounded-xl';
        row.style.border = '1.5px solid var(--border)';
        row.style.background = 'var(--surface)';
        row.innerHTML = `
          <div class="flex justify-between gap-3 mb-1">
            <p class="font-bold text-sm" style="color:var(--text)">${escapeHTML(log.source_type)} / ${escapeHTML(log.source_id)}</p>
            <button class="text-xs px-2 py-1 rounded-xl" style="color:var(--danger);border:1px solid var(--border)" data-delete-rag-log="${escapeHTML(log._index)}"><i class="fas fa-trash"></i></button>
          </div>
          <p class="text-xs mb-2" style="color:var(--text2)">${escapeHTML(log.timestamp)} · ${escapeHTML(log.review_status)}</p>
          <p class="text-xs mb-1" style="color:var(--text2)">備註：${escapeHTML(log.review_notes || '-')}</p>
          <details class="text-xs">
            <summary class="cursor-pointer" style="color:var(--accent2)">查看審查版本</summary>
            <pre class="mt-2 p-2 whitespace-pre-wrap break-words rounded-xl max-h-36 overflow-y-auto" style="background:var(--surface2);color:var(--text2)">${escapeHTML(log.reviewed_text || '')}</pre>
          </details>`;
        row.querySelector('[data-delete-rag-log]').onclick = async () => {
          if (!confirm('確定刪除這筆 Ollama 審查紀錄？')) return;
          await api.deleteRagReviewLog(log._index);
          await loadRagData();
        };
        logsBox.appendChild(row);
      });
      if (!logsBox.innerHTML) logsBox.innerHTML = `<p class="text-sm" style="color:var(--text2)">目前沒有審查紀錄。</p>`;
    }
  } catch { }
}

async function addRagDoc() {
  const box = document.getElementById('ragNewText');
  const sourceText = box.value.trim();
  if (!sourceText) return alert('請先輸入 RAG 文本。');
  try {
    const data = await api.addRagDoc({ source_text: sourceText });
    if (data.status !== 'success') return alert(data.message || '保存失敗');
    box.value = '';
    await loadRagData();
    alert('已完成 Ollama 審查並保存。');
  } catch {
    alert('保存失敗。');
  }
}

async function loadCustomerServiceData() {
  try {
    const data = await api.getCustomerServiceLogs();
    const box = document.getElementById('customerServiceLogsList');
    if (!box) return;
    const logs = data.logs || [];
    box.innerHTML = '';
    logs.slice().reverse().forEach(log => {
      const row = document.createElement('div');
      row.className = 'p-3 rounded-xl';
      row.style.border = '1.5px solid var(--border)';
      row.style.background = 'var(--surface)';
      const timeText = log.timestamp
        ? new Date(Number(log.timestamp) * 1000).toLocaleString()
        : '-';
      const mediaSrc = log.media_url ? `${API_BASE}${log.media_url}` : '';
      row.innerHTML = `
        <div class="flex justify-between gap-3 mb-2">
          <div class="min-w-0">
            <p class="font-bold text-sm truncate" style="color:var(--text)">${escapeHTML(log.session_id || '-')}</p>
            <p class="text-xs" style="color:var(--text2)">${escapeHTML(timeText)} · ${escapeHTML(log.mode || '-')} · ${escapeHTML(log.language || '-')}</p>
          </div>
          <span class="text-xs px-2 py-1 rounded-xl h-fit" style="background:var(--surface2);color:var(--text2)">${escapeHTML(log.priority || 'normal')}</span>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
          <div>
            <p class="text-xs font-semibold mb-1" style="color:var(--text2)">顧客語音</p>
            <p class="text-sm" style="color:var(--text)">${escapeHTML(log.user_text || '-')}</p>
            ${mediaSrc ? `<audio class="mt-2 w-full" controls src="${escapeHTML(mediaSrc)}"></audio>` : `<p class="text-xs mt-2" style="color:var(--text2)">沒有保存錄音檔。</p>`}
          </div>
          <div>
            <p class="text-xs font-semibold mb-1" style="color:var(--text2)">客服回覆</p>
            <p class="text-sm" style="color:var(--text)">${escapeHTML(log.customer_reply || '-')}</p>
            <textarea class="human-reply-input w-full h-20 mt-2 p-2 rounded-xl text-xs outline-none resize-none" style="border:1px solid var(--border);background:var(--surface2)" placeholder="輸入真人客服回覆文字，按下按鈕後會產生語音播放。">${escapeHTML(log.human_reply || '')}</textarea>
            <button class="human-reply-btn btn-primary px-3 py-2 text-xs mt-2" data-source-id="${escapeHTML(log.source_id || '')}" data-language="${escapeHTML(log.language || 'zh')}">
              <i class="fas fa-volume-up mr-1"></i>客服回覆語音
            </button>
          </div>
        </div>
        <div class="flex flex-wrap gap-2 text-xs mb-2">
          <span class="px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">情緒：${escapeHTML(log.emotion || '-')}</span>
          <span class="px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">RAG：${escapeHTML(log.rag_doc_id || '-')}</span>
        </div>
        <details class="text-xs">
          <summary class="cursor-pointer" style="color:var(--accent2)">客服摘要 / Ollama 原始結果</summary>
          <pre class="mt-2 p-2 whitespace-pre-wrap break-words rounded-xl max-h-36 overflow-y-auto" style="background:var(--surface2);color:var(--text2)">${escapeHTML(log.staff_summary || '')}\n\n${escapeHTML(log.ollama_result || '')}</pre>
        </details>`;
      row.querySelector('.human-reply-btn')?.addEventListener('click', async () => {
        const btn = row.querySelector('.human-reply-btn');
        const reply = row.querySelector('.human-reply-input')?.value.trim();
        if (!reply) return alert('請先輸入真人客服回覆文字。');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>產生中';
        try {
          const data = await api.sendHumanReply(log.source_id, { reply, language: log.language || 'zh' });
          if (data.status !== 'success') throw new Error(data.message || '產生失敗');
          playVoice(data.audio_base64);
          await loadCustomerServiceData();
        } catch (err) {
          alert(err.message || '客服回覆語音產生失敗。');
        } finally {
          btn.disabled = false;
          btn.innerHTML = '<i class="fas fa-volume-up mr-1"></i>客服回覆語音';
        }
      });
      box.appendChild(row);
    });
    if (!box.innerHTML) box.innerHTML = `<p class="text-sm" style="color:var(--text2)">目前沒有客服紀錄。</p>`;
  } catch { }
}

document.getElementById('inp-performance-mode')?.addEventListener('change', (e) => {
  applyPerformancePreset(e.target.value);
});
document.getElementById('inp-model-name')?.addEventListener('change', (e) => {
  const askModelInput = document.getElementById('inp-ask-model-name');
  if (askModelInput) askModelInput.value = e.target.value || 'llama3.2';
});

Object.assign(window, {
  closeVoiceBubble,
  switchMainView,
  switchAdminTab,
  loadInterventionStats,
  loadEmotionClips,
  loadCustomerServiceData,
  clearPushLogs,
  toggleFeature,
  saveSettings,
  clearEmotionClips,
  saveMenu,
  loadRagData,
  clearAllRagDocs,
  addRagDoc,
  uploadRagPdf,
  updateCartQty: trackedUpdateCartQty,
  deleteCartItem: trackedDeleteCartItem,
  trackInteractionEvent,
  reportInteractionEvent,
  maybeCheckBarrierState
});

cartManager.renderCart();
applyFeaturesToPOS();
initAdminToggles();
