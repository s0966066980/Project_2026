import * as api from '../shared/api.js';
import {
  ui,
  escapeHTML,
  switchMainView as switchMainViewUI,
} from '../shared/ui.js';
import {
  ensureMediaTracks as ensureMediaTracksCore,
  createVideoRecorder,
  createAudioRecorder,
  captureVideoFrameBlob
} from './media.js';
import { createCartManager } from './cart.js';
import { connectRealtime } from '../shared/realtime_client.js';

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
let isSystemRunning = false;
let orderCompleted = false;
let menuData = [];
let sessionPushedIds = new Set();
let sessionAiPushCartCount = 0;
let sessionCartSources = []; // [{id, source}] 記錄每筆加入來源
let voiceBubbleTimer = null;
let lastInterventionEventAt = 0;
let interactionModalTimer = null;
let lastInteractionAt = Date.now();
let pageDwellTimer = null;
let posRealtime = null;
let askRecordingStartedAt = 0;
let lastValidOrderActionAt = 0;
let lastCartAddAt = Date.now();
let choiceHesitationTimer = null;
let currentChoiceHesitationItem = null;
const CHOICE_HESITATION_IDLE_MS = 60_000;
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
  { id: 'happymeal', label: 'Happy Meal®', labelEn: 'Happy Meal®', image: '/static/mcd_categories/kids.jpg', categories: ['Happy Meal®'] },
  { id: 'single', label: '單點餐品', labelEn: 'A La Carte', image: '/static/mcd_categories/deals.jpg', categories: ['點心'] },
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
let fullSettings = {};
let runtimeSettings = {};



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
}

// =========================================================
// 功能模組狀態
// =========================================================
const FEAT_DEFAULTS = {
  emotion: true,
  voiceAssist: true,
  recommend: true,
  choiceHesitation: true,
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
    impatience_detected: '等待不耐',
    service_needed: '需要真人協助',
    potential_complaint: '疑似客訴',
    low_confidence: '資訊不足',
    unknown: '未知狀態',
  },
  action: {
    none: '不介入',
    show_payment_tutorial: '顯示付款教學',
    show_operation_hint: '顯示操作提示',
    recommend_popular_combo: '推薦熱門組合',
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
    menu_grid: '菜單區域',
    service_button: '客服按鈕',
    demo_ui: '實施例腳本',
    page_timer: '頁面停留計時',
    document: '畫面空白處',
    unknown: '未知來源',
  },
};

