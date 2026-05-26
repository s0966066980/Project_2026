import * as api from './api.js?v=20260527';
import { API_BASE } from './api.js?v=20260527';
import {
  ui,
  escapeHTML,
  switchMainView as switchMainViewUI,
  switchAdminTab as switchAdminTabUI,
  updateEmotionCameraPanel as updateEmotionCameraPanelUI,
  updateEmotionDetectionOverlay as updateEmotionDetectionOverlayUI
} from './ui.js?v=20260527';
import {
  ensureMediaTracks as ensureMediaTracksCore,
  createVideoRecorder,
  createAudioRecorder,
  captureVideoFrameBlob
} from './media.js?v=20260527';
import { createCartManager } from './cart.js?v=20260527';
import { createRecommendationManager } from './recommendation.js?v=20260527';
import { connectRealtime } from './realtime_client.js?v=20260527';
import {
  captureTriggeredClip,
  hasRollingMediaBuffer,
  startRollingMediaBuffer,
  stopRollingMediaBuffer
} from './media_buffer.js?v=20260527';

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
let sessionEmotionLog = [];
let isSystemRunning = false;
let orderCompleted = false;
let menuData = [];
let sessionPushedIds = new Set();
let recommendPending = false;
let voiceBubbleTimer = null;
let emotionCardTimer = null;
let emotionLoopId = null;
let detectionLoopId = null;
let detectionInFlight = false;
let recommendLoopId = null;
let recommendRequestInFlight = false;
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
let posRealtime = null;
let adminRealtime = null;
let voiceOrderingAvailable = false;
let autoVoiceTimer = null;
let autoVoiceInFlight = false;
let askRecordingStartedAt = 0;
let lastValidOrderActionAt = 0;
let kioskScreen = 'categories';
let kioskActiveGroup = '';
let kioskActiveFilter = '全部';
let kioskLang = localStorage.getItem('kiosk_lang') === 'en' ? 'en' : 'zh';
const interactionState = {
  pageId: 'startup',
  pageEnteredAt: Date.now(),
  lastActivityAt: Date.now(),
  backCount: 0,
  invalidTouchCount: 0,
  paymentFailCount: 0,
  couponErrorCount: 0,
  cartEditCount: 0,
  categorySwitchCount: 0,
  cartRemoveCount: 0,
  recommendIgnoreCount: 0,
  lastReportedDwellPage: '',
};

const KIOSK_GROUPS = [
  { id: 'recommended', label: '推薦套餐', labelEn: 'Recommended Meals', image: '/static/mcd_categories/recommended.jpg', categories: ['超值全餐', '極選系列'], featuredLimit: 10 },
  { id: 'value', label: '超值全餐', labelEn: 'Value Meals', image: '/static/mcd_categories/value.jpg', categories: ['超值全餐'] },
  { id: 'premium', label: '極選系列', labelEn: 'Signature Meals', image: '/static/menu_images/MCD014.jpg', categories: ['極選系列'] },
  { id: 'side', label: '超值配餐', labelEn: 'Value Sides', image: '/static/mcd_categories/single.jpg', categories: ['超值全餐配餐'] },
  { id: 'plusone', label: '1+1星級點', labelEn: '1+1 Star Picks', image: '/static/mcd_categories/value.jpg', categories: ['1+1星級點'] },
  { id: 'sharebox', label: '分享盒', labelEn: 'Share Box', image: '/static/mcd_categories/recommended.jpg', categories: ['麥當勞分享盒'] },
  { id: 'happymeal', label: 'Happy Meal®', labelEn: 'Happy Meal®', image: '/static/mcd_categories/single.jpg', categories: ['Happy Meal®'] },
  { id: 'single', label: '單點餐品', labelEn: 'A La Carte', image: '/static/mcd_categories/single.jpg', categories: ['點心'] },
  { id: 'drinks', label: '飲料甜點', labelEn: 'Drinks & Desserts', image: '/static/mcd_categories/drinks.jpg', categories: ['飲料', 'McCafé®', 'McCafé'] },
  { id: 'breakfast', label: '早餐', labelEn: 'Breakfast', image: '/static/menu_images/MCD029.jpg', categories: ['早餐'] },
];

const KIOSK_TEXT = {
  zh: {
    chooseCategory: '請選擇餐點類別',
    chooseCategorySub: '選擇分類後開始點餐',
    addHint: '點選加號加入購物車',
    searchFilter: '搜尋<br>篩選',
    home: '回首頁',
    emptyCategory: '此分類目前沒有可顯示餐點',
    addToCart: '加入購物車',
    checkoutGo: '結帳去',
    continueOrder: '繼續點餐',
    clearCart: '清空購物車',
    yourCart: '您的購物車',
    fastPayKicker: '點點卡、信用卡、掃碼支付',
    fastPayTitle: '在此快速結帳',
    counterPay: '至櫃檯排隊付款',
    backCart: '回購物車',
    cancelOrder: '取消整單訂單',
    paymentTitle: '請選擇付款方式',
    menuFallback: '目前沒有選擇任何餐點。',
    langButton: '中文',
    friendlyMode: '友善模式',
    total: '總計',
    subtotal: '小計',
    secureCheckout: '安全交易 · 安心結帳',
    checkoutDone: '點餐完成！',
    thankYou: '感謝您的使用 · Thank you',
    cartCount: '共 {count} 項',
    cartEmptyTitle: '購物車是空的',
    cartEmptySub: '快去選擇喜愛的餐點吧！',
    holdVoiceOrder: '語音模式',
    voiceAskHint: '語音協助開啟後可點餐與詢問 AI 助理',
    listeningAsk: '收音中...',
    listeningOrder: '聆聽語音協助中...',
    aiThinking: 'AI 思考中...',
    recognizingOrder: '辨識餐點中...',
    languageZh: '繁體中文',
    languageEn: 'English',
    emotion: '情緒',
    priority: '優先級',
    customer: '顧客',
    addedToCart: '已加入購物車：{items}',
    noVoiceOrderItem: '沒有在菜單中找到可加入購物車的餐點。',
    networkFailed: '網路連線失敗，請稍後再試。',
    voiceOrderFailed: '語音協助失敗，請稍後再試。',
    voiceTooShort: '沒有聽到完整語音，請再說一次。',
    voiceMicNotReady: '麥克風尚未準備完成，請確認瀏覽器麥克風權限。',
    zhOutput: '繁體中文輸出',
    enOutput: 'English output',
    checkoutProcessing: '結帳中...',
    counterPayCreating: '建立櫃檯付款單...',
    counterPayDone: '請至櫃檯付款',
    filters: {
      '全部': '全部',
      '牛肉系列': '牛肉系列',
      '雞肉系列': '雞肉系列',
      '魚肉系列': '魚肉系列',
      '點心飲料': '點心飲料',
    },
  },
  en: {
    chooseCategory: 'Choose a Category',
    chooseCategorySub: 'Select a category to start ordering',
    addHint: 'Tap plus to add to cart',
    searchFilter: 'Search<br>Filter',
    home: 'Home',
    emptyCategory: 'No items in this category',
    addToCart: 'Add to Cart',
    checkoutGo: 'Checkout',
    continueOrder: 'Continue Ordering',
    clearCart: 'Clear Cart',
    yourCart: 'Your Cart',
    fastPayKicker: 'Card, credit card, QR payment',
    fastPayTitle: 'Quick Checkout Here',
    counterPay: 'Pay at Counter',
    backCart: 'Back to Cart',
    cancelOrder: 'Cancel Order',
    paymentTitle: 'Choose Payment Method',
    menuFallback: 'No items selected.',
    langButton: 'EN',
    friendlyMode: 'Accessibility Mode',
    total: 'Total',
    subtotal: 'Subtotal',
    secureCheckout: 'Secure Checkout',
    checkoutDone: 'Order Complete!',
    thankYou: 'Thank you',
    cartCount: '{count} items',
    cartEmptyTitle: 'Your cart is empty',
    cartEmptySub: 'Choose your favorite meal to begin.',
    holdVoiceOrder: 'Voice Mode',
    voiceAskHint: 'Enable voice assistance for ordering and AI questions',
    listeningAsk: 'Listening...',
    listeningOrder: 'Listening for voice assist...',
    aiThinking: 'AI is thinking...',
    recognizingOrder: 'Recognizing order...',
    languageZh: 'Traditional Chinese',
    languageEn: 'English',
    emotion: 'Emotion',
    priority: 'Priority',
    customer: 'Customer',
    addedToCart: 'Added to cart: {items}',
    noVoiceOrderItem: 'No matching menu item was found.',
    networkFailed: 'Network failed. Please try again later.',
    voiceOrderFailed: 'Voice assistance failed. Please try again later.',
    voiceTooShort: 'I did not hear a complete request. Please try again.',
    voiceMicNotReady: 'The microphone is not ready. Please check browser microphone permission.',
    zhOutput: 'Traditional Chinese output',
    enOutput: 'English output',
    checkoutProcessing: 'Checking out...',
    counterPayCreating: 'Creating counter payment...',
    counterPayDone: 'Please pay at the counter',
    filters: {
      '全部': 'All',
      '牛肉系列': 'Beef',
      '雞肉系列': 'Chicken',
      '魚肉系列': 'Fish',
      '安格斯系列': 'Angus',
      '早餐系列': 'Breakfast',
      '點心飲料': 'Snacks & Drinks',
    },
  },
};

function kt(key) {
  return KIOSK_TEXT[kioskLang]?.[key] || KIOSK_TEXT.zh[key] || key;
}

function kFilterLabel(filter) {
  return KIOSK_TEXT[kioskLang]?.filters?.[filter] || filter;
}

function groupLabel(group) {
  return kioskLang === 'en' ? (group.labelEn || group.label) : group.label;
}
let runtimeSettings = {
  PERFORMANCE_MODE: 'balanced',
  EMOTION_PING_INTERVAL_SEC: 15,
  EMOTION_RECORD_MS: 900,
  YOLO_FRAME_INTERVAL_MS: 650,
  RECOMMEND_INTERVAL_SEC: 10,
  RECOMMEND_AFTER_ASK_DELAY_MS: 1200,
  OLLAMA_NUM_PREDICT: 220,
  RAG_TOP_K: 3,
  ENABLE_TTS_CACHE: true,
  EVENT_TRIGGERED_MULTIMODAL_ENABLED: true,
  EMOTION_PERIODIC_ENABLED: false
};

