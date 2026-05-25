import * as api from './api.js?v=uifix-20260521';
import { API_BASE } from './api.js?v=uifix-20260521';
import {
  ui,
  escapeHTML,
  switchMainView as switchMainViewUI,
  switchAdminTab as switchAdminTabUI,
  updateEmotionCameraPanel as updateEmotionCameraPanelUI,
  updateEmotionDetectionOverlay as updateEmotionDetectionOverlayUI
} from './ui.js?v=uifix-20260521';
import {
  ensureMediaTracks as ensureMediaTracksCore,
  createVideoRecorder,
  createAudioRecorder,
  captureVideoFrameBlob
} from './media.js?v=uifix-20260521';
import { createCartManager } from './cart.js?v=uifix-20260521';
import { createRecommendationManager } from './recommendation.js?v=uifix-20260521';
import { connectRealtime } from './realtime_client.js?v=uifix-20260521';
import {
  captureTriggeredClip,
  hasRollingMediaBuffer,
  startRollingMediaBuffer,
  stopRollingMediaBuffer
} from './media_buffer.js?v=uifix-20260521';

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
let demoRecommendTimer = null;
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
let voiceOrderingAvailable = false;
let autoVoiceTimer = null;
let autoVoiceInFlight = false;
let askRecordingStartedAt = 0;
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
    holdVoiceOrder: '長按語音點餐',
    voiceAskHint: '語音發問開啟後可詢問 AI 助理',
    listeningAsk: '聆聽發問中...',
    listeningOrder: '聆聽點餐中...',
    aiThinking: 'AI 思考中...',
    recognizingOrder: '辨識餐點中...',
    serviceTitle: '通知客服人員',
    serviceSub: '確認後開始收音並分析語系與情緒',
    serviceRecordStart: '開始收音',
    serviceRecordStop: '停止並送出',
    serviceWaiting: '等待客服請求。',
    serviceRecording: '正在收音，停止後會通知客服並分析語系與情緒。',
    serviceTooShort: '收音時間過短，請重新操作。',
    languageZh: '繁體中文',
    languageEn: 'English',
    emotion: '情緒',
    priority: '優先級',
    customer: '顧客',
    serviceReply: '客服回覆',
    serviceAccepted: '已立即通知客服；語音文字與情緒證據會在背景完成後更新到客服紀錄。',
    addedToCart: '已加入購物車：{items}',
    noVoiceOrderItem: '沒有在菜單中找到可加入購物車的餐點。',
    networkFailed: '網路連線失敗，請稍後再試。',
    voiceOrderFailed: '語音點餐失敗，請稍後再試。',
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
    holdVoiceOrder: 'Hold to Order',
    voiceAskHint: 'Enable voice Q&A to ask the AI assistant',
    listeningAsk: 'Listening...',
    listeningOrder: 'Listening for order...',
    aiThinking: 'AI is thinking...',
    recognizingOrder: 'Recognizing order...',
    serviceTitle: 'Call Staff',
    serviceSub: 'Record voice for language and emotion analysis',
    serviceRecordStart: 'Start Recording',
    serviceRecordStop: 'Stop and Send',
    serviceWaiting: 'Waiting for service request.',
    serviceRecording: 'Recording. Stop to notify staff and analyze.',
    serviceTooShort: 'Recording is too short. Please try again.',
    languageZh: 'Traditional Chinese',
    languageEn: 'English',
    emotion: 'Emotion',
    priority: 'Priority',
    customer: 'Customer',
    serviceReply: 'Service Reply',
    serviceAccepted: 'Staff has been notified. Voice text and emotion evidence will update in the background.',
    addedToCart: 'Added to cart: {items}',
    noVoiceOrderItem: 'No matching menu item was found.',
    networkFailed: 'Network failed. Please try again later.',
    voiceOrderFailed: 'Voice ordering failed. Please try again later.',
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
  if (demoRecommendTimer) clearTimeout(demoRecommendTimer);
  emotionLoopId = null;
  detectionLoopId = null;
  recommendLoopId = null;
  demoRecommendTimer = null;
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
  voiceAsk: false,
  recommend: true,
  emotionBackend: false,
  emotionChat: false,
  emotionCamera: false,
  emotionRecommend: true,
  eventTriggeredMultimodal: true,
  abTest: false,
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
    const versionMatches = localStorage.getItem('kiosk_feat_version') === FEATURE_SCHEMA_VERSION;
    const hasSavedFeatures = Boolean(localStorage.getItem('kiosk_feat'));
    const saved = JSON.parse(localStorage.getItem('kiosk_feat') || '{}');
    const features = { ...FEAT_DEFAULTS, ...saved };
    const shouldApplyDemoDefaults = isDemoPublicMode() && (!hasSavedFeatures || !versionMatches);
    if (!versionMatches || shouldApplyDemoDefaults) {
      features.emotionBackend = false;
      if (shouldApplyDemoDefaults) {
        features.voiceAsk = true;
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
      features.voiceAsk = true;
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
  if (key === 'voiceAsk' && !f.voiceAsk && askRecorder?.state === 'recording') askRecorder.stop();
  if ((key === 'emotion' || key === 'emotionBackend') && (!f.emotion || !f.emotionBackend)) stopEmotionLoop();
  applyFeaturesToPOS();
  if (isSystemRunning && (key === 'voiceAsk' || key === 'emotion' || key === 'emotionBackend')) {
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
  if (key === 'abTest') clearAllPushCards();
  if (key === 'emotion') updateEmotionAdminVisibility();
  if (key === 'emotionRecommend') loadEmotionStatus();
}

function applyFeaturesToPOS() {
  const f = getFeatures();
  const center = document.getElementById('centerPanel');
  // 攝影機作為背景感測來源保留，不在 POS 版面中顯示欄位
  const cam = document.getElementById('mod-camera');
  if (cam) cam.style.display = 'none';
  // 語音按鈕
  const voice = document.getElementById('mod-voice');
  if (voice) voice.style.display = 'none';
  if (ui.serviceFab) ui.serviceFab.style.display = 'none';
  if (ui.kioskVoiceBtn) ui.kioskVoiceBtn.style.display = 'inline-flex';
  if (ui.askText && isDemoPublicMode()) {
    ui.askText.textContent = '您可以直接說：我想吃雞肉，有什麼推薦？';
  }
  // 感測區永遠不佔版面，避免功能關閉後留下空白 UI 欄位
  if (center) center.style.display = 'none';
  // 語音回覆氣泡（關閉語音模組時隱藏）
  if (!f.voiceAsk) closeVoiceBubble();
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
  ui.serviceFab?.classList.remove('hidden');
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
  kioskScreen = 'menu';
  kioskActiveGroup = groupId;
  kioskActiveFilter = filter;
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
  ui.serviceFab?.classList.add('hidden');
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
  if (ui.askText) ui.askText.textContent = kt('holdVoiceOrder');
  const askHint = document.querySelector('#askBtnText + span');
  if (askHint) askHint.textContent = kt('voiceAskHint');
  const serviceTitle = document.querySelector('#posServiceWindow .font-bold.text-sm');
  if (serviceTitle) serviceTitle.textContent = kt('serviceTitle');
  const serviceSub = document.querySelector('#posServiceWindow .text-xs');
  if (serviceSub) serviceSub.textContent = kt('serviceSub');
  if (ui.serviceRecordText && !ui.serviceRecord?.classList.contains('recording')) {
    ui.serviceRecordText.textContent = kt('serviceRecordStart');
  }
  if (ui.serviceResult && !ui.serviceResult.dataset.hasResponse) {
    ui.serviceResult.textContent = kt('serviceWaiting');
  }
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
  promotionPausedUntil = Date.now() + 10 * 60 * 1000;
  recommendPending = false;
  stopAutoVoiceOrdering();
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
  // urgent=true 或 needs_human_staff=true 時跳出回應 modal，admin 可即時回覆
  if (payload.urgent || payload.needs_human_staff) {
    showCsUrgentModal(payload);
  }
  loadCustomerServiceData({ silent: true });
}

let csUrgentActiveSourceId = '';

function showCsUrgentModal(payload = {}) {
  const modal = document.getElementById('csUrgentModal');
  if (!modal) return;
  csUrgentActiveSourceId = String(payload.source_id || '');
  const setText = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value || '—';
  };
  setText('csUrgentUserText', payload.user_text || '（等待語音文字）');
  setText('csUrgentEmotion', payload.emotion || '—');
  setText('csUrgentState', payload.customer_service_state || '—');
  setText('csUrgentDraft', payload.customer_reply || payload.staff_summary || '—');
  setText('csUrgentPriority', String(payload.priority || 'high').toUpperCase());
  const replyArea = document.getElementById('csUrgentReply');
  if (replyArea && !replyArea.value) replyArea.value = payload.customer_reply || '';
  const sendBtn = document.getElementById('csUrgentSend');
  if (sendBtn) sendBtn.disabled = !csUrgentActiveSourceId;
  const status = document.getElementById('csUrgentStatus');
  if (status) status.style.display = 'none';
  modal.classList.remove('hidden');
  // 提示音 + 視覺：暫時不加重以避免干擾，依需要可加 audio
}

function hideCsUrgentModal() {
  const modal = document.getElementById('csUrgentModal');
  if (modal) modal.classList.add('hidden');
  csUrgentActiveSourceId = '';
  const replyArea = document.getElementById('csUrgentReply');
  if (replyArea) replyArea.value = '';
}

async function submitCsUrgentReply() {
  const status = document.getElementById('csUrgentStatus');
  const reply = (document.getElementById('csUrgentReply')?.value || '').trim();
  if (!csUrgentActiveSourceId) {
    if (status) { status.textContent = '尚未收到完整客服紀錄，請稍候片刻再回覆。'; status.style.display = 'block'; }
    return;
  }
  if (!reply) {
    if (status) { status.textContent = '請先輸入回覆內容。'; status.style.display = 'block'; }
    return;
  }
  const sendBtn = document.getElementById('csUrgentSend');
  if (sendBtn) sendBtn.disabled = true;
  if (status) { status.textContent = '送出中...'; status.style.display = 'block'; }
  try {
    const result = await api.sendHumanReply(csUrgentActiveSourceId, { reply, language: 'zh' });
    if (result?.status === 'success') {
      if (status) status.textContent = '已送出，POS 端會立即播放語音。';
      setTimeout(hideCsUrgentModal, 800);
      loadCustomerServiceData({ silent: true });
    } else {
      if (status) status.textContent = `送出失敗：${result?.message || '未知錯誤'}`;
      if (sendBtn) sendBtn.disabled = false;
    }
  } catch (e) {
    if (status) status.textContent = `送出失敗：${e.message || e}`;
    if (sendBtn) sendBtn.disabled = false;
  }
}

(function bindCsUrgentModalControls() {
  if (typeof document === 'undefined') return;
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('csUrgentClose')?.addEventListener('click', hideCsUrgentModal);
    document.getElementById('csUrgentLater')?.addEventListener('click', hideCsUrgentModal);
    document.getElementById('csUrgentSend')?.addEventListener('click', submitCsUrgentReply);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') hideCsUrgentModal();
    });
  });
})();

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
    const needAudio = true;
    const mediaReady = await ensureMediaTracks({ video: needVideo, audio: needAudio });
    if (!mediaReady && (needVideo || needAudio)) console.warn('Media permission unavailable; POS flow continues without rolling buffer.');
    await loadMenu();
    applyFeaturesToPOS();
    if (ui.serviceFab) ui.serviceFab.style.display = 'none';
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
    setupAskRecorder();
  } catch { alert("無法存取攝影機與麥克風。"); }
};

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

