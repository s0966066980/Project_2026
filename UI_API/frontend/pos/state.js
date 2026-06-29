// =========================================================
// POS 共享可變狀態。app.js 與各功能模組 import 同一個物件，
// 取得 live binding（避免以值傳遞造成的過時讀取）。
// 僅放跨模組共享的欄位；只在 app.js 內使用的狀態仍留在 app.js。
// =========================================================
export const state = {
  // 菜單與 kiosk 視圖
  menuData: [],
  kioskScreen: 'categories',
  kioskActiveGroup: '',
  kioskActiveFilter: '全部',
  // 猶豫彈窗
  currentChoiceHesitationItem: null,
  lastCartAddAt: Date.now(),
  passiveLastTriggerAt: 0,
  // 付款倒數
  paymentCountdownTimer: null,
  pendingPaymentEmotion: null,
  paymentEmotionPromise: null,
  paymentCountdownCartIds: [],
  // 媒體串流 / 語音錄音器（跨模組共享）
  stream: null,
  askRecorder: null,
  // 語音
  isVoiceProcessing: false,
  askRecordingStartedAt: 0,
  voiceBubbleTimer: null,
  // session 累計 + UI 計時器（跨模組共享）
  sessionPushedIds: new Set(),
  sessionCartSources: [],   // [{id, source}] 記錄每筆加入來源
  interactionModalTimer: null,
  lastValidOrderActionAt: 0,
  member: null,
};