function perfValue(key) {
  return runtimeSettings[key];
}

function isEventTriggeredMultimodalEnabled() {
  return getFeatures().emotion && runtimeSettings.EVENT_TRIGGERED_MULTIMODAL_ENABLED !== false;
}

function isPeriodicEmotionEnabled() {
  return runtimeSettings.EMOTION_PERIODIC_ENABLED === true;
}

function isDemoPublicMode() {
  return runtimeSettings.DEMO_PUBLIC_MODE === true || runtimeSettings.DEMO_PUBLIC_MODE === 'true';
}

async function loadRuntimeSettings() {
  try {
    const settings = isAdminMode() ? await api.getSettings() : await api.getPublicSettings();
    runtimeSettings = { ...runtimeSettings, ...settings };
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
    startRecommendLoop();
  }
}

// =========================================================
// 功能模組狀態
// =========================================================
const FEAT_DEFAULTS = {
  emotion: true,
  voiceAssist: true,
  recommend: true,
  emotionBackend: false,
  emotionChat: false,
  emotionCamera: false,
  emotionRecommend: true,
  eventTriggeredMultimodal: true,
  multiLang: true
};
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
    voice_assist_started: '語音協助開始',
    voice_assist_failed: '語音協助失敗',
    voice_ask_started: '語音協助開始',
    unknown: '未知事件',
  },
  source: {
    checkoutBtn: '確認餐點按鈕',
    confirmPayBtn: '確認付款按鈕',
    orderConfirmCloseBtn: '關閉確認訂單',
    confirmBackBtn: '返回修改按鈕',
    orderModalBackdrop: '訂單視窗背景',
    escapeKey: '鍵盤返回',
    voiceAssistBtn: '語音協助按鈕',
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
    const versionMatches = localStorage.getItem('kiosk_feat_version') === FEATURE_SCHEMA_VERSION;
    const hasSavedFeatures = Boolean(localStorage.getItem('kiosk_feat'));
    const saved = JSON.parse(localStorage.getItem('kiosk_feat') || '{}');
    const features = { ...FEAT_DEFAULTS, ...saved };
    const shouldApplyDemoDefaults = isDemoPublicMode() && (!hasSavedFeatures || !versionMatches);
    if (!versionMatches || shouldApplyDemoDefaults) {
      features.emotionBackend = false;
      if (shouldApplyDemoDefaults) {
        features.voiceAssist = true;
        features.recommend = true;
        features.emotionBackend = false;
        features.emotionCamera = false;
        features.eventTriggeredMultimodal = true;
      }
      localStorage.setItem('kiosk_feat', JSON.stringify(features));
      localStorage.setItem('kiosk_feat_version', FEATURE_SCHEMA_VERSION);
    }
    return features;
  }
  catch {
    const features = { ...FEAT_DEFAULTS };
    if (isDemoPublicMode()) {
      features.voiceAssist = true;
      features.recommend = true;
      features.emotionBackend = false;
      features.emotionCamera = false;
      features.eventTriggeredMultimodal = true;
    }
    return features;
  }
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
  if (key === 'voiceAssist' && !f.voiceAssist && askRecorder?.state === 'recording') askRecorder.stop();
  if ((key === 'emotion' || key === 'emotionBackend') && (!f.emotion || !f.emotionBackend)) stopEmotionLoop();
  applyFeaturesToPOS();
  if (isSystemRunning && (key === 'voiceAssist' || key === 'emotion' || key === 'emotionBackend')) {
    ensureMediaTracks({
      video: f.emotionBackend || isEventTriggeredMultimodalEnabled(),
      audio: true
    }).then(ok => {
      if (ok) setupAskRecorder();
      if (ok) {
        updateEmotionCameraPanel();
        maybeStartRollingMediaBuffer();
        if (key === 'emotionBackend' && f.emotionBackend && isPeriodicEmotionEnabled()) startEmotionLoop();
      }
    });
  }
  if (key === 'emotion') updateEmotionAdminVisibility();
  if (key === 'emotionRecommend') loadEmotionStatus();
}

function applyFeaturesToPOS() {
  const f = getFeatures();
  const center = document.getElementById('centerPanel');
  // 攝影機作為背景感測來源保留，不在 POS 版面中顯示欄位
  const cam = document.getElementById('mod-camera');
  if (cam) cam.style.display = 'none';
  // 語音協助按鈕只出現在底部導覽列，不出現在購物車、付款、完成頁。
  updateVoiceAssistVisibility();
  // 感測區永遠不佔版面，避免功能關閉後留下空白 UI 欄位
  if (center) center.style.display = 'none';
  // 語音回覆氣泡（關閉語音協助時隱藏）
  if (!f.voiceAssist) closeVoiceBubble();
  // 推播（關閉時清除現有浮動卡）
  if (!f.recommend) clearAllPushCards();
  if (!f.emotionChat) clearEmotionCards();
  if (!f.emotionBackend) stopEmotionLoop();
  if (!f.emotion && detectionLoopId) {
    clearInterval(detectionLoopId);
    detectionLoopId = null;
  } else if (f.emotion && !detectionLoopId && isSystemRunning && isPosMode()) {
    startDetectionLoop();
  }
  if (!f.emotion) setVoiceOrderingAvailable(true);
  updateEmotionCameraPanel();
}