async function fetchAndDisplayRecommend() {
  const f = getFeatures();
  if (!f.recommend) return;
  if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) return;
  if (document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open')) return;
  if (Date.now() < promotionPausedUntil) return;
  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('ab_mode', f.abTest ? 'ab' : 'single');
  fd.append('emotion_influence', String(Boolean(f.emotion && f.emotionRecommend)));
  try {
    const data = await api.autoRecommend(fd);
    if (data.status === 'success') displayRecommendation(data);
  } catch { }
}

function scheduleDemoFirstRecommend() {
  if (!isDemoPublicMode() || demoRecommendTimer || !isPosActive() || !getFeatures().recommend) return;
  const delayMs = 8000 + Math.floor(Math.random() * 4000);
  demoRecommendTimer = setTimeout(async () => {
    demoRecommendTimer = null;
    if (!isPosActive() || document.hidden || recommendPending) return;
    await fetchAndDisplayRecommend();
  }, delayMs);
}

function startRecommendLoop() {
  if (isAdminMode()) return;
  if (recommendLoopId) return;
  recommendLoopId = setInterval(async () => {
    if (!isPosActive() || recommendPending) return;
    if (document.hidden) return;
    await fetchAndDisplayRecommend();
  }, Math.max(10, Number(perfValue('RECOMMEND_INTERVAL_SEC')) || 30) * 1000);
  scheduleDemoFirstRecommend();
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

function setVoiceOrderingAvailable(available) {
  voiceOrderingAvailable = Boolean(available);
  const disabled = isPosMode() && isSystemRunning && getFeatures().emotion && !voiceOrderingAvailable;
  ui.askBtn?.classList.toggle('opacity-50', disabled);
  ui.kioskVoiceBtn?.classList.toggle('opacity-50', disabled);
  if (ui.askText && disabled) ui.askText.textContent = kioskLang === 'en' ? 'Voice ordering is not ready yet' : '語音點餐尚未準備完成';
  if (ui.askBtn) ui.askBtn.disabled = disabled;
  if (ui.kioskVoiceBtn) ui.kioskVoiceBtn.disabled = disabled;
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
      trackInteractionEvent({
        event_type: 'voice_order_failed',
        button_id: 'askBtn',
        metadata: { reason: 'audio_too_short', duration_ms: durationMs, bytes: blob.size }
      });
      ui.askText.textContent = kt('holdVoiceOrder');
      autoVoiceInFlight = false;
      return;
    }

    const voiceAskEnabled = true;
    ui.askText.textContent = voiceAskEnabled ? kt('aiThinking') : kt('recognizingOrder');
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('audio', blob);
    fd.append('multi_lang', String(getFeatures().multiLang));
    fd.append('use_ollama', String(voiceAskEnabled));
    try {
      const data = await api.ask(fd);
      if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) {
        autoVoiceInFlight = false;
        return;
      }
      if (data.status === 'success') {
        lastVoiceText = data.user_text || lastVoiceText;
        if (data.audio_base64) playVoice(data.audio_base64);
        showVoiceBubble(data);
        const appliedOrders = cartManager.applyCartActions(data.cart_actions || []);
        if (appliedOrders.length) {
          trackInteractionEvent({
            event_type: 'cart_edit',
            button_id: 'askBtn',
            cart_edit_count: appliedOrders.length,
            metadata: { source: 'voice_order', items: appliedOrders }
          });
          showPushNotice(kt('addedToCart').replace('{items}', appliedOrders.join('、')));
        }

        if (voiceAskEnabled && data.trigger_recommend && getFeatures().recommend) {
          recommendPending = true;
          setTimeout(async () => {
            await fetchAndDisplayRecommend();
            recommendPending = false;
          }, Number(perfValue('RECOMMEND_AFTER_ASK_DELAY_MS')) || 1200);
        }
        if (data.mentioned_ids) data.mentioned_ids.forEach(id => sessionPushedIds.add(id));
      } else {
        console.debug('[voice assistant skipped]', data.message || data.status);
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
          dialogue: { zh: { user_text: '', ai_response: kt('networkFailed') } }
        });
      } else {
        showPushNotice(kt('voiceOrderFailed'));
      }
    }
    ui.askText.textContent = kt('holdVoiceOrder');
    autoVoiceInFlight = false;
  };
}