function getFeatures() {
  try {
    const versionMatches = localStorage.getItem('kiosk_feat_version') === FEATURE_SCHEMA_VERSION;
    const hasSavedFeatures = Boolean(localStorage.getItem('kiosk_feat'));
    const saved = JSON.parse(localStorage.getItem('kiosk_feat') || '{}');
    const features = { ...FEAT_DEFAULTS, ...saved };
    const shouldApplyDemoDefaults = isDemoPublicMode() && (!hasSavedFeatures || !versionMatches);
    if (!versionMatches || shouldApplyDemoDefaults) {
      if (shouldApplyDemoDefaults) {
        features.voiceAssist = true;
        features.recommend = true;
        features.choiceHesitation = true;
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
      features.choiceHesitation = true;
      features.eventTriggeredMultimodal = true;
    }
    return features;
  }
}
function saveFeatures(f) {
  localStorage.setItem('kiosk_feat', JSON.stringify(f));
  localStorage.setItem('kiosk_feat_version', FEATURE_SCHEMA_VERSION);
}


function applyFeaturesToPOS() {
  const f = getFeatures();
  const center = document.getElementById('centerPanel');
  // 語音協助按鈕只出現在底部導覽列，不出現在購物車、付款、完成頁。
  updateVoiceAssistVisibility();
  // 感測區永遠不佔版面，避免功能關閉後留下空白 UI 欄位
  if (center) center.style.display = 'none';
  // 語音回覆氣泡（關閉語音協助時隱藏）
  if (!f.voiceAssist) closeVoiceBubble();
  if (!f.recommend) aiPush.stop();
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
  closeVoiceBubble();
  hideVoiceAssistOverlay();
  hideChoiceHesitationModal();
  aiPush.hide();
}



function switchMainView(view) {
  if (view === 'admin' && !isAdminMode()) return;
  switchMainViewUI(view, { clearPOSFloatingUI, applyFeaturesToPOS, loadMenu });
  if (view !== 'admin') {
    startPosRealtime();
  }
  setInteractionPage(view === 'admin' ? 'admin_page' : 'menu_page', { source: 'switch_main_view' });
}


function findMenuItems(ids = []) {
  return ids
    .map(id => String(id || '').replace(/[^a-zA-Z0-9]/g, ''))
    .map(cleanId => menuData.find(m => m.id === cleanId || m.id.includes(cleanId)))
    .filter(Boolean);
}

const cartManager = createCartManager({ ui, escapeHTML, findMenuItems, onCartChange: updateKioskCartSummary, t: kt, lang: () => kioskLang });

function trackedAddToCart(item, metadata = {}) {
  lastValidOrderActionAt = Date.now();
  lastCartAddAt = Date.now();
  if (metadata.source === 'ai_push' || metadata.source === 'choice_hesitation') sessionAiPushCartCount++;
  if (item?.id) sessionCartSources.push({ id: item.id, source: metadata.source || 'manual' });
  hideChoiceHesitationModal();
  restartChoiceHesitationTimer();
  cartManager.addToCart(item);
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
  if (!cartManager.getCartIds().includes(id)) {
    sessionCartSources = sessionCartSources.filter(e => e.id !== id);
  }
  trackInteractionEvent({
    event_type: 'cart_edit',
    button_id: `cart_qty_${id}`,
    cart_edit_count: 1,
    metadata: { action: 'qty', item_id: id, delta }
  });
  if (cartManager.getCartIds().length === 0) {
    lastCartAddAt = Date.now();
    restartChoiceHesitationTimer();
  }
}

function trackedDeleteCartItem(id) {
  lastValidOrderActionAt = Date.now();
  interactionState.cartRemoveCount += 1;
  cartManager.deleteCartItem(id);
  sessionCartSources = sessionCartSources.filter(e => e.id !== id);
  trackInteractionEvent({
    event_type: 'cart_edit',
    button_id: `cart_delete_${id}`,
    cart_edit_count: 1,
    cart_remove_count: interactionState.cartRemoveCount,
    metadata: { action: 'delete', item_id: id }
  });
  if (cartManager.getCartIds().length === 0) {
    lastCartAddAt = Date.now();
    restartChoiceHesitationTimer();
  }
}

function clearAllPushCards() {
  ui.floatPush?.replaceChildren();
}

function showPushNotice(text) {
  if (!isPosActive() || !ui.floatPush) return;
  ui.floatPush.replaceChildren();
  const card = document.createElement('div');
  card.className = 'push-card push-notice';
  const p = document.createElement('p');
  p.className = 'push-notice-text';
  p.textContent = text;
  card.appendChild(p);
  ui.floatPush.appendChild(card);
  setTimeout(() => ui.floatPush?.replaceChildren(), 4000);
}


// =========================================================
// AI 推播底部欄
// =========================================================

const aiPush = (() => {
  const REFRESH_MS = 15_000;
  const RETRY_MS   = 1_000;
  let _timer    = null;
  let _inFlight = false;
  let _item     = null;

  // ── DOM shortcuts ──
  const $ = id => document.getElementById(id);

  function _eligible() {
    if (!$('aiPushBar')) return false;
    const paymentOpen = ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden');
    const cartOpen    = Boolean(document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open'));
    return Boolean(isPosActive() && !document.hidden && !_isVoiceActive() && !paymentOpen && !cartOpen && menuData.length);
  }

  function _render(item, pushText) {
    if (!item || !$('aiPushBar')) return;
    const visual = getMenuVisual(item);
    _item = item;

    const nameEl = $('aiPushItemName');
    const textEl = $('aiPushText');
    const imgEl  = $('aiPushImage');
    const emEl   = $('aiPushFallback');

    if (nameEl) nameEl.textContent = item.name || '';
    const prEl = $('aiPushItemPrice');
    if (prEl) prEl.textContent = formatItemPrice(item);
    if (textEl) textEl.textContent = pushText || `${item.name || '這份餐點'}現在很適合來一份！`;

    if (imgEl) {
      if (visual.image) {
        imgEl.src = visual.image;
        imgEl.alt = item.name || '';
        imgEl.style.display = 'block';
        imgEl.onerror = () => {
          imgEl.style.display = 'none';
          if (emEl) { emEl.textContent = visual.emoji || '🍔'; emEl.style.display = 'block'; }
        };
      } else {
        imgEl.style.display = 'none';
      }
    }
    if (emEl) {
      emEl.textContent = visual.emoji || '🍔';
      emEl.style.display = visual.image ? 'none' : 'block';
    }

    $('aiPushBar').classList.remove('hidden', 'loading');
  }

  // 從菜單選預設推播（不呼叫 Ollama）
  function _pickDefault() {
    const priority = ['超值全餐', '極選系列', '點心'];
    for (const cat of priority) {
      const hit = menuData.find(m => m.category === cat && m.id);
      if (hit) return hit;
    }
    return menuData[0] || null;
  }

  // 本地隨機備選（Ollama 失敗時使用），excludeCurrent=true 排除目前品項
  function _pickRandom(excludeCurrent = true) {
    const priced = menuData.filter(m => m && m.id && Number(m.price || 0) > 0);
    if (!priced.length) return _pickDefault();
    const pool = excludeCurrent && _item?.id
      ? priced.filter(m => m.id !== _item.id)
      : priced;
    const src = pool.length ? pool : priced;
    return src[Math.floor(Math.random() * src.length)];
  }

  // excludeCurrentItem=false 時不排除目前項目（首次呼叫用）
  async function _fetch(excludeCurrentItem = true) {
    if (_inFlight || !_eligible()) { if (!_eligible()) hide(); return; }
    _inFlight = true;
    if (!_item) $('aiPushBar')?.classList.add('loading');

    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('exclude_ids', JSON.stringify(excludeCurrentItem && _item?.id ? [_item.id] : []));
    try {
      const data = await api.aiPush(fd);
      const id     = data?.recommendation_id || '';
      const aiItem = id ? menuData.find(m => m.id === id) : null;
      // AI 推薦有效且與目前不同 → 採用；否則本地隨機備選
      const item = (aiItem && aiItem.id !== _item?.id)
        ? aiItem
        : _pickRandom(excludeCurrentItem);
      if (item) _render(item, (aiItem ? (data.push_text || '') : '') || `${item.name}是現在的熱門選擇，快來試試！`);
    } catch {
      // Ollama 無法連線，使用本地隨機備選確保畫面更新
      const fallback = _pickRandom(excludeCurrentItem);
      if (fallback) _render(fallback, `${fallback.name}是現在的熱門選擇，快來試試！`);
    } finally {
      _inFlight = false;
      $('aiPushBar')?.classList.remove('loading');
      _schedule(REFRESH_MS);
    }
  }

  function _schedule(delay) {
    _clearTimer();
    _timer = setTimeout(() => {
      _timer = null;
      if (_eligible()) _fetch();
      else { hide(); _schedule(RETRY_MS); }
    }, delay);
  }

  function _clearTimer() {
    if (_timer) { clearTimeout(_timer); _timer = null; }
  }

  // ── 對外介面 ──

  function start() {
    // ① 立即預載預設推播（零延遲，無需等待 Ollama）
    const def = _pickDefault();
    if (def) _render(def, `${def.name}是現在的熱門選擇，快來試試！`);
    // ② 背景呼叫 Ollama 生成真實推播文字（不排除預載項目，讓 AI 自由選擇）
    if (_eligible()) _fetch(false);
    else _schedule(RETRY_MS);
  }

  function stop() {
    _clearTimer();
    _inFlight = false;
    _item     = null;
    hide();
  }

  function hide() {
    const bar = $('aiPushBar');
    if (bar) { bar.classList.add('hidden'); bar.classList.remove('loading'); }
  }

  function scheduleAfterCartClose() { start(); }

  // 事件監聽（module 頂層執行一次）
  document.addEventListener('DOMContentLoaded', () => {
    $('aiPushPickBtn')?.addEventListener('click', () => {
      if (!_item) return;
      showItemConfirmModal(_item, 'ai_push');
      _schedule(REFRESH_MS);
    });
    $('aiPushRefreshBtn')?.addEventListener('click', () => _fetch());
    $('aiPushVoiceBtn')?.addEventListener('click', () => startAskRecording($('aiPushVoiceBtn')));
  });

  return { start, stop, hide, scheduleAfterCartClose };
})();

// =========================================================
// 餐點確認彈窗
// =========================================================
let _icItem   = null;
let _icQty    = 1;
let _icSource = 'menu_card';

function showItemConfirmModal(item, source = 'menu_card') {
  _icSource = source;
  if (!item) return;
  _icItem = item;
  _icQty  = 1;

  const visual = getMenuVisual(item);
  const modal  = document.getElementById('itemConfirmModal');
  if (!modal) return;

  const imgEl  = document.getElementById('itemConfirmImg');
  const emEl   = document.getElementById('itemConfirmEmoji');
  if (imgEl) {
    imgEl.src = visual.image || '';
    imgEl.alt = item.name || '';
    imgEl.style.display = visual.image ? 'block' : 'none';
    imgEl.onerror = () => {
      imgEl.style.display = 'none';
      if (emEl) { emEl.textContent = visual.emoji || '🍔'; emEl.style.display = 'block'; }
    };
  }
  if (emEl) {
    emEl.textContent = visual.emoji || '🍔';
    emEl.style.display = visual.image ? 'none' : 'block';
  }

  const nameEl  = document.getElementById('itemConfirmName');
  const priceEl = document.getElementById('itemConfirmPrice');
  const descEl  = document.getElementById('itemConfirmDesc');
  const qtyEl   = document.getElementById('itemConfirmQtyDisplay');
  if (nameEl)  nameEl.textContent  = item.name || '';
  if (priceEl) priceEl.textContent = formatItemPrice(item);
  if (descEl)  descEl.textContent  = item.description || '';
  if (qtyEl)   qtyEl.textContent   = '1';

  modal.classList.remove('hidden');
}

function hideItemConfirmModal() {
  _icItem   = null;
  _icQty    = 1;
  _icSource = 'menu_card';
  document.getElementById('itemConfirmModal')?.classList.add('hidden');
}

// wire up once after DOM ready
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('itemConfirmClose')?.addEventListener('click', hideItemConfirmModal);
  document.getElementById('itemConfirmBackdrop')?.addEventListener('click', hideItemConfirmModal);
  document.getElementById('itemConfirmCancel')?.addEventListener('click', hideItemConfirmModal);

  document.getElementById('itemConfirmMinus')?.addEventListener('click', () => {
    if (_icQty <= 1) return;
    _icQty--;
    const el = document.getElementById('itemConfirmQtyDisplay');
    if (el) el.textContent = String(_icQty);
  });

  document.getElementById('itemConfirmPlus')?.addEventListener('click', () => {
    if (_icQty >= 20) return;
    _icQty++;
    const el = document.getElementById('itemConfirmQtyDisplay');
    if (el) el.textContent = String(_icQty);
  });

  document.getElementById('itemConfirmAdd')?.addEventListener('click', () => {
    if (!_icItem) return;
    for (let i = 0; i < _icQty; i++) {
      trackedAddToCart(_icItem, { source: _icSource });
    }
    hideItemConfirmModal();
  });
});

