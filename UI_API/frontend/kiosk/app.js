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
import { getMenuVisual, formatItemPrice, formatItemPriceDetail, resolveItemPrice } from './menuVisuals.js';
import { createKioskMenuController } from './controllers/kioskMenuController.js';
import { createPromoBannerController } from './controllers/promoBannerController.js';
import { createTouchId, isServerAuthoredTouch, observeVisibleImpression } from '../shared/touchEventClient.js';
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
  pickChoiceHesitationItem, renderChoiceHesitationItem,
} from './choiceHesitation.js';
import { openPaymentCountdown, closePaymentCountdown, showPaymentCountdownSection } from './paymentCountdown.js';
import { showMemberChoice, renderMemberMenuHeader } from './member.js';
import {
  buildKioskSessionId,
  loadKioskFeatures,
  resolveKioskAppMode,
  saveKioskFeatures,
} from './features/bootstrap/runtimePreferences.js';
import { createDeviceIdentityController } from './features/bootstrap/deviceIdentity.js';
import { recommendationEligibility, recommendationRefreshAction } from './recommendationContinuity.js';

const APP_MODE = resolveKioskAppMode(window.location);

// Admin is its own application (ADR-0024). The kiosk bundle is only ever
// served at /kiosk, so it no longer carries an Admin runtime mode.
export function isKioskMode() { return APP_MODE === 'kiosk'; }
export function isPosMode() { return isKioskMode(); }

// =========================================================
// Controller 狀態
// =========================================================

export let sessionId = buildKioskSessionId(window.location);
let entryFlow = null;
let entryIdleTimer = null;
let isSystemRunning = false;
let orderCompleted = false;
let sessionAiPushCartCount = 0;
let lastInterventionEventAt = 0;
let lastInteractionAt = Date.now();
let pageDwellTimer = null;
let kioskRealtime = null;
let periodicEmotionTimer = null;
let periodicEmotionGeneration = 0;
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

let fullSettings = {};
let runtimeSettings = {};
export function getRuntimeSettings() { return runtimeSettings; }

function isDemoPublicMode() {
  return runtimeSettings.DEMO_PUBLIC_MODE === true || runtimeSettings.DEMO_PUBLIC_MODE === 'true';
}

async function loadRuntimeSettings(timeoutMs = 3000) {
  try {
    const settingsRequest = api.getPublicSettings();
    const settings = await Promise.race([
      settingsRequest,
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error('runtime settings timeout')), timeoutMs);
      }),
    ]);
    runtimeSettings = { ...runtimeSettings, ...settings };
    return true;
  } catch (error) {
    console.warn('[Kiosk] 公開設定載入失敗，使用會員流程安全預設值。', error);
    return false;
  }
}

function restartLoops() {
}

// =========================================================
// 功能模組狀態
// =========================================================
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
  return loadKioskFeatures(localStorage, isDemoPublicMode());
}
function saveFeatures(f) {
  saveKioskFeatures(localStorage, f);
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
  switchMainViewUI(view, { clearKioskFloatingUI, applyFeaturesToKiosk, loadMenu });
  startKioskRealtime();
  setInteractionPage(view === 'admin' ? 'admin_page' : 'menu_page', { source: 'switch_main_view' });
}