function startAskRecording(sourceBtn) {
  if (!voiceOrderingAvailable) {
    showPushNotice(kioskLang === 'en' ? 'Voice ordering is not ready yet.' : '語音點餐尚未準備完成。');
    return;
  }
  if (askRecorder && askRecorder.state === 'inactive') {
    trackInteractionEvent({
      event_type: getFeatures().voiceAsk ? 'voice_ask_started' : 'voice_order_started',
      button_id: sourceBtn?.id || 'askBtn',
      metadata: { voice_ask_enabled: getFeatures().voiceAsk }
    });
    askRecordingStartedAt = Date.now();
    askRecorder.start();
    ui.askBtn.classList.add('recording');
    ui.kioskVoiceBtn?.classList.add('recording');
    ui.askText.textContent = getFeatures().voiceAsk ? kt('listeningAsk') : kt('listeningOrder');
  }
}
function stopAskRecording() {
  if (askRecorder && askRecorder.state === 'recording') {
    askRecorder.stop();
    ui.askBtn.classList.remove('recording');
    ui.kioskVoiceBtn?.classList.remove('recording');
  }
}
ui.askBtn.onmousedown = ui.askBtn.ontouchstart = (e) => {
  e.preventDefault();
  startAskRecording(ui.askBtn);
};
ui.askBtn.onmouseup = ui.askBtn.ontouchend = (e) => {
  e.preventDefault();
  stopAskRecording();
};
if (ui.kioskVoiceBtn) {
  ui.kioskVoiceBtn.onmousedown = ui.kioskVoiceBtn.ontouchstart = (e) => {
    e.preventDefault();
    startAskRecording(ui.kioskVoiceBtn);
  };
  ui.kioskVoiceBtn.onmouseup = ui.kioskVoiceBtn.ontouchend = (e) => {
    e.preventDefault();
    stopAskRecording();
  };
}