function getChoiceHesitationModal() {
  return document.getElementById('choiceHesitationModal');
}

function isChoiceHesitationVisible() {
  return !getChoiceHesitationModal()?.classList.contains('hidden');
}

function hideChoiceHesitationModal(resetIdle = false) {
  const modal = getChoiceHesitationModal();
  modal?.classList.add('hidden');
  modal?.setAttribute('aria-hidden', 'true');
  currentChoiceHesitationItem = null;
  if (resetIdle) {
    lastCartAddAt = Date.now();
    restartChoiceHesitationTimer();
  }
}

function isChoiceHesitationEligible() {
  const paymentOpen = ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden');
  return Boolean(
    getFeatures().choiceHesitation !== false
    && isPosActive()
    && !document.hidden
    && !_isVoiceActive()
    && !paymentOpen
    && !isCartScreenOpen()
    && cartManager.getCartIds().length === 0
    && menuData.length
  );
}

function getChoiceHesitationCandidates() {
  const pricedItems = menuData.filter(item => item && item.id && Number(item.price || 0) > 0);
  if (!pricedItems.length) return [];
  if (kioskScreen === 'menu') {
    const group = KIOSK_GROUPS.find(row => row.id === kioskActiveGroup);
    const allowed = new Set(group?.categories || []);
    let scoped = pricedItems.filter(item => allowed.has(String(item.category || '')));
    if (kioskActiveFilter && kioskActiveFilter !== '全部') {
      scoped = scoped.filter(item => itemMatchesSubFilter(item, kioskActiveFilter));
    }
    if (scoped.length) return scoped;
  }
  const preferredCategories = new Set(['超值全餐', '極選系列', '點心']);
  const preferred = pricedItems.filter(item => preferredCategories.has(String(item.category || '')));
  return preferred.length ? preferred : pricedItems;
}