function isCartScreenOpen() {
  return Boolean(document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open'));
}

function updateVoiceAssistVisibility() {
  const voiceAssistMod = document.getElementById('mod-voice-assist');
  if (!voiceAssistMod) return;
  const paymentOpen = ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden');
  const visible = getFeatures().voiceAssist && isPosMode() && !isCartScreenOpen() && !paymentOpen && !orderCompleted;
  voiceAssistMod.classList.toggle('hidden', !visible);
}

function isPosActive() {
  return isSystemRunning && !orderCompleted && ui.posView && !ui.posView.classList.contains('hidden');
}

function clearPOSFloatingUI() {
  clearAllPushCards();
  clearEmotionCards();
  closeVoiceBubble();
  hideVoiceAssistOverlay();
  if (ui.emotionCameraPanel) ui.emotionCameraPanel.classList.add('hidden');
}

function initAdminToggles() {
  const f = getFeatures();
  Object.keys(FEAT_DEFAULTS).forEach(key => {
    const el = document.getElementById('tog-' + key);
    if (el) el.classList.toggle('on', f[key]);
  });
  updateEmotionAdminVisibility();
}

function updateEmotionAdminVisibility() {
  const visible = Boolean(getFeatures().emotion);
  const tabBtn = document.getElementById('tab-btn-emotion');
  const tabContent = document.getElementById('tab-emotion');
  if (tabBtn) tabBtn.classList.toggle('hidden', !visible);
  if (!visible && tabContent && !tabContent.classList.contains('hidden')) {
    switchAdminTab('features');
  }
}

async function loadEmotionStatus() {
  const statusBox = document.getElementById('emotionStatusBox');
  if (!statusBox) return;
  statusBox.innerHTML = '<span class="text-sm" style="color:var(--text2)">檢查 Emotion-LLaMA 連線中...</span>';
  try {
    const data = await api.getEmotionStatus();
    const ok = Boolean(data.available);
    statusBox.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div class="rounded-xl p-4" style="background:var(--surface2)">
          <p class="text-xs font-semibold" style="color:var(--text2)">推論服務</p>
          <p class="text-xl font-extrabold" style="color:${ok ? 'var(--success)' : 'var(--danger)'}">${ok ? '已啟動' : '未連線'}</p>
        </div>
        <div class="rounded-xl p-4" style="background:var(--surface2)">
          <p class="text-xs font-semibold" style="color:var(--text2)">服務位址</p>
          <p class="text-sm font-bold break-all">${escapeHTML(data.gradio_url || data.url || '-')}</p>
        </div>
        <div class="rounded-xl p-4" style="background:var(--surface2)">
          <p class="text-xs font-semibold" style="color:var(--text2)">AI 推播影響</p>
          <p class="text-xl font-extrabold" style="color:var(--accent2)">${getFeatures().emotionRecommend ? '開啟' : '關閉'}</p>
        </div>
      </div>
      <p class="text-xs mt-3" style="color:var(--text2)">${escapeHTML(data.message || '')}</p>`;
  } catch (e) {
    statusBox.innerHTML = '<span class="text-sm" style="color:var(--danger)">Emotion-LLaMA 狀態讀取失敗。</span>';
  }
}

function updateEmotionCameraPanel() {
  updateEmotionCameraPanelUI({ features: getFeatures(), isPosActive: isPosActive(), stream });
}

function updateEmotionDetectionOverlay(personCheck = {}) {
  updateEmotionDetectionOverlayUI(personCheck, { features: getFeatures(), isPosActive: isPosActive(), stream });
  if (personCheck && personCheck.person_detected === true) {
    setVoiceOrderingAvailable(true);
    if (detectionLoopId) {
      clearInterval(detectionLoopId);
      detectionLoopId = null;
    }
  } else if (getFeatures().emotion) {
    setVoiceOrderingAvailable(false);
  }
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
  if (id === 'emotion') loadEmotionStatus();
}

function findMenuItems(ids = []) {
  return ids
    .map(id => String(id || '').replace(/[^a-zA-Z0-9]/g, ''))
    .map(cleanId => menuData.find(m => m.id === cleanId || m.id.includes(cleanId)))
    .filter(Boolean);
}

const cartManager = createCartManager({ ui, escapeHTML, findMenuItems, onCartChange: updateKioskCartSummary, t: kt });

function trackedAddToCart(item, metadata = {}) {
  lastValidOrderActionAt = Date.now();
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
  lastValidOrderActionAt = Date.now();
  cartManager.updateCartQty(id, delta);
  trackInteractionEvent({
    event_type: 'cart_edit',
    button_id: `cart_qty_${id}`,
    cart_edit_count: 1,
    metadata: { action: 'qty', item_id: id, delta }
  });
}

function trackedDeleteCartItem(id) {
  lastValidOrderActionAt = Date.now();
  interactionState.cartRemoveCount += 1;
  cartManager.deleteCartItem(id);
  trackInteractionEvent({
    event_type: 'cart_edit',
    button_id: `cart_delete_${id}`,
    cart_edit_count: 1,
    cart_remove_count: interactionState.cartRemoveCount,
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
      { id: 'MCD001', name: '測試大麥克', price: 100, category: '超值全餐', description: '後端未連線，這是預設測試資料。' },
      { id: 'MCD002', name: '測試薯條', price: 60, category: '點心', description: '請確認 http://127.0.0.1:8000 已啟動。' }
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
  document.getElementById('view-pos')?.classList.remove('kiosk-screen-menu');
  document.getElementById('view-pos')?.classList.add('kiosk-screen-categories');
  kioskActiveGroup = '';
  kioskActiveFilter = '全部';
  ui.menuGrid.innerHTML = '';
  ui.menuGrid.className = 'kiosk-category-grid';
  if (ui.kioskTitle) ui.kioskTitle.textContent = '';
  if (ui.kioskSubtitle) ui.kioskSubtitle.textContent = kt('chooseCategorySub');
  document.getElementById('kioskLogo')?.classList.remove('hidden');
  document.getElementById('kioskLangBtn')?.classList.remove('hidden');
  ui.kioskBackBtn?.classList.add('hidden');
  ui.kioskSearchBtn?.classList.add('hidden');
  ui.kioskSectionHead?.classList.add('hidden');

  const heading = document.createElement('div');
  heading.className = 'kiosk-category-heading';
  heading.textContent = kt('chooseCategory');
  ui.menuGrid.appendChild(heading);

  KIOSK_GROUPS.forEach(group => {
    const card = document.createElement('button');
    card.className = 'kiosk-category-card';
    card.type = 'button';
    card.onclick = () => showMenuGroup(group.id);
    card.innerHTML = `
      <img src="${group.image}" alt="${escapeHTML(groupLabel(group))}" onerror="this.style.display='none'">
      <strong>${escapeHTML(groupLabel(group))}</strong>`;
    ui.menuGrid.appendChild(card);
  });
  updateKioskCartSummary();
}

function showMenuGroup(groupId, filter = '全部') {
  const switchingInMenu = kioskScreen === 'menu' && (kioskActiveGroup !== groupId || kioskActiveFilter !== filter);
  kioskScreen = 'menu';
  kioskActiveGroup = groupId;
  kioskActiveFilter = filter;
  if (switchingInMenu) {
    interactionState.categorySwitchCount += 1;
    if (interactionState.categorySwitchCount >= 4) {
      trackInteractionEvent({
        event_type: 'category_switch_repeat',
        button_id: `category_${groupId}`,
        category_switch_count: interactionState.categorySwitchCount,
        metadata: { action: 'category_switch', group_id: groupId, filter }
      });
    }
  }
  renderMenu();
}

function groupItems(groupId) {
  const group = KIOSK_GROUPS.find(g => g.id === groupId) || KIOSK_GROUPS[1];
  const allowed = new Set((group.categories || []).map(String));
  const items = menuData.filter(item => allowed.has(String(item.category || '')));
  return group.featuredLimit ? items.slice(0, group.featuredLimit) : items;
}

function itemMatchesSubFilter(item, filter) {
  if (!filter || filter === '全部') return true;
  const name = String(item.name || '').replace(/鷄/g, '雞');
  if (filter === '牛肉系列') return /牛|安格斯|大麥克|吉事|四盎司/.test(name);
  if (filter === '雞肉系列') return /雞|脆|辣/.test(name);
  if (filter === '魚肉系列') return /魚/.test(name);
  if (filter === '安格斯系列') return /安格斯/.test(name);
  if (filter === '早餐系列') return String(item.category || '') === '早餐' || /滿福|鬆餅|薯餅/.test(name);
  if (filter === '點心飲料') return /薯|派|湯|茶|可樂|咖啡|那堤|奶茶/.test(name);
  return true;
}

function subFiltersForGroup(groupId) {
  if (groupId === 'value' || groupId === 'recommended') return ['全部', '牛肉系列', '雞肉系列', '魚肉系列'];
  if (groupId === 'premium') return ['全部', '安格斯系列', '雞肉系列'];
  if (groupId === 'single' || groupId === 'drinks') return ['全部', '點心飲料'];
  if (groupId === 'breakfast') return ['全部', '早餐系列'];
  return ['全部'];
}

function renderKioskMenuItems() {
  document.getElementById('view-pos')?.classList.remove('kiosk-screen-categories');
  document.getElementById('view-pos')?.classList.add('kiosk-screen-menu');
  const group = KIOSK_GROUPS.find(g => g.id === kioskActiveGroup) || KIOSK_GROUPS[1];
  const filters = subFiltersForGroup(group.id);
  const items = groupItems(group.id).filter(item => itemMatchesSubFilter(item, kioskActiveFilter));
  ui.menuGrid.innerHTML = '';
  ui.menuGrid.className = 'kiosk-menu-list';
  if (ui.kioskTitle) ui.kioskTitle.textContent = groupLabel(group);
  if (ui.kioskSubtitle) ui.kioskSubtitle.textContent = kt('addHint');
  document.getElementById('kioskLogo')?.classList.add('hidden');
  document.getElementById('kioskLangBtn')?.classList.add('hidden');
  ui.kioskBackBtn?.classList.remove('hidden');
  ui.kioskSearchBtn?.classList.remove('hidden');
  ui.kioskSectionHead?.classList.add('hidden');

  const tabs = document.createElement('div');
  tabs.className = 'kiosk-menu-tabs';
  tabs.innerHTML = filters.map(filter => `
    <button type="button" class="${filter === kioskActiveFilter ? 'active' : ''}" data-filter="${escapeHTML(filter)}">
      ${escapeHTML(kFilterLabel(filter))}
    </button>`).join('');
  tabs.querySelectorAll('button').forEach(button => {
    button.addEventListener('click', () => showMenuGroup(group.id, button.dataset.filter || '全部'));
  });
  ui.menuGrid.appendChild(tabs);

  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'kiosk-empty-menu';
    empty.textContent = kt('emptyCategory');
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
        <strong>${escapeHTML(formatItemPrice(item))}</strong>
      </div>
      <button class="kiosk-add-btn" type="button" aria-label="${escapeHTML(kt('addToCart'))}"><i class="fas fa-plus"></i></button>`;
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
    if (label) label.textContent = `${kt('checkoutGo')} $${total}`;
  }
}

function applyKioskLanguage() {
  const startupLangText = document.querySelector('#startupLangBtn span');
  if (startupLangText) startupLangText.textContent = kt('langButton');
  const langText = document.querySelector('#kioskLangBtn span');
  if (langText) langText.textContent = kt('langButton');
  if (ui.startBtn) ui.startBtn.textContent = kioskLang === 'en' ? 'Start Order' : '開始點餐';
  if (ui.kioskSearchBtn) {
    const span = ui.kioskSearchBtn.querySelector('span');
    if (span) span.innerHTML = kt('searchFilter');
  }
  if (ui.kioskHomeBtn) {
    const span = ui.kioskHomeBtn.querySelector('span');
    if (span) span.textContent = kt('home');
  }
  if (ui.continueOrderBtn) ui.continueOrderBtn.textContent = kt('continueOrder');
  if (ui.clearCartBtn) ui.clearCartBtn.innerHTML = `<i class="fas fa-trash-alt"></i> ${escapeHTML(kt('clearCart'))}`;
  const cartHeading = document.querySelector('.cart-shell.kiosk-cart-open h3') || document.querySelector('.cart-shell h3');
  if (cartHeading) cartHeading.textContent = kt('yourCart');
  const checkoutLabel = ui.checkoutBtn?.querySelector('span');
  if (checkoutLabel) checkoutLabel.textContent = `${kt('checkoutGo')} ${ui.totalPrice?.textContent || '$0'}`;
  const fastPayKicker = document.querySelector('.kiosk-payment-kicker');
  if (fastPayKicker) fastPayKicker.textContent = kt('fastPayKicker');
  const fastPayTitle = ui.kioskFastPayBtn?.querySelector('strong');
  if (fastPayTitle) fastPayTitle.textContent = kt('fastPayTitle');
  if (ui.kioskCounterPayBtn) ui.kioskCounterPayBtn.textContent = kt('counterPay');
  if (ui.kioskPaymentBackBtn) ui.kioskPaymentBackBtn.textContent = kt('backCart');
  if (ui.kioskCancelOrderBtn) ui.kioskCancelOrderBtn.textContent = kt('cancelOrder');
  const friendlyBtn = document.querySelector('.kiosk-payment-footer button:nth-child(2)');
  if (friendlyBtn) friendlyBtn.textContent = kt('friendlyMode');
  const paymentTitle = document.querySelector('.kiosk-payment-inner h1');
  if (paymentTitle) paymentTitle.textContent = kt('paymentTitle');
  const totalLabels = document.querySelectorAll('.cart-card .font-semibold.text-lg, .order-summary-total .grand span');
  totalLabels.forEach(el => { el.textContent = kt('total'); });
  const subtotalLabel = document.querySelector('.order-summary-total div:first-child span');
  if (subtotalLabel) subtotalLabel.textContent = kt('subtotal');
  const secureNotes = document.querySelectorAll('.order-secure-note, .cart-card.p-7 > p');
  secureNotes.forEach(el => {
    const icon = el.querySelector('i')?.outerHTML || '';
    el.innerHTML = `${icon}${escapeHTML(kt('secureCheckout'))}`;
  });
  const checkoutDoneTitle = document.querySelector('#checkoutOverlay h1');
  if (checkoutDoneTitle) checkoutDoneTitle.textContent = kt('checkoutDone');
  const checkoutDoneSub = document.querySelector('#checkoutOverlay p');
  if (checkoutDoneSub) checkoutDoneSub.textContent = kt('thankYou');
  const _vaLangText = document.getElementById('voiceAssistBtnText');
  if (_vaLangText) _vaLangText.textContent = kt('holdVoiceOrder');
  if (ui.voiceAssistOverlayTitle) ui.voiceAssistOverlayTitle.textContent = kioskLang === 'en' ? 'Voice Mode' : '語音模式';
  if (ui.voiceAssistOverlaySubtitle) ui.voiceAssistOverlaySubtitle.textContent = kioskLang === 'en' ? 'I am listening. Please say what you need.' : '我正在聽，請說出您的需求';
  if (ui.voiceAssistStopText) ui.voiceAssistStopText.textContent = kioskLang === 'en' ? 'Hold to stop listening' : '按住關閉收音';
  if (ui.cartCountBadge) {
    const qty = cartManager?.getCartItems?.().reduce((sum, item) => sum + Number(item.quantity || 0), 0) || 0;
    ui.cartCountBadge.textContent = kt('cartCount').replace('{count}', String(qty));
  }
}

function setKioskLanguage(lang) {
  kioskLang = lang === 'en' ? 'en' : 'zh';
  localStorage.setItem('kiosk_lang', kioskLang);
  applyKioskLanguage();
  renderMenu();
  cartManager.renderCart();
  updateKioskCartSummary();
}

function showCartScreen() {
  document.querySelector('.cart-shell')?.classList.add('kiosk-cart-open');
  ui.kioskBottomBar?.classList.remove('hidden');
  setInteractionPage('checkout_page', { source: 'cart_open' });
  updateVoiceAssistVisibility();
  updateKioskCartSummary();
}

function hideCartScreen() {
  document.querySelector('.cart-shell')?.classList.remove('kiosk-cart-open');
  if (!orderCompleted && ui.kioskPaymentScreen?.classList.contains('hidden')) {
    setInteractionPage(kioskScreen === 'categories' ? 'menu_page' : 'menu_page', { source: 'continue_order' });
  }
  updateVoiceAssistVisibility();
}

function showPaymentScreen() {
  hideCartScreen();
  ui.kioskPaymentScreen?.classList.remove('hidden');
  ui.kioskPaymentScreen?.setAttribute('aria-hidden', 'false');
  setInteractionPage('payment_page', { source: 'checkout_button' });
  promotionPausedUntil = Date.now() + 10 * 60 * 1000;
  recommendPending = false;
  stopAutoVoiceOrdering();
  clearPOSFloatingUI();
  updateVoiceAssistVisibility();
}

function hidePaymentScreen() {
  ui.kioskPaymentScreen?.classList.add('hidden');
  ui.kioskPaymentScreen?.setAttribute('aria-hidden', 'true');
  updateVoiceAssistVisibility();
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
    voice_assist_enabled: Boolean(getFeatures().voiceAssist),
    recommend_enabled: Boolean(getFeatures().recommend),
    promotion_paused: Date.now() < promotionPausedUntil,
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
    category_switch_count: Number(event.category_switch_count ?? interactionState.categorySwitchCount) || 0,
    cart_remove_count: Number(event.cart_remove_count ?? interactionState.cartRemoveCount) || 0,
    recommend_ignore_count: Number(event.recommend_ignore_count ?? interactionState.recommendIgnoreCount) || 0,
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

function handleRealtimeSettingsChanged(event = {}) {
  const settings = event.payload?.settings;
  if (!settings || typeof settings !== 'object') return;
  fullSettings = { ...fullSettings, ...settings };
  runtimeSettings = { ...runtimeSettings, ...settings };
}

function handleRealtimeHumanReply(event = {}) {
  const payload = event.payload || {};
  if (!payload.reply) return;
  if (payload.audio_base64) playVoice(payload.audio_base64);
  showPushNotice(payload.reply.slice(0, 80));
}

function handleRealtimeInteractionIntervention(event = {}) {
  lastInterventionEventAt = Date.now();
  const payload = event.payload || {};
  applyIntervention(payload.intervention || {}, payload.barrier_result || {});
  if (payload.intervention?.staff_notify) showPushNotice('已通知店員');
}

function handleRealtimeEmotionAnalysisStarted(event = {}) {
  const payload = event.payload || {};
  console.debug('emotion_analysis_started', payload);
}

function handleRealtimeEmotionAnalysisCompleted(event = {}) {
  const payload = event.payload || {};
  console.debug('emotion_analysis_completed', payload);
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
  }, 4000);
}