window.addEventListener('beforeunload', () => {
  try {
    if (askRecorder?.state === 'recording') askRecorder.stop();
    if (serviceRecorder?.state === 'recording') serviceRecorder.stop();
    if (adminServiceRecorder?.state === 'recording') adminServiceRecorder.stop();
  } catch { }
  if (emotionLoopId) clearInterval(emotionLoopId);
  if (detectionLoopId) clearInterval(detectionLoopId);
  if (recommendLoopId) clearInterval(recommendLoopId);
  if (demoRecommendTimer) clearTimeout(demoRecommendTimer);
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
  ui.serviceResult.dataset.hasResponse = html && html !== kt('serviceWaiting') ? '1' : '';
}

function renderServiceResponse(targetEl, data) {
  const langLabel = data.detected_lang === 'en' ? kt('languageEn') : kt('languageZh');
  const acceptedNote = data.accepted
    ? `<p class="text-xs mb-2 font-semibold" style="color:var(--accent2)">${escapeHTML(kt('serviceAccepted'))}</p>`
    : '';
  targetEl.innerHTML = `
    <div class="flex flex-wrap gap-2 mb-3">
      <span class="text-xs px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">${escapeHTML(langLabel)}</span>
      <span class="text-xs px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">${escapeHTML(kt('emotion'))} ${escapeHTML(formatEmotion(data.emotion || '-'))}</span>
      <span class="text-xs px-2 py-0.5 rounded-full" style="background:var(--surface2);color:var(--text2)">${escapeHTML(kt('priority'))} ${escapeHTML(data.priority || '-')}</span>
    </div>
    ${acceptedNote}
    <p class="text-xs mb-1" style="color:var(--text2)">${escapeHTML(kt('customer'))}</p>
    <p class="mb-2 font-medium" style="color:var(--text)">${escapeHTML(data.user_text || data.staff_summary || '')}</p>
    <p class="text-xs mb-1" style="color:var(--text2)">${escapeHTML(kt('serviceReply'))}</p>
    <p class="font-semibold" style="color:var(--text)">${escapeHTML(data.customer_reply || '')}</p>
  `;
  targetEl.dataset.hasResponse = '1';
}

function resetServiceButton() {
  ui.serviceRecord.classList.remove('recording');
  ui.serviceRecordText.textContent = kt('serviceRecordStart');
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
  ui.serviceRecordText.textContent = kt('serviceRecordStop');
  setServiceResult(kt('serviceRecording'));
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
    setServiceResult(kt('serviceTooShort'));
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
  loadCustomerServiceData();
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
    document.getElementById('inp-rag-min-score').value = rag.min_retrieval_score || 0.08;
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
    strict_grounding: document.getElementById('inp-rag-strict-grounding').checked,
    answer_verification: document.getElementById('inp-rag-answer-verification').checked,
    fail_closed_on_eval_error: document.getElementById('inp-rag-fail-closed').checked,
    min_retrieval_score: parseFloat(document.getElementById('inp-rag-min-score').value || '0.08'),
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
      const suffix = log.media_url && log.media_url.includes('?') ? api.adminQuerySuffix('&') : api.adminQuerySuffix();
      const mediaSrc = log.media_url ? `${API_BASE}${log.media_url}${suffix}` : '';
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
  loadEmotionStatus,
  loadCustomerServiceData,
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
  maybeCheckBarrierState
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