function pickChoiceHesitationItem() {
  const candidates = getChoiceHesitationCandidates();
  if (!candidates.length) return null;
  const pool = candidates.length > 1 && currentChoiceHesitationItem
    ? candidates.filter(item => item.id !== currentChoiceHesitationItem.id)
    : candidates;
  return pool[Math.floor(Math.random() * pool.length)] || candidates[0];
}

function renderChoiceHesitationItem(item) {
  const modal = getChoiceHesitationModal();
  if (!modal || !item) return;
  const visual = getMenuVisual(item);
  const nameEl = document.getElementById('choiceHesitationName');
  const priceEl = document.getElementById('choiceHesitationPrice');
  const reasonEl = document.getElementById('choiceHesitationReason');
  const imageEl = document.getElementById('choiceHesitationImage');
  const fallbackEl = document.getElementById('choiceHesitationFallback');
  if (nameEl) nameEl.textContent = item.name || '推薦餐點';
  if (priceEl) priceEl.textContent = formatItemPrice(item);
  if (reasonEl) reasonEl.textContent = item.description || '先試試這份熱門餐點。';
  if (fallbackEl) {
    fallbackEl.textContent = visual.emoji || '🍔';
    fallbackEl.style.display = visual.image ? 'none' : 'block';
  }
  if (imageEl) {
    imageEl.style.display = visual.image ? 'block' : 'none';
    imageEl.src = visual.image || '';
    imageEl.alt = item.name || '推薦餐點';
    imageEl.onerror = () => {
      imageEl.style.display = 'none';
      if (fallbackEl) fallbackEl.style.display = 'block';
    };
  }
}