function stopAdminLiveRefresh() {
  if (!adminRefreshTimer) return;
  clearInterval(adminRefreshTimer);
  adminRefreshTimer = null;
}

async function showScenarioRecommendationCard(intervention = {}, barrierResult = {}) {
  if (!isPosActive() || !ui.floatPush) return;
  if (_isVoiceActive()) return;   // 語音進行中不顯示
  // 清除所有現有推播卡及殘留的 app-level 計時器
  if (interactionModalTimer) { clearTimeout(interactionModalTimer); interactionModalTimer = null; }
  clearAllPushCards();

  // 使用 closure 計時器（不污染全域 interactionModalTimer）
  let _scenarioCardTimer = null;
  const _clearScenarioTimer = () => {
    if (_scenarioCardTimer) { clearTimeout(_scenarioCardTimer); _scenarioCardTimer = null; }
  };

  async function resolveItems() {
    const directIds = Array.isArray(intervention.recommendation_ids)
      ? intervention.recommendation_ids : [];
    let items = findMenuItems(directIds);
    if (items.length) return items.slice(0, 3);
    const fd = new FormData();
    fd.append('session_id', sessionId);
    try {
      const data = await api.autoRecommend(fd);
      if (data.status === 'success') items = findMenuItems(data.recommendation_ids || []);
    } catch { /* ignore */ }
    if (!items.length) {
      items = menuData.filter(item => item && item.id && Number(item.price || 0) > 0).slice(0, 3);
    }
    return items.slice(0, 3);
  }

  function _makeBtn(label, cls, icon) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = cls;
    if (icon) { const i = document.createElement('i'); i.className = icon; btn.appendChild(i); btn.appendChild(document.createTextNode(' ')); }
    btn.appendChild(document.createTextNode(label));
    return btn;
  }

  function render(items = []) {
    const itemList = items.filter(Boolean).slice(0, 3);
    const names = itemList.map(i => i.name || '').filter(Boolean).join('、') || '熱門餐點';
    const total = itemList.reduce((s, i) => s + Number(i.price || 0), 0);

    const card = document.createElement('div');
    card.className = 'push-card';

    const header = document.createElement('div');
    header.className = 'push-card-header';
    const titleEl = document.createElement('span');
    titleEl.className = 'push-card-title';
    titleEl.textContent = '還在猶豫嗎？';
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button'; closeBtn.className = 'push-close-btn'; closeBtn.setAttribute('aria-label', '關閉');
    const closeIcon = document.createElement('i'); closeIcon.className = 'fas fa-times';
    closeBtn.appendChild(closeIcon);
    closeBtn.addEventListener('click', () => { _clearScenarioTimer(); clearAllPushCards(); });
    header.append(titleEl, closeBtn);

    const nameEl = document.createElement('div');
    nameEl.className = 'push-item-names'; nameEl.textContent = names;

    const reasonEl = document.createElement('p');
    reasonEl.className = 'push-reason';
    reasonEl.textContent = String(intervention.tts_text || '我可以推薦幾個熱門選擇給您。');

    const btnGrid = document.createElement('div');
    btnGrid.className = 'grid gap-2';

    if (total) {
      const priceEl = document.createElement('div');
      priceEl.className = 'push-item-price';
      priceEl.textContent = itemList.length > 1 ? `組合 $${total}` : `$${Number(itemList[0].price || 0)}`;
      card.append(header, nameEl, priceEl, reasonEl, btnGrid);
    } else {
      card.append(header, nameEl, reasonEl, btnGrid);
    }

    const addBtn = _makeBtn('加入推薦餐點', 'push-add-btn btn-primary', 'fas fa-cart-plus');
    addBtn.addEventListener('click', () => {
      _clearScenarioTimer();
      itemList.forEach(item => trackedAddToCart(item, { source: 'scenario_recommendation' }));
      showPushNotice('已加入推薦餐點');
    });
    const refreshBtn = _makeBtn('換一個推薦', 'push-add-btn', null);
    refreshBtn.addEventListener('click', async () => { _clearScenarioTimer(); render(await resolveItems()); });
    const voiceBtn = _makeBtn('語音模式', 'push-add-btn', 'fas fa-microphone');
    voiceBtn.addEventListener('click', () => {
      _clearScenarioTimer(); clearAllPushCards();
      startAskRecording(document.getElementById('voiceAssistBtn'));
    });
    btnGrid.append(addBtn, refreshBtn, voiceBtn);

    ui.floatPush.replaceChildren(card);

    // 10 秒後自動消失
    _clearScenarioTimer();
    _scenarioCardTimer = setTimeout(() => { _scenarioCardTimer = null; clearAllPushCards(); }, 10000);
  }

  render(await resolveItems());
}

function applyIntervention(intervention = {}, barrierResult = {}) {
  if (!intervention || intervention.action === 'none') return;
  console.log('[interaction intervention]', { intervention, barrierResult });

  document.getElementById('interactionInterventionBox')?.remove();

  if (intervention.ui_patch?.disable_promotion) {
    promotionPausedUntil = Date.now() + 45000;
    clearAllPushCards();
  }

  if (intervention.staff_notify) {
    showPushNotice('建議店員協助');
  }

  const modalName = intervention.ui_patch?.show_modal || '';
  if (!modalName) return;
  if (modalName === 'operation_hint') {
    showTutorialPopup();
    return;
  }
  if (modalName === 'recommendation_card') {
    // 只有顧客超過 15 秒沒有點選任何餐點，才顯示猶豫推播，避免干擾正在選餐的顧客
    const HESITATION_IDLE_MS = 15_000;
    if (Date.now() - lastValidOrderActionAt < HESITATION_IDLE_MS) {
      console.log('[intervention] skip recommendation_card: user acted within 15s');
      return;
    }
    showScenarioRecommendationCard(intervention, barrierResult);
    return;
  }
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
  const safeTitle = escapeHTML(titleMap[modalName] || '操作提示');
  const safeBody = escapeHTML(intervention.tts_text || intervention.reason || '需要協助時可通知店員。');
  const safeCategory = escapeHTML(barrierResult.intervention_category_label || '');
  const safeRisk = (barrierResult.risk_score != null)
    ? escapeHTML(`風險 ${barrierResult.risk_score}/${barrierResult.risk_score_scale || 10}`)
    : '';
  const tagHtml = [safeCategory, safeRisk].filter(Boolean)
    .map(t => '<span class="inline-block text-xs px-2 py-0.5 mr-1 rounded-full" style="background:var(--surface2);color:var(--text2)">' + t + '</span>')
    .join('');
  const staffHtml = intervention.staff_notify
    ? '<p class="text-xs mt-2 font-bold" style="color:var(--danger)">建議店員協助</p>'
    : '';
  box.innerHTML = (
    '<div class="flex items-start justify-between gap-3">'
    + '<div>'
    + '<p class="text-sm font-bold mb-1" style="color:var(--accent2)">' + safeTitle + '</p>'
    + (tagHtml ? '<div class="mb-2">' + tagHtml + '</div>' : '')
    + '<p class="text-sm leading-relaxed">' + safeBody + '</p>'
    + staffHtml
    + '</div>'
    + '<button type="button" data-close-intervention style="color:var(--text2)"><i class="fas fa-times"></i></button>'
    + '</div>'
  );
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
    `風險分數：${riskResult.risk_score ?? 0}/${riskResult.risk_score_scale ?? 10}（${riskResult.risk_level || 'none'}）`,
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
        event_type: pageId === 'menu_page' ? 'menu_page_dwell_timeout' : 'page_dwell_timeout',
        button_id: 'page_timer',
        dwell_time_sec: getDwellTimeSec(),
        metadata: { reason: 'same_page_over_30_sec' }
      });
    }
  }, 5000);
}

