import * as api from '../shared/apiClient.js';
import { useDomReady } from '../shared/hooks/useDomEvents.js';
import {
  ui,
  escapeHTML,
  switchMainView as switchMainViewUI,
} from '../shared/ui.js';
import {
  ensureMediaTracks as ensureMediaTracksCore,
  startRollingBuffer,
  stopRollingBuffer,
  capturePreEventClip,
} from './media.js';
import { createCartManager } from './cart.js';
import { createRealtimeClient } from '../shared/realtimeClient.js';
import { getMenuVisual, formatItemPrice, resolveItemPrice } from './menuVisuals.js';
import { createKioskMenuController } from './controllers/kioskMenuController.js';
import { state } from './state.js';
import { configureKioskRuntime } from './runtime.js';
import {
  KIOSK_GROUPS,
  kioskFilterLabel,
  kioskGroupLabel,
  kioskText,
} from './constants/kiosk.js';
import {
  hideChoiceHesitationModal,
  isChoiceHesitationVisible, pickChoiceHesitationItem, renderChoiceHesitationItem,
  getChoiceHesitationModal,
} from './choiceHesitation.js';
import { openPaymentCountdown, closePaymentCountdown, showPaymentCountdownSection } from './paymentCountdown.js';
import { showMemberChoice, renderMemberMenuHeader } from './member.js';

const APP_MODE = (() => {
  const path = window.location.pathname;
  if (window.location.port === '9001') return 'admin';
  if (window.location.port === '9000') return 'kiosk';
  if (path.startsWith('/admin')) return 'admin';
  if (path.startsWith('/kiosk') || path.startsWith('/pos')) return 'kiosk';
  return 'kiosk';
})();

export function isAdminMode() { return APP_MODE === 'admin'; }
export function isKioskMode() { return APP_MODE === 'kiosk'; }
export function isPosMode() { return isKioskMode(); }

// =========================================================
// Controller 狀態
// =========================================================

function buildSessionId() {
  const requested = new URLSearchParams(window.location.search).get('session_id');
  const safeRequested = String(requested || '').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 80);
  return safeRequested || ('kiosk_' + Math.random().toString(36).substr(2, 9));
}

export const sessionId = buildSessionId();
let isSystemRunning = false;
let orderCompleted = false;
let sessionAiPushCartCount = 0;
let lastInterventionEventAt = 0;
let lastInteractionAt = Date.now();
let pageDwellTimer = null;
let kioskRealtime = null;
let passiveAudioStream = null;
let passiveAudioRecorder = null;
let passiveRecordingTimer = null;
let isPassiveListening = false;
let isPassivePaused = false;
let isPassiveRequestInFlight = false;
const PASSIVE_TRIGGER_COOLDOWN_MS = 10000;
const PASSIVE_CHUNK_MS = 5000;
let kioskLang = localStorage.getItem('kiosk_lang') === 'en' ? 'en' : 'zh';
export function getKioskLang() { return kioskLang; }
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

function resetRecommendationTracking() {
  sessionAiPushCartCount = 0;
  state.sessionPushedIds.clear();
  state.sessionCartSources = [];
  state.sessionRecommendationEvents.clear();
}

export function kt(key) {
  return kioskText(kioskLang, key);
}
let fullSettings = {};
let runtimeSettings = {};
export function getRuntimeSettings() { return runtimeSettings; }

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

export function getFeatures() {
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
      features.eventTriggeredMultimodal = true;
    }
    return features;
  }
}
function saveFeatures(f) {
  localStorage.setItem('kiosk_feat', JSON.stringify(f));
  localStorage.setItem('kiosk_feat_version', FEATURE_SCHEMA_VERSION);
}


function applyFeaturesToKiosk() {
  const f = getFeatures();
  const center = document.getElementById('centerPanel');
  // 語音協助按鈕只出現在底部導覽列，不出現在購物車、付款、完成頁。
  updateVoiceAssistVisibility();
  // 感測區永遠不佔版面，避免功能關閉後留下空白 UI 欄位
  if (center) center.style.display = 'none';
  // 語音回覆氣泡（關閉語音協助時隱藏）
  if (!f.voiceAssist) closeVoiceBubble();
  if (!f.recommend) aiRecommendationController.stop();
}