function showChoiceHesitationModal() {
  if (!isChoiceHesitationEligible() || isChoiceHesitationVisible()) return;
  const item = pickChoiceHesitationItem();
  if (!item) return;
  currentChoiceHesitationItem = item;
  renderChoiceHesitationItem(item);
  const modal = getChoiceHesitationModal();
  modal?.classList.remove('hidden');
  modal?.setAttribute('aria-hidden', 'false');
}

function restartChoiceHesitationTimer() {
  if (choiceHesitationTimer) clearTimeout(choiceHesitationTimer);
  choiceHesitationTimer = null;
  if (!isPosMode() || !isSystemRunning || orderCompleted || getFeatures().choiceHesitation === false) return;
  const elapsed = Date.now() - lastCartAddAt;
  const delay = Math.max(1000, CHOICE_HESITATION_IDLE_MS - elapsed);
  choiceHesitationTimer = setTimeout(() => {
    choiceHesitationTimer = null;
    if (Date.now() - lastCartAddAt >= CHOICE_HESITATION_IDLE_MS && isChoiceHesitationEligible()) {
      showChoiceHesitationModal();
      return;
    }
    restartChoiceHesitationTimer();
  }, delay);
}

function stopChoiceHesitationTimer() {
  if (choiceHesitationTimer) clearTimeout(choiceHesitationTimer);
  choiceHesitationTimer = null;
  hideChoiceHesitationModal();
}


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
      showItemConfirmModal(item);
    });
    row.addEventListener('click', () => showItemConfirmModal(item));
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
  aiPush.hide();
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
  aiPush.scheduleAfterCartClose();
}