function getMenuVisual(item) {
  const id = String(item.id || '').toUpperCase();
  const category = String(item.category || '');
  const name = String(item.name || '');
  const categoryVisuals = {
    '超值全餐': { tag: '超值全餐', icon: 'fas fa-burger', emoji: '🍔' },
    '超值全餐配餐': { tag: '配餐', icon: 'fas fa-cubes-stacked', emoji: '🍟' },
    '極選系列': { tag: '推薦套餐', icon: 'fas fa-star', emoji: '🍔' },
    '1+1星級點': { tag: '1+1', icon: 'fas fa-plus', emoji: '✨' },
    '麥當勞分享盒': { tag: '分享盒', icon: 'fas fa-box', emoji: '📦' },
    'Happy Meal®': { tag: 'Happy Meal', icon: 'fas fa-child-reaching', emoji: '🧒' },
    '早餐': { tag: '早餐', icon: 'fas fa-sun', emoji: '🥞' },
    '飲料': { tag: '飲料甜點', icon: 'fas fa-glass-water', emoji: '🥤' },
    'McCafé': { tag: 'McCafé', icon: 'fas fa-mug-hot', emoji: '☕' },
    'McCafé®': { tag: 'McCafé', icon: 'fas fa-mug-hot', emoji: '☕' },
    '點心': { tag: '單點餐品', icon: 'fas fa-cookie-bite', emoji: '🍟' },
  };
  let fallback = categoryVisuals[category] || { tag: category || '精選餐點', icon: 'fas fa-utensils', emoji: '🍽️' };
  // 細項表情：依品名再校正一次預設 emoji，避免分享盒/1+1 全部變相同圖示。
  if (/薯條|薯餅/.test(name)) fallback = { ...fallback, emoji: '🍟' };
  else if (/雞翅|鷄翅|鷄塊|雞塊|麥脆/.test(name)) fallback = { ...fallback, emoji: '🍗' };
  else if (/咖啡|拿鐵|那堤|拿提|美式/.test(name)) fallback = { ...fallback, emoji: '☕' };
  else if (/可樂|雪碧|汽水/.test(name)) fallback = { ...fallback, emoji: '🥤' };
  else if (/茶/.test(name)) fallback = { ...fallback, emoji: '🍵' };
  else if (/沙拉|藜麥/.test(name)) fallback = { ...fallback, emoji: '🥗' };
  else if (/魚/.test(name)) fallback = { ...fallback, emoji: '🐟' };
  else if (/派/.test(name)) fallback = { ...fallback, emoji: '🥧' };
  else if (/玉米|湯/.test(name)) fallback = { ...fallback, emoji: '🌽' };
  else if (/鬆餅|滿福|焙果/.test(name)) fallback = { ...fallback, emoji: '🥞' };
  else if (/Happy Meal|快樂兒童餐/.test(name)) fallback = { ...fallback, emoji: '🧒' };
  return { ...fallback, image: item.image || (id.startsWith('MCD') ? `/static/menu_images/${id}.jpg` : '') };
}

function formatItemPrice(item) {
  const price = Number(item.price || 0);
  if (price > 0) return `$${price}`;
  return kioskLang === 'en' ? 'Store Price' : '依店價';
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
    const needVideo = f.emotionBackend || isEventTriggeredMultimodalEnabled();
    const needAudio = Boolean(f.voiceAssist);
    const mediaReady = await ensureMediaTracks({ video: needVideo, audio: needAudio });
    if (!mediaReady && (needVideo || needAudio)) console.warn('Media permission unavailable; POS flow continues without rolling buffer.');
    await loadMenu();
    applyFeaturesToPOS();
    ui.overlay.style.opacity = '0';
    setTimeout(() => { ui.overlay.classList.add('hidden'); }, 500);
    isSystemRunning = true;
    setVoiceOrderingAvailable(true);
    if (f.emotion) startDetectionLoop();
    updateEmotionCameraPanel();
    startPageDwellWatcher();
    setInteractionPage('menu_page', { source: 'start_system' });
    maybeStartRollingMediaBuffer();
    if (f.emotionBackend && isPeriodicEmotionEnabled()) startEmotionLoop();
    startRecommendLoop();
    if (f.voiceAssist) setupAskRecorder();
  } catch { alert("無法存取攝影機與麥克風。"); }
};

ui.startBtn?.addEventListener('pointerdown', () => {
  ui.overlay?.classList.add('startup-pressing');
});
['pointerup', 'pointercancel', 'pointerleave'].forEach(eventName => {
  ui.startBtn?.addEventListener(eventName, () => {
    ui.overlay?.classList.remove('startup-pressing');
  });
});

document.getElementById('kioskLangBtn')?.addEventListener('click', () => {
  setKioskLanguage(kioskLang === 'zh' ? 'en' : 'zh');
});
document.getElementById('startupLangBtn')?.addEventListener('click', () => {
  setKioskLanguage(kioskLang === 'zh' ? 'en' : 'zh');
});

function startDetectionLoop() {
  if (detectionLoopId) return;
  detectionLoopId = setInterval(captureDetectionFrame, Math.max(250, Number(perfValue('YOLO_FRAME_INTERVAL_MS')) || 650));
}

function captureDetectionFrame() {
  const f = getFeatures();
  if (!f.emotion) return;
  const panelVisible = ui.emotionCameraPanel && !ui.emotionCameraPanel.classList.contains('hidden');
  if (!isPosActive() && !panelVisible) return;
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

function _isVoiceActive() {
  // 語音 overlay 可見（聆聽 or 思考中）時視為語音模式進行中
  return ui.voiceAssistOverlay && !ui.voiceAssistOverlay.classList.contains('hidden');
}

async function fetchAndDisplayRecommend() {
  const f = getFeatures();
  if (!f.recommend) return;
  if (recommendRequestInFlight) return;
  if (_isVoiceActive()) return;                     // 語音模式進行中，不蓋推播
  if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) return;
  if (document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open')) return;
  if (Date.now() < promotionPausedUntil) return;
  // 有 scenario 計時器殘留時先清除，避免它干擾新推播卡
  if (interactionModalTimer) { clearTimeout(interactionModalTimer); interactionModalTimer = null; }
  const fd = new FormData();
  fd.append('session_id', sessionId);
  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), 12000);
  recommendRequestInFlight = true;
  recommendPending = true;
  try {
    const data = await api.autoRecommend(fd, ctrl.signal);
    if (data.status === 'success') displayRecommendation(data);
  } catch (err) {
    console.warn('[auto_recommend failed]', err);
  } finally {
    clearTimeout(tid);
    recommendRequestInFlight = false;
    recommendPending = false;
  }
}

function startRecommendLoop() {
  if (isAdminMode() || recommendLoopId) return;
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
  if (!isPosActive()) return;
  const lang = data.detected_lang || 'zh';
  const dialogue = data.dialogue || {
    zh: { user_text: lang === 'zh' ? data.user_text : '', ai_response: lang === 'zh' ? data.ai_response : '' },
    en: { user_text: lang === 'en' ? data.user_text : '', ai_response: lang === 'en' ? data.ai_response : '' }
  };
  const d = dialogue[lang] || { user_text: data.user_text || '', ai_response: data.ai_response || '' };
  ui.voiceDialogueGrid.innerHTML = `
    <div class="dialogue-lane active">
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs font-bold" style="color:var(--accent2)">${escapeHTML(lang === 'en' ? kt('languageEn') : kt('languageZh'))}</span>
        <i class="fas fa-volume-up text-xs" style="color:var(--accent2)"></i>
      </div>
      <p class="text-xs mb-1 truncate" style="color:var(--text2)">${escapeHTML(d.user_text || data.user_text || '-')}</p>
      <p class="text-sm font-medium leading-snug" style="color:var(--text)">${escapeHTML(d.ai_response || data.ai_response || '-')}</p>
    </div>`;
  ui.voiceLangBadge.textContent = lang === 'en' ? kt('enOutput') : kt('zhOutput');
  ui.voiceBubble.style.display = 'block';
  if (voiceBubbleTimer) clearTimeout(voiceBubbleTimer);
  voiceBubbleTimer = setTimeout(() => closeVoiceBubble(false), 12000);
}

function showVoiceAssistMessage(message, lang = kioskLang) {
  const detected = lang === 'en' ? 'en' : 'zh';
  showVoiceBubble({
    detected_lang: detected,
    user_text: '',
    ai_response: message,
    dialogue: {
      zh: { user_text: '', ai_response: detected === 'zh' ? message : '' },
      en: { user_text: '', ai_response: detected === 'en' ? message : '' },
    }
  });
}

function showVoiceAssistOverlay(state = 'listening') {
  if (!ui.voiceAssistOverlay) return;
  const listening = state !== 'thinking';
  ui.voiceAssistOverlay.classList.remove('hidden');
  ui.voiceAssistOverlay.classList.toggle('thinking', !listening);
  ui.voiceAssistOverlay.setAttribute('aria-hidden', 'false');
  if (ui.voiceAssistOverlayTitle) ui.voiceAssistOverlayTitle.textContent = kioskLang === 'en' ? 'Voice Mode' : '語音模式';
  if (ui.voiceAssistOverlaySubtitle) {
    ui.voiceAssistOverlaySubtitle.textContent = listening
      ? (kioskLang === 'en' ? 'I am listening. Please say what you need.' : '我正在聽，請說出您的需求')
      : (kioskLang === 'en' ? 'Processing your voice...' : '正在處理您的語音...');
  }
  if (ui.voiceAssistStopText) {
    ui.voiceAssistStopText.textContent = listening
      ? (kioskLang === 'en' ? 'Hold to stop listening' : '按住關閉收音')
      : (kioskLang === 'en' ? 'Processing...' : '處理中...');
  }
}

