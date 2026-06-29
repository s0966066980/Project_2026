import { hideFlexElement, showFlexElement } from './components/VisibilityDisplay.js';

export const ui = {
  posView: document.getElementById('view-pos'),
  adminView: document.getElementById('view-admin'),
  overlay: document.getElementById('startupOverlay'),
  adminNotificationBox: document.getElementById('adminNotificationBox'),
  checkoutOverlay: document.getElementById('checkoutOverlay'),
  kioskPaymentScreen: document.getElementById('kioskPaymentScreen'),
  kioskFastPayBtn: document.getElementById('kioskFastPayBtn'),
  kioskCounterPayBtn: document.getElementById('kioskCounterPayBtn'),
  kioskPaymentBackBtn: document.getElementById('kioskPaymentBackBtn'),
  kioskCancelOrderBtn: document.getElementById('kioskCancelOrderBtn'),
  paymentCountdownBackdrop: document.getElementById('paymentCountdownBackdrop'),
  paymentCountdownModal: document.getElementById('paymentCountdownModal'),
  paymentCountdownCounting: document.getElementById('paymentCountdownCounting'),
  paymentCountdownFailed: document.getElementById('paymentCountdownFailed'),
  paymentCountdownNotified: document.getElementById('paymentCountdownNotified'),
  paymentCountdownArc: document.getElementById('paymentCountdownArc'),
  paymentCountdownNumber: document.getElementById('paymentCountdownNumber'),
  paymentCountdownCancelButton: document.getElementById('paymentCountdownCancelButton'),
  paymentCountdownAssistButton: document.getElementById('paymentCountdownAssistButton'),
  paymentCountdownBackButton: document.getElementById('paymentCountdownBackButton'),
  paymentCountdownNotifyMessage: document.getElementById('paymentCountdownNotifyMessage'),
  kioskTitle: document.getElementById('kioskTitle'),
  kioskSubtitle: document.getElementById('kioskSubtitle'),
  kioskBackBtn: document.getElementById('kioskBackBtn'),
  kioskSearchBtn: document.getElementById('kioskSearchBtn'),
  kioskSectionHead: document.getElementById('kioskSectionHead'),
  kioskBottomBar: document.getElementById('kioskBottomBar'),
  kioskHomeBtn: document.getElementById('kioskHomeBtn'),
  kioskCartBtn: document.getElementById('kioskCartBtn'),
  kioskBottomCount: document.getElementById('kioskBottomCount'),
  kioskBottomTotal: document.getElementById('kioskBottomTotal'),
  continueOrderBtn: document.getElementById('continueOrderBtn'),
  clearCartBtn: document.getElementById('clearCartBtn'),
  startBtn: document.getElementById('startSystemBtn'),
  menuGrid: document.getElementById('menuGrid'),
  cartList: document.getElementById('cartList'),
  cartCountBadge: document.getElementById('cartCountBadge'),
  totalPrice: document.getElementById('totalPrice'),
  checkoutBtn: document.getElementById('checkoutBtn'),
  orderConfirmModal: document.getElementById('orderConfirmModal'),
  orderConfirmCloseBtn: document.getElementById('orderConfirmCloseBtn'),
  confirmOrderList: document.getElementById('confirmOrderList'),
  confirmSubtotalPrice: document.getElementById('confirmSubtotalPrice'),
  confirmServiceFee: document.getElementById('confirmServiceFee'),
  confirmTotalPrice: document.getElementById('confirmTotalPrice'),
  confirmOrderNumber: document.getElementById('confirmOrderNumber'),
  confirmPrepTime: document.getElementById('confirmPrepTime'),
  confirmBackBtn: document.getElementById('confirmBackBtn'),
  confirmPayBtn: document.getElementById('confirmPayBtn'),
  webcam: document.getElementById('webcam'),
  voiceAssistBtn: document.getElementById('voiceAssistBtn'),
  voiceAssistBtnText: document.getElementById('voiceAssistBtnText'),
  voiceAssistOverlay: document.getElementById('voiceAssistOverlay'),
  voiceAssistOverlayTitle: document.getElementById('voiceAssistOverlayTitle'),
  voiceAssistOverlaySubtitle: document.getElementById('voiceAssistOverlaySubtitle'),
  voiceAssistStopBtn: document.getElementById('voiceAssistStopBtn'),
  voiceAssistStopText: document.getElementById('voiceAssistStopText'),
  audio: document.getElementById('ttsAudio'),
  centerPanel: document.getElementById('centerPanel'),
  floatPush: document.getElementById('floatPush'),
  aiPushBar: document.getElementById('aiPushBar'),
  voiceBubble: document.getElementById('voiceReplyBubble'),
  voiceDialogueGrid: document.getElementById('voiceDialogueGrid'),
  voiceLangBadge: document.getElementById('voiceLangBadge'),
};

export function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

export function switchMainView(view, callbacks = {}) {
  if (view === 'admin') {
    callbacks.clearPOSFloatingUI?.();
    hideFlexElement(ui.posView);
    showFlexElement(ui.adminView);
    callbacks.loadAdminData?.();
  } else {
    hideFlexElement(ui.adminView);
    showFlexElement(ui.posView);
    callbacks.applyFeaturesToPOS?.();
    callbacks.loadMenu?.();
  }
}