function findMenuItems(ids = []) {
  return ids
    .map(id => String(id || '').replace(/[^a-zA-Z0-9]/g, ''))
    .map(cleanId => state.menuData.find(m => m.id === cleanId || m.id.includes(cleanId)))
    .filter(Boolean);
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

function promotionOfferFromBanner(promotion = {}) {
  const promotionPrice = Number(promotion.promo_price || promotion.promotion_price || 0);
  const originalPrice = Number(promotion.original_price || 0);
  if (!promotionPrice) return null;
  return {
    offer_id: promotion.id || promotion.offer_id || '',
    title: promotion.title || '',
    pricing: {
      type: 'add_on_fixed_price',
      original_price: originalPrice || resolveItemPrice(promotion),
      promotion_price: promotionPrice,
      currency: 'TWD',
    },
  };
}

function promotionTargetItem(promotion = {}) {
  const itemIds = Array.isArray(promotion.item_ids) ? promotion.item_ids : [];
  const targetType = String(promotion.target_type || '').trim();
  const targetValue = String(promotion.target_value || '').trim();
  if (itemIds.length) return findMenuItems(itemIds)[0] || null;
  if (targetType === 'item' && targetValue) return findMenuItems([targetValue])[0] || null;
  if (targetType === 'category' && targetValue) {
    return state.menuData.find(item => item.category === targetValue) || null;
  }
  return null;
}

function bestPricedOfferForItem(item = {}) {
  const offers = Array.isArray(item.offers) ? item.offers : [];
  return offers.find(offer => Number(offer?.pricing?.promotion_price || 0) > 0) || null;
}

function showItemById(itemId = '', source = 'promotion_banner') {
  const item = findMenuItems([itemId])[0];
  if (item) showItemConfirmModal(item, source);
}

function handlePromotionCta(promotion = {}) {
  if (promotion.member_only && !state.member) {
    showMemberChoice((member) => {
      renderMemberMenuHeader();
      if (member) handlePromotionCta(promotion);
    }, { hooks: midSessionMemberHooks() });
    return;
  }
  const requiredIds = Array.isArray(promotion.required_cart_item_ids)
    ? promotion.required_cart_item_ids
    : [];
  const cartIds = new Set(cartManager.getCartIds());
  const missingRequiredId = requiredIds.find(id => !cartIds.has(id));
  if (missingRequiredId) {
    showPushNotice('此優惠需先將指定餐點加入購物車');
    showItemById(missingRequiredId, 'promotion_requirement');
    return;
  }
  const targetType = String(promotion.target_type || '').trim() || 'none';
  const targetValue = String(promotion.target_value || '').trim();
  const item = promotionTargetItem(promotion);
  if (item) {
    const offer = promotionOfferFromBanner(promotion);
    const cartItem = offer ? applyPromotionPricing(item, offer) : item;
    showItemConfirmModal(cartItem, 'promotion');
    return;
  }
  if (targetType === 'category' && targetValue) {
    const group = KIOSK_GROUPS.find(candidate => candidate.id === targetValue || candidate.label === targetValue || candidate.categories.includes(targetValue));
    if (group) showMenuGroup(group.id);
    return;
  }
  if (targetType === 'recommendation') {
    aiRecommendationController.start();
  }
}

export const cartManager = createCartManager({ ui, escapeHTML, findMenuItems, onCartChange: handleCartChange, t: kioskText, getVisual: getMenuVisual });

const kioskMenuController = createKioskMenuController({
  api,
  state,
  ui,
  escapeHTML,
  getMenuVisual,
  formatItemPrice,
  groups: KIOSK_GROUPS,
  translate: kioskText,
  translateFilter: kioskFilterLabel,
  translateGroup: kioskGroupLabel,
  showItemConfirmModal,
  updateKioskCartSummary,
  getSessionId: () => sessionId,
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

/** @param {string} eventType @param {Record<string, unknown>} [details] */
function sendCommercialTouch(eventType, details = {}) {
  // ADR-0020：顧客可見活動的權威在 server。推薦 API 失敗時 kiosk 自己挑的佔位品項
  // 既無 decision 也無 campaign，渲染它只是為了不留白，不得計入商業曝光或點擊。
  if (!isServerAuthoredTouch(details)) return;
  api.reportCommercialTouch({
    event_id: createTouchId('touch'),
    event_type: eventType,
    session_id: sessionId,
    audience: state.member ? 'member' : 'guest',
    ...details,
  }).catch(error => console.warn('[commercial touch failed]', error));
}

/** @param {string} placement */
function campaignTouchHandler(placement) {
  /** @param {"impression" | "click"} eventType @param {Record<string, unknown>} promotion @param {string} impressionId */
  return (eventType, promotion, impressionId) => sendCommercialTouch(eventType, {
    impression_id: impressionId,
    campaign_id: String(promotion.id || promotion.offer_id || ''),
    campaign_version: Number(promotion.version || promotion.campaign_version || 0) || undefined,
    placement,
    item_id: String((promotion.item_ids || [])[0] || promotion.target_value || ''),
  });
}

const promoBannerController = createPromoBannerController({
  api,
  root: ui.posPromoBannerRoot,
  escapeHTML,
  groups: KIOSK_GROUPS,
  showMenuGroup,
  showItemById,
  surface: 'pos_home_banner',
  variant: 'home',
  onPromotionCta: handlePromotionCta,
  onRecommendationTarget: () => aiRecommendationController.start(),
  onTouch: campaignTouchHandler('pos_home_banner'),
});

const cartPromoBannerController = createPromoBannerController({
  api: {
    ...api,
    async getPosPromotionBanners(surface) {
      const response = await api.getPosPromotionBanners(surface);
      const items = Array.isArray(response?.items) ? response.items : [];
      if (items.length || surface !== 'kiosk_cart_banner') return response;
      return api.getPosPromotionBanners('pos_home_banner');
    },
  },
  root: ui.cartPromoBannerRoot,
  escapeHTML,
  groups: KIOSK_GROUPS,
  showMenuGroup,
  showItemById,
  surface: 'kiosk_cart_banner',
  variant: 'cart',
  onPromotionCta: handlePromotionCta,
  onRecommendationTarget: () => aiRecommendationController.start(),
  onTouch: campaignTouchHandler('kiosk_cart_banner'),
});

configureKioskRuntime({
  cartManager,
  clearAllPushCards,
  getFeatures,
  getRuntimeSettings,
  isKioskActive,
  isKioskMode,
  isPosActive,
  isPosMode,
  itemMatchesSubFilter,
  kioskText,
  sessionId,
  showPushNotice,
  trackInteractionEvent,
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
  const DEFAULT_REFRESH_DELAY_MS = 15_000;
  const RECOMMENDATION_RETRY_DELAY_MS   = 1_000;
  let recommendationTimer    = null;
  let isRecommendationRequestInFlight = false;
  let currentRecommendationItem     = null;
  let currentRecommendationRecord = null;
  let currentCommercialImpressionId = '';
  let stopCommercialImpression = null;
  // 本次點餐已展示過的品項。「換一個」若只排除當前這一項，按兩下就會轉回第一項。
  const seenRecommendationIds = new Set();
  // 預先取回的候選，讓「換一個」立刻換掉畫面而不必等待後端。
  let prefetchedRecommendations = [];

  function refreshDelayMs() {
    const seconds = Number(runtimeSettings.AI_PUSH_REFRESH_SEC);
    return Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : DEFAULT_REFRESH_DELAY_MS;
  }

  function excludeSeenEnabled() {
    return runtimeSettings.AI_PUSH_EXCLUDE_SEEN !== false;
  }

  function prefetchEnabled() {
    return runtimeSettings.AI_PUSH_PREFETCH !== false;
  }

  function excludedIdsForRequest(excludeCurrentItem) {
    if (excludeSeenEnabled()) return [...seenRecommendationIds];
    return excludeCurrentItem && currentRecommendationItem?.id ? [currentRecommendationItem.id] : [];
  }

  // ── DOM shortcuts ──
  const $ = id => document.getElementById(id);

  function isRecommendationEligible() {
    const paymentOpen = ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden');
    const cartOpen    = Boolean(document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open'));
    return recommendationEligibility({
      featureEnabled: getFeatures().recommend,
      barPresent: Boolean($('aiPushBar')),
      kioskActive: Boolean(isKioskActive()),
      documentVisible: !document.hidden,
      voiceActive: isVoiceAssistantActive(),
      paymentOpen: Boolean(paymentOpen),
      cartOpen,
      eligibleItemCount: state.menuData.filter(item => item?.id && resolveItemPrice(item) > 0).length,
    }).eligible;
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
      decision_id: recommendation.decision_id || item.decision_id || '',
      strategy_version: recommendation.strategy_version || item.strategy_version || '',
      fallback_status: recommendation.fallback_status || item.fallback_status || '',
    };
    const visual = getMenuVisual(item);
    if (currentRecommendationItem?.id && currentRecommendationItem.id !== item.id) {
      markCurrentRecommendationIgnored('replaced_by_new_ai_push');
    }
    currentRecommendationItem = displayItem;
    if (item.id) {
      state.sessionPushedIds.add(item.id);
      seenRecommendationIds.add(item.id);
    }
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
    if (priceElement) priceElement.textContent = formatItemPrice(displayItem);
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

    $('aiPushBar').classList.remove('loading');
    $('aiPushBar').classList.toggle('hidden', !isRecommendationEligible());
    stopCommercialImpression?.();
    currentCommercialImpressionId = createTouchId('impression');
    stopCommercialImpression = observeVisibleImpression($('aiPushBar'), {
      onVisible: () => sendCommercialTouch('impression', {
        decision_id: String(displayItem.decision_id || ''),
        impression_id: currentCommercialImpressionId,
        placement: 'ai_push',
        item_id: String(displayItem.id || ''),
        strategy: String(displayItem.strategy || ''),
        strategy_version: String(displayItem.strategy_version || ''),
        experiment_id: String(displayItem.experiment_id || ''),
        variant_id: String(displayItem.variant_id || ''),
        fallback_status: String(displayItem.fallback_status || ''),
      }),
    });
  }

  // 三種備援文案刻意各自不同：畫面上看到哪一句，就知道走了哪一條路徑。
  // local_default   = start() 的零延遲預載，尚未取得後端回應
  // client_fallback = 後端有回應但品項不在本地菜單
  // client_error    = 推播 API 失敗（離線、未授權、後端錯誤）
  const LOCAL_PUSH_TEXT = {
    local_default: name => `${name}是現在的熱門選擇，快來試試！`,
    client_fallback: name => `${name}也很受歡迎，要不要加一份？`,
    client_error: name => `${name}是店長推薦，不妨試試看。`,
  };

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

  /** 把後端回應轉成 renderRecommendation 需要的形狀。 */
  function toRenderable(data) {
    const id = data?.recommendation_id || '';
    const item = id ? state.menuData.find(m => m.id === id) : null;
    if (!item) return null;
    return {
      item,
      pushText: data.push_text || LOCAL_PUSH_TEXT.client_fallback(item.name),
      recommendation: {
        ...(data.recommendation || {}),
        decision_id: data.decision_id || '',
        strategy_version: data.strategy_version || '',
        fallback_status: data.fallback_status || '',
        // 後端在 recommendation.model_status 帶出 authored_campaign / authored_base /
        // description_fallback；此處僅在缺漏時補上頂層 status。
        model_status: data.recommendation?.model_status || data.status || '',
      },
    };
  }

  async function requestRecommendation(excludeCurrentItem) {
    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('exclude_ids', JSON.stringify(excludedIdsForRequest(excludeCurrentItem)));
    formData.append('cart_ids', JSON.stringify(cartManager.getCartIds()));
    return toRenderable(await api.requestAiPushRecommendation(formData));
  }

  /** 背景補一筆候選，讓下一次「換一個」不必等待網路。 */
  async function prefetchNext() {
    if (!prefetchEnabled() || prefetchedRecommendations.length || !isRecommendationEligible()) return;
    try {
      const next = await requestRecommendation(true);
      // 預取期間畫面可能已經換過，重複的候選就沒有意義了。
      if (next && !seenRecommendationIds.has(next.item.id)) prefetchedRecommendations.push(next);
    } catch {
      // 預取只是加速手段，失敗時維持原本的即時請求路徑即可。
    }
  }

  // excludeCurrentItem=false 時不排除目前項目（首次呼叫用）
  async function fetchRecommendation(excludeCurrentItem = true) {
    const action = recommendationRefreshAction({
      eligible: isRecommendationEligible(),
      requestInFlight: isRecommendationRequestInFlight,
      hasCurrent: Boolean(currentRecommendationItem),
    });
    if (action === 'hide_and_retry') {
      hide();
      scheduleRecommendationRefresh(RECOMMENDATION_RETRY_DELAY_MS);
      return;
    }
    if (action === 'show_current_and_retry' || action === 'retry') {
      if (action === 'show_current_and_retry') $('aiPushBar')?.classList.remove('hidden');
      scheduleRecommendationRefresh(RECOMMENDATION_RETRY_DELAY_MS);
      return;
    }

    // 已預取到候選就直接換上，使用者按下「換一個」不會看到等待。
    const ready = excludeCurrentItem ? prefetchedRecommendations.shift() : null;
    if (ready) {
      renderRecommendation(ready.item, ready.pushText, ready.recommendation);
      scheduleRecommendationRefresh(refreshDelayMs());
      void prefetchNext();
      return;
    }

    isRecommendationRequestInFlight = true;
    if (!currentRecommendationItem) $('aiPushBar')?.classList.add('loading');
    try {
      const next = await requestRecommendation(excludeCurrentItem);
      if (next) {
        // 一律採用後端選出的品項與文案。即使與目前顯示的品項相同也要採用，
        // 否則 start() 預載的本地預設會讓第一次的推薦詞整個被丟掉。
        renderRecommendation(next.item, next.pushText, next.recommendation);
      } else {
        // 後端沒有給出菜單中的品項才用本地隨機備選，文案也必須換成本地文案。
        console.warn('AI 推播回傳的品項不在本地菜單，改用本地備選。');
        const fallback = pickRandomRecommendation(excludeCurrentItem);
        if (fallback) {
          renderRecommendation(fallback, LOCAL_PUSH_TEXT.client_fallback(fallback.name), {
            source: 'local_fallback', reasons: ['local_fallback'], fallback_status: 'client_fallback',
            model_status: 'client_fallback',
          });
        }
      }
    } catch (error) {
      // 推播 API 失敗（離線、未授權），使用本地隨機備選確保畫面更新
      console.warn('AI 推播 API 失敗，改用本地備選：', error);
      const fallback = pickRandomRecommendation(excludeCurrentItem);
      if (fallback) {
        renderRecommendation(fallback, LOCAL_PUSH_TEXT.client_error(fallback.name), {
          source: 'local_fallback', reasons: ['local_fallback'], fallback_status: 'client_error',
          model_status: 'client_error',
        });
      }
    } finally {
      isRecommendationRequestInFlight = false;
      $('aiPushBar')?.classList.remove('loading');
      scheduleRecommendationRefresh(refreshDelayMs());
      void prefetchNext();
    }
  }

  function scheduleRecommendationRefresh(delay) {
    clearRecommendationTimer();
    recommendationTimer = setTimeout(() => {
      recommendationTimer = null;
      const action = recommendationRefreshAction({
        eligible: isRecommendationEligible(),
        requestInFlight: isRecommendationRequestInFlight,
        hasCurrent: Boolean(currentRecommendationItem),
      });
      if (action === 'hide_and_retry') {
        hide();
        scheduleRecommendationRefresh(RECOMMENDATION_RETRY_DELAY_MS);
        return;
      }
      if (currentRecommendationItem) $('aiPushBar')?.classList.remove('hidden');
      if (isRecommendationRequestInFlight) {
        scheduleRecommendationRefresh(RECOMMENDATION_RETRY_DELAY_MS);
        return;
      }
      void fetchRecommendation();
    }, delay);
  }

  function clearRecommendationTimer() {
    if (recommendationTimer) { clearTimeout(recommendationTimer); recommendationTimer = null; }
  }

  // ── 對外介面 ──

  function start() {
    // ① 立即預載預設推播（零延遲）
    const defaultRecommendation = pickDefaultRecommendation();
    if (defaultRecommendation) {
      renderRecommendation(defaultRecommendation, LOCAL_PUSH_TEXT.local_default(defaultRecommendation.name), {
        source: 'local_default', reasons: ['local_default'], model_status: 'local_default',
      });
    }
    // ② 背景取回後端選品與其預寫推薦詞（不排除預載項目，讓引擎自由選擇）
    if (isRecommendationEligible()) fetchRecommendation(false);
    else scheduleRecommendationRefresh(RECOMMENDATION_RETRY_DELAY_MS);
  }

  function stop() {
    clearRecommendationTimer();
    isRecommendationRequestInFlight = false;
    markCurrentRecommendationIgnored('ai_push_stopped');
    currentRecommendationItem     = null;
    currentRecommendationRecord = null;
    // 已看過的品項與預取候選都只屬於這一次點餐，結束時必須清掉，
    // 否則下一位顧客會繼承上一位的排除清單而看不到大部分品項。
    seenRecommendationIds.clear();
    prefetchedRecommendations = [];
    stopCommercialImpression?.();
    stopCommercialImpression = null;
    hide();
  }

  function hide() {
    const bar = $('aiPushBar');
    if (bar) { bar.classList.add('hidden'); bar.classList.remove('loading'); }
  }

  function syncVisibility() {
    if (!isRecommendationEligible()) {
      hide();
      scheduleRecommendationRefresh(RECOMMENDATION_RETRY_DELAY_MS);
      return;
    }
    if (currentRecommendationItem) {
      $('aiPushBar')?.classList.remove('hidden');
      scheduleRecommendationRefresh(refreshDelayMs());
      return;
    }
    const fallback = pickDefaultRecommendation();
    if (fallback) {
      renderRecommendation(fallback, LOCAL_PUSH_TEXT.local_default(fallback.name), {
        source: 'local_default', reasons: ['local_default'], model_status: 'local_default',
      });
    }
    if (!isRecommendationRequestInFlight) void fetchRecommendation(false);
  }

  function scheduleAfterCartClose() { syncVisibility(); }

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
      sendCommercialTouch('click', {
        decision_id: String(currentRecommendationItem.decision_id || ''),
        impression_id: currentCommercialImpressionId,
        placement: 'ai_push',
        item_id: String(currentRecommendationItem.id || ''),
        strategy: String(currentRecommendationItem.strategy || ''),
        strategy_version: String(currentRecommendationItem.strategy_version || ''),
        experiment_id: String(currentRecommendationItem.experiment_id || ''),
        variant_id: String(currentRecommendationItem.variant_id || ''),
      });
      showItemConfirmModal(currentRecommendationItem, 'ai_push');
      scheduleRecommendationRefresh(refreshDelayMs());
    });
    $('aiPushRefreshBtn')?.addEventListener('click', () => fetchRecommendation());
    document.addEventListener('visibilitychange', syncVisibility);
    globalThis.addEventListener?.('kiosk:recommendation-eligibility-changed', syncVisibility);
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
  if (priceEl) priceEl.textContent = formatItemPriceDetail(item);
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

let cartQuoteTimer = 0;
let cartQuoteSequence = 0;

/**
 * @param {import('../types.d.ts').CartItem[]} items
 * @param {"cart_change" | "quote_applied" | "quote_pending" | "quote_failed"} [reason]
 */
function handleCartChange(items, reason = 'cart_change') {
  updateKioskCartSummary();
  if (reason !== 'cart_change') return;
  window.clearTimeout(cartQuoteTimer);
  const sequence = ++cartQuoteSequence;
  if (!items.length) {
    kioskMenuController.refreshPriceProjections([], sessionId).catch(() => {});
    return;
  }
  cartManager.markQuotePending();
  cartQuoteTimer = window.setTimeout(async () => {
    try {
      const quote = await api.quoteCart(items, sessionId);
      if (sequence !== cartQuoteSequence) return;
      cartManager.applyServerQuote(quote);
      await kioskMenuController.refreshPriceProjections(cartManager.getCartIds());
    } catch {
      if (sequence !== cartQuoteSequence) return;
      cartManager.markQuoteFailed();
    }
  }, 120);
}

function updateKioskCartSummary() {
  const items = cartManager?.getCartItems ? cartManager.getCartItems() : [];
  const quote = cartManager?.getQuoteState?.() || { status: 'idle', total: null };
  const calculatedTotal = items.reduce((sum, item) => sum + resolveItemPrice(item) * Number(item.quantity || 0), 0);
  const total = quote.status === 'ready' && quote.total !== null ? quote.total : calculatedTotal;
  const quantity = items.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
  if (ui.kioskBottomCount) ui.kioskBottomCount.textContent = String(quantity);
  const totalLabel = quote.status === 'pending'
    ? '價格確認中'
    : (quote.status === 'failed' ? '請重試價格確認' : `$${total}`);
  if (ui.kioskBottomTotal) ui.kioskBottomTotal.textContent = totalLabel;
  if (ui.totalPrice) ui.totalPrice.textContent = totalLabel;
  if (ui.checkoutBtn) {
    ui.checkoutBtn.disabled = quantity <= 0 || quote.status !== 'ready';
    const label = ui.checkoutBtn.querySelector('span');
    if (label) label.textContent = quote.status === 'ready'
      ? `${kioskText('checkoutGo')} $${total}`
      : totalLabel;
  }
}

function applyKioskText() {
  const startBtnLabel = document.getElementById('startBtnLabel');
  if (startBtnLabel) startBtnLabel.textContent = '開始點餐';
  if (ui.kioskHomeBtn) {
    const span = ui.kioskHomeBtn.querySelector('span');
    if (span) span.textContent = kioskText('home');
  }
  if (ui.continueOrderBtn) ui.continueOrderBtn.textContent = kioskText('continueOrder');
  if (ui.clearCartBtn) ui.clearCartBtn.innerHTML = `<i class="fas fa-trash-alt"></i> ${escapeHTML(kioskText('clearCart'))}`;
  const cartHeading = document.querySelector('.cart-shell.kiosk-cart-open h3') || document.querySelector('.cart-shell h3');
  if (cartHeading) cartHeading.textContent = kioskText('yourCart');
  const checkoutLabel = ui.checkoutBtn?.querySelector('span');
  if (checkoutLabel) checkoutLabel.textContent = `${kioskText('checkoutGo')} ${ui.totalPrice?.textContent || '$0'}`;
  const fastPayKicker = document.querySelector('.kiosk-payment-kicker');
  if (fastPayKicker) fastPayKicker.textContent = kioskText('fastPayKicker');
  const fastPayTitle = ui.kioskFastPayBtn?.querySelector('strong');
  if (fastPayTitle) fastPayTitle.textContent = kioskText('fastPayTitle');
  if (ui.kioskCounterPayBtn) ui.kioskCounterPayBtn.textContent = kioskText('counterPay');
  if (ui.kioskPaymentBackBtn) ui.kioskPaymentBackBtn.textContent = kioskText('backCart');
  if (ui.kioskCancelOrderBtn) ui.kioskCancelOrderBtn.textContent = kioskText('cancelOrder');
  const paymentTitle = document.querySelector('.kiosk-payment-inner h1');
  if (paymentTitle) paymentTitle.textContent = kioskText('paymentTitle');
  const totalLabels = document.querySelectorAll('.cart-card .font-semibold.text-lg, .order-summary-total .grand span');
  totalLabels.forEach(element => { element.textContent = kioskText('total'); });
  const subtotalLabel = document.querySelector('.order-summary-total div:first-child span');
  if (subtotalLabel) subtotalLabel.textContent = kioskText('subtotal');
  const secureNotes = document.querySelectorAll('.order-secure-note, .cart-card.p-7 > p');
  secureNotes.forEach(element => {
    const icon = element.querySelector('i')?.outerHTML || '';
    element.innerHTML = `${icon}${escapeHTML(kioskText('secureCheckout'))}`;
  });
  const checkoutDoneTitle = document.querySelector('#checkoutOverlay h1');
  if (checkoutDoneTitle) checkoutDoneTitle.textContent = kioskText('checkoutDone');
  const checkoutDoneSub = document.querySelector('#checkoutOverlay p');
  if (checkoutDoneSub) checkoutDoneSub.textContent = kioskText('thankYou');
  const voiceAssistantLanguageText = document.getElementById('voiceAssistBtnText');
  if (voiceAssistantLanguageText) voiceAssistantLanguageText.textContent = '語音準備中';
  if (ui.cartCountBadge) {
    const quantity = cartManager?.getCartItems?.().reduce((sum, item) => sum + Number(item.quantity || 0), 0) || 0;
    ui.cartCountBadge.textContent = kioskText('cartCount').replace('{count}', String(quantity));
  }
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
  // 付款畫面不再接受加購，進行中的語音回合在此收斂為「已取消」終局。
  cancelActiveVoiceTurn();
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

async function handleRealtimeCampaignsChanged() {
  if (!isSystemRunning) return;
  await Promise.allSettled([
    promoBannerController.load(),
    cartPromoBannerController.load(),
  ]);
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
      campaigns_changed: handleRealtimeCampaignsChanged,
      open: handleRealtimeCampaignsChanged,
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
  let audioReady = !audio;
  let videoReady = !video;

  if (audio) {
    try {
      state.stream = await ensureMediaTracksCore(state.stream, ui, { audio: true });
      audioReady = Boolean(state.stream?.getAudioTracks().length);
    } catch (error) {
      console.warn('[Kiosk] 無法取得麥克風。', error);
      alert('無法取得麥克風權限，語音模式將暫時停用。');
    }
  }

  if (video) {
    try {
      state.stream = await ensureMediaTracksCore(state.stream, ui, { video: true });
      videoReady = Boolean(state.stream?.getVideoTracks().length);
    } catch (error) {
      console.warn('[Kiosk] 相機不可用，語音模式將只使用麥克風。', error);
    }
  }

  return { audioReady, videoReady };
}

// =========================================================
// 啟動
// =========================================================
let isStartTransitionPending = false;
let isMenuStarting = false;

function setStartButtonPending(pending) {
  isStartTransitionPending = pending;
  if (ui.startBtn) ui.startBtn.disabled = pending;
  const label = document.getElementById('startBtnLabel');
  if (label) label.textContent = pending ? '正在載入…' : '開始點餐';
}

// 入口啟動失敗與菜單初始化失敗共用同一個錯誤 overlay，用這個旗標區分重試語意。
let entryErrorMode = '';

const MENU_LOAD_ERROR_TEXT = {
  menu: { title: '菜單暫時無法載入', message: '請確認網路連線後再試一次。' },
  entry_start: { title: '暫時無法開始點餐', message: '請確認網路連線後再試一次；連線恢復後即可選擇點餐方式。' },
};

function hideMenuLoadError() {
  const overlay = document.getElementById('menuLoadErrorOverlay');
  overlay?.classList.add('hidden');
  overlay?.setAttribute('aria-hidden', 'true');
}

function showMenuLoadError(mode = 'menu') {
  entryErrorMode = mode;
  const overlay = document.getElementById('menuLoadErrorOverlay');
  overlay?.classList.remove('hidden');
  overlay?.setAttribute('aria-hidden', 'false');
  const text = MENU_LOAD_ERROR_TEXT[mode] || MENU_LOAD_ERROR_TEXT.menu;
  const title = document.getElementById('menuLoadErrorTitle');
  if (title) title.textContent = text.title;
  const message = document.getElementById('menuLoadErrorMessage');
  if (message) message.textContent = text.message;
  const retry = document.getElementById('menuLoadRetry');
  if (retry) {
    retry.disabled = false;
    retry.textContent = '重試';
  }
  // 入口尚未建立時沒有「點餐方式」可返回，隱藏該出口避免死路。
  document.getElementById('menuLoadBack')?.classList.toggle('hidden', mode === 'entry_start');
}

async function beginEntryFlow() {
  if (isStartTransitionPending) return;
  setStartButtonPending(true);
  try {
    hideMenuLoadError();
    const settingsLoaded = await loadRuntimeSettings(3000);
    entryFlow = await api.startEntryFlow({
      policy_version: String(getRuntimeSettings().ENTRY_POLICY_VERSION || 'runtime-v1'),
      policy_loaded: settingsLoaded,
      policy: { membership_enabled: !(settingsLoaded && getRuntimeSettings().MEMBER_ENABLED === false) },
    });
    if (entryFlow.ordering_session_id) sessionId = entryFlow.ordering_session_id;
    armEntryIdleTimeout();
    const inputDependentStates = new Set([
      'member_lookup',
      'registration_offered',
      'member_lookup_degraded',
      'member_registration',
    ]);
    if (inputDependentStates.has(entryFlow.state)) {
      entryFlow = await api.commandEntryFlow(
        entryFlow.entry_flow_id,
        entryFlow.phase_revision,
        'return_to_mode',
        { safe_reason: 'browser_sensitive_input_unavailable' },
      );
    }
    if (entryFlow.state === 'choosing_mode') {
      ui.overlay.classList.add('hidden');  // 收起開始頁，露出會員選擇 overlay
      showMemberChoice(() => { void runPosStartup(); }, { hooks: entryFlowHooks() });
    } else if (entryFlow.state === 'menu_initialization_failed') {
      ui.overlay.classList.add('hidden');
      showMenuLoadError();
    } else {
      await runPosStartup();
    }
  } catch (error) {
    // 入口流程建立失敗（後端錯誤、裝置範圍不足、網路中斷）必須是可見且可重試的，
    // 否則顧客只會看到按鈕閃一下，等同沒有點餐方式可選。
    console.error('[Kiosk] 點餐入口啟動失敗。', error);
    entryFlow = null;
    showMenuLoadError('entry_start');
  } finally {
    setStartButtonPending(false);
  }
}

ui.startBtn.onclick = () => { void beginEntryFlow(); };

async function advanceEntryFlow(command, payload = {}) {
  if (!entryFlow) throw new Error('entry_flow_missing');
  entryFlow = await api.commandEntryFlow(entryFlow.entry_flow_id, entryFlow.phase_revision, command, payload);
  if (entryFlow.ordering_session_id) sessionId = entryFlow.ordering_session_id;
  armEntryIdleTimeout();
  return entryFlow;
}

function armEntryIdleTimeout() {
  if (entryIdleTimer) clearTimeout(entryIdleTimer);
  entryIdleTimer = null;
  if (!entryFlow || ['menu_ready', 'abandoned'].includes(entryFlow.state)) return;
  const timeoutMs = Number(getRuntimeSettings().ENTRY_FLOW_IDLE_TIMEOUT_MS || 120000);
  entryIdleTimer = setTimeout(async () => {
    try { await advanceEntryFlow('abandon', { safe_reason: 'idle_timeout' }); } catch { /* reload still clears sensitive memory */ }
    location.reload();
  }, Math.max(30000, timeoutMs));
}

function entryFlowHooks() {
  return {
    onMemberMode: () => advanceEntryFlow('choose_member'),
    onMemberNotFound: () => advanceEntryFlow('member_not_found'),
    onMemberUnavailable: () => advanceEntryFlow('member_unavailable'),
    onMemberRetry: () => advanceEntryFlow('retry_member'),
    onReturnToMode: () => advanceEntryFlow('return_to_mode'),
    onRegistrationStarted: () => advanceEntryFlow('begin_registration'),
    onMemberFound: async member => {
      await advanceEntryFlow('member_found', { member_ref: member.member_id || '' });
      if (member.phone) await api.memberLogin(sessionId, member.phone);
    },
    onRegistered: async member => {
      await advanceEntryFlow('registration_completed', { member_ref: member.member_id || '' });
      if (member.phone) await api.memberLogin(sessionId, member.phone);
    },
    onGuest: () => advanceEntryFlow('choose_guest'),
  };
}

// 會員限定優惠在點餐途中再次叫出會員選擇時，entry flow 早已是 menu_ready，
// choose_guest / choose_member 在 server 上都不是合法轉換（ordering_entry 只允許
// 從 choosing_mode 等入口狀態發出）。這裡的「訪客」不是入口決策，而是關掉這次
// 登入邀請、維持既有的訪客身分，所以只做會員登入，不再送 entry flow 指令。
function midSessionMemberHooks() {
  const keepCurrentMode = async () => {};
  return {
    onMemberMode: keepCurrentMode,
    onMemberNotFound: keepCurrentMode,
    onMemberUnavailable: keepCurrentMode,
    onMemberRetry: keepCurrentMode,
    onReturnToMode: keepCurrentMode,
    onRegistrationStarted: keepCurrentMode,
    onMemberFound: async member => {
      if (member.phone) await api.memberLogin(sessionId, member.phone);
    },
    onRegistered: async member => {
      if (member.phone) await api.memberLogin(sessionId, member.phone);
    },
    onGuest: keepCurrentMode,
  };
}

function stopPeriodicEmotionAnalysis() {
  periodicEmotionGeneration += 1;
  if (periodicEmotionTimer) clearTimeout(periodicEmotionTimer);
  periodicEmotionTimer = null;
  stopRollingBuffer();
}

function releaseEmotionVideoTracks() {
  state.stream?.getVideoTracks().forEach(track => {
    track.stop();
    state.stream?.removeTrack?.(track);
  });
}

function startPeriodicEmotionAnalysis(clipSec) {
  stopPeriodicEmotionAnalysis();
  const generation = periodicEmotionGeneration;
  const intervalMs = Math.max(10, Number(clipSec) || 5) * 1000;

  const schedule = delay => {
    if (generation !== periodicEmotionGeneration) return;
    periodicEmotionTimer = setTimeout(runOnce, delay);
  };

  async function runOnce() {
    periodicEmotionTimer = null;
    if (generation !== periodicEmotionGeneration) return;
    if (!isSystemRunning || !isKioskActive() || state.isVoiceProcessing) {
      schedule(intervalMs);
      return;
    }
    try {
      const readiness = await api.getEmotionReadiness();
      if (generation !== periodicEmotionGeneration) return;
      if (!readiness?.ready) {
        stopRollingBuffer();
        releaseEmotionVideoTracks();
        schedule(intervalMs);
        return;
      }

      const mediaReady = await ensureMediaTracks({ video: true });
      if (generation !== periodicEmotionGeneration) return;
      if (!mediaReady.videoReady || !state.stream?.getVideoTracks().some(track => track.readyState === 'live')) {
        stopRollingBuffer();
        schedule(intervalMs);
        return;
      }
      startRollingBuffer(state.stream, clipSec);
      const clip = capturePreEventClip();
      if (clip) await api.analyzeVoiceEmotionEvent(sessionId, 'ordering_periodic', clip);
    } catch (error) {
      stopRollingBuffer();
      releaseEmotionVideoTracks();
      console.warn('[emotion] 模型未就緒或定期分析未完成，已暫停擷取並等待恢復。', error);
    }
    schedule(intervalMs);
  }

  schedule(0);
}

async function runPosStartup() {
  if (isMenuStarting) return false;
  isMenuStarting = true;
  hideMenuLoadError();
  try {
    resetVoiceEmotionRound();
    const f = getFeatures();
    await loadMenu();
    if (entryFlow?.state === 'initializing_menu') await advanceEntryFlow('menu_initialized');
    const needAudio = Boolean(f.voiceAssist);
    // Periodic emotion analysis requests the camera only after its model gate is
    // ready. Voice assistance can still request the microphone independently.
    const mediaReady = await ensureMediaTracks({ video: false, audio: needAudio });
    if (!mediaReady.audioReady && needAudio) console.warn('Microphone unavailable; Kiosk flow continues without voice assistance.');
    promoBannerController.load();
    cartPromoBannerController.load();
    applyFeaturesToKiosk();
    ui.overlay.style.opacity = '0';
    setTimeout(() => { ui.overlay.classList.add('hidden'); }, 500);
    isSystemRunning = true;
    state.lastCartAddAt = Date.now();
    startPageDwellWatcher();
    setInteractionPage('menu_page', { source: 'start_system' });
    renderMemberMenuHeader();
    setTimeout(() => aiRecommendationController.start(), 600);
    if (f.voiceAssist) await setupAskRecorder();
    if (
      getRuntimeSettings().EMOTION_ENABLED
      && getRuntimeSettings().EMOTION_CAPTURE_MODE === 'periodic'
    ) {
      const bufferSec = Math.max(2, Math.min(30, Number(getRuntimeSettings().EMOTION_CLIP_SEC) || 5));
      startPeriodicEmotionAnalysis(bufferSec);
    }
    return true;
  } catch (error) {
    if (entryFlow?.state === 'initializing_menu') {
      await advanceEntryFlow('menu_failed', { safe_reason: String(error?.message || 'menu_initialization_failed') }).catch(() => {});
    }
    console.error('[Kiosk] 菜單初始化失敗。', error);
    isSystemRunning = false;
    showMenuLoadError();
    return false;
  } finally {
    isMenuStarting = false;
  }
}

document.getElementById('menuLoadRetry')?.addEventListener('click', () => {
  const retry = document.getElementById('menuLoadRetry');
  if (retry) {
    retry.disabled = true;
    retry.textContent = '重新載入中…';
  }
  void (async () => {
    if (entryErrorMode === 'entry_start') {
      hideMenuLoadError();
      await beginEntryFlow();
      return;
    }
    if (entryFlow?.state === 'menu_initialization_failed') await advanceEntryFlow('retry_menu');
    await runPosStartup();
  })();
});

document.getElementById('menuLoadBack')?.addEventListener('click', () => {
  hideMenuLoadError();
  void (async () => {
    if (entryFlow?.state === 'menu_initialization_failed') await advanceEntryFlow('return_to_mode');
    showMemberChoice(() => { void runPosStartup(); }, { preserveInput: true, hooks: entryFlowHooks() });
  })();
});

// 閒置偵測：任何觸控 / 點擊都重設計時（全域，只需註冊一次）
document.addEventListener('pointerdown', () => { lastInteractionAt = Date.now(); armEntryIdleTimeout(); }, { passive: true });
document.addEventListener('touchstart',  () => { lastInteractionAt = Date.now(); armEntryIdleTimeout(); }, { passive: true });

ui.startBtn?.addEventListener('pointerdown', () => {
  ui.overlay?.classList.add('startup-pressing');
});
['pointerup', 'pointercancel', 'pointerleave'].forEach(eventName => {
  ui.startBtn?.addEventListener(eventName, () => {
    ui.overlay?.classList.remove('startup-pressing');
  });
});

import {
  isVoiceAssistantActive,
  cancelActiveVoiceTurn,
  closeVoiceBubble,
  hideVoiceAssistOverlay,
  resetVoiceEmotionRound,
  setupAskRecorder,
  startAskRecording,
} from './voice.js';

window.addEventListener('beforeunload', () => {
  cancelActiveVoiceTurn();
  stopPeriodicEmotionAnalysis();
  if (pageDwellTimer) clearInterval(pageDwellTimer);
  if (entryIdleTimer) clearTimeout(entryIdleTimer);
  aiRecommendationController.stop();
});


// =========================================================
// 結帳
// =========================================================
let selectedFulfillment = 'takeout';
let selectedPayment = 'credit-card';
let activeCheckoutQuote = null;
let checkoutIdempotencyKey = '';

// 取餐號由伺服器在訂單建立時配號（confirmed_orders.pickup_number），
// 報價階段並不存在，因此確認頁不得自行編造號碼。
const PENDING_ORDER_NUMBER_LABEL = '付款完成後產生';

function updateChoiceGroup(selector, selectedValue) {
  document.querySelectorAll(selector).forEach(button => {
    const value = button.dataset.fulfillment || button.dataset.payment;
    button.classList.toggle('selected', value === selectedValue);
    if (value === selectedValue && !button.querySelector('b')) {
      button.insertAdjacentHTML('beforeend', '<b><i class="fas fa-check"></i></b>');
    }
  });
}

function renderOrderConfirm(quote = activeCheckoutQuote) {
  const items = Array.isArray(quote?.pricing?.cart_items) ? quote.pricing.cart_items : [];
  const prepMinutes = Math.max(0, ...items.map(item => Number(item.prep_time_minutes || item.prep_minutes || 0)));
  const totals = {
    subtotal: Number(quote?.pricing?.subtotal || 0),
    serviceFee: Number(quote?.pricing?.fee_total || 0),
    total: Number(quote?.pricing?.total || 0),
  };

  if (ui.confirmSubtotalPrice) ui.confirmSubtotalPrice.textContent = `$${totals.subtotal}`;
  if (ui.confirmServiceFee) ui.confirmServiceFee.textContent = `$${totals.serviceFee}`;
  if (ui.confirmTotalPrice) ui.confirmTotalPrice.textContent = `$${totals.total}`;
  if (ui.confirmOrderNumber) ui.confirmOrderNumber.textContent = PENDING_ORDER_NUMBER_LABEL;
  if (ui.confirmPrepTime) ui.confirmPrepTime.textContent = `約 ${prepMinutes || 5} 分鐘`;
  if (ui.confirmPayBtn) ui.confirmPayBtn.disabled = !items.length;

  if (!ui.confirmOrderList) return;
  if (!items.length) {
    ui.confirmOrderList.innerHTML = `
      <div class="order-empty">
        <i class="fas fa-shopping-bag"></i>
        <p>${escapeHTML(kioskText('menuFallback'))}</p>
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
          ${visual.image ? `<img src="${escapeHTML(visual.image)}" alt="${escapeHTML(item.name)}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">` : ''}
          <span class="menu-photo-fallback" style="display:${visual.image ? 'none' : 'flex'}">${escapeHTML(visual.emoji || '🍔')}</span>
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

// 伺服器建立的訂單才帶有權威的取餐號與定價快照；kiosk 一律沿用，不自行重算。
function confirmedOrderResult(order) {
  return {
    orderNumber: order?.pickup_number || 0,
    sessionId: order?.session_id || sessionId,
    pricing: order?.pricing || null,
  };
}

function showConfirmationPendingNotice() {
  const overlay = document.getElementById('confirmationPendingOverlay');
  overlay?.classList.remove('hidden');
  overlay?.setAttribute('aria-hidden', 'false');
  const assist = document.getElementById('confirmationPendingAssist');
  if (assist) assist.disabled = false;
}

function hideConfirmationPendingNotice() {
  const overlay = document.getElementById('confirmationPendingOverlay');
  overlay?.classList.add('hidden');
  overlay?.setAttribute('aria-hidden', 'true');
}

document.getElementById('confirmationPendingAssist')?.addEventListener('click', event => {
  const button = event.currentTarget;
  if (button.disabled) return;
  button.disabled = true;
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_staff_requested',
    button_id: 'confirmationPendingAssist',
    metadata: { reason: 'confirmation_outcome_unknown' },
  });
});

// Confirmation Outcome Unknown：以同一個 quote_id 與 idempotency key 持續查詢，
// 直到找到訂單或收到權威拒絕為止。不確定不等於失敗，因此期間顯示的是進行中狀態。
const CONFIRMATION_RESOLVE_TIMEOUT_MS = 60000;
const CONFIRMATION_POLL_MAX_DELAY_MS = 3000;
// Confirm 有時限，但逾時的意義是「結果未知」而不是「失敗」：中止只代表這個瀏覽器
// 不知道訂單建立了沒有，之後由同一個 quote_id 與 idempotency key 查出真相。
// 二十秒是為了不把一個只是比較慢、其實會成功的 confirm 誤推進不確定狀態——
// 那條路徑會自己恢復，但顧客會先看到一次不必要的「仍在確認訂單」。
const CONFIRMATION_REQUEST_TIMEOUT_MS = 20000;

async function resolveUnknownConfirmation(quoteId, idempotencyKey) {
  showConfirmationPendingNotice();
  const deadline = Date.now() + CONFIRMATION_RESOLVE_TIMEOUT_MS;
  let delay = 300;
  try {
    while (Date.now() < deadline) {
      const outcome = await api.getCheckoutOutcome(quoteId, idempotencyKey).catch(() => null);
      if (outcome?.order) {
        hideConfirmationPendingNotice();
        return confirmedOrderResult(outcome.order);
      }
      // 權威拒絕（報價過期、品項不可供應）是確定的結果，立即結束不確定狀態。
      if (outcome?.type && outcome.type !== 'confirmed' && outcome.type !== 'unknown') {
        hideConfirmationPendingNotice();
        throw new Error(outcome.type);
      }
      await new Promise(resolve => setTimeout(resolve, delay));
      delay = Math.min(delay * 2, CONFIRMATION_POLL_MAX_DELAY_MS);
    }
  } catch (error) {
    hideConfirmationPendingNotice();
    throw error;
  }
  // 逾時仍未確定：維持等待畫面，交給服務人員處理，絕不呈現為結帳失敗或誘導再次付款。
  const title = document.getElementById('confirmationPendingTitle');
  if (title) title.textContent = '仍在確認訂單，請稍候';
  const unresolved = new Error('仍在確認訂單狀態，請洽服務人員協助，請勿重複付款。');
  unresolved.code = 'confirmation_outcome_unknown';
  throw unresolved;
}

async function writeCheckoutLog(cartIds = []) {
  const quote = activeCheckoutQuote || await prepareAuthoritativeCheckout();
  const quoteId = String(quote.quote_id || '');
  const idempotencyKey = checkoutIdempotencyKey || `checkout:${sessionId}:${quoteId}`;
  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), CONFIRMATION_REQUEST_TIMEOUT_MS);
  try {
    const res = await api.confirmCheckout(quoteId, idempotencyKey, ctrl.signal);
    if (!res?.ok) {
      const payload = await res?.json().catch(() => ({}));
      const detail = payload?.detail;
      const message = typeof detail === 'string'
        ? detail
        : (detail?.message || `checkout failed (${res?.status || 'network'})`);
      throw new Error(message);
    }
    const data = await res.json().catch(() => ({}));
    if (data.type !== 'confirmed') throw new Error(data.type || 'confirmation_rejected');
    return confirmedOrderResult(data.order);
  } catch (error) {
    if (quoteId && (error?.name === 'AbortError' || error instanceof TypeError)) {
      return await resolveUnknownConfirmation(quoteId, idempotencyKey);
    }
    trackInteractionEvent({
      event_type: 'payment_failed',
      button_id: 'confirmPayBtn',
      payment_fail_count: 1,
      metadata: { reason: error?.message || 'checkout_log_failed' }
    });
    throw error;
  } finally {
    clearTimeout(tid);
  }
}

async function prepareAuthoritativeCheckout() {
  await api.syncCart(sessionId, cartManager.getCartItems());
  activeCheckoutQuote = await api.prepareCheckout(sessionId);
  checkoutIdempotencyKey = `checkout:${sessionId}:${activeCheckoutQuote.quote_id}`;
  renderOrderConfirm(activeCheckoutQuote);
  return activeCheckoutQuote;
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

    // 金額一律沿用伺服器的訂單定價快照（含費用與促銷），不得由購物車重算，
    // 否則完成畫面會與顧客確認過的 Checkout Quote 不一致。
    const total = Number.isFinite(Number(orderData.pricing?.total))
      ? Number(orderData.pricing.total)
      : cartItems.reduce((sum, item) => sum + item.price * item.quantity, 0);
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
  } catch (error) {
    if (error?.code === 'confirmation_outcome_unknown') {
      // 結果仍不確定：等待畫面保持可見，付款按鈕維持停用，避免顧客重複付款。
      if (button) button.innerHTML = originalHTML;
      showPushNotice(error.message);
      return;
    }
    orderCompleted = false;
    setConfirmButtonsDisabled(false);
    updateVoiceAssistVisibility();
    if (button) button.innerHTML = originalHTML;
    showPushNotice(`結帳失敗：${error?.message || '請稍後再試'}`);
    return;
  }

  if (button) button.innerHTML = originalHTML;

  // 完成畫面優先使用伺服器訂單的定價快照；只有在快照缺漏時才退回本地購物車內容。
  const quotedItems = Array.isArray(orderData.pricing?.cart_items) ? orderData.pricing.cart_items : [];
  const rawItems = quotedItems.length
    ? quotedItems
    : (cartManager.getCartItems ? cartManager.getCartItems() : []);
  orderData.cartItems = rawItems.map(item => ({
    name: item.name || item.id || '',
    quantity:  Number(item.qty || item.quantity || 1),
    price: resolveItemPrice(item),
  }));

  resetVoiceEmotionRound();
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

ui.checkoutBtn.onclick = async () => {
  if (!cartManager.getCartIds().length) return;
  ui.checkoutBtn.disabled = true;
  try {
    await prepareAuthoritativeCheckout();
    openOrderConfirmModal();
  } catch (error) {
    showPushNotice(`無法準備結帳：${error?.message || '請稍後再試'}`);
    return;
  } finally {
    ui.checkoutBtn.disabled = false;
  }
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
  totalClickCount = 0;
  clearKioskFloatingUI();
  hideChoiceHesitationModal();
  cancelActiveVoiceTurn();
  stopPeriodicEmotionAnalysis();
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

ui.paymentCountdownAssistButton?.addEventListener('click', () => {
  // 防止重複點擊：立即禁用按鈕，避免多次發出人員通知
  if (ui.paymentCountdownAssistButton.disabled) return;
  ui.paymentCountdownAssistButton.disabled = true;

  // 立刻切換到 notified 畫面，讓使用者知道已收到點擊
  showPaymentCountdownSection('notified');

  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_staff_requested',
    button_id: 'paymentCountdownAssistButton',
    metadata: {}
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
  finishOrder(cartIds, ui.kioskCounterPayBtn, kioskText('counterPayCreating'));
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
  finishOrder(cartIds, ui.confirmPayBtn, kioskText('checkoutProcessing'));
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
  priceSpan.textContent = formatItemPrice(item);

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
  finishOrder(cartIds, null, kioskText('counterPayCreating'));
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
    reasons: item.reasons || ['choice_hesitation'],
    offer_ids: item.offer_ids || [],
    experiment_id: item.experiment_id || '',
    variant_id: item.variant_id || '',
    strategy: item.strategy || '',
  });
  renderChoiceHesitationItem(item);
}

Object.assign(window, {
  closeVoiceBubble,
  switchMainView,
  updateCartQty: trackedUpdateCartQty,
  deleteCartItem: trackedDeleteCartItem,
  trackInteractionEvent,
  reportInteractionEvent,
});

let kioskRuntimeInitialized = false;

async function initializeAuthenticatedKiosk() {
  if (kioskRuntimeInitialized) return;
  kioskRuntimeInitialized = true;
  applyKioskText();
  cartManager.renderCart();
  applyFeaturesToKiosk();
  initRealtimeClients();
}

createDeviceIdentityController({
  apiBaseUrl: api.API_BASE,
  onAuthenticated: initializeAuthenticatedKiosk,
}).bind();