function showPaymentScreen() {
  hideCartScreen();
  ui.kioskPaymentScreen?.classList.remove('hidden');
  ui.kioskPaymentScreen?.setAttribute('aria-hidden', 'false');
  setInteractionPage('payment_page', { source: 'checkout_button' });
  stopChoiceHesitationTimer();
  aiPush.stop();
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
    promotion_paused: false,
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

function handleRealtimeSettingsChanged(event = {}) {
  const settings = event.payload?.settings;
  if (!settings || typeof settings !== 'object') return;
  fullSettings = { ...fullSettings, ...settings };
  runtimeSettings = { ...runtimeSettings, ...settings };
}

function handleRealtimeHumanReply(event = {}) {
  const payload = event.payload || {};
  if (!payload.reply) return;
  showPushNotice(payload.reply.slice(0, 80));
}

function handleRealtimeInteractionIntervention(event = {}) {
  lastInterventionEventAt = Date.now();
  const payload = event.payload || {};
  applyIntervention(payload.intervention || {}, payload.barrier_result || {});
  if (payload.intervention?.staff_notify) showPushNotice('已通知店員');
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

function initRealtimeClients() {
  if (isPosMode()) startPosRealtime();
}

function applyIntervention(intervention = {}, barrierResult = {}) {
  if (!intervention || intervention.action === 'none') return;
  console.log('[interaction intervention]', { intervention, barrierResult });

  document.getElementById('interactionInterventionBox')?.remove();

  if (intervention.ui_patch?.disable_promotion) {
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
    operation_hint: '操作協助',
  };
  const safeTitle = escapeHTML(titleMap[modalName] || '操作提示');
  const safeBody = escapeHTML(intervention.tts_text || intervention.reason || '需要協助時可通知店員。');
  const safeCategory = escapeHTML(barrierResult.intervention_category_label || '');
  const tagHtml = [safeCategory].filter(Boolean)
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



async function reportInteractionEvent(payload) {
  try {
    return await api.reportInteractionEvent(payload);
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
    const needAudio = Boolean(f.voiceAssist);
    const mediaReady = await ensureMediaTracks({ video: false, audio: needAudio });
    if (!mediaReady && needAudio) console.warn('Media permission unavailable; POS flow continues without rolling buffer.');
    await loadMenu();
    applyFeaturesToPOS();
    ui.overlay.style.opacity = '0';
    setTimeout(() => { ui.overlay.classList.add('hidden'); }, 500);
    isSystemRunning = true;
    lastCartAddAt = Date.now();
    startPageDwellWatcher();
    setInteractionPage('menu_page', { source: 'start_system' });
    restartChoiceHesitationTimer();
    setTimeout(() => aiPush.start(), 600); // overlay 淡出 500ms 後再顯示推播
    if (f.voiceAssist) setupAskRecorder();
  } catch { alert("無法存取攝影機與麥克風。"); }
};

// 閒置偵測：任何觸控 / 點擊都重設計時（全域，只需註冊一次）
document.addEventListener('pointerdown', () => { lastInteractionAt = Date.now(); }, { passive: true });
document.addEventListener('touchstart',  () => { lastInteractionAt = Date.now(); }, { passive: true });

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


function _isVoiceActive() {
  // 語音 overlay 可見（聆聽 or 思考中）時視為語音模式進行中
  return ui.voiceAssistOverlay && !ui.voiceAssistOverlay.classList.contains('hidden');
}

// =========================================================
// 語音問答（問題3: 回覆綁定浮動氣泡，問題5: 語言偵測）
// =========================================================
function closeVoiceBubble(stopAudio = true) {
  if (voiceBubbleTimer) clearTimeout(voiceBubbleTimer);
  voiceBubbleTimer = null;
  if (stopAudio && ui.audio) {
    ui.audio.pause();
    ui.audio.currentTime = 0;
  }
  ui.voiceBubble?.classList.add('hidden');
  ui.voiceBubble?.setAttribute('aria-hidden', 'true');
  const timerBar = document.getElementById('voiceReplyTimerBar');
  if (timerBar) {
    timerBar.style.transition = 'none';
    timerBar.style.width = '100%';
  }
}

function playVoice(b64, format = 'wav') {
  if (!b64 || !ui.audio) return;
  ui.audio.src = `data:audio/${format};base64,${b64}`;
  ui.audio.play().catch(() => {});
}

function showVoiceBubble(data) {
  if (!isPosActive() || !ui.voiceBubble || !ui.voiceDialogueGrid) return;
  hideVoiceAssistOverlay();
  const lang = data.detected_lang || 'zh';
  const dialogue = data.dialogue || {
    zh: { user_text: lang === 'zh' ? data.user_text : '', ai_response: lang === 'zh' ? data.ai_response : '' },
    en: { user_text: lang === 'en' ? data.user_text : '', ai_response: lang === 'en' ? data.ai_response : '' }
  };
  const d = dialogue[lang] || { user_text: data.user_text || '', ai_response: data.ai_response || '' };
  const userText = String(d.user_text || data.user_text || '').trim();
  const answerText = String(d.ai_response || data.ai_response || '-').trim();
  ui.voiceDialogueGrid.innerHTML = `
    ${userText ? `
      <div class="voice-reply-row voice-reply-question">
        <i class="fas fa-microphone"></i>
        <div>${escapeHTML(userText)}</div>
      </div>` : ''}
    <div class="voice-reply-row voice-reply-answer">
      <i class="fas fa-volume-up"></i>
      <div>${escapeHTML(answerText || '-')}</div>
    </div>`;
  if (ui.voiceLangBadge) ui.voiceLangBadge.textContent = lang === 'en' ? kt('enOutput') : kt('zhOutput');
  ui.voiceBubble.classList.remove('hidden');
  ui.voiceBubble.setAttribute('aria-hidden', 'false');
  const timerBar = document.getElementById('voiceReplyTimerBar');
  if (timerBar) {
    timerBar.style.transition = 'none';
    timerBar.style.width = '100%';
    requestAnimationFrame(() => {
      timerBar.style.transition = 'width 12s linear';
      timerBar.style.width = '0%';
    });
  }
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


function setupAskRecorder() {
  if (isAdminMode()) return;
  if (askRecorder) return; // 避免重複設定
  if (!stream || !stream.getAudioTracks().length) return;

  // 改用 video recorder：同步捕捉音訊+影像，供後端 Whisper + Emotion-LLaMA 並行使用
  askRecorder = createVideoRecorder(stream);
  let chunks = [];
  askRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
  askRecorder.onstop = async () => {
    const blob = new Blob(chunks, { type: 'video/webm' });
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
      showVoiceAssistMessage(kt('voiceTooShort'));
      return;
    }
    showVoiceAssistOverlay('thinking');
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('media', blob, 'voice_ask.webm');
    fd.append('multi_lang', String(getFeatures().multiLang));
    try {
      const data = await api.ask(fd);
      if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) {
        hideVoiceAssistOverlay();
        return;
      }
      if (data.status === 'success') {
        if (data.audio_base64) playVoice(data.audio_base64, data.audio_format || 'wav');
        showVoiceBubble(data);
        const appliedOrders = cartManager.applyCartActions(data.cart_actions || []);
        (data.cart_actions || []).forEach(action => {
          if (action.action === 'add' && action.id) {
            for (let i = 0; i < (Number(action.quantity) || 1); i++) {
              sessionCartSources.push({ id: action.id, source: 'voice_assist' });
            }
          }
        });
        if (appliedOrders.length) {
          lastValidOrderActionAt = Date.now();
          lastCartAddAt = Date.now();
          restartChoiceHesitationTimer();
          trackInteractionEvent({
            event_type: 'cart_edit', button_id: 'askBtn',
            cart_edit_count: appliedOrders.length,
            metadata: { source: 'voice_assist', items: appliedOrders }
          });
          showPushNotice(kt('addedToCart').replace('{items}', appliedOrders.join('、')));
        }
        if (data.mentioned_ids) data.mentioned_ids.forEach(id => sessionPushedIds.add(id));
      } else {
        showVoiceAssistMessage(data.ai_response || data.message || kt('voiceOrderFailed'), data.detected_lang || kioskLang);
        if (data.audio_base64) playVoice(data.audio_base64, data.audio_format || 'wav');
      }
    } catch {
      trackInteractionEvent({ event_type: 'voice_assist_failed', button_id: 'voiceAssistBtn', metadata: { reason: 'api_error' } });
      showVoiceAssistMessage(kt('voiceOrderFailed'));
    }
    const _doneText = document.getElementById('voiceAssistBtnText');
    if (_doneText) _doneText.textContent = kt('holdVoiceOrder');
    hideVoiceAssistOverlay();
  };
}

function startAskRecording(sourceBtn) {
  if (!askRecorder) setupAskRecorder();
  if (!askRecorder || askRecorder.state !== 'inactive') {
    showVoiceAssistMessage(kt('voiceMicNotReady'));
    return;
  }
  if (askRecorder && askRecorder.state === 'inactive') {
    // 開始錄音前先清除推播卡與殘留計時器，避免語音模式與推播卡重疊
    if (interactionModalTimer) { clearTimeout(interactionModalTimer); interactionModalTimer = null; }
    clearAllPushCards();
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
  if (pageDwellTimer) clearInterval(pageDwellTimer);
  if (choiceHesitationTimer) clearTimeout(choiceHesitationTimer);
  aiPush.stop();
});

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
  if (target.closest('#startupOverlay,#tutorialPopup,#choiceHesitationModal,#cancelGuidePopup,#voiceAssistOverlay,#voiceReplyBubble,#aiOverlayStack')) {
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
  fd.append('ai_push_cart_count', String(sessionAiPushCartCount));
  fd.append('cart_sources', JSON.stringify(sessionCartSources));
  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), 5000);
  try {
    const res = await api.checkout(fd, ctrl.signal);
    if (res && res.ok) {
      const data = await res.json().catch(() => ({}));
      return { orderNumber: data.order_number ?? 0, sessionId: data.session_id || sessionId };
    }
  } catch (err) {
    trackInteractionEvent({
      event_type: 'payment_failed',
      button_id: 'confirmPayBtn',
      payment_fail_count: 1,
      metadata: { reason: err?.message || 'checkout_log_failed' }
    });
  } finally {
    clearTimeout(tid);
  }
  return { orderNumber: 0, sessionId };
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

function showCompletionOverlay(orderData = {}) {
  try {
    switchMainView('pos');
    closeOrderConfirmModal();
    hidePaymentScreen();

    const overlay = document.getElementById('checkoutOverlay');
    if (!overlay) { setTimeout(() => location.reload(), 500); return; }

    const { orderNumber = 0, sessionId: sid = '', cartItems = [] } = orderData;

    // 取餐號碼：3 位數補零
    const pickNum = String(orderNumber).padStart(3, '0');
    // 訂單編號：直接用 session_id
    const orderId = sid || sessionId;

    const numEl = overlay.querySelector('[data-pick-number]');
    if (numEl) numEl.textContent = pickNum;

    const orderIdEl = overlay.querySelector('[data-order-id]');
    if (orderIdEl) orderIdEl.textContent = orderId;

    const listEl = overlay.querySelector('[data-item-list]');
    if (listEl) {
      listEl.textContent = '';
      cartItems.forEach(({ name, qty, price }) => {
        const row = document.createElement('div');
        row.className = 'co-item-row';
        const nameSpan = document.createElement('span');
        nameSpan.textContent = name;
        const qtySpan = document.createElement('span');
        qtySpan.className = 'co-item-qty';
        qtySpan.textContent = `×${qty}`;
        const priceSpan = document.createElement('span');
        priceSpan.className = 'co-item-price';
        priceSpan.textContent = `$${price}`;
        row.append(nameSpan, qtySpan, priceSpan);
        listEl.appendChild(row);
      });
    }

    const total = cartItems.reduce((s, i) => s + i.price * i.qty, 0);
    const totalEl = overlay.querySelector('[data-total]');
    if (totalEl) totalEl.textContent = `$${total}`;

    overlay.classList.remove('hidden', 'opacity-0');

    overlay.querySelector('[data-home-btn]')
      ?.addEventListener('click', () => location.reload());
  } catch (e) {
    console.error('[showCompletionOverlay]', e);
    setTimeout(() => location.reload(), 1000);
  }
}

async function finishOrder(cartIds, button, loadingText) {
  orderCompleted = true;
  updateVoiceAssistVisibility();
  clearPOSFloatingUI();
  stopChoiceHesitationTimer();
  aiPush.stop();
  const originalHTML = button?.innerHTML || '';
  setConfirmButtonsDisabled(true);
  if (button) button.innerHTML = `<i class="fas fa-spinner fa-spin mr-2"></i>${loadingText}`;

  let orderData = {};
  try {
    orderData = (await writeCheckoutLog(cartIds)) || {};
  } catch { /* silent */ }

  if (button) button.innerHTML = originalHTML;

  // Collect cart items snapshot for the completion screen
  const rawItems = cartManager.getCartItems ? cartManager.getCartItems() : [];
  orderData.cartItems = rawItems.map(item => ({
    name: item.name || item.id || '',
    qty:  Number(item.qty || item.quantity || 1),
    price: Number(item.price || 0),
  }));

  showCompletionOverlay(orderData);
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
  stopChoiceHesitationTimer();
  aiPush.stop();
  cartManager.clearCart();
  sessionCartSources = [];
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
  sessionCartSources = [];
  hideCartScreen();
  renderKioskCategories();
  lastCartAddAt = Date.now();
  restartChoiceHesitationTimer();
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
  sessionCartSources = [];
  hidePaymentScreen();
  renderKioskCategories();
  aiPush.start();
  lastCartAddAt = Date.now();
  restartChoiceHesitationTimer();
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
  finishOrder(cartIds, ui.kioskFastPayBtn, kt('checkoutProcessing'));
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
  finishOrder(cartIds, ui.kioskCounterPayBtn, kt('counterPayCreating'));
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
  finishOrder(cartIds, ui.confirmPayBtn, kt('checkoutProcessing'));
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

document.getElementById('choiceHesitationClose')?.addEventListener('click', () => hideChoiceHesitationModal(true));
document.querySelector('[data-choice-hesitation-close]')?.addEventListener('click', () => hideChoiceHesitationModal(true));
document.getElementById('choiceHesitationPick')?.addEventListener('click', () => {
  if (!currentChoiceHesitationItem) return;
  const item = currentChoiceHesitationItem;
  hideChoiceHesitationModal();
  showItemConfirmModal(item, 'choice_hesitation');
});
document.getElementById('choiceHesitationNext')?.addEventListener('click', () => {
  const nextItem = pickChoiceHesitationItem();
  if (!nextItem) return;
  currentChoiceHesitationItem = nextItem;
  renderChoiceHesitationItem(nextItem);
});
document.getElementById('choiceHesitationVoice')?.addEventListener('click', () => {
  hideChoiceHesitationModal(true);
  startAskRecording(document.getElementById('voiceAssistBtn'));
});
document.getElementById('voiceReplyBubbleClose')?.addEventListener('click', () => closeVoiceBubble());
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
  finishOrder(cartIds, null, kt('counterPayCreating'));
});

document.getElementById('cancelGuideConfirmCancel')?.addEventListener('click', () => {
  hideCancelGuide();
  cancelClickCount = 0;
  cartManager.clearCart();
  sessionCartSources = [];
  hidePaymentScreen();
  renderKioskCategories();
  aiPush.start();
  lastCartAddAt = Date.now();
  restartChoiceHesitationTimer();
});


Object.assign(window, {
  closeVoiceBubble,
  switchMainView,
  updateCartQty: trackedUpdateCartQty,
  deleteCartItem: trackedDeleteCartItem,
  trackInteractionEvent,
  reportInteractionEvent,
});

if (isAdminMode()) {
  switchMainView('admin');
  initRealtimeClients();
} else {
  applyKioskLanguage();
  cartManager.renderCart();
  applyFeaturesToPOS();
  initRealtimeClients();
}
