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
  emotionCameraPanel: document.getElementById('emotionCameraPanel'),
  emotionCameraVideo: document.getElementById('emotionCameraVideo'),
  emotionCameraStatus: document.getElementById('emotionCameraStatus'),
  emotionDetectBox: document.getElementById('emotionDetectBox'),
  emotionDetectLabel: document.getElementById('emotionDetectLabel'),
  audio: document.getElementById('ttsAudio'),
  voiceAssistBtn: document.getElementById('voiceAssistBtn'),
  voiceAssistBtnText: document.getElementById('voiceAssistBtnText'),
  voiceAssistOverlay: document.getElementById('voiceAssistOverlay'),
  voiceAssistOverlayTitle: document.getElementById('voiceAssistOverlayTitle'),
  voiceAssistOverlaySubtitle: document.getElementById('voiceAssistOverlaySubtitle'),
  voiceAssistStopBtn: document.getElementById('voiceAssistStopBtn'),
  voiceAssistStopText: document.getElementById('voiceAssistStopText'),
  centerPanel: document.getElementById('centerPanel'),
  pingInd: document.getElementById('pingIndicator'),
  emotionBadge: document.getElementById('emotionBadge'),
  emotionText: document.getElementById('emotionText'),
  floatPush: document.getElementById('floatPush'),
  emotionFeed: document.getElementById('emotionFeed'),
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
    ui.posView.classList.replace('flex', 'hidden');
    ui.adminView.classList.replace('hidden', 'flex');
    callbacks.loadAdminData?.();
    callbacks.initAdminToggles?.();
  } else {
    ui.adminView.classList.replace('flex', 'hidden');
    ui.posView.classList.replace('hidden', 'flex');
    callbacks.applyFeaturesToPOS?.();
    callbacks.loadMenu?.();
  }
}

export function switchAdminTab(id, callbacks = {}) {
  document.querySelectorAll('.admin-tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.admin-tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + id)?.classList.remove('hidden');
  document.getElementById('tab-btn-' + id)?.classList.add('active');
  if (id === 'clips') callbacks.loadEmotionClips?.();
}

export function updateEmotionCameraPanel({ features, isPosActive, stream }) {
  if (!ui.emotionCameraPanel) return;
  const shouldShow = Boolean(features.emotionCamera && isPosActive && stream?.getVideoTracks().length);
  ui.emotionCameraPanel.classList.toggle('hidden', !shouldShow);
  if (shouldShow && ui.emotionCameraVideo && ui.emotionCameraVideo.srcObject !== stream) {
    ui.emotionCameraVideo.srcObject = stream;
  }
}

export function updateEmotionDetectionOverlay(personCheck = {}, context = {}) {
  updateEmotionCameraPanel(context);
  if (!ui.emotionDetectBox || !ui.emotionCameraStatus) return;
  const available = personCheck && personCheck.available !== false;
  const detected = Boolean(personCheck && personCheck.person_detected);
  const box = (personCheck.boxes || [])[0] || null;
  ui.emotionDetectBox.classList.toggle('detected', detected);
  ui.emotionDetectBox.classList.toggle('undetected', available && !detected);
  if (detected && box) {
    const w = Math.max(4, Math.min(100, Number(box.w || 0) * 100));
    const h = Math.max(4, Math.min(100, Number(box.h || 0) * 100));
    const x = Math.max(0, Math.min(100 - w, 100 - (Number(box.x || 0) * 100) - w));
    const y = Math.max(0, Math.min(100 - h, Number(box.y || 0) * 100));
    ui.emotionDetectBox.style.left = `${x}%`;
    ui.emotionDetectBox.style.top = `${y}%`;
    ui.emotionDetectBox.style.width = `${w}%`;
    ui.emotionDetectBox.style.height = `${h}%`;
    ui.emotionDetectBox.style.right = 'auto';
    ui.emotionDetectBox.style.bottom = 'auto';
  } else {
    ui.emotionDetectBox.style.left = '18%';
    ui.emotionDetectBox.style.right = '18%';
    ui.emotionDetectBox.style.top = '12%';
    ui.emotionDetectBox.style.bottom = '16%';
    ui.emotionDetectBox.style.width = 'auto';
    ui.emotionDetectBox.style.height = 'auto';
  }
  const hits = Number(personCheck.person_hits ?? personCheck.face_hits ?? 0);
  const frames = Number(personCheck.frames_checked || 0);
  if (detected) {
    const conf = box?.confidence ? ` ${Math.round(Number(box.confidence) * 100)}%` : '';
    ui.emotionCameraStatus.textContent = `YOLO11 人物 ${hits}/${frames || '-'}`;
    if (ui.emotionDetectLabel) ui.emotionDetectLabel.textContent = `person${conf}`;
  } else if (available) {
    ui.emotionCameraStatus.textContent = `YOLO11 未偵測 ${hits}/${frames || '-'}`;
    if (ui.emotionDetectLabel) ui.emotionDetectLabel.textContent = 'no person';
  } else {
    ui.emotionCameraStatus.textContent = '偵測不可用';
    if (ui.emotionDetectLabel) ui.emotionDetectLabel.textContent = '等待偵測';
  }
}