function hideVoiceAssistOverlay() {
  ui.voiceAssistOverlay?.classList.add('hidden');
  ui.voiceAssistOverlay?.setAttribute('aria-hidden', 'true');
}

function setVoiceOrderingAvailable(available) {
  voiceOrderingAvailable = Boolean(available);
  const disabled = isPosMode() && isSystemRunning && getFeatures().emotion && !voiceOrderingAvailable;
  const _vaBtn = document.getElementById('voiceAssistBtn');
  const _vaBtnText = document.getElementById('voiceAssistBtnText');
  if (_vaBtn) _vaBtn.classList.toggle('opacity-50', disabled);
  if (_vaBtnText && disabled) _vaBtnText.textContent = kioskLang === 'en' ? 'Voice assist is not ready yet' : '語音協助尚未準備完成';
  if (_vaBtn) _vaBtn.disabled = disabled;
  if (!voiceOrderingAvailable) stopAutoVoiceOrdering();
}

function stopAutoVoiceOrdering() {
  if (autoVoiceTimer) clearTimeout(autoVoiceTimer);
  autoVoiceTimer = null;
  autoVoiceInFlight = false;
  if (askRecorder?.state === 'recording') {
    try { stopAskRecording(); } catch { }
  }
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
    const durationMs = askRecordingStartedAt ? Date.now() - askRecordingStartedAt : 0;
    askRecordingStartedAt = 0;
    chunks = [];
    if (blob.size < 1500 || durationMs < 650) {
      hideVoiceAssistOverlay();
      trackInteractionEvent({
        event_type: 'voice_assist_failed',
        button_id: 'voiceAssistBtn',
        metadata: { reason: 'audio_too_short', duration_ms: durationMs, bytes: blob.size }
      });
      const _tooShort = document.getElementById('voiceAssistBtnText');
      if (_tooShort) _tooShort.textContent = kt('holdVoiceOrder');
      showVoiceAssistMessage(kt('voiceTooShort'));
      autoVoiceInFlight = false;
      return;
    }

    const _btnText = document.getElementById('voiceAssistBtnText');
    if (_btnText) _btnText.textContent = kt('aiThinking');
    showVoiceAssistOverlay('thinking');
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('audio', blob);
    fd.append('multi_lang', String(getFeatures().multiLang));
    try {
      const data = await api.ask(fd);
      if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) {
        hideVoiceAssistOverlay();
        autoVoiceInFlight = false;
        return;
      }
      if (data.status === 'success') {
        lastVoiceText = data.user_text || lastVoiceText;
        if (data.audio_base64) playVoice(data.audio_base64);
        showVoiceBubble(data);
        // 累積 session 情緒記錄，結帳時批次寫 RAG
        if (lastEmotionStructured) {
          sessionEmotionLog.push({
            ts: new Date().toISOString(),
            emotion_label: lastEmotionStructured.emotion_label || lastEmotionStructured.emotion_display || '',
            emotion_evidence: lastEmotionStructured.emotion_evidence || '',
            user_text: data.user_text || '',
            ai_response: data.ai_response || '',
          });
        }
        const appliedOrders = cartManager.applyCartActions(data.cart_actions || []);
        if (appliedOrders.length) {
          trackInteractionEvent({
            event_type: 'cart_edit',
            button_id: 'askBtn',
            cart_edit_count: appliedOrders.length,
            metadata: { source: 'voice_assist', items: appliedOrders }
          });
          showPushNotice(kt('addedToCart').replace('{items}', appliedOrders.join('、')));
        }

        if (data.trigger_recommend && getFeatures().recommend) {
          setTimeout(async () => {
            await fetchAndDisplayRecommend();
          }, Number(perfValue('RECOMMEND_AFTER_ASK_DELAY_MS')) || 1200);
        }
        if (data.mentioned_ids) data.mentioned_ids.forEach(id => sessionPushedIds.add(id));
      } else {
        console.debug('[voice assistant skipped]', data.message || data.status);
        showVoiceAssistMessage(
          data.ai_response || data.message || kt('voiceOrderFailed'),
          data.detected_lang || kioskLang
        );
        if (data.audio_base64) playVoice(data.audio_base64);
      }
    } catch (err) {
      trackInteractionEvent({
        event_type: 'voice_assist_failed',
        button_id: 'voiceAssistBtn',
        metadata: { reason: 'api_error' }
      });
      showVoiceBubble({
        detected_lang: 'zh',
        dialogue: { zh: { user_text: '', ai_response: kt('networkFailed') } }
      });
    }
    const _doneText = document.getElementById('voiceAssistBtnText');
    if (_doneText) _doneText.textContent = kt('holdVoiceOrder');
    hideVoiceAssistOverlay();
    autoVoiceInFlight = false;
  };
}

// 語音模式開始時非同步捕捉 emotion 快照（不阻塞錄音）
function captureEmotionSnapshotForVoice() {
  if (!stream || !stream.getVideoTracks().length) return;
  if (!getFeatures().emotion) return;
  if (!isPosActive()) return;
  const rec = createVideoRecorder(stream);
  const chunks = [];
  rec.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
  rec.onstop = async () => {
    const blob = new Blob(chunks, { type: 'video/webm' });
    if (blob.size < 2000) return;
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('video', blob, 'voice_emotion_snapshot.webm');
    fd.append('detect_only', 'false');
    try {
      const d = await api.pingState(fd);
      if (d.person_check) updateEmotionDetectionOverlay(d.person_check);
      if ((d.status === 'success' || d.status === 'not_executed') && d.emotion_structured) {
        lastEmotionStructured = d.emotion_structured;
      }
    } catch { /* 非關鍵路徑，靜默忽略 */ }
  };
  try {
    rec.start();
    setTimeout(() => { if (rec.state === 'recording') rec.stop(); }, 1000);
  } catch { /* 無攝影機時靜默跳過 */ }
}

function startAskRecording(sourceBtn) {
  if (!voiceOrderingAvailable) {
    showPushNotice(kioskLang === 'en' ? 'Voice assist is not ready yet.' : '語音協助尚未準備完成。');
    return;
  }
  if (!askRecorder) setupAskRecorder();
  if (!askRecorder || askRecorder.state !== 'inactive') {
    showVoiceAssistMessage(kt('voiceMicNotReady'));
    return;
  }
  if (askRecorder && askRecorder.state === 'inactive') {
    // 開始錄音前先清除推播卡與殘留計時器，避免語音模式與推播卡重疊
    if (interactionModalTimer) { clearTimeout(interactionModalTimer); interactionModalTimer = null; }
    clearAllPushCards();
    captureEmotionSnapshotForVoice();
    trackInteractionEvent({
      event_type: 'voice_assist_started',
      button_id: sourceBtn?.id || 'voiceAssistBtn',
      metadata: {}
    });
    askRecordingStartedAt = Date.now();
    askRecorder.start();
    document.getElementById('voiceAssistBtn')?.classList.add('recording');
    showVoiceAssistOverlay('listening');
    const _startText = document.getElementById('voiceAssistBtnText');
    if (_startText) _startText.textContent = kt('listeningAsk');
  }
}
function stopAskRecording() {
  if (askRecorder && askRecorder.state === 'recording') {
    askRecorder.stop();
    document.getElementById('voiceAssistBtn')?.classList.remove('recording');
    showVoiceAssistOverlay('thinking');
  }
}
const _vaFabBtn = document.getElementById('voiceAssistBtn');
if (_vaFabBtn) {
  _vaFabBtn.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    startAskRecording(_vaFabBtn);
  });
}
function stopOrHideVoiceAssistOverlay(event) {
  event?.preventDefault?.();
  if (askRecorder?.state === 'recording') {
    stopAskRecording();
  } else {
    hideVoiceAssistOverlay();
  }
}

// X 按鈕：按住即停止收音；click 保留給桌面瀏覽器與舊行為。
ui.voiceAssistStopBtn?.addEventListener('pointerdown', stopOrHideVoiceAssistOverlay);
ui.voiceAssistStopBtn?.addEventListener('click', stopOrHideVoiceAssistOverlay);

