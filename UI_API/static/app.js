import * as api from './api.js?v=mediafix-20260520';
import { API_BASE } from './api.js?v=mediafix-20260520';
import {
  ui,
  escapeHTML,
  switchMainView as switchMainViewUI,
  switchAdminTab as switchAdminTabUI,
  updateEmotionCameraPanel as updateEmotionCameraPanelUI,
  updateEmotionDetectionOverlay as updateEmotionDetectionOverlayUI
} from './ui.js?v=mediafix-20260520';
import {
  ensureMediaTracks as ensureMediaTracksCore,
  createVideoRecorder,
  createAudioRecorder,
  captureVideoFrameBlob
} from './media.js?v=mediafix-20260520';
import { createCartManager } from './cart.js?v=mediafix-20260520';
import { createRecommendationManager } from './recommendation.js?v=mediafix-20260520';
import { connectRealtime } from './realtime_client.js?v=mediafix-20260520';
import {
  captureTriggeredClip,
  hasRollingMediaBuffer,
  startRollingMediaBuffer,
  stopRollingMediaBuffer
} from './media_buffer.js?v=mediafix-20260520';

const APP_MODE = (() => {
  const path = window.location.pathname;
  if (window.location.port === '8001') return 'admin';
  if (window.location.port === '8000') return 'pos';
  if (path.startsWith('/admin')) return 'admin';
  if (path.startsWith('/pos')) return 'pos';
  return 'pos';
})();

function isAdminMode() { return APP_MODE === 'admin'; }
function isPosMode() { return APP_MODE === 'pos'; }

// =========================================================
// Controller 狀態
// =========================================================

function buildSessionId() {
  const requested = new URLSearchParams(window.location.search).get('session_id');
  const safeRequested = String(requested || '').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 80);
  return safeRequested || ('pos_' + Math.random().toString(36).substr(2, 9));
}

const sessionId = buildSessionId();
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
let lastInterventionEventAt = 0;
let interactionModalTimer = null;
let pageDwellTimer = null;
let adminRefreshTimer = null;
let interventionStatsLoading = false;
let customerServiceLoading = false;
let posRealtime = null;
let adminRealtime = null;
let kioskScreen = 'categories';
let kioskActiveGroup = '';
let kioskActiveFilter = '全部';
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

const KIOSK_GROUPS = [
  { id: 'recommended', label: '推薦套餐', image: '/static/mcd_categories/recommended.jpg', categories: ['極選系列'] },
  { id: 'value', label: '超值全餐', image: '/static/mcd_categories/value.jpg', categories: ['超值全餐'] },
  { id: 'single', label: '單點餐品', image: '/static/mcd_categories/single.jpg', categories: ['點心', '早餐'] },
  { id: 'drinks', label: '飲料甜點', image: '/static/mcd_categories/drinks.jpg', categories: ['飲料', 'McCafé®', 'McCafé'] },
  { id: 'kids', label: '兒童餐', image: '/static/mcd_categories/kids.jpg', categories: ['早餐', '點心'] },
  { id: 'deals', label: '最新優惠', image: '/static/mcd_categories/deals.jpg', categories: [] },
];
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
  ENABLE_RECOMMEND_CACHE: true,
  EVENT_TRIGGERED_MULTIMODAL_ENABLED: true,
  EMOTION_PERIODIC_ENABLED: false,
  CUSTOMER_SERVICE_MODE: 'ollama'
};

function perfValue(key) {
  return runtimeSettings[key];
}

function isEventTriggeredMultimodalEnabled() {
  return runtimeSettings.EVENT_TRIGGERED_MULTIMODAL_ENABLED !== false;
}

function isPeriodicEmotionEnabled() {
  return runtimeSettings.EMOTION_PERIODIC_ENABLED === true;
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
  if (isSystemRunning && isPosMode()) {
    if (isEventTriggeredMultimodalEnabled()) maybeStartRollingMediaBuffer();
    else stopRollingMediaBuffer();
    if (getFeatures().emotionBackend && isPeriodicEmotionEnabled()) startEmotionLoop();
    startDetectionLoop();
    startRecommendLoop();
  }
}

// =========================================================
// 功能模組狀態
// =========================================================
const FEAT_DEFAULTS = { emotion: true, voiceAsk: false, recommend: true, emotionBackend: false, emotionChat: false, emotionCamera: false, abTest: false, multiLang: true };
const FEATURE_SCHEMA_VERSION = 'event-triggered-20260519';

const INTERACTION_LABELS = {
  barrier: {
    normal_operation: '正常操作',
    menu_hesitation: '菜單選擇猶豫',
    operation_confusion: '操作困惑',
    payment_confusion: '付款卡關',
    coupon_confusion: '優惠券/掃碼卡關',
    impatience_detected: '等待不耐',
    service_needed: '需要真人協助',
    potential_complaint: '疑似客訴',
    low_confidence: '資訊不足',
    unknown: '未知狀態',
  },
  action: {
    none: '不介入',
    show_payment_tutorial: '顯示付款教學',
    show_coupon_guide: '顯示優惠券指引',
    show_operation_hint: '顯示操作提示',
    recommend_popular_combo: '推薦熱門組合',
    call_staff_or_fast_mode: '通知店員或快速模式',
    call_staff: '通知店員',
    ask_clarifying_question: '詢問釐清問題',
    unknown: '未知動作',
  },
  page: {
    startup: '啟動頁',
    menu_page: '菜單頁',
    payment_page: '付款頁',
    checkout_page: '結帳頁',
    completed_page: '完成頁',
    admin_page: '後台頁',
    unknown: '未知頁面',
  },
  event: {
    enter_menu_page: '進入菜單頁',
    enter_payment_page: '進入付款頁',
    page_dwell_timeout: '停留過久',
    back_navigation: '返回上一頁',
    invalid_touch: '無效點擊',
    cart_edit: '購物車修改',
    payment_attempt: '付款嘗試',
    payment_failed: '付款失敗',
    checkout_error: '結帳錯誤',
    coupon_error: '優惠券錯誤',
    customer_service_clicked: '點擊客服',
    customer_service_started: '客服收音開始',
    customer_service_failed: '客服失敗',
    voice_order_started: '語音點餐開始',
    voice_order_failed: '語音點餐失敗',
    voice_ask_started: '語音發問開始',
    unknown: '未知事件',
  },
  source: {
    checkoutBtn: '確認餐點按鈕',
    confirmPayBtn: '確認付款按鈕',
    orderConfirmCloseBtn: '關閉確認訂單',
    confirmBackBtn: '返回修改按鈕',
    orderModalBackdrop: '訂單視窗背景',
    escapeKey: '鍵盤返回',
    posServiceFab: '客服按鈕',
    posServiceRecord: '客服收音按鈕',
    startSystemBtn: '開始點餐按鈕',
    linepay_button: 'LINE Pay 按鈕',
    coupon_input: '優惠券輸入欄',
    menu_grid: '菜單區域',
    service_button: '客服按鈕',
    demo_ui: '實施例腳本',
    page_timer: '頁面停留計時',
    document: '畫面空白處',
    unknown: '未知來源',
  },
};