export function isCartScreenOpen() {
  return Boolean(document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open'));
}

function updateVoiceAssistVisibility() {
  const voiceAssistMod = document.getElementById('mod-voice-assist');
  if (!voiceAssistMod) return;
  const paymentOpen = ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden');
  const visible = getFeatures().voiceAssist && isKioskMode() && !isCartScreenOpen() && !paymentOpen && !orderCompleted;
  voiceAssistMod.classList.toggle('hidden', !visible);
}

export function isKioskActive() {
  return isSystemRunning && !orderCompleted && ui.kioskView && !ui.kioskView.classList.contains('hidden');
}
export function isPosActive() { return isKioskActive(); }

function clearKioskFloatingUI() {
  clearAllPushCards();
  closeVoiceBubble();
  hideVoiceAssistOverlay();
  hideChoiceHesitationModal();
  aiRecommendationController.hide();
}



function switchMainView(view) {
  if (view === 'admin' && !isAdminMode()) return;
  switchMainViewUI(view, { clearKioskFloatingUI, applyFeaturesToKiosk, loadMenu });
  if (view !== 'admin') {
    startKioskRealtime();
  }
  setInteractionPage(view === 'admin' ? 'admin_page' : 'menu_page', { source: 'switch_main_view' });
}


function findMenuItems(ids = []) {
  return ids
    .map(id => String(id || '').replace(/[^a-zA-Z0-9]/g, ''))
    .map(cleanId => state.menuData.find(m => m.id === cleanId || m.id.includes(cleanId)))
    .filter(Boolean);
}

function findPromotionTargetItem(offer = {}) {
  const itemIds = Array.isArray(offer.item_ids) ? offer.item_ids : [];
  const categories = Array.isArray(offer.categories) ? offer.categories : [];
  return findMenuItems(itemIds)[0] || state.menuData.find(item => categories.includes(item.category)) || null;
}

function applyPromotionPricing(item = {}, offer = {}) {
  const pricing = offer.pricing && typeof offer.pricing === 'object' ? offer.pricing : {};
  const promotionPrice = Number(pricing.promotion_price || 0);
  if (!promotionPrice) return { ...item };
  return {
    ...item,
    price: promotionPrice,
    original_price: Number(pricing.original_price || resolveItemPrice(item)),
    applied_offer_id: offer.offer_id || '',
    offer_ids: [offer.offer_id].filter(Boolean),
    promotion_title: offer.title || '',
  };
}

function bestPricedOfferForItem(item = {}) {
  const offers = Array.isArray(item.offers) ? item.offers : [];
  return offers.find(offer => Number(offer?.pricing?.promotion_price || 0) > 0) || null;
}

function getActivePromotionOffer() {
  return state.activePromotionOffer;
}

function handlePromotionPick(offer = {}) {
  const item = findPromotionTargetItem(offer);
  if (!item) return;
  const promotionItem = applyPromotionPricing(item, offer);
  trackedAddToCart(promotionItem, {
    source: 'promotion',
    offer_id: offer.offer_id || '',
    offer_ids: [offer.offer_id].filter(Boolean),
    promotion_price: promotionItem.price,
    original_price: promotionItem.original_price || resolveItemPrice(item),
  });
}

export const cartManager = createCartManager({ ui, escapeHTML, findMenuItems, onCartChange: updateKioskCartSummary, t: kt, lang: () => kioskLang, getVisual: getMenuVisual });

const kioskMenuController = createKioskMenuController({
  api,
  state,
  ui,
  escapeHTML,
  getMenuVisual,
  formatItemPrice,
  groups: KIOSK_GROUPS,
  getLanguage: () => kioskLang,
  translate: kt,
  translateFilter: (filter) => kioskFilterLabel(kioskLang, filter),
  translateGroup: (group) => kioskGroupLabel(kioskLang, group),
  showItemConfirmModal,
  getActivePromotionOffer,
  onPromotionPick: handlePromotionPick,
  updateKioskCartSummary,
  onCategorySwitchRepeat(groupId, filter) {
    interactionState.categorySwitchCount += 1;
    if (interactionState.categorySwitchCount >= 4) {
      trackInteractionEvent({
        event_type: 'category_switch_repeat',
        button_id: `category_${groupId}`,
        category_switch_count: interactionState.categorySwitchCount,
        metadata: { action: 'category_switch', group_id: groupId, filter },
      });
    }
  },
});

const {
  loadMenu,
  renderMenu,
  renderKioskCategories,
  showMenuGroup,
} = kioskMenuController;

export const itemMatchesSubFilter = kioskMenuController.itemMatchesSubFilter;

configureKioskRuntime({
  cartManager,
  clearAllPushCards,
  getFeatures,
  getKioskLang,
  getRuntimeSettings,
  isAdminMode,
  isKioskActive,
  isKioskMode,
  isPosActive,
  isPosMode,
  itemMatchesSubFilter,
  kt,
  sessionId,
  showPushNotice,
  trackInteractionEvent,
  pausePassiveListener,
  resumePassiveListener,
  triggerEmotionCapture,
  triggerEmotionCaptureAndWait,
});

function trackedAddToCart(item, metadata = {}) {
  state.lastValidOrderActionAt = Date.now();
  state.lastCartAddAt = Date.now();
  const offer = metadata.offer_id ? null : bestPricedOfferForItem(item);
  const cartItem = offer ? applyPromotionPricing(item, offer) : item;
  if (metadata.source === 'ai_push') sessionAiPushCartCount++;
  if (cartItem?.id) state.sessionCartSources.push({ id: cartItem.id, source: metadata.source || 'manual' });
  if (['ai_push', 'assist_recommend', 'choice_hesitation', 'promotion'].includes(metadata.source || '')) {
    reportRecommendationEvent('recommendation_added_to_cart', cartItem, {
      surface: metadata.source,
      source: metadata.source,
      quantity: 1,
      offer_ids: metadata.offer_ids || cartItem.offer_ids || [],
      metadata: { cart_source: metadata.source, offer_id: metadata.offer_id || cartItem.applied_offer_id || '' },
    });
  }
  hideChoiceHesitationModal();
  cartManager.addToCart(cartItem);
  trackInteractionEvent({
    event_type: 'cart_edit',
    button_id: cartItem?.id ? `menu_${cartItem.id}` : 'add_to_cart',
    cart_edit_count: 1,
    metadata: { action: 'add', item_id: cartItem?.id || '', ...metadata }
  });
}

function trackedUpdateCartQty(id, delta) {
  state.lastValidOrderActionAt = Date.now();
  cartManager.updateCartQty(id, delta);
  if (!cartManager.getCartIds().includes(id)) {
    state.sessionCartSources = state.sessionCartSources.filter(e => e.id !== id);
  }
  trackInteractionEvent({
    event_type: 'cart_edit',
    button_id: `cart_qty_${id}`,
    cart_edit_count: 1,
    metadata: { action: 'qty', item_id: id, delta }
  });
  if (cartManager.getCartIds().length === 0) {
    state.lastCartAddAt = Date.now();
  }
}

function trackedDeleteCartItem(id) {
  state.lastValidOrderActionAt = Date.now();
  interactionState.cartRemoveCount += 1;
  const removedSources = state.sessionCartSources.filter(e => e.id === id).map(e => e.source);
  cartManager.deleteCartItem(id);
  state.sessionCartSources = state.sessionCartSources.filter(e => e.id !== id);
  if (removedSources.some(source => ['ai_push', 'assist_recommend', 'choice_hesitation', 'voice_assist'].includes(source))) {
    const item = state.menuData.find(menuItem => menuItem.id === id) || { id };
    reportRecommendationEvent('recommendation_removed_from_cart', item, {
      surface: removedSources[0] === 'voice_assist' ? 'voice' : removedSources[0],
      source: removedSources[0],
      metadata: { cart_source: removedSources[0] },
    });
  }
  trackInteractionEvent({
    event_type: 'cart_edit',
    button_id: `cart_delete_${id}`,
    cart_edit_count: 1,
    cart_remove_count: interactionState.cartRemoveCount,
    metadata: { action: 'delete', item_id: id }
  });
  if (cartManager.getCartIds().length === 0) {
    state.lastCartAddAt = Date.now();
  }
}

export function clearAllPushCards() {
  ui.floatPush?.replaceChildren();
}

export function showPushNotice(text) {
  if (!isKioskActive() || !ui.floatPush) return;
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

const aiRecommendationController = (() => {
  const RECOMMENDATION_REFRESH_DELAY_MS = 15_000;
  const RECOMMENDATION_RETRY_DELAY_MS   = 1_000;
  let recommendationTimer    = null;
  let isRecommendationRequestInFlight = false;
  let currentRecommendationItem     = null;
  let currentRecommendationRecord = null;

  // ── DOM shortcuts ──
  const $ = id => document.getElementById(id);

  function isRecommendationEligible() {
    if (!$('aiPushBar')) return false;
    const paymentOpen = ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden');
    const cartOpen    = Boolean(document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open'));
    return Boolean(isKioskActive() && !document.hidden && !isVoiceAssistantActive() && !paymentOpen && !cartOpen && state.menuData.length);
  }

  function markCurrentRecommendationIgnored(reason = 'replaced') {
    if (!currentRecommendationItem || !currentRecommendationRecord || currentRecommendationRecord.completed) return;
    reportRecommendationEvent('recommendation_ignored', currentRecommendationItem, {
      ...currentRecommendationRecord,
      recommendationRecord: currentRecommendationRecord,
      quantity: 0,
      metadata: { reason },
    });
    currentRecommendationRecord.completed = true;
  }

  function renderRecommendation(item, pushText, recommendation = {}) {
    if (!item || !$('aiPushBar')) return;
    const recommendationOffers = Array.isArray(recommendation.offers) ? recommendation.offers : [];
    const displayItem = {
      ...item,
      offer_ids: recommendation.offer_ids || item.offer_ids || [],
      offers: recommendationOffers,
      rank: recommendation.rank || item.rank || 1,
      score: recommendation.score || item.score || 0,
      reasons: recommendation.reasons || item.reasons || [],
      strategy: recommendation.strategy || item.strategy || '',
      experiment_id: recommendation.experiment_id || item.experiment_id || '',
      variant_id: recommendation.variant_id || item.variant_id || '',
      source: recommendation.source || item.source || 'ai_push',
    };
    const pricedOffer = recommendationOffers.find(offer => Number(offer?.pricing?.promotion_price || 0) > 0);
    if (pricedOffer) {
      state.activePromotionOffer = pricedOffer;
      if (state.kioskScreen === 'menu') renderMenu();
    }
    const visual = getMenuVisual(item);
    if (currentRecommendationItem?.id && currentRecommendationItem.id !== item.id) {
      markCurrentRecommendationIgnored('replaced_by_new_ai_push');
    }
    currentRecommendationItem = displayItem;
    if (item.id) state.sessionPushedIds.add(item.id);
    currentRecommendationRecord = reportRecommendationEvent('recommendation_shown', displayItem, {
      surface: 'ai_push',
      source: recommendation.source || 'ai_push',
      rank: recommendation.rank || 1,
      score: recommendation.score || 0,
      reasons: recommendation.reasons || [],
      offer_ids: recommendation.offer_ids || [],
      experiment_id: recommendation.experiment_id || '',
      variant_id: recommendation.variant_id || '',
      strategy: recommendation.strategy || '',
      metadata: {
        model_status: recommendation.model_status || '',
        push_text: pushText || '',
        experiment_id: recommendation.experiment_id || '',
        variant_id: recommendation.variant_id || '',
        strategy: recommendation.strategy || '',
      },
    });

    const nameElement = $('aiPushItemName');
    const textElement = $('aiPushText');
    const imageElement  = $('aiPushImage');
    const emojiElement   = $('aiPushFallback');

    if (nameElement) nameElement.textContent = item.name || '';
    const priceElement = $('aiPushItemPrice');
    if (priceElement) priceElement.textContent = formatItemPrice(displayItem, kioskLang);
    if (textElement) textElement.textContent = pushText || `${item.name || '這份餐點'}現在很適合來一份！`;

    if (imageElement) {
      if (visual.image) {
        imageElement.src = visual.image;
        imageElement.alt = item.name || '';
        imageElement.style.display = 'block';
        imageElement.onerror = () => {
          imageElement.style.display = 'none';
          if (emojiElement) { emojiElement.textContent = visual.emoji || '🍔'; emojiElement.style.display = 'block'; }
        };
      } else {
        imageElement.style.display = 'none';
      }
    }
    if (emojiElement) {
      emojiElement.textContent = visual.emoji || '🍔';
      emojiElement.style.display = visual.image ? 'none' : 'block';
    }

    $('aiPushBar').classList.remove('hidden', 'loading');
  }

  // 從菜單選預設推播（不呼叫 Ollama）
  function pickDefaultRecommendation() {
    const priority = ['超值全餐', '極選系列', '點心'];
    for (const cat of priority) {
      const hit = state.menuData.find(m => m.category === cat && m.id);
      if (hit) return hit;
    }
    return state.menuData[0] || null;
  }

  // 本地隨機備選（Ollama 失敗時使用），excludeCurrent=true 排除目前品項
  function pickRandomRecommendation(excludeCurrent = true) {
    const priced = state.menuData.filter(m => m && m.id && resolveItemPrice(m) > 0);
    if (!priced.length) return pickDefaultRecommendation();
    const pool = excludeCurrent && currentRecommendationItem?.id
      ? priced.filter(m => m.id !== currentRecommendationItem.id)
      : priced;
    const src = pool.length ? pool : priced;
    return src[Math.floor(Math.random() * src.length)];
  }

  // excludeCurrentItem=false 時不排除目前項目（首次呼叫用）
  async function fetchRecommendation(excludeCurrentItem = true) {
    if (isRecommendationRequestInFlight || !isRecommendationEligible()) { if (!isRecommendationEligible()) hide(); return; }
    isRecommendationRequestInFlight = true;
    if (!currentRecommendationItem) $('aiPushBar')?.classList.add('loading');

    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('exclude_ids', JSON.stringify(excludeCurrentItem && currentRecommendationItem?.id ? [currentRecommendationItem.id] : []));
    formData.append('cart_ids', JSON.stringify(cartManager.getCartIds()));
    try {
      const data = await api.requestAiPushRecommendation(formData);
      const id     = data?.recommendation_id || '';
      const aiItem = id ? state.menuData.find(m => m.id === id) : null;
      // AI 推薦有效且與目前不同 → 採用；否則本地隨機備選
      const item = (aiItem && aiItem.id !== currentRecommendationItem?.id)
        ? aiItem
        : pickRandomRecommendation(excludeCurrentItem);
      if (item) {
        const recommendation = aiItem ? (data.recommendation || {}) : { source: 'local_fallback', reasons: ['local_fallback'] };
        renderRecommendation(item, (aiItem ? (data.push_text || '') : '') || `${item.name}是現在的熱門選擇，快來試試！`, recommendation);
      }
    } catch {
      // Ollama 無法連線，使用本地隨機備選確保畫面更新
      const fallback = pickRandomRecommendation(excludeCurrentItem);
      if (fallback) renderRecommendation(fallback, `${fallback.name}是現在的熱門選擇，快來試試！`, { source: 'local_fallback', reasons: ['local_fallback'] });
    } finally {
      isRecommendationRequestInFlight = false;
      $('aiPushBar')?.classList.remove('loading');
      scheduleRecommendationRefresh(RECOMMENDATION_REFRESH_DELAY_MS);
    }
  }

  function scheduleRecommendationRefresh(delay) {
    clearRecommendationTimer();
    recommendationTimer = setTimeout(() => {
      recommendationTimer = null;
      if (isRecommendationEligible()) fetchRecommendation();
      else { hide(); scheduleRecommendationRefresh(RECOMMENDATION_RETRY_DELAY_MS); }
    }, delay);
  }

  function clearRecommendationTimer() {
    if (recommendationTimer) { clearTimeout(recommendationTimer); recommendationTimer = null; }
  }

  // ── 對外介面 ──

  function start() {
    // ① 立即預載預設推播（零延遲，無需等待 Ollama）
    const defaultRecommendation = pickDefaultRecommendation();
    if (defaultRecommendation) renderRecommendation(defaultRecommendation, `${defaultRecommendation.name}是現在的熱門選擇，快來試試！`, { source: 'local_default', reasons: ['local_default'] });
    // ② 背景呼叫 Ollama 生成真實推播文字（不排除預載項目，讓 AI 自由選擇）
    if (isRecommendationEligible()) fetchRecommendation(false);
    else scheduleRecommendationRefresh(RECOMMENDATION_RETRY_DELAY_MS);
  }

  function stop() {
    clearRecommendationTimer();
    isRecommendationRequestInFlight = false;
    markCurrentRecommendationIgnored('ai_push_stopped');
    currentRecommendationItem     = null;
    currentRecommendationRecord = null;
    hide();
  }

  function hide() {
    const bar = $('aiPushBar');
    if (bar) { bar.classList.add('hidden'); bar.classList.remove('loading'); }
  }

  function scheduleAfterCartClose() { start(); }

  // 事件監聽（module 頂層執行一次）
  useDomReady(() => {
    $('aiPushPickBtn')?.addEventListener('click', () => {
      if (!currentRecommendationItem) return;
      if (currentRecommendationRecord) {
        reportRecommendationEvent('recommendation_clicked', currentRecommendationItem, {
          ...currentRecommendationRecord,
          recommendationRecord: currentRecommendationRecord,
        });
      }
      showItemConfirmModal(currentRecommendationItem, 'ai_push');
      scheduleRecommendationRefresh(RECOMMENDATION_REFRESH_DELAY_MS);
    });
    $('aiPushRefreshBtn')?.addEventListener('click', () => fetchRecommendation());
    $('aiPushVoiceBtn')?.addEventListener('click', () => startAskRecording($('aiPushVoiceBtn')));
  });

  return { start, stop, hide, scheduleAfterCartClose };
})();

// =========================================================
// 餐點確認彈窗
// =========================================================
let itemConfirmSelectedItem   = null;
let itemConfirmQuantity    = 1;
let itemConfirmSource = 'menu_card';

function showItemConfirmModal(item, source = 'menu_card') {
  itemConfirmSource = source;
  if (!item) return;
  itemConfirmSelectedItem = item;
  itemConfirmQuantity  = 1;

  const visual = getMenuVisual(item);
  const modal  = document.getElementById('itemConfirmModal');
  if (!modal) return;

  const imageElement  = document.getElementById('itemConfirmImg');
  const emojiElement   = document.getElementById('itemConfirmEmoji');
  if (imageElement) {
    imageElement.src = visual.image || '';
    imageElement.alt = item.name || '';
    imageElement.style.display = visual.image ? 'block' : 'none';
    imageElement.onerror = () => {
      imageElement.style.display = 'none';
      if (emojiElement) { emojiElement.textContent = visual.emoji || '🍔'; emojiElement.style.display = 'block'; }
    };
  }
  if (emojiElement) {
    emojiElement.textContent = visual.emoji || '🍔';
    emojiElement.style.display = visual.image ? 'none' : 'block';
  }

  const nameElement  = document.getElementById('itemConfirmName');
  const priceEl = document.getElementById('itemConfirmPrice');
  const descEl  = document.getElementById('itemConfirmDesc');
  const qtyEl   = document.getElementById('itemConfirmQtyDisplay');
  if (nameElement)  nameElement.textContent  = item.name || '';
  if (priceEl) priceEl.textContent = formatItemPrice(item, kioskLang);
  if (descEl)  descEl.textContent  = item.description || '';
  if (qtyEl)   qtyEl.textContent   = '1';

  modal.classList.remove('hidden');
}

function hideItemConfirmModal() {
  itemConfirmSelectedItem   = null;
  itemConfirmQuantity    = 1;
  itemConfirmSource = 'menu_card';
  document.getElementById('itemConfirmModal')?.classList.add('hidden');
}

// wire up once after DOM ready
useDomReady(() => {
  document.getElementById('itemConfirmClose')?.addEventListener('click', hideItemConfirmModal);
  document.getElementById('itemConfirmBackdrop')?.addEventListener('click', hideItemConfirmModal);
  document.getElementById('itemConfirmCancel')?.addEventListener('click', hideItemConfirmModal);

  document.getElementById('itemConfirmMinus')?.addEventListener('click', () => {
    if (itemConfirmQuantity <= 1) return;
    itemConfirmQuantity--;
    const quantityDisplayElement = document.getElementById('itemConfirmQtyDisplay');
    if (quantityDisplayElement) quantityDisplayElement.textContent = String(itemConfirmQuantity);
  });

  document.getElementById('itemConfirmPlus')?.addEventListener('click', () => {
    if (itemConfirmQuantity >= 20) return;
    itemConfirmQuantity++;
    const quantityDisplayElement = document.getElementById('itemConfirmQtyDisplay');
    if (quantityDisplayElement) quantityDisplayElement.textContent = String(itemConfirmQuantity);
  });

  document.getElementById('itemConfirmAdd')?.addEventListener('click', () => {
    if (!itemConfirmSelectedItem) return;
    for (let i = 0; i < itemConfirmQuantity; i++) {
      trackedAddToCart(itemConfirmSelectedItem, { source: itemConfirmSource });
    }
    hideItemConfirmModal();
  });
});

// =========================================================
// 菜單
// =========================================================

function updateKioskCartSummary() {
  const items = cartManager?.getCartItems ? cartManager.getCartItems() : [];
  const total = items.reduce((sum, item) => sum + resolveItemPrice(item) * Number(item.quantity || 0), 0);
  const quantity = items.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
  if (ui.kioskBottomCount) ui.kioskBottomCount.textContent = String(quantity);
  if (ui.kioskBottomTotal) ui.kioskBottomTotal.textContent = `$${total}`;
  if (ui.totalPrice) ui.totalPrice.textContent = `$${total}`;
  if (ui.checkoutBtn) {
    ui.checkoutBtn.disabled = quantity <= 0;
    const label = ui.checkoutBtn.querySelector('span');
    if (label) label.textContent = `${kt('checkoutGo')} $${total}`;
  }
}

function applyKioskLanguage() {
  const startupLangText = document.querySelector('#startupLangBtn span');
  if (startupLangText) startupLangText.textContent = kt('langButton');
  const langText = document.querySelector('#kioskLangBtn span');
  if (langText) langText.textContent = kt('langButton');
  const startBtnLabel = document.getElementById('startBtnLabel');
  if (startBtnLabel) startBtnLabel.textContent = kioskLang === 'en' ? 'Start Order' : '開始點餐';
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
  const paymentTitle = document.querySelector('.kiosk-payment-inner h1');
  if (paymentTitle) paymentTitle.textContent = kt('paymentTitle');
  const totalLabels = document.querySelectorAll('.cart-card .font-semibold.text-lg, .order-summary-total .grand span');
  totalLabels.forEach(element => { element.textContent = kt('total'); });
  const subtotalLabel = document.querySelector('.order-summary-total div:first-child span');
  if (subtotalLabel) subtotalLabel.textContent = kt('subtotal');
  const secureNotes = document.querySelectorAll('.order-secure-note, .cart-card.p-7 > p');
  secureNotes.forEach(element => {
    const icon = element.querySelector('i')?.outerHTML || '';
    element.innerHTML = `${icon}${escapeHTML(kt('secureCheckout'))}`;
  });
  const checkoutDoneTitle = document.querySelector('#checkoutOverlay h1');
  if (checkoutDoneTitle) checkoutDoneTitle.textContent = kt('checkoutDone');
  const checkoutDoneSub = document.querySelector('#checkoutOverlay p');
  if (checkoutDoneSub) checkoutDoneSub.textContent = kt('thankYou');
  const voiceAssistantLanguageText = document.getElementById('voiceAssistBtnText');
  if (voiceAssistantLanguageText) voiceAssistantLanguageText.textContent = kt('holdVoiceOrder');
  if (ui.voiceAssistOverlayTitle) ui.voiceAssistOverlayTitle.textContent = kioskLang === 'en' ? 'Voice Mode' : '語音模式';
  if (ui.voiceAssistOverlaySubtitle) ui.voiceAssistOverlaySubtitle.textContent = kioskLang === 'en' ? 'I am listening. Please say what you need.' : '我正在聽，請說出您的需求';
  if (ui.voiceAssistStopText) ui.voiceAssistStopText.textContent = kioskLang === 'en' ? 'Hold to stop listening' : '按住關閉收音';
  if (ui.cartCountBadge) {
    const quantity = cartManager?.getCartItems?.().reduce((sum, item) => sum + Number(item.quantity || 0), 0) || 0;
    ui.cartCountBadge.textContent = kt('cartCount').replace('{count}', String(quantity));
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
  aiRecommendationController.hide();
  document.querySelector('.cart-shell')?.classList.add('kiosk-cart-open');
  ui.kioskBottomBar?.classList.remove('hidden');
  setInteractionPage('checkout_page', { source: 'cart_open' });
  updateVoiceAssistVisibility();
  updateKioskCartSummary();
}

function hideCartScreen() {
  document.querySelector('.cart-shell')?.classList.remove('kiosk-cart-open');
  if (!orderCompleted && ui.kioskPaymentScreen?.classList.contains('hidden')) {
    setInteractionPage(state.kioskScreen === 'categories' ? 'menu_page' : 'menu_page', { source: 'continue_order' });
  }
  updateVoiceAssistVisibility();
  aiRecommendationController.scheduleAfterCartClose();
}

function showPaymentScreen() {
  hideCartScreen();
  ui.kioskPaymentScreen?.classList.remove('hidden');
  ui.kioskPaymentScreen?.setAttribute('aria-hidden', 'false');
  setInteractionPage('payment_page', { source: 'checkout_button' });
  hideChoiceHesitationModal();
  aiRecommendationController.stop();
  clearKioskFloatingUI();
  updateVoiceAssistVisibility();
}

function hidePaymentScreen() {
  ui.kioskPaymentScreen?.classList.add('hidden');
  ui.kioskPaymentScreen?.setAttribute('aria-hidden', 'true');
  updateVoiceAssistVisibility();
}

// =========================================================
// Kiosk 互動障礙事件追蹤
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

function setVisible(element, visible) {
  if (!element) return;
  element.style.display = visible ? '' : 'none';
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


function startKioskRealtime() {
  if (!kioskRealtime) {
    kioskRealtime = createRealtimeClient('pos', sessionId, {
      human_reply: handleRealtimeHumanReply,
      interaction_intervention: handleRealtimeInteractionIntervention,
      settings_changed: handleRealtimeSettingsChanged,
    });
  }
}

function initRealtimeClients() {
  if (isKioskMode()) startKioskRealtime();
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
  if (state.interactionModalTimer) clearTimeout(state.interactionModalTimer);
  state.interactionModalTimer = setTimeout(() => box.remove(), 10000);
}



async function reportInteractionEvent(payload) {
  try {
    return await api.reportInteractionEvent(payload);
  } catch (err) {
    console.warn('[interaction_event failed]', err);
    return null;
  }
}

export function trackInteractionEvent(event = {}) {
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

function recommendationKey(surface, itemId) {
  return `${surface || 'unknown'}:${itemId || 'unknown'}`;
}

function createRecommendationId(surface, itemId) {
  const suffix = Math.random().toString(36).slice(2, 8);
  return `rec_${sessionId}_${surface || 'unknown'}_${itemId || 'unknown'}_${Date.now()}_${suffix}`;
}

function findRecommendationRecord(itemId, surface = '', source = '') {
  return (
    state.sessionRecommendationEvents.get(recommendationKey(surface, itemId))
    || state.sessionRecommendationEvents.get(recommendationKey(source, itemId))
    || state.sessionRecommendationEvents.get(recommendationKey('item', itemId))
    || null
  );
}

function rememberRecommendationRecord(record) {
  if (!record?.item_id) return record;
  state.sessionRecommendationEvents.set(recommendationKey(record.surface, record.item_id), record);
  state.sessionRecommendationEvents.set(recommendationKey(record.source, record.item_id), record);
  state.sessionRecommendationEvents.set(recommendationKey('item', record.item_id), record);
  return record;
}

function normalizeOfferIds(value) {
  const raw = Array.isArray(value) ? value : (typeof value === 'string' ? value.split(',') : []);
  const seen = new Set();
  return raw.map(v => String(v || '').trim()).filter((v) => {
    if (!v || seen.has(v)) return false;
    seen.add(v);
    return true;
  });
}

function reportRecommendationEvent(eventType, item = {}, options = {}) {
  const itemId = String(options.item_id || item?.id || '').trim();
  if (!itemId) return null;
  const surface = String(options.surface || options.source || 'unknown');
  const existing = options.recommendationRecord || findRecommendationRecord(itemId, surface, options.source || '');
  const source = String(options.source || existing?.source || surface);
  const offerIds = normalizeOfferIds(options.offer_ids || item.offer_ids || existing?.offer_ids || []);
  const experimentId = String(options.experiment_id || item.experiment_id || existing?.experiment_id || '').trim();
  const variantId = String(options.variant_id || item.variant_id || existing?.variant_id || '').trim();
  const strategy = String(options.strategy || item.strategy || existing?.strategy || '').trim();
  const record = {
    recommendation_id: options.recommendation_id || item.recommendation_id || existing?.recommendation_id || createRecommendationId(surface, itemId),
    item_id: itemId,
    item_name: String(options.item_name || item?.name || existing?.item_name || ''),
    category: String(options.category || item?.category || existing?.category || ''),
    surface,
    source,
    rank: Number(options.rank ?? item.rank ?? existing?.rank ?? 0) || 0,
    score: Number(options.score ?? item.score ?? existing?.score ?? 0) || 0,
    reasons: Array.isArray(options.reasons) ? options.reasons : (Array.isArray(item.reasons) ? item.reasons : (existing?.reasons || [])),
    offer_ids: offerIds,
    experiment_id: experimentId,
    variant_id: variantId,
    strategy,
  };
  if (['recommendation_added_to_cart', 'recommendation_checked_out', 'recommendation_ignored', 'recommendation_removed_from_cart'].includes(eventType)) {
    record.completed = true;
    if (existing) existing.completed = true;
  }
  rememberRecommendationRecord(record);
  const metadata = { ...(options.metadata || {}) };
  if (offerIds.length) metadata.offer_ids = offerIds;
  if (experimentId) metadata.experiment_id = experimentId;
  if (variantId) metadata.variant_id = variantId;
  if (strategy) metadata.strategy = strategy;
  api.reportRecommendationEvent({
    session_id: sessionId,
    event_type: eventType,
    recommendation_id: record.recommendation_id,
    surface: record.surface,
    source: record.source,
    item_id: record.item_id,
    item_name: record.item_name,
    category: record.category,
    rank: record.rank,
    score: record.score,
    reasons: record.reasons,
    quantity: Number(options.quantity || 0) || 0,
    audience: state.member ? 'member' : 'guest',
    offer_ids: offerIds,
    experiment_id: experimentId,
    variant_id: variantId,
    strategy,
    metadata,
    ui_context: buildUIContext({ recommendation_surface: record.surface, recommendation_source: record.source }),
  }).catch(err => console.warn('[recommendation_event failed]', err));
  return record;
}

function startPageDwellWatcher() {
  if (isAdminMode()) return;
  if (pageDwellTimer) clearInterval(pageDwellTimer);
  pageDwellTimer = setInterval(() => {
    if (!isSystemRunning || !isKioskActive()) return;
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

async function ensureMediaTracks({ video = false, audio = false } = {}) {
  try {
    state.stream = await ensureMediaTracksCore(state.stream, ui, { video, audio });
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
  await loadRuntimeSettings();
  if (getRuntimeSettings().MEMBER_ENABLED) {
    ui.overlay.classList.add('hidden');  // 收起開始頁，露出會員選擇 overlay
    showMemberChoice(() => { runPosStartup(); });
  } else {
    runPosStartup();
  }
};

async function runPosStartup() {
  try {
    const f = getFeatures();
    const needAudio = Boolean(f.voiceAssist);
    const needVideo = Boolean(getRuntimeSettings().EMOTION_LLAMA_ENABLED);
    const mediaReady = await ensureMediaTracks({ video: needVideo, audio: needAudio });
    if (!mediaReady && needAudio) console.warn('Media permission unavailable; Kiosk flow continues without rolling buffer.');
    await loadMenu();
    applyFeaturesToKiosk();
    ui.overlay.style.opacity = '0';
    setTimeout(() => { ui.overlay.classList.add('hidden'); }, 500);
    isSystemRunning = true;
    state.lastCartAddAt = Date.now();
    startPageDwellWatcher();
    setInteractionPage('menu_page', { source: 'start_system' });
    renderMemberMenuHeader();
    setTimeout(() => aiRecommendationController.start(), 600);
    if (f.voiceAssist) setupAskRecorder();
    if (getRuntimeSettings().EMOTION_LLAMA_ENABLED && state.stream) {
      const bufferSec = Math.max(
        Number(getRuntimeSettings().EMOTION_LLAMA_CLIP_SEC) || 2.0,
        Number(getRuntimeSettings().PAYMENT_EMOTION_CLIP_SEC) || 5.0,
      );
      startRollingBuffer(state.stream, bufferSec);
    }
  } catch { alert("無法存取攝影機與麥克風。"); }
  startPassiveListener();
}

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


import {
  isVoiceAssistantActive, closeVoiceBubble, hideVoiceAssistOverlay, setupAskRecorder, startAskRecording,
} from './voice.js';

window.addEventListener('beforeunload', () => {
  try {
    if (state.askRecorder?.state === 'recording') state.askRecorder.stop();
  } catch { }
  if (pageDwellTimer) clearInterval(pageDwellTimer);
  aiRecommendationController.stop();
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
    const price = resolveItemPrice(item);
    const visual = getMenuVisual(item);
    const lineLabel = `$${price * quantity}`;
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
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('pushed_ids', JSON.stringify(Array.from(state.sessionPushedIds)));
  formData.append('cart_ids', JSON.stringify(cartIds));
  formData.append('cart_items', JSON.stringify(cartManager.getCartItems()));
  formData.append('ai_push_cart_count', String(sessionAiPushCartCount));
  formData.append('cart_sources', JSON.stringify(state.sessionCartSources));
  formData.append('cart_total', String(cartManager.getCartTotal()));
  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), 5000);
  try {
    const res = await api.submitCheckout(formData, ctrl.signal);
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

function saveAbandonedOrder(reason) {
  if (!state.member) return;
  const cartIds = cartManager.getCartIds();
  if (!cartIds.length) return;
  const cartTotal = cartManager.getCartTotal();
  api.recordAbandonedOrder(sessionId, cartIds, cartTotal, reason)
    .then((result) => {
      if (result?.ok) {
        state.member = null;
        renderMemberMenuHeader();
      }
    })
    .catch(() => {});
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
    switchMainView('kiosk');
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
      cartItems.forEach(({ name, quantity, price }) => {
        const row = document.createElement('div');
        row.className = 'co-item-row';
        const nameSpan = document.createElement('span');
        nameSpan.textContent = name;
        const qtySpan = document.createElement('span');
        qtySpan.className = 'co-item-qty';
        qtySpan.textContent = `×${quantity}`;
        const priceSpan = document.createElement('span');
        priceSpan.className = 'co-item-price';
        priceSpan.textContent = `$${price}`;
        row.append(nameSpan, qtySpan, priceSpan);
        listEl.appendChild(row);
      });
    }

    const total = cartItems.reduce((sum, item) => sum + item.price * item.quantity, 0);
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
  clearKioskFloatingUI();
  hideChoiceHesitationModal();
  aiRecommendationController.stop();
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
    quantity:  Number(item.qty || item.quantity || 1),
    price: resolveItemPrice(item),
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
  if (state.kioskScreen === 'menu') renderKioskCategories();
});
ui.kioskHomeBtn?.addEventListener('click', () => {
  hideCartScreen();
  hidePaymentScreen();
  if (orderCompleted) return;
  saveAbandonedOrder('home_button');
  isSystemRunning = false;
  orderCompleted = false;
  totalClickCount = 0;
  clearKioskFloatingUI();
  hideChoiceHesitationModal();
  stopPassiveListener();
  aiRecommendationController.stop();
  cartManager.clearCart();
  resetRecommendationTracking();
  ui.overlay.classList.remove('hidden');
  ui.overlay.style.opacity = '1';
  state.kioskScreen = 'categories';
  setInteractionPage('startup', { source: 'home_button' });
});
ui.kioskCartBtn?.addEventListener('click', () => {
  showCartScreen();
});
ui.continueOrderBtn?.addEventListener('click', () => {
  hideCartScreen();
  if (state.kioskScreen === 'categories') showMenuGroup('value');
});
ui.clearCartBtn?.addEventListener('click', () => {
  cartManager.clearCart();
  resetRecommendationTracking();
  hideCartScreen();
  renderKioskCategories();
  state.lastCartAddAt = Date.now();
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
  saveAbandonedOrder('cancel_order');
  cartManager.clearCart();
  resetRecommendationTracking();
  hidePaymentScreen();
  renderKioskCategories();
  aiRecommendationController.start();
  state.lastCartAddAt = Date.now();
});
ui.kioskFastPayBtn?.addEventListener('click', () => {
  const cartIds = cartManager.getCartIds();
  if (!cartIds.length) return;
  selectedPayment = 'credit-card';
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_countdown_start',
    button_id: 'kioskFastPayBtn',
    metadata: { payment: selectedPayment, fulfillment: selectedFulfillment, cart_ids: cartIds }
  });
  openPaymentCountdown(cartIds);
});
ui.paymentCountdownCancelButton?.addEventListener('click', () => {
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_countdown_cancel',
    button_id: 'paymentCountdownCancelButton',
    metadata: {}
  });
  closePaymentCountdown();
});

ui.paymentCountdownBackButton?.addEventListener('click', () => {
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_cd_back',
    button_id: 'paymentCountdownBackButton',
    metadata: {}
  });
  closePaymentCountdown();
});

ui.paymentCountdownAssistButton?.addEventListener('click', async () => {
  // 防止重複點擊：立即禁用按鈕，避免 async await 期間多次觸發
  if (ui.paymentCountdownAssistButton.disabled) return;
  ui.paymentCountdownAssistButton.disabled = true;

  // 立刻切換到 notified 畫面，讓使用者知道已收到點擊
  showPaymentCountdownSection('notified');

  // 背景等待情緒分析（最長 12 秒），完成後更新 admin 通知
  if (!state.pendingPaymentEmotion && state.paymentEmotionPromise) {
    await Promise.race([state.paymentEmotionPromise, new Promise(r => setTimeout(r, 12000))]);
  }
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_staff_requested',
    button_id: 'paymentCountdownAssistButton',
    metadata: { emotion: state.pendingPaymentEmotion }
  });
  setTimeout(() => { closePaymentCountdown(); }, 3000);
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
// 2-1: Ripple effect addDomEventListener .btn-primary buttons
// =========================================================
document.addEventListener('pointerdown', (e) => {
  const buttonElement = e.target?.closest?.('.btn-primary');
  if (!buttonElement) return;
  const ripple = document.createElement('span');
  ripple.className = 'btn-ripple';
  const rect = buttonElement.getBoundingClientRect();
  ripple.style.left = (e.clientX - rect.left - 30) + 'px';
  ripple.style.top  = (e.clientY - rect.top  - 30) + 'px';
  buttonElement.appendChild(ripple);
  ripple.addEventListener('animationend', () => ripple.remove());
}, true);

// =========================================================
// 2-2: Emotion capture helpers
// =========================================================

export function triggerEmotionCapture(eventType) {
  if (!runtimeSettings.EMOTION_LLAMA_ENABLED || !isKioskMode()) return;
  const blob = capturePreEventClip(); // 同步，不再 await
  if (!blob) return;
  api.analyzeEmotionEvent(sessionId, eventType, blob).catch(e => {
    console.warn('[emotion] analyze_event failed:', e);
  });
}

export async function triggerEmotionCaptureAndWait(eventType) {
  if (!runtimeSettings.EMOTION_LLAMA_ENABLED || !isKioskMode()) return;
  const blob = capturePreEventClip(); // 同步
  if (!blob) return;
  try {
    await api.analyzeEmotionEvent(sessionId, eventType, blob);
  } catch (e) {
    console.warn('[emotion] analyze_event (analysis mode) failed:', e);
  }
}

document.getElementById('choiceHesitationClose')?.addEventListener('click', () => closeChoiceHesitationModal(true, 'closed_by_customer'));
document.querySelector('[data-choice-hesitation-close]')?.addEventListener('click', () => closeChoiceHesitationModal(true, 'backdrop_closed'));
document.getElementById('choiceHesitationPick')?.addEventListener('click', () => {
  if (!state.currentChoiceHesitationItem) return;
  const item = state.currentChoiceHesitationItem;
  if (state.currentChoiceHesitationRecommendationRecord) {
    reportRecommendationEvent('recommendation_clicked', item, {
      ...state.currentChoiceHesitationRecommendationRecord,
      recommendationRecord: state.currentChoiceHesitationRecommendationRecord,
      surface: 'choice_hesitation',
      source: 'choice_hesitation',
    });
  }
  hideChoiceHesitationModal();
  showItemConfirmModal(item, 'choice_hesitation');
});
document.getElementById('choiceHesitationNext')?.addEventListener('click', () => {
  markCurrentChoiceHesitationIgnored('replaced_by_next_choice');
  const nextItem = pickChoiceHesitationItem();
  if (!nextItem) return;
  showChoiceHesitationRecommendation(nextItem);
});
document.getElementById('choiceHesitationVoice')?.addEventListener('click', () => {
  markCurrentChoiceHesitationIgnored('switched_to_voice');
  hideChoiceHesitationModal(true);
  startAskRecording(document.getElementById('voiceAssistBtn'));
});
document.getElementById('voiceReplyBubbleClose')?.addEventListener('click', () => closeVoiceBubble());

// =========================================================
// 協助 Modal (需要協助嗎？)
// =========================================================
function showAssistModal() {
  document.getElementById('assistModal')?.classList.remove('hidden');
  showAssistPanel('main');
  trackInteractionEvent({ event_type: 'assist_modal_open', button_id: '' });
}

function hideAssistModal() {
  isAssistRecommendationLoading = false;
  document.getElementById('assistModal')?.classList.add('hidden');
  trackInteractionEvent({ event_type: 'assist_modal_close', button_id: '' });
}

function showAssistPanel(name) {
  const panels = { main: 'assistMain', recommend: 'assistRecommend', tutorial: 'assistTutorial' };
  Object.entries(panels).forEach(([key, id]) => {
    document.getElementById(id)?.classList.toggle('hidden', key !== name);
  });
}

let isAssistRecommendationLoading = false;

async function loadAssistRecommendations() {
  if (isAssistRecommendationLoading) return;
  isAssistRecommendationLoading = true;
  showAssistPanel('recommend');
  trackInteractionEvent({ event_type: 'assist_recommend_open', button_id: 'assistBtnRecommend' });
  const listEl = document.getElementById('assistRecommendItems');
  const loadingEl = document.getElementById('assistRecommendLoading');
  if (loadingEl) loadingEl.classList.remove('hidden');
  [...(listEl?.children || [])].forEach(c => { if (c !== loadingEl) c.remove(); });

  try {
    const items = await api.getAssistRecommendations(sessionId, cartManager.getCartIds());
    if (loadingEl) loadingEl.classList.add('hidden');
    (Array.isArray(items) ? items : []).forEach(item => {
      listEl?.appendChild(buildAssistItemCard(item));
    });
    isAssistRecommendationLoading = false;
  } catch (e) {
    if (loadingEl) loadingEl.textContent = '推薦載入失敗，請重試';
    isAssistRecommendationLoading = false;
  }
}

function buildAssistItemCard(item) {
  const visual = getMenuVisual(item);
  const recommendationRecord = reportRecommendationEvent('recommendation_shown', item, {
    surface: 'assist_recommend',
    source: item.source || 'recommendation_engine',
    rank: item.rank || 0,
    score: item.score || 0,
    reasons: item.reasons || [],
    offer_ids: item.offer_ids || [],
    experiment_id: item.experiment_id || '',
    variant_id: item.variant_id || '',
    strategy: item.strategy || '',
  });
  const card = document.createElement('div');
  card.className = 'assist-item-card';

  const photoDiv = document.createElement('div');
  photoDiv.className = 'assist-item-photo';

  const hasImg = Boolean(visual.image);
  const emojiSpan = document.createElement('span');
  emojiSpan.className = 'assist-item-emoji';
  emojiSpan.textContent = visual.emoji || '🍔';
  if (hasImg) {
    const img = document.createElement('img');
    img.src = visual.image;
    img.alt = item.name || '';
    emojiSpan.style.display = 'none';
    img.addEventListener('error', () => {
      img.style.display = 'none';
      emojiSpan.style.display = 'flex';
    });
    photoDiv.appendChild(img);
  }
  photoDiv.appendChild(emojiSpan);

  const infoDiv = document.createElement('div');
  infoDiv.className = 'assist-item-info';

  const nameSpan = document.createElement('span');
  nameSpan.className = 'assist-item-name';
  nameSpan.textContent = item.name || '推薦餐點';

  const pushP = document.createElement('p');
  pushP.className = 'assist-item-push';
  pushP.textContent = item.push_text || '';

  const priceSpan = document.createElement('span');
  priceSpan.className = 'assist-item-price';
  priceSpan.textContent = formatItemPrice(item, kioskLang);

  infoDiv.append(nameSpan, pushP, priceSpan);

  const addButton = document.createElement('button');
  addButton.className = 'assist-item-add-btn';
  addButton.type = 'button';
  addButton.textContent = '加入購物車';
  addButton.addEventListener('click', () => {
    reportRecommendationEvent('recommendation_clicked', item, {
      ...recommendationRecord,
      recommendationRecord,
      surface: 'assist_recommend',
    });
    hideAssistModal();
    showItemConfirmModal(item, 'assist_recommend');
  });

  card.append(photoDiv, infoDiv, addButton);
  return card;
}

document.getElementById('assistBackdrop')?.addEventListener('click', hideAssistModal);
document.getElementById('assistClose')?.addEventListener('click', hideAssistModal);
document.getElementById('assistBtnRecommend')?.addEventListener('click', loadAssistRecommendations);
document.getElementById('assistBtnVoice')?.addEventListener('click', () => {
  hideAssistModal();
  trackInteractionEvent({ event_type: 'assist_voice_open', button_id: 'assistBtnVoice' });
  startAskRecording(document.getElementById('voiceAssistBtn'));
});
document.getElementById('assistBtnTutorial')?.addEventListener('click', () => {
  showAssistPanel('tutorial');
  trackInteractionEvent({ event_type: 'assist_tutorial_open', button_id: 'assistBtnTutorial' });
});
document.getElementById('assistRecommendBack')?.addEventListener('click', () => showAssistPanel('main'));
document.getElementById('assistRecommendCancel')?.addEventListener('click', hideAssistModal);
document.getElementById('assistRecommendRefresh')?.addEventListener('click', loadAssistRecommendations);
document.getElementById('assistTutorialBack')?.addEventListener('click', () => showAssistPanel('main'));
document.getElementById('assistTutorialClose')?.addEventListener('click', hideAssistModal);

// =========================================================
// 協助 Modal 點擊計數（任意點擊累積 50 次觸發）
// =========================================================
let totalClickCount = 0;
const ASSIST_CLICK_THRESHOLD = 50;

document.addEventListener('pointerdown', () => {
  if (!isKioskActive() || orderCompleted) return;
  if (document.getElementById('assistModal')?.classList.contains('hidden') === false) return;
  totalClickCount++;
  if (totalClickCount >= ASSIST_CLICK_THRESHOLD) {
    totalClickCount = 0;
    showAssistModal();
  }
});

// =========================================================
// 2-3: Cancel order popup after CANCEL_POPUP_THRESHOLD clicks
// =========================================================
let cancelClickCount = 0;
const CANCEL_POPUP_THRESHOLD = 2;
const cancelGuideEl = document.getElementById('cancelGuidePopup');

function showCancelGuide() {
  cancelGuideEl?.classList.remove('hidden');
}
function hideCancelGuide() { cancelGuideEl?.classList.add('hidden'); }

document.getElementById('cancelGuideClose')?.addEventListener('click', hideCancelGuide);

document.getElementById('cancelGuideFastPay')?.addEventListener('click', () => {
  hideCancelGuide();
  cancelClickCount = 0;
  totalClickCount = 0;
});

document.getElementById('cancelGuideCounter')?.addEventListener('click', () => {
  hideCancelGuide();
  cancelClickCount = 0;
  totalClickCount = 0;
  const cartIds = cartManager.getCartIds();
  if (!cartIds.length) return;
  finishOrder(cartIds, null, kt('counterPayCreating'));
});

document.getElementById('cancelGuideConfirmCancel')?.addEventListener('click', () => {
  hideCancelGuide();
  cancelClickCount = 0;
  totalClickCount = 0;
  saveAbandonedOrder('confirm_cancel_order');
  cartManager.clearCart();
  resetRecommendationTracking();
  hidePaymentScreen();
  renderKioskCategories();
  aiRecommendationController.start();
  state.lastCartAddAt = Date.now();
});


// =========================================================
// 被動語音監聽（MediaRecorder + 服務端 Whisper STT）
// =========================================================

function startPassiveListener() {
  if (isPassiveListening) return;
  if (!navigator.mediaDevices?.getUserMedia) return;
  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      passiveAudioStream = stream;
      isPassiveListening = true;
      isPassivePaused = false;
      console.log('[PassiveVoice] ✅ 被動語音監聽已啟動');
      schedulePassiveAudioChunk();
    })
    .catch(e => console.warn('[PassiveVoice] 麥克風失敗:', e.message));
}

function schedulePassiveAudioChunk() {
  if (!isPassiveListening || !passiveAudioStream) return;
  const chunks = [];
  try {
    passiveAudioRecorder = new MediaRecorder(passiveAudioStream, { mimeType: 'audio/webm' });
  } catch {
    passiveAudioRecorder = new MediaRecorder(passiveAudioStream);
  }
  passiveAudioRecorder.ondataavailable = e => { if (e.data?.size > 0) chunks.push(e.data); };
  passiveAudioRecorder.onstop = () => {
    if (!isPassiveListening) return;
    schedulePassiveAudioChunk();
    if (isPassivePaused || isPassiveRequestInFlight) return;
    const blob = new Blob(chunks, { type: 'audio/webm' });
    if (blob.size < 500) return;
    isPassiveRequestInFlight = true;
    api.checkPassiveVoice(sessionId, blob)
      .then(result => { if (result?.status === 'hit') handlePassiveVoiceHit(result); })
      .catch(e => console.warn('[PassiveVoice] API 錯誤:', e))
      .finally(() => { isPassiveRequestInFlight = false; });
  };
  passiveAudioRecorder.start();
  passiveRecordingTimer = setTimeout(() => {
    if (passiveAudioRecorder?.state === 'recording') passiveAudioRecorder.stop();
  }, PASSIVE_CHUNK_MS);
}

function stopPassiveListener() {
  isPassiveListening = false;
  isPassivePaused = false;
  clearTimeout(passiveRecordingTimer);
  try { passiveAudioRecorder?.stop(); } catch {}
  passiveAudioStream?.getTracks().forEach(t => t.stop());
  passiveAudioStream = null;
  passiveAudioRecorder = null;
}

export function pausePassiveListener() {
  isPassivePaused = true;
}

export function resumePassiveListener() {
  isPassivePaused = false;
}

function markCurrentChoiceHesitationIgnored(reason = 'dismissed') {
  const item = state.currentChoiceHesitationItem;
  const record = state.currentChoiceHesitationRecommendationRecord;
  if (!item || !record || record.completed) return;
  reportRecommendationEvent('recommendation_ignored', item, {
    ...record,
    recommendationRecord: record,
    surface: 'choice_hesitation',
    source: 'choice_hesitation',
    quantity: 0,
    metadata: { reason },
  });
  record.completed = true;
}

function closeChoiceHesitationModal(resetIdle = false, reason = 'dismissed') {
  markCurrentChoiceHesitationIgnored(reason);
  hideChoiceHesitationModal(resetIdle);
}

function showChoiceHesitationRecommendation(item) {
  if (!item) return;
  state.currentChoiceHesitationItem = item;
  state.currentChoiceHesitationRecommendationRecord = reportRecommendationEvent('recommendation_shown', item, {
    surface: 'choice_hesitation',
    source: 'choice_hesitation',
    rank: item.rank || 0,
    score: item.score || 0,
    reasons: item.reasons || ['passive_voice_hesitation'],
    offer_ids: item.offer_ids || [],
    experiment_id: item.experiment_id || '',
    variant_id: item.variant_id || '',
    strategy: item.strategy || '',
  });
  renderChoiceHesitationItem(item);
}

function handlePassiveVoiceHit(result) {
  if (!isKioskActive() || orderCompleted || isVoiceAssistantActive()) return;
  if (Date.now() - state.passiveLastTriggerAt < PASSIVE_TRIGGER_COOLDOWN_MS) return;
  const item = state.menuData.find(m => m.id === result.item?.id) || result.item;
  if (!item) return;
  state.passiveLastTriggerAt = Date.now();
  console.log(`[PassiveVoice] ✅ 命中「${item.name}」（${result.matched_label}）→ 顯示猶豫彈跳視窗`);
  showHesitationForItem(item);
}

function showHesitationForItem(item) {
  if (isChoiceHesitationVisible()) {
    console.log('[PassiveVoice] 猶豫彈跳視窗已顯示，略過');
    return;
  }
  if (!isSystemRunning || orderCompleted || !isKioskActive()) {
    console.log('[PassiveVoice] showHesitationForItem 被系統狀態攔截');
    return;
  }
  showChoiceHesitationRecommendation(item);
  const modal = getChoiceHesitationModal();
  modal?.classList.remove('hidden');
  modal?.setAttribute('aria-hidden', 'false');
  console.log(`[PassiveVoice] 🎯 猶豫彈跳視窗已顯示（${item.name}）`);
}

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
  applyFeaturesToKiosk();
  initRealtimeClients();
}