window.addEventListener('beforeunload', () => {
  try {
    if (askRecorder?.state === 'recording') askRecorder.stop();
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
// 無效點擊偵測（需連續 N 次才觸發教學提示）
// =========================================================
const INVALID_CLICK_THRESHOLD = 3;
const INVALID_CLICK_WINDOW_MS = 4000;
const INVALID_CLICK_MIN_DWELL_MS = 7000;
const INVALID_CLICK_RECENT_ACTION_GRACE_MS = 3000;
let invalidClickTimestamps = [];

function shouldTrackInvalidClick(target) {
  if (!isSystemRunning || !isPosActive() || orderCompleted) return false;
  if (!target?.closest) return false;
  const interactive = target.closest(
    'button,a,input,textarea,select,[onclick],[data-fulfillment],[data-payment],.menu-card,.cart-item,#voiceReplyBubble'
  );
  if (interactive) return false;
  if (target.closest('#startupOverlay,#tutorialPopup,#cancelGuidePopup,#voiceAssistOverlay,#voiceReplyBubble,#aiOverlayStack,#emotionFeed,#emotionCameraPanel')) {
    return false;
  }
  if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) return false;
  if (document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open')) return false;
  if (!['menu_page', 'checkout_page'].includes(interactionState.pageId)) return false;

  const now = Date.now();
  if (now - interactionState.pageEnteredAt < INVALID_CLICK_MIN_DWELL_MS) return false;
  if (now - lastValidOrderActionAt < INVALID_CLICK_RECENT_ACTION_GRACE_MS) return false;
  return true;
}

document.addEventListener('pointerdown', (event) => {
  const target = event.target;
  if (shouldTrackInvalidClick(target)) {
    trackInteractionEvent({
      event_type: 'invalid_touch',
      button_id: 'document',
      metadata: { tag: target?.tagName || '' }
    });
    const _now = Date.now();
    invalidClickTimestamps = invalidClickTimestamps.filter(t => _now - t < INVALID_CLICK_WINDOW_MS);
    invalidClickTimestamps.push(_now);
    if (invalidClickTimestamps.length >= INVALID_CLICK_THRESHOLD) {
      invalidClickTimestamps = [];
      showTutorialPopup();
    }
  }
});

function applyPerformancePreset(mode) {
  const presets = {
    eco: { emotion: 30, record: 700, recommend: 60, tokens: 160, rag: 2 },
    balanced: { emotion: 15, record: 900, recommend: 30, tokens: 220, rag: 3 },
    quality: { emotion: 8, record: 1500, recommend: 18, tokens: 360, rag: 4 }
  };
  const p = presets[mode] || presets.balanced;
  document.getElementById('inp-emotion-interval').value = p.emotion;
  document.getElementById('inp-emotion-record-ms').value = p.record;
  document.getElementById('inp-recommend-interval').value = p.recommend;
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
        <p>${escapeHTML(kt('menuFallback'))}</p>
      </div>`;
    return;
  }

  ui.confirmOrderList.innerHTML = items.map(item => {
    const quantity = Number(item.quantity || 0);
    const price = Number(item.price || 0);
    const visual = getMenuVisual(item);
    const lineLabel = price > 0
      ? `$${price * quantity}`
      : (kioskLang === 'en' ? 'Store Price' : '依店價');
    return `
      <div class="order-summary-item">
        <div class="order-summary-photo">
          <img src="${visual.image}" alt="${escapeHTML(item.name)}" onerror="this.style.display='none';this.parentElement.innerHTML='${visual.emoji}'">
        </div>
        <div class="order-summary-name">${escapeHTML(item.name)}</div>
        <div class="order-summary-meta">
          <span class="order-summary-qty">× ${quantity}</span>
          <strong class="order-summary-price">${escapeHTML(lineLabel)}</strong>
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
  if (sessionEmotionLog.length > 0) {
    fd.append('emotion_session_log', JSON.stringify(sessionEmotionLog));
  }
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
  updateVoiceAssistVisibility();
  clearPOSFloatingUI();
  stopAutoVoiceOrdering();
  stopRollingMediaBuffer();
  recommendPending = false;
  const originalHTML = button?.innerHTML || '';
  setConfirmButtonsDisabled(true);
  if (button) button.innerHTML = `<i class="fas fa-spinner fa-spin mr-2"></i>${loadingText}`;
  await writeCheckoutLog(cartIds);
  if (button) button.innerHTML = originalHTML;
  showCompletionOverlay(doneTitle, kt('thankYou'));
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
  if (orderCompleted) return;
  isSystemRunning = false;
  orderCompleted = false;
  clearPOSFloatingUI();
  stopAutoVoiceOrdering();
  stopRollingMediaBuffer();
  cartManager.clearCart();
  ui.overlay.classList.remove('hidden');
  ui.overlay.style.opacity = '1';
  kioskScreen = 'categories';
  setInteractionPage('startup', { source: 'home_button' });
});
ui.kioskCartBtn?.addEventListener('click', () => {
  showCartScreen();
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
  cancelClickCount += 1;
  if (cancelClickCount >= CANCEL_POPUP_THRESHOLD) {
    showCancelGuide();
    return;
  }
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
  finishOrder(cartIds, ui.kioskFastPayBtn, kt('checkoutProcessing'), kt('checkoutDone'));
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
  finishOrder(cartIds, ui.kioskCounterPayBtn, kt('counterPayCreating'), kt('counterPayDone'));
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
  finishOrder(cartIds, ui.confirmPayBtn, kt('checkoutProcessing'), kt('checkoutDone'));
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
  loadEmotionClips();
  loadRagStatus();
  loadOllamaModelOptions();
}

async function loadRagStatus() {
  const container = document.getElementById('ragStatusContainer');
  if (!container) return;
  container.textContent = '載入中...';
  try {
    const res = await api.getRagStatus();
    
    if (res.error) {
      container.textContent = `錯誤: ${res.error}`;
      return;
    }
    
    const meta = res.vector_meta || {};
    const count = res.chunk_count || 0;
    const lr = res.last_retrieval || {};
    const evalOk = lr.evaluation?.sufficient !== false;
    const gateOk = lr.quality_gate?.sufficient !== false;
    
    let html = `<div class="mb-2"><strong style="color:var(--info)">向量資料庫</strong>: ${meta.active_dir || '未建立'}<br>`;
    html += `<strong>Embedding</strong>: ${meta.embedding_key || 'N/A'}<br>`;
    html += `<strong>RAG 筆數</strong>: ${count} 區塊<br>`;
    html += `<strong>最後更新</strong>: ${meta.updated_at || '無紀錄'}</div>`;
    
    if (lr.question) {
      html += `<div class="border-t border-gray-700 pt-2 mt-2">`;
      html += `<strong>最近檢索問題</strong>: ${lr.question}<br>`;
      html += `<strong>評估通過 (Answerability)</strong>: <span class="${evalOk ? 'text-green-400' : 'text-red-400'}">${evalOk ? '是' : '否'}</span> (${lr.evaluation?.reason || 'N/A'})<br>`;
      html += `<strong>品質門檻 (Quality Gate)</strong>: <span class="${gateOk ? 'text-green-400' : 'text-red-400'}">${gateOk ? '是' : '否'}</span> (${lr.quality_gate?.reason || 'N/A'})<br>`;
      html += `<strong>引用來源數</strong>: ${(lr.citations || []).length} 筆<br>`;
      html += `</div>`;
    } else {
      html += `<div class="border-t border-gray-700 pt-2 mt-2 text-gray-400">尚無檢索紀錄</div>`;
    }
    
    container.innerHTML = html;
  } catch (e) {
    container.textContent = `無法載入狀態: ${e.message}`;
  }
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

    // 三大專利實施例統計
    const scenarioCounts = data.scenario_counts || {};
    const scenarioRate = data.scenario_success_rate || {};
    [
      ['operation_difficulty', 'operation'],
      ['menu_hesitation',      'hesitation'],
      ['payment_problem',      'payment'],
    ].forEach(([sid, key]) => {
      const countEl = document.getElementById(`scenario-${key}-count`);
      const rateEl  = document.getElementById(`scenario-${key}-rate`);
      if (countEl) countEl.textContent = String(scenarioCounts[sid] ?? 0);
      if (rateEl)  rateEl.textContent  = `成功率 ${Math.round(Number(scenarioRate[sid] ?? 0) * 100)}%`;
    });

    const tbody = document.getElementById('interventionLogsBody');
    if (!tbody) return;
    const logs = Array.isArray(data.recent_logs) ? data.recent_logs : [];
    lastInterventionLogs = logs;
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
    [['operation','0'],['hesitation','0'],['payment','0']].forEach(([key, val]) => {
      const c = document.getElementById(`scenario-${key}-count`);
      const r = document.getElementById(`scenario-${key}-rate`);
      if (c) c.textContent = val;
      if (r) r.textContent = '成功率 0%';
    });
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
      const suffix = clip.url && clip.url.includes('?') ? api.adminQuerySuffix('&') : api.adminQuerySuffix();
      const url = clip.url ? `${API_BASE}${clip.url}${suffix}` : '';
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
    document.getElementById('inp-rag-strict-grounding').checked = rag.strict_grounding === true;
    document.getElementById('inp-rag-answer-verification').checked = rag.answer_verification === true;
    document.getElementById('inp-rag-fail-closed').checked = rag.fail_closed_on_eval_error === true;
    document.getElementById('inp-rag-min-overlap').value = rag.min_keyword_overlap || 1;
    document.getElementById('inp-rag-max-chars').value = rag.max_answer_chars || 420;
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
    document.getElementById('inp-tts-cache').checked = fullSettings.ENABLE_TTS_CACHE !== false;
    document.getElementById('inp-emotion-prompt').value = fullSettings.EMOTION_LLAMA_PROMPT || '';
    document.getElementById('inp-recommend-prompt').value = fullSettings.RECOMMEND_SYSTEM_PROMPT || '';
    document.getElementById('inp-ask-prompt').value = fullSettings.ASK_SYSTEM_PROMPT || '';
    document.getElementById('inp-ask-prompt-en').value = fullSettings.ASK_SYSTEM_PROMPT_EN || '';
    const _vaModelEl = document.getElementById('inp-voice-assist-model');
    if (_vaModelEl) _vaModelEl.value = fullSettings.VOICE_ASSIST_MODEL || 'qwen3.5:9b';
    const _vaPromptEl = document.getElementById('inp-voice-assist-prompt');
    if (_vaPromptEl) _vaPromptEl.value = fullSettings.VOICE_ASSIST_SYSTEM_PROMPT || '';
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
    strict_grounding: document.getElementById('inp-rag-strict-grounding').checked,
    answer_verification: document.getElementById('inp-rag-answer-verification').checked,
    fail_closed_on_eval_error: document.getElementById('inp-rag-fail-closed').checked,
    min_keyword_overlap: parseInt(document.getElementById('inp-rag-min-overlap').value || '1', 10),
    max_answer_chars: parseInt(document.getElementById('inp-rag-max-chars').value || '420', 10),
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
  fullSettings.ENABLE_TTS_CACHE = document.getElementById('inp-tts-cache').checked;
  fullSettings.EMOTION_LLAMA_PROMPT = document.getElementById('inp-emotion-prompt').value;
  fullSettings.RECOMMEND_SYSTEM_PROMPT = document.getElementById('inp-recommend-prompt').value;
  fullSettings.ASK_SYSTEM_PROMPT = document.getElementById('inp-ask-prompt').value;
  fullSettings.ASK_SYSTEM_PROMPT_EN = document.getElementById('inp-ask-prompt-en').value;
  const _vaSave = document.getElementById('inp-voice-assist-model');
  fullSettings.VOICE_ASSIST_MODEL = _vaSave ? (_vaSave.value.trim() || 'qwen3.5:9b') : 'qwen3.5:9b';
  const _vaPSave = document.getElementById('inp-voice-assist-prompt');
  fullSettings.VOICE_ASSIST_SYSTEM_PROMPT = _vaPSave ? _vaPSave.value : '';
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
    alert('菜單 JSON 已儲存。');
  } catch { alert('JSON 格式錯誤！'); }
}

async function loadRagData() {
  try {
    const data = await api.getRagDocs();
    const docs = data.docs || [];
    const docsBox = document.getElementById('ragDocsList');
    const reviewSummary = document.getElementById('ragReviewSummary');
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
    if (reviewSummary) {
      const activeCount = docs.filter(doc => !doc.deleted).length;
      reviewSummary.textContent = `目前 RAG 文本 ${activeCount} 筆。按下一鍵審查後，系統會使用選定 Ollama 模型重新審查並修正格式。`;
    }
  } catch {
    showAdminNotice('RAG 資料載入失敗。', 'error');
  }
}

async function loadOllamaModelOptions() {
  const input = document.getElementById('ragReviewModel');
  const list = document.getElementById('ollamaModelList');
  if (!input || !list) return;
  try {
    const data = await api.getOllamaModels();
    const models = Array.isArray(data.models) ? data.models : [];
    list.innerHTML = models.map(name => `<option value="${escapeHTML(name)}"></option>`).join('');
    if (!input.value && models.length) input.value = models[0];
  } catch { }
}

async function reviewAllRagDocs() {
  const modelName = document.getElementById('ragReviewModel')?.value?.trim() || fullSettings.MODEL_NAME || 'llama3.2';
  if (!confirm(`確定使用 ${modelName} 重新審查所有 RAG 文本？`)) return;
  const resultBox = document.getElementById('ragReviewResult');
  if (resultBox) resultBox.textContent = 'Ollama 審查中，請稍候...';
  try {
    const data = await api.reviewAllRagDocs({ model_name: modelName });
    if (data.status !== 'success') throw new Error(data.message || '審查失敗');
    if (resultBox) {
      resultBox.textContent = `完成：已修正 ${data.reviewed_count || 0} 筆，刪除不相關 ${data.deleted_count || 0} 筆，模型 ${data.model_name || modelName}`;
    }
    await loadRagData();
    await loadRagStatus();
  } catch (e) {
    if (resultBox) resultBox.textContent = `審查失敗：${e.message || e}`;
  }
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

document.getElementById('inp-performance-mode')?.addEventListener('change', (e) => {
  applyPerformancePreset(e.target.value);
});
document.getElementById('inp-model-name')?.addEventListener('change', (e) => {
  const askModelInput = document.getElementById('inp-ask-model-name');
  if (askModelInput) askModelInput.value = e.target.value || 'llama3.2';
});

// =========================================================
// 2-1: Ripple effect on .btn-primary buttons
// =========================================================
document.addEventListener('pointerdown', (e) => {
  const btn = e.target?.closest?.('.btn-primary');
  if (!btn) return;
  const ripple = document.createElement('span');
  ripple.className = 'btn-ripple';
  const rect = btn.getBoundingClientRect();
  ripple.style.left = (e.clientX - rect.left - 30) + 'px';
  ripple.style.top  = (e.clientY - rect.top  - 30) + 'px';
  btn.appendChild(ripple);
  ripple.addEventListener('animationend', () => ripple.remove());
}, true);

// =========================================================
// 2-2: Tutorial popup for invalid clicks
// =========================================================
let tutorialPopupTimer = null;
let lastTutorialShowAt = 0;
const TUTORIAL_COOLDOWN_MS = 8000;
const tutorialPopupEl = document.getElementById('tutorialPopup');
const tutorialTimerBar = document.getElementById('tutorialPopupTimerBar');

function showTutorialPopup() {
  const now = Date.now();
  if (now - lastTutorialShowAt < TUTORIAL_COOLDOWN_MS) return;
  if (!tutorialPopupEl) return;
  lastTutorialShowAt = now;
  if (tutorialPopupTimer) clearTimeout(tutorialPopupTimer);
  tutorialPopupEl.classList.remove('hidden');
  if (tutorialTimerBar) {
    tutorialTimerBar.style.transition = 'none';
    tutorialTimerBar.style.width = '100%';
    requestAnimationFrame(() => requestAnimationFrame(() => {
      tutorialTimerBar.style.transition = 'width 5s linear';
      tutorialTimerBar.style.width = '0%';
    }));
  }
  tutorialPopupTimer = setTimeout(hideTutorialPopup, 5000);
}
function hideTutorialPopup() {
  if (tutorialPopupTimer) { clearTimeout(tutorialPopupTimer); tutorialPopupTimer = null; }
  tutorialPopupEl?.classList.add('hidden');
}
document.getElementById('tutorialPopupClose')?.addEventListener('click', hideTutorialPopup);

// =========================================================
// 2-3: Cancel order popup after CANCEL_POPUP_THRESHOLD clicks
// =========================================================
let cancelClickCount = 0;
const CANCEL_POPUP_THRESHOLD = 2;
const cancelGuideEl = document.getElementById('cancelGuidePopup');

function showCancelGuide() { cancelGuideEl?.classList.remove('hidden'); }
function hideCancelGuide() { cancelGuideEl?.classList.add('hidden'); }

document.getElementById('cancelGuideClose')?.addEventListener('click', hideCancelGuide);

document.getElementById('cancelGuideFastPay')?.addEventListener('click', () => {
  hideCancelGuide();
  cancelClickCount = 0;
});

document.getElementById('cancelGuideCounter')?.addEventListener('click', () => {
  hideCancelGuide();
  cancelClickCount = 0;
  const cartIds = cartManager.getCartIds();
  if (!cartIds.length) return;
  finishOrder(cartIds, null, kt('counterPayCreating'), kt('counterPayDone'));
});

document.getElementById('cancelGuideConfirmCancel')?.addEventListener('click', () => {
  hideCancelGuide();
  cancelClickCount = 0;
  cartManager.clearCart();
  hidePaymentScreen();
  renderKioskCategories();
});

// =========================================================
// 2-4: Admin intervention tab + history with delete
// =========================================================
let lastInterventionLogs = [];

function _makeInterventionCell(text, styleStr) {
  const td = document.createElement('td');
  td.className = 'p-3 text-xs';
  if (styleStr) td.setAttribute('style', styleStr);
  td.textContent = text;
  return td;
}
function _makeInterventionResultBadge(success) {
  const badge = document.createElement('span');
  badge.className = 'text-xs font-bold px-2 py-0.5 rounded-full';
  if (success) {
    badge.setAttribute('style', 'background:#dcf5e7;color:var(--success)');
    badge.textContent = '完成';
  } else {
    badge.setAttribute('style', 'background:var(--surface2);color:var(--text2)');
    badge.textContent = '待觀察';
  }
  return badge;
}
function _makeInterventionHistoryRow(log) {
  const barrier = log.barrier_result || {};
  const intervention = log.intervention || {};
  const uiContext = log.ui_context || {};
  const result = log.result || {};
  const success = Boolean(result.checkout_success || result.payment_success);
  const tr = document.createElement('tr');
  tr.appendChild(_makeInterventionCell(log.timestamp ? new Date(log.timestamp).toLocaleString() : '-', 'color:var(--text2)'));
  tr.appendChild(_makeInterventionCell(zhInteractionLabel('page', uiContext.page_id || '-'), 'color:var(--text)'));
  tr.appendChild(_makeInterventionCell(zhInteractionLabel('barrier', barrier.barrier_state || '-'), 'color:var(--accent2)'));
  tr.appendChild(_makeInterventionCell(zhInteractionLabel('action', intervention.action || '-'), 'color:var(--info)'));
  const resultTd = document.createElement('td');
  resultTd.className = 'p-3 text-center';
  resultTd.appendChild(_makeInterventionResultBadge(success));
  tr.appendChild(resultTd);
  const delTd = document.createElement('td');
  delTd.className = 'p-3 text-center';
  const delBtn = document.createElement('button');
  delBtn.className = 'text-xs px-2 py-1 rounded-xl';
  delBtn.setAttribute('style', 'color:var(--danger);border:1px solid var(--border)');
  const icon = document.createElement('i');
  icon.className = 'fas fa-trash';
  delBtn.appendChild(icon);
  delBtn.onclick = () => tr.remove();
  delTd.appendChild(delBtn);
  tr.appendChild(delTd);
  return tr;
}
function renderInterventionHistory() {
  const tbody = document.getElementById('interventionHistoryBody');
  if (!tbody) return;
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  if (!lastInterventionLogs.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 6;
    td.className = 'p-4 text-center text-sm';
    td.setAttribute('style', 'color:var(--text2)');
    td.textContent = '尚無歷史介入紀錄。';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  lastInterventionLogs.forEach(log => tbody.appendChild(_makeInterventionHistoryRow(log)));
}
window.switchInterventionTab = function(tab) {
  const panelCurrent = document.getElementById('int-panel-current');
  const panelHistory = document.getElementById('int-panel-history');
  const btnCurrent = document.getElementById('int-tab-current');
  const btnHistory = document.getElementById('int-tab-history');
  if (!panelCurrent || !panelHistory) return;
  if (tab === 'history') {
    panelCurrent.classList.add('hidden');
    panelHistory.classList.remove('hidden');
    btnCurrent?.classList.remove('active');
    btnHistory?.classList.add('active');
    renderInterventionHistory();
  } else {
    panelHistory.classList.add('hidden');
    panelCurrent.classList.remove('hidden');
    btnHistory?.classList.remove('active');
    btnCurrent?.classList.add('active');
  }
};
window.clearInterventionHistory = async function() {
  if (!confirm('確定清空所有介入歷史紀錄？此操作無法還原。')) return;
  try {
    await api.clearInterventionLogs();
    lastInterventionLogs = [];
    renderInterventionHistory();
    showAdminNotice('歷史介入紀錄已清空。', 'success');
    loadInterventionStats();
  } catch {
    showAdminNotice('清空失敗，請重試。', 'error');
  }
};


Object.assign(window, {
  closeVoiceBubble,
  switchMainView,
  switchAdminTab,
  loadInterventionStats,
  loadEmotionClips,
  loadEmotionStatus,
  clearPushLogs,
  toggleFeature,
  saveSettings,
  clearEmotionClips,
  saveMenu,
  loadRagData,
  clearAllRagDocs,
  addRagDoc,
  reviewAllRagDocs,
  uploadRagPdf,
  updateCartQty: trackedUpdateCartQty,
  deleteCartItem: trackedDeleteCartItem,
  trackInteractionEvent,
  reportInteractionEvent,
  maybeCheckBarrierState,
  loadRagStatus,
  switchInterventionTab: window.switchInterventionTab,
  clearInterventionHistory: window.clearInterventionHistory,
});

if (isAdminMode()) {
  switchMainView('admin');
  initRealtimeClients();
} else {
  applyKioskLanguage();
  cartManager.renderCart();
  applyFeaturesToPOS();
  initAdminToggles();
  initRealtimeClients();
}