function zhInteractionLabel(type, value) {
  const raw = String(value || 'unknown');
  const label = INTERACTION_LABELS[type]?.[raw] || raw;
  if (label !== raw) return label;
  if (['barrier', 'action', 'page', 'event', 'source'].includes(type)) return '未分類';
  return raw;
}

function getFeatures() {
  try {
    const saved = JSON.parse(localStorage.getItem('kiosk_feat') || '{}');
    const features = { ...FEAT_DEFAULTS, ...saved };
    if (localStorage.getItem('kiosk_feat_version') !== FEATURE_SCHEMA_VERSION) {
      features.emotionBackend = false;
      localStorage.setItem('kiosk_feat', JSON.stringify(features));
      localStorage.setItem('kiosk_feat_version', FEATURE_SCHEMA_VERSION);
    }
    return features;
  }
  catch { return { ...FEAT_DEFAULTS }; }
}
function saveFeatures(f) {
  localStorage.setItem('kiosk_feat', JSON.stringify(f));
  localStorage.setItem('kiosk_feat_version', FEATURE_SCHEMA_VERSION);
}

function stopEmotionLoop() {
  if (!emotionLoopId) return;
  clearInterval(emotionLoopId);
  emotionLoopId = null;
}

function toggleFeature(key, el) {
  const f = getFeatures();
  f[key] = !f[key];
  saveFeatures(f);
  el.classList.toggle('on', f[key]);
  if (key === 'voiceAsk' && !f.voiceAsk && askRecorder?.state === 'recording') askRecorder.stop();
  if (key === 'emotionBackend' && !f.emotionBackend) stopEmotionLoop();
  applyFeaturesToPOS();
  if (isSystemRunning && (key === 'voiceAsk' || key === 'emotion' || key === 'emotionBackend' || key === 'emotionCamera')) {
    ensureMediaTracks({
      video: f.emotionBackend || f.emotionCamera || isEventTriggeredMultimodalEnabled(),
      audio: true
    }).then(ok => {
      if (ok) setupAskRecorder();
      if (ok) {
        updateEmotionCameraPanel();
        maybeStartRollingMediaBuffer();
        if (key === 'emotionBackend' && f.emotionBackend && isPeriodicEmotionEnabled()) startEmotionLoop();
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
  if (!f.emotionBackend) stopEmotionLoop();
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

function maybeStartRollingMediaBuffer() {
  if (!isPosMode() || !isSystemRunning || !isEventTriggeredMultimodalEnabled()) return false;
  if (!stream || !stream.getVideoTracks().length || !stream.getAudioTracks().length) return false;
  return startRollingMediaBuffer(stream, Number(runtimeSettings.INTERACTION_PRE_EVENT_BUFFER_SEC) || 5);
}

function switchMainView(view) {
  if (view === 'admin' && !isAdminMode()) return;
  switchMainViewUI(view, { clearPOSFloatingUI, loadAdminData, initAdminToggles, applyFeaturesToPOS, loadMenu });
  if (view === 'admin') {
    startAdminRealtime();
    startAdminLiveRefresh();
  } else {
    startPosRealtime();
    stopAdminLiveRefresh();
  }
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

const cartManager = createCartManager({ ui, escapeHTML, findMenuItems, onCartChange: updateKioskCartSummary });

function trackedAddToCart(item, metadata = {}) {
  cartManager.addToCart(item);
  if (isPosMode() && isSystemRunning && metadata.source === 'menu_card') showCartScreen();
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
  if (kioskScreen === 'categories') {
    renderKioskCategories();
    return;
  }
  renderKioskMenuItems();
}

function renderKioskCategories() {
  kioskScreen = 'categories';
  kioskActiveGroup = '';
  kioskActiveFilter = '全部';
  ui.menuGrid.innerHTML = '';
  ui.menuGrid.className = 'kiosk-category-grid';
  if (ui.kioskTitle) ui.kioskTitle.textContent = '';
  if (ui.kioskSubtitle) ui.kioskSubtitle.textContent = '選擇分類後開始點餐';
  document.getElementById('kioskLogo')?.classList.remove('hidden');
  document.getElementById('kioskLangBtn')?.classList.remove('hidden');
  ui.serviceFab?.classList.remove('hidden');
  ui.kioskBackBtn?.classList.add('hidden');
  ui.kioskSearchBtn?.classList.add('hidden');
  ui.kioskSectionHead?.classList.add('hidden');

  const heading = document.createElement('div');
  heading.className = 'kiosk-category-heading';
  heading.textContent = '請選擇餐點類別';
  ui.menuGrid.appendChild(heading);

  KIOSK_GROUPS.forEach(group => {
    const card = document.createElement('button');
    card.className = 'kiosk-category-card';
    card.type = 'button';
    card.onclick = () => showMenuGroup(group.id);
    card.innerHTML = `
      <img src="${group.image}" alt="${escapeHTML(group.label)}" onerror="this.style.display='none'">
      <strong>${escapeHTML(group.label)}</strong>`;
    ui.menuGrid.appendChild(card);
  });
  updateKioskCartSummary();
}

function showMenuGroup(groupId, filter = '全部') {
  kioskScreen = 'menu';
  kioskActiveGroup = groupId;
  kioskActiveFilter = filter;
  renderMenu();
}

function groupItems(groupId) {
  const group = KIOSK_GROUPS.find(g => g.id === groupId) || KIOSK_GROUPS[1];
  if (groupId === 'deals') return menuData.slice(0, 10);
  const allowed = new Set((group.categories || []).map(String));
  return menuData.filter(item => allowed.has(String(item.category || '')));
}

function itemMatchesSubFilter(item, filter) {
  if (!filter || filter === '全部') return true;
  const name = String(item.name || '').replace(/鷄/g, '雞');
  if (filter === '牛肉系列') return /牛|安格斯|大麥克|吉事|四盎司/.test(name);
  if (filter === '雞肉系列') return /雞|脆|辣/.test(name);
  if (filter === '魚肉系列') return /魚/.test(name);
  if (filter === '點心飲料') return /薯|派|湯|茶|可樂|咖啡|那堤|奶茶/.test(name);
  return true;
}

function subFiltersForGroup(groupId) {
  if (groupId === 'value' || groupId === 'recommended') return ['全部', '牛肉系列', '雞肉系列', '魚肉系列'];
  if (groupId === 'single' || groupId === 'drinks' || groupId === 'deals') return ['全部', '點心飲料'];
  return ['全部'];
}

function renderKioskMenuItems() {
  const group = KIOSK_GROUPS.find(g => g.id === kioskActiveGroup) || KIOSK_GROUPS[1];
  const filters = subFiltersForGroup(group.id);
  const items = groupItems(group.id).filter(item => itemMatchesSubFilter(item, kioskActiveFilter));
  ui.menuGrid.innerHTML = '';
  ui.menuGrid.className = 'kiosk-menu-list';
  if (ui.kioskTitle) ui.kioskTitle.textContent = group.label;
  if (ui.kioskSubtitle) ui.kioskSubtitle.textContent = '點選加號加入購物車';
  document.getElementById('kioskLogo')?.classList.add('hidden');
  document.getElementById('kioskLangBtn')?.classList.add('hidden');
  ui.serviceFab?.classList.add('hidden');
  ui.kioskBackBtn?.classList.remove('hidden');
  ui.kioskSearchBtn?.classList.remove('hidden');
  ui.kioskSectionHead?.classList.add('hidden');

  const tabs = document.createElement('div');
  tabs.className = 'kiosk-menu-tabs';
  tabs.innerHTML = filters.map(filter => `
    <button type="button" class="${filter === kioskActiveFilter ? 'active' : ''}" data-filter="${escapeHTML(filter)}">
      ${escapeHTML(filter)}
    </button>`).join('');
  tabs.querySelectorAll('button').forEach(button => {
    button.addEventListener('click', () => showMenuGroup(group.id, button.dataset.filter || '全部'));
  });
  ui.menuGrid.appendChild(tabs);

  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'kiosk-empty-menu';
    empty.textContent = '此分類目前沒有可顯示餐點';
    ui.menuGrid.appendChild(empty);
    return;
  }

  items.forEach(item => {
    const visual = getMenuVisual(item);
    const row = document.createElement('div');
    row.id = `menu-${item.id}`;
    row.className = 'kiosk-menu-row';
    row.innerHTML = `
      <div class="kiosk-menu-photo">
        <img src="${visual.image}" alt="${escapeHTML(item.name)}" onerror="this.style.display='none';this.nextElementSibling.style.display='block'">
        <span class="menu-photo-fallback">${visual.emoji}</span>
      </div>
      <div class="kiosk-menu-copy">
        <h3>${escapeHTML(item.name)}</h3>
        <strong>$${escapeHTML(item.price)}</strong>
      </div>
      <button class="kiosk-add-btn" type="button" aria-label="加入購物車"><i class="fas fa-plus"></i></button>`;
    row.querySelector('.kiosk-add-btn')?.addEventListener('click', event => {
      event.stopPropagation();
      trackedAddToCart(item, { source: 'menu_card' });
    });
    row.addEventListener('click', () => trackedAddToCart(item, { source: 'menu_card' }));
    ui.menuGrid.appendChild(row);
  });
}

function updateKioskCartSummary() {
  const items = cartManager?.getCartItems ? cartManager.getCartItems() : [];
  const total = items.reduce((sum, item) => sum + Number(item.price || 0) * Number(item.quantity || 0), 0);
  const qty = items.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
  if (ui.kioskBottomCount) ui.kioskBottomCount.textContent = String(qty);
  if (ui.kioskBottomTotal) ui.kioskBottomTotal.textContent = `$${total}`;
  if (ui.totalPrice) ui.totalPrice.textContent = `$${total}`;
  if (ui.checkoutBtn) {
    ui.checkoutBtn.disabled = qty <= 0;
    const label = ui.checkoutBtn.querySelector('span');
    if (label) label.textContent = `結帳去 $${total}`;
  }
}

function showCartScreen() {
  document.querySelector('.cart-shell')?.classList.add('kiosk-cart-open');
  ui.kioskBottomBar?.classList.remove('hidden');
  setInteractionPage('checkout_page', { source: 'cart_open' });
  updateKioskCartSummary();
}

function hideCartScreen() {
  document.querySelector('.cart-shell')?.classList.remove('kiosk-cart-open');
  if (!orderCompleted && ui.kioskPaymentScreen?.classList.contains('hidden')) {
    setInteractionPage(kioskScreen === 'categories' ? 'menu_page' : 'menu_page', { source: 'continue_order' });
  }
}

function showPaymentScreen() {
  hideCartScreen();
  ui.kioskPaymentScreen?.classList.remove('hidden');
  ui.kioskPaymentScreen?.setAttribute('aria-hidden', 'false');
  setInteractionPage('payment_page', { source: 'checkout_button' });
  clearPOSFloatingUI();
}

function hidePaymentScreen() {
  ui.kioskPaymentScreen?.classList.add('hidden');
  ui.kioskPaymentScreen?.setAttribute('aria-hidden', 'true');
}

// =========================================================
// POS 互動障礙事件追蹤
// =========================================================
function currentPageId() {
  if (ui.adminView && !ui.adminView.classList.contains('hidden')) return 'admin_page';
  if (orderCompleted) return 'completed_page';
  if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) return 'payment_page';
  if (document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open')) return 'checkout_page';
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

function showAdminNotice(message, type = 'info') {
  if (!ui.adminNotificationBox) return;
  const palette = type === 'error'
    ? { bg: '#fff0f0', border: '#efb2b2', color: '#8a1f1f' }
    : type === 'success'
      ? { bg: '#ecf8ef', border: '#b7dfc3', color: '#245b34' }
      : { bg: '#fff4e8', border: '#f0c9a5', color: '#6b3b19' };
  ui.adminNotificationBox.textContent = message;
  ui.adminNotificationBox.style.background = palette.bg;
  ui.adminNotificationBox.style.borderColor = palette.border;
  ui.adminNotificationBox.style.color = palette.color;
  ui.adminNotificationBox.classList.remove('hidden');
}

function customerServiceMode() {
  return String(runtimeSettings.CUSTOMER_SERVICE_MODE || fullSettings.CUSTOMER_SERVICE_MODE || 'ollama') === 'human'
    ? 'human'
    : 'ollama';
}

function setVisible(el, visible) {
  if (!el) return;
  el.style.display = visible ? '' : 'none';
}

function updateGeminiOptionsVisibility(settings = fullSettings) {
  const enabled = settings?.ENABLE_GEMINI_OPTIONS === true;
  const providerSelect = document.getElementById('inp-ai-provider');
  const geminiOption = providerSelect?.querySelector('option[value="gemini"]');
  if (geminiOption) {
    geminiOption.hidden = !enabled;
    geminiOption.disabled = !enabled;
  }
  if (providerSelect && !enabled) providerSelect.value = 'ollama';

  setVisible(document.getElementById('inp-gemini-model-name')?.closest('div'), enabled);
  setVisible(document.getElementById('inp-gemini-fallback')?.closest('label'), enabled);
  setVisible(document.getElementById('inp-gemini-cooldown')?.closest('div'), enabled);
}

function updateCustomerServiceModeUI(mode = customerServiceMode()) {
  adminServiceOllamaDirect = mode !== 'human';
  ui.adminServiceToggle?.classList.toggle('on', adminServiceOllamaDirect);
  if (ui.adminServiceModeLabel) {
    ui.adminServiceModeLabel.textContent = adminServiceOllamaDirect
      ? '目前模式：Ollama 直接回覆'
      : '目前模式：真人客服模式';
  }
  if (ui.adminServiceResult && adminServiceRecorder?.state !== 'recording') {
    ui.adminServiceResult.textContent = adminServiceOllamaDirect
      ? '目前模式：Ollama 直接回覆。'
      : '目前模式：真人客服模式。POS 客服會立即通知真人客服，不等待 AI 回覆。';
  }
}

function handleRealtimeSettingsChanged(event = {}) {
  const settings = event.payload?.settings;
  if (!settings || typeof settings !== 'object') return;
  fullSettings = { ...fullSettings, ...settings };
  runtimeSettings = { ...runtimeSettings, ...settings };
  updateCustomerServiceModeUI(settings.CUSTOMER_SERVICE_MODE || customerServiceMode());
}

function handleRealtimeHumanReply(event = {}) {
  const payload = event.payload || {};
  if (!payload.reply) return;
  ui.serviceWindow?.classList.add('open');
  setServiceResult(`
    <div class="flex flex-wrap gap-2 mb-3">
      <span class="text-xs px-2 py-0.5 rounded-full" style="background:#dcf5e7;color:var(--success)">真人客服回覆</span>
      <span class="text-xs px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">優先級 ${escapeHTML(payload.priority || '-')}</span>
    </div>
    <p class="text-xs mb-1" style="color:var(--text2)">客服回覆</p>
    <p class="font-semibold" style="color:var(--text)">${escapeHTML(payload.reply || '')}</p>
  `);
  if (payload.audio_base64) playVoice(payload.audio_base64);
}

function handleRealtimeCustomerServiceRequest(event = {}) {
  const payload = event.payload || {};
  showAdminNotice(`收到客服請求：${payload.user_text || payload.customer_service_state || '等待真人處理'}`);
  loadCustomerServiceData({ silent: true });
}

function handleRealtimeInteractionIntervention(event = {}) {
  lastInterventionEventAt = Date.now();
  const payload = event.payload || {};
  applyIntervention(payload.intervention || {}, payload.barrier_result || {});
  if (payload.intervention?.staff_notify) showPushNotice('已通知店員');
}

function handleRealtimeEmotionAnalysisStarted(event = {}) {
  const payload = event.payload || {};
  showAdminNotice(`事件觸發情緒分析開始：${payload.session_id || payload.page_id || 'POS'}`);
}

function handleRealtimeEmotionAnalysisCompleted(event = {}) {
  const payload = event.payload || {};
  const state = payload.barrier_result?.barrier_state || payload.status || 'completed';
  showAdminNotice(`事件觸發情緒分析完成：${zhInteractionLabel('barrier', state)}`, 'success');
  loadInterventionStats();
}

function handleRealtimeStaffNotify(event = {}) {
  const payload = event.payload || {};
  showAdminNotice(`建議店員協助：${payload.reason || payload.barrier_result?.barrier_state || '高風險互動'}`, 'warning');
}

function startPosRealtime() {
  if (!posRealtime) {
    posRealtime = connectRealtime('pos', sessionId, {
      human_reply: handleRealtimeHumanReply,
      interaction_intervention: handleRealtimeInteractionIntervention,
      settings_changed: handleRealtimeSettingsChanged,
    });
  }
}

function startAdminRealtime() {
  if (!adminRealtime) {
    adminRealtime = connectRealtime('admin', 'global', {
      customer_service_request: handleRealtimeCustomerServiceRequest,
      emotion_analysis_started: handleRealtimeEmotionAnalysisStarted,
      emotion_analysis_completed: handleRealtimeEmotionAnalysisCompleted,
      staff_notify: handleRealtimeStaffNotify,
      settings_changed: handleRealtimeSettingsChanged,
    });
  }
}

function initRealtimeClients() {
  if (isPosMode()) startPosRealtime();
  if (isAdminMode()) startAdminRealtime();
}

function startAdminLiveRefresh() {
  if (adminRefreshTimer) return;
  adminRefreshTimer = setInterval(() => {
    if (ui.adminView?.classList.contains('hidden')) return;
    loadInterventionStats();
    loadCustomerServiceData({ silent: true });
  }, 4000);
}

function stopAdminLiveRefresh() {
  if (!adminRefreshTimer) return;
  clearInterval(adminRefreshTimer);
  adminRefreshTimer = null;
}

function isCustomerServiceEditing() {
  const active = document.activeElement;
  return Boolean(
    active?.closest?.('#customerServiceLogsList')
    || adminServiceRecorder?.state === 'recording'
  );
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

function buildInteractionContextForTrigger(riskResult = {}) {
  const reasons = Array.isArray(riskResult.trigger_reasons) ? riskResult.trigger_reasons : [];
  const context = buildUIContext();
  return [
    `目前頁面：${context.page_id || interactionState.pageId}`,
    `購物車數量：${context.cart_count ?? 0}`,
    `風險分數：${riskResult.risk_score ?? 0}`,
    reasons.length ? `觸發原因：${reasons.join('、')}` : '觸發原因：未提供',
    lastVoiceText ? `最近語音：${lastVoiceText.slice(0, 80)}` : '',
  ].filter(Boolean).join('\n');
}

async function maybeCheckBarrierState(riskResult = {}) {
  if (!riskResult.triggered || barrierCheckInFlight) return;
  if (Date.now() - lastBarrierCheckAt < 10000) return;
  barrierCheckInFlight = true;
  lastBarrierCheckAt = Date.now();
  try {
    const uiContext = buildUIContext();
    if (isEventTriggeredMultimodalEnabled() && hasRollingMediaBuffer()) {
      ui.pingInd.style.opacity = '1';
      showPushNotice('情緒分析開始');
      showAdminNotice('事件觸發式多模態分析開始。');
      const blob = await captureTriggeredClip(Number(runtimeSettings.INTERACTION_POST_EVENT_BUFFER_SEC) || 5);
      const fd = new FormData();
      fd.append('session_id', sessionId);
      fd.append('video', blob, 'triggered_interaction.webm');
      fd.append('risk_result_json', JSON.stringify(riskResult || {}));
      fd.append('ui_context_json', JSON.stringify(uiContext));
      fd.append('interaction_context', buildInteractionContextForTrigger(riskResult));
      const data = await api.triggeredMultimodalAnalysis(fd);
      if (data.status === 'success') {
        lastVoiceText = data.speech_text || lastVoiceText;
        lastEmotionStructured = data.emotion_structured || lastEmotionStructured;
        lastMediaSignals = data.multimodal_evidence?.audio_evidence || lastMediaSignals || {};
        showPushNotice('分析完成，等待服務介入推送');
        setTimeout(() => {
          if (
            Date.now() - lastInterventionEventAt > 1800
            && data.intervention?.action
            && data.intervention.action !== 'none'
          ) {
            applyIntervention(data.intervention, data.barrier_result);
            if (data.intervention?.staff_notify) showPushNotice('已通知店員');
          }
        }, 2000);
        return;
      }
      console.warn('[triggered multimodal skipped]', data);
    }

    const data = await api.barrierState({
      session_id: sessionId,
      speech_text: lastVoiceText,
      emotion_structured: lastEmotionStructured || {},
      ui_context: uiContext,
      media_signals: lastMediaSignals || {},
    });
    if (data.status === 'success') {
      applyIntervention(data.intervention, data.barrier_result);
    }
  } catch (err) {
    console.warn('[interaction barrier_state failed]', err);
  } finally {
    ui.pingInd.style.opacity = '0';
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
  const idleBeforeEvent = getIdleTimeSec();
  if (event.event_type === 'back_navigation') interactionState.backCount += 1;
  if (event.event_type === 'invalid_touch') interactionState.invalidTouchCount += 1;
  if (event.event_type === 'payment_failed') interactionState.paymentFailCount += 1;
  if (event.event_type === 'checkout_error') interactionState.paymentFailCount += 1;
  if (event.event_type === 'coupon_error') interactionState.couponErrorCount += 1;
  if (event.event_type === 'cart_edit') interactionState.cartEditCount += 1;
  const payload = normalizeInteractionPayload({
    ...event,
    idle_time_sec: event.idle_time_sec ?? idleBeforeEvent
  });
  interactionState.lastActivityAt = Date.now();
  reportInteractionEvent(payload);
}

function startPageDwellWatcher() {
  if (isAdminMode()) return;
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
  return { ...visual, image: item.image || `/static/menu_${id}.png` };
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
  if (isAdminMode()) return;
  try {
    await loadRuntimeSettings();
    const f = getFeatures();
    const needVideo = f.emotionBackend || f.emotionCamera || isEventTriggeredMultimodalEnabled();
    const needAudio = true;
    const mediaReady = await ensureMediaTracks({ video: needVideo, audio: needAudio });
    if (!mediaReady && (needVideo || needAudio)) console.warn('Media permission unavailable; POS flow continues without rolling buffer.');
    await loadMenu();
    applyFeaturesToPOS();
    ui.serviceFab.style.display = 'flex';
    ui.overlay.style.opacity = '0';
    setTimeout(() => { ui.overlay.classList.add('hidden'); }, 500);
    isSystemRunning = true;
    updateEmotionCameraPanel();
    startPageDwellWatcher();
    setInteractionPage('menu_page', { source: 'start_system' });
    maybeStartRollingMediaBuffer();
    if (f.emotionBackend && isPeriodicEmotionEnabled()) startEmotionLoop();
    startDetectionLoop();
    startRecommendLoop();
    setupAskRecorder();
  } catch { alert("無法存取攝影機與麥克風。"); }
};

function startDetectionLoop() {
  if (isAdminMode()) return;
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
  if (isAdminMode()) return;
  if (!isPeriodicEmotionEnabled()) return;
  if (!getFeatures().emotionBackend) return;
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
      showAdminNotice('Emotion-LLaMA 情緒模型開始分析短片段。');
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
        if (d.status === 'success') showAdminNotice('Emotion-LLaMA 情緒分析完成。', 'success');
        if (d.status === 'not_executed') showAdminNotice('Emotion-LLaMA 本次未執行：模型未連線或功能未啟用。');
      } catch {
        showAdminNotice('Emotion-LLaMA 情緒分析失敗，請檢查推論服務。', 'error');
      }
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
  if (isAdminMode()) return;
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
  if (isAdminMode()) return;
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
  const acceptedNote = data.accepted
    ? '<p class="text-xs mb-2 font-semibold" style="color:var(--accent2)">已立即通知客服；語音文字與情緒證據會在背景完成後更新到客服紀錄。</p>'
    : '';
  targetEl.innerHTML = `
    <div class="flex flex-wrap gap-2 mb-3">
      <span class="text-xs px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">語系 ${escapeHTML(langLabel)}</span>
      <span class="text-xs px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">情緒 ${escapeHTML(formatEmotion(data.emotion || '-'))}</span>
      <span class="text-xs px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">優先級 ${escapeHTML(data.priority || '-')}</span>
    </div>
    ${acceptedNote}
    <p class="text-xs mb-1" style="color:var(--text2)">顧客</p>
    <p class="mb-2 font-medium" style="color:var(--text)">${escapeHTML(data.user_text || data.staff_summary || '')}</p>
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

  const serviceMode = runtimeSettings.CUSTOMER_SERVICE_MODE || 'ollama';
  const useOllama = serviceMode !== 'human';
  setServiceResult(useOllama ? '正在分析客服語音，請稍候。' : '已通知真人客服，請稍候。');
  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('media', blob, 'pos_customer_service.webm');
  fd.append('use_ollama', String(useOllama));
  fd.append('multi_lang', String(getFeatures().multiLang));
  try {
    const data = await api.customerService(fd);
    if (data.status !== 'success') throw new Error(data.message || '客服流程失敗');
    renderServiceResponse(ui.serviceResult, data);
    if (useOllama && data.audio_base64) playVoice(data.audio_base64);
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
  ui.adminServiceResult.textContent = adminServiceOllamaDirect
    ? '正在收音，停止後會分析語系、情緒並產生 AI 客服回覆。'
    : '正在收音，真人模式只會保存顧客錄音、文字與情緒判斷，不會讓 Ollama 直接回覆。';
  showAdminNotice('客服情緒模型將在收音完成後啟動分析。');
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

  const useOllama = customerServiceMode() !== 'human';
  ui.adminServiceResult.textContent = useOllama
    ? '正在分析客服語音並產生 AI 回覆，請稍候。'
    : '已收到客服錄音，正在保存文字與情緒證據；Ollama 直接回覆已關閉。';
  showAdminNotice('客服情緒模型開始分析顧客錄音。');
  const fd = new FormData();
  fd.append('session_id', `${sessionId}_admin_service`);
  fd.append('media', blob, 'admin_customer_service.webm');
  fd.append('use_ollama', String(useOllama));
  fd.append('multi_lang', String(getFeatures().multiLang));
  try {
    const data = await api.customerService(fd);
    if (data.status !== 'success') throw new Error(data.message || '客服流程失敗');
    renderServiceResponse(ui.adminServiceResult, data);
    await loadCustomerServiceData();
    showAdminNotice(
      useOllama ? '客服分析與 AI 回覆已完成。' : '真人客服模式已保存顧客錄音與文字，未產生 Ollama 直接回覆。',
      'success'
    );
    if (useOllama && data.audio_base64) playVoice(data.audio_base64);
  } catch (err) {
    ui.adminServiceResult.textContent = err.message || '客服流程失敗。';
    showAdminNotice('客服流程失敗，請檢查後端或情緒模型服務。', 'error');
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
  ui.adminServiceToggle.onclick = async () => {
    const nextMode = customerServiceMode() === 'human' ? 'ollama' : 'human';
    fullSettings = { ...fullSettings, CUSTOMER_SERVICE_MODE: nextMode };
    runtimeSettings = { ...runtimeSettings, CUSTOMER_SERVICE_MODE: nextMode };
    updateCustomerServiceModeUI(nextMode);
    try {
      await api.saveSettings(fullSettings);
      showAdminNotice(
        nextMode === 'human' ? '已切換為真人客服模式。' : '已切換為 Ollama 直接回覆模式。',
        'success'
      );
    } catch {
      const rollbackMode = nextMode === 'human' ? 'ollama' : 'human';
      fullSettings = { ...fullSettings, CUSTOMER_SERVICE_MODE: rollbackMode };
      runtimeSettings = { ...runtimeSettings, CUSTOMER_SERVICE_MODE: rollbackMode };
      updateCustomerServiceModeUI(rollbackMode);
      showAdminNotice('客服模式儲存失敗，已還原。', 'error');
    }
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
    ui.kioskFastPayBtn,
    ui.kioskCounterPayBtn,
    ui.kioskPaymentBackBtn,
    ui.kioskCancelOrderBtn,
    ...document.querySelectorAll('[data-fulfillment], [data-payment]')
  ]
    .filter(Boolean)
    .forEach(button => { button.disabled = disabled; });
}

function showCompletionOverlay(title, subtitle) {
  switchMainView('pos');
  closeOrderConfirmModal();
  hidePaymentScreen();
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
  showPaymentScreen();
}

function closeOrderConfirmModal() {
  ui.orderConfirmModal?.classList.add('hidden');
  ui.orderConfirmModal?.setAttribute('aria-hidden', 'true');
  hidePaymentScreen();
  if (!orderCompleted) setInteractionPage('menu_page', { source: 'close_order_confirm' });
}

ui.checkoutBtn.onclick = () => {
  if (!cartManager.getCartIds().length) return;
  openOrderConfirmModal();
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'enter_payment_page',
    button_id: 'checkoutBtn',
    metadata: { cart_ids: cartManager.getCartIds() }
  });
};

ui.kioskBackBtn?.addEventListener('click', () => {
  if (kioskScreen === 'menu') renderKioskCategories();
});
ui.kioskHomeBtn?.addEventListener('click', () => {
  hideCartScreen();
  hidePaymentScreen();
  renderKioskCategories();
});
ui.kioskCartBtn?.addEventListener('click', () => {
  if (cartManager.getCartIds().length) showCartScreen();
});
ui.continueOrderBtn?.addEventListener('click', () => {
  hideCartScreen();
  if (kioskScreen === 'categories') showMenuGroup('value');
});
ui.clearCartBtn?.addEventListener('click', () => {
  cartManager.clearCart();
  hideCartScreen();
  renderKioskCategories();
});
ui.kioskPaymentBackBtn?.addEventListener('click', () => {
  hidePaymentScreen();
  showCartScreen();
});
ui.kioskCancelOrderBtn?.addEventListener('click', () => {
  cartManager.clearCart();
  hidePaymentScreen();
  renderKioskCategories();
});
ui.kioskFastPayBtn?.addEventListener('click', () => {
  const cartIds = cartManager.getCartIds();
  if (!cartIds.length) return;
  selectedPayment = 'credit-card';
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_attempt',
    button_id: 'kioskFastPayBtn',
    metadata: { payment: selectedPayment, fulfillment: selectedFulfillment, cart_ids: cartIds }
  });
  finishOrder(cartIds, ui.kioskFastPayBtn, '結帳中...', '點餐完成！');
});
ui.kioskCounterPayBtn?.addEventListener('click', () => {
  const cartIds = cartManager.getCartIds();
  if (!cartIds.length) return;
  selectedPayment = 'counter';
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_attempt',
    button_id: 'kioskCounterPayBtn',
    metadata: { payment: selectedPayment, fulfillment: selectedFulfillment, cart_ids: cartIds }
  });
  finishOrder(cartIds, ui.kioskCounterPayBtn, '建立櫃檯付款單...', '請至櫃檯付款');
});

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
    page_id: 'payment_page',
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

function topCountLabel(counts = {}, labelType = '') {
  const entries = Object.entries(counts || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
  if (!entries.length) return '-';
  return `${zhInteractionLabel(labelType, entries[0][0])} (${entries[0][1]})`;
}

function renderCountList(containerId, counts = {}, labelType = '') {
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
          <span class="truncate" style="color:var(--text)">${escapeHTML(zhInteractionLabel(labelType, label))}</span>
          <b style="color:var(--accent2)">${value}</b>
        </div>
        <div class="h-2 rounded-full overflow-hidden" style="background:var(--surface2)">
          <i class="block h-full rounded-full" style="width:${width}%;background:var(--accent)"></i>
        </div>
      </div>`;
  }).join('');
}

async function loadInterventionStats() {
  if (interventionStatsLoading) return;
  interventionStatsLoading = true;
  try {
    const data = await api.getInterventionStats();
    if (data.status !== 'success') throw new Error(data.message || 'stats failed');
    const total = Number(data.total_interventions || 0);
    const successRate = Math.round(Number(data.success_rate || 0) * 100);
    document.getElementById('intervention-total').textContent = total;
    document.getElementById('intervention-success-rate').textContent = `${successRate}%`;
    document.getElementById('intervention-top-state').textContent = topCountLabel(data.barrier_state_counts, 'barrier');
    document.getElementById('intervention-top-action').textContent = topCountLabel(data.action_counts, 'action');
    renderCountList('barrierStateCounts', data.barrier_state_counts, 'barrier');
    renderCountList('interventionActionCounts', data.action_counts, 'action');
    renderCountList(
      'pageIssueCounts',
      data.event_page_issue_counts || data.intervention_page_counts || data.page_issue_counts,
      'page'
    );

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
      const barrierLabel = zhInteractionLabel('barrier', barrier.barrier_state || '-');
      const actionLabel = zhInteractionLabel('action', intervention.action || '-');
      const pageLabel = zhInteractionLabel('page', uiContext.page_id || '-');
      tr.innerHTML = `
        <td class="p-3 text-xs" style="color:var(--text2)">${log.timestamp ? new Date(log.timestamp).toLocaleString() : '-'}</td>
        <td class="p-3 text-xs" style="color:var(--text)">${escapeHTML(pageLabel)}</td>
        <td class="p-3 text-xs" style="color:var(--accent2)">${escapeHTML(barrierLabel)}</td>
        <td class="p-3 text-xs" style="color:var(--info)">${escapeHTML(actionLabel)}</td>
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
      const eventPageLabel = zhInteractionLabel('page', event.page_id || '-');
      const eventTypeLabel = zhInteractionLabel('event', event.event_type || '-');
      const sourceLabel = zhInteractionLabel('source', source);
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="p-3 text-xs" style="color:var(--text2)">${event.timestamp ? new Date(event.timestamp).toLocaleString() : '-'}</td>
        <td class="p-3 text-xs" style="color:var(--text)">${escapeHTML(eventPageLabel)}</td>
        <td class="p-3 text-xs" style="color:var(--accent2)">${escapeHTML(eventTypeLabel)}</td>
        <td class="p-3 text-xs" style="color:var(--text2)">${escapeHTML(sourceLabel)}</td>`;
      eventsBody.appendChild(tr);
    });
    if (!events.length) {
      eventsBody.innerHTML = `<tr><td colspan="4" class="p-4 text-center text-sm" style="color:var(--text2)">尚無 POS 操作事件。</td></tr>`;
    }
  } catch {
    renderCountList('barrierStateCounts', {});
    renderCountList('interventionActionCounts', {});
    renderCountList('pageIssueCounts', {});
  } finally {
    interventionStatsLoading = false;
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
      const url = clip.url ? `${API_BASE}${clip.url}` : '';
      const personLabel = clip.person_detected ? '偵測到人物' : '未偵測到人物';
      const hitCount = clip.person_hits ?? clip.face_hits ?? 0;
      const signals = clip.media_signals || {};
      const signalText = signals.motion_level
        ? `音量 ${signals.audio_mean_db ?? '-'} dB / 動作 ${signals.motion_level}`
        : '';
      const mediaHtml = url
        ? `<video controls muted playsinline preload="metadata" src="${escapeHTML(url)}"></video>`
        : `<div class="clip-media-placeholder">
            <i class="fas fa-shield-alt"></i>
            <span>已依隱私設定只保存分析資料</span>
          </div>`;
      item.innerHTML = `
        ${mediaHtml}
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
            ${clip.raw_clip_saved ? '<span>raw saved</span>' : '<span>metadata only</span>'}
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
    updateGeminiOptionsVisibility(fullSettings);
    const allowGemini = fullSettings.ENABLE_GEMINI_OPTIONS === true;
    const qaProvider = allowGemini ? (fullSettings.QA_AI_PROVIDER || 'ollama') : 'ollama';
    document.getElementById('inp-ai-provider').value = qaProvider;
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
    updateCustomerServiceModeUI(fullSettings.CUSTOMER_SERVICE_MODE || 'ollama');
  } catch { }
}

async function saveSettings() {
  const selectedModel = document.getElementById('inp-model-name').value || 'llama3.2';
  const allowGemini = fullSettings.ENABLE_GEMINI_OPTIONS === true;
  fullSettings.AI_PROVIDER = 'ollama';
  fullSettings.QA_AI_PROVIDER = allowGemini
    ? (document.getElementById('inp-ai-provider').value || 'ollama')
    : 'ollama';
  fullSettings.EMOTION_AI_PROVIDER = 'ollama';
  fullSettings.MODEL_NAME = selectedModel;
  fullSettings.ASK_MODEL_NAME = selectedModel;
  fullSettings.GEMINI_MODEL_NAME = document.getElementById('inp-gemini-model-name').value.trim() || 'gemini-3-flash-preview';
  fullSettings.CUSTOMER_SERVICE_MODE = customerServiceMode();
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

async function loadCustomerServiceData(options = {}) {
  if (customerServiceLoading) return;
  if (options.silent && isCustomerServiceEditing()) return;
  customerServiceLoading = true;
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
      const serviceState = log.customer_service_state || '-';
      const needsHumanStaff = log.needs_human_staff === true ? '是' : '否';
      const servicePriority = log.customer_service_priority || log.priority || 'normal';
      const serviceEvidence = Array.isArray(log.service_state_evidence)
        ? log.service_state_evidence
        : (log.service_state_evidence ? [String(log.service_state_evidence)] : []);
      const serviceEvidenceText = serviceEvidence.length
        ? serviceEvidence.map(item => `- ${item}`).join('\n')
        : '-';
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
          <span class="px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">客服狀態：${escapeHTML(serviceState)}</span>
          <span class="px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">真人協助：${escapeHTML(needsHumanStaff)}</span>
          <span class="px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">狀態優先級：${escapeHTML(servicePriority)}</span>
        </div>
        <details class="text-xs">
          <summary class="cursor-pointer" style="color:var(--accent2)">客服摘要 / 狀態證據 / Ollama 原始結果</summary>
          <pre class="mt-2 p-2 whitespace-pre-wrap break-words rounded-xl max-h-44 overflow-y-auto" style="background:var(--surface2);color:var(--text2)">${escapeHTML(log.staff_summary || '')}\n\n客服狀態證據：\n${escapeHTML(serviceEvidenceText)}\n\n${escapeHTML(log.ollama_result || '')}</pre>
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
  } catch {
    if (!options.silent) showAdminNotice('客服紀錄更新失敗。', 'error');
  } finally {
    customerServiceLoading = false;
  }
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

if (isAdminMode()) {
  switchMainView('admin');
  initRealtimeClients();
} else {
  cartManager.renderCart();
  applyFeaturesToPOS();
  initAdminToggles();
  initRealtimeClients();
}
