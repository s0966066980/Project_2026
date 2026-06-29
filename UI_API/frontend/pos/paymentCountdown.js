// =========================================================
// 付款倒數 Modal：15 秒倒數 → Emotion-LLaMA 擷取 → 失敗畫面/人員協助。
// =========================================================
import * as api from '../shared/apiClient.js';
import { ui } from '../shared/ui.js';
import { state } from './state.js';
import { capturePreEventClip } from './media.js';
import { getRequiredRuntimeDependency } from './runtime.js';

const PAYMENT_COUNTDOWN_TOTAL_SECONDS = 15;        // 倒數總秒數
const PAYMENT_COUNTDOWN_CIRCUMFERENCE = 314.16;  // 2πr, r=50

export function showPaymentCountdownSection(name) {
  // name: 'counting' | 'failed' | 'notified'
  ui.paymentCountdownCounting?.classList.toggle('hidden', name !== 'counting');
  ui.paymentCountdownFailed?.classList.toggle('hidden', name !== 'failed');
  ui.paymentCountdownNotified?.classList.toggle('hidden', name !== 'notified');
}

export function openPaymentCountdown(cartIds) {
  state.paymentCountdownCartIds = cartIds.slice();
  state.pendingPaymentEmotion = null;
  state.paymentEmotionPromise = null;
  ui.paymentCountdownBackdrop?.classList.remove('hidden');
  ui.paymentCountdownModal?.classList.remove('hidden');
  showPaymentCountdownSection('counting');
  startPaymentCountdown();
}

export function closePaymentCountdown() {
  if (state.paymentCountdownTimer) { clearInterval(state.paymentCountdownTimer); state.paymentCountdownTimer = null; }
  ui.paymentCountdownBackdrop?.classList.add('hidden');
  ui.paymentCountdownModal?.classList.add('hidden');
  state.pendingPaymentEmotion = null;
  state.paymentEmotionPromise = null;
  state.paymentCountdownCartIds = [];
}

function startPaymentCountdown() {
  if (state.paymentCountdownTimer) clearInterval(state.paymentCountdownTimer);
  let secondsLeft = PAYMENT_COUNTDOWN_TOTAL_SECONDS;

  // 付款倒數擷取：在第 (TOTAL - paymentClipSec) 秒觸發，確保 buffer 有 paymentClipSec 秒的影像
  const paymentClipSec = Number(getRequiredRuntimeDependency('getRuntimeSettings')().PAYMENT_EMOTION_CLIP_SEC) || 5.0;
  const captureAtRemaining = Math.max(1, Math.round(PAYMENT_COUNTDOWN_TOTAL_SECONDS - paymentClipSec));
  let captured = false;

  const updateUI = () => {
    if (ui.paymentCountdownNumber) ui.paymentCountdownNumber.textContent = String(secondsLeft);
    if (ui.paymentCountdownArc) {
      const elapsed = PAYMENT_COUNTDOWN_TOTAL_SECONDS - secondsLeft;
      ui.paymentCountdownArc.style.strokeDashoffset =
        String(PAYMENT_COUNTDOWN_CIRCUMFERENCE * (elapsed / PAYMENT_COUNTDOWN_TOTAL_SECONDS));
      const color = secondsLeft > 8 ? '#1db87a' : (secondsLeft > 3 ? '#f5871f' : '#e84040');
      ui.paymentCountdownArc.style.stroke = color;
    }
  };
  updateUI();

  state.paymentCountdownTimer = setInterval(() => {
    secondsLeft -= 1;
    updateUI();

    if (!captured && secondsLeft === captureAtRemaining
        && getRequiredRuntimeDependency('getRuntimeSettings')().EMOTION_LLAMA_ENABLED
        && getRequiredRuntimeDependency('getRuntimeSettings')().EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT !== false) {
      captured = true;
      capturePaymentEmotion();
    }

    if (secondsLeft <= 0) {
      clearInterval(state.paymentCountdownTimer);
      state.paymentCountdownTimer = null;
      getRequiredRuntimeDependency('trackInteractionEvent')({
        page_id: 'payment_page',
        event_type: 'payment_timeout',
        button_id: 'paymentCountdownModal',
        metadata: { cart_ids: state.paymentCountdownCartIds }
      });
      showPaymentCountdownSection('failed');
    }
  }, 1000);
}

function capturePaymentEmotion() {
  if (!getRequiredRuntimeDependency('isPosMode')()) return;
  const blob = capturePreEventClip();
  if (!blob) return;
  state.paymentEmotionPromise = api.analyzeEmotionEvent(getRequiredRuntimeDependency('sessionId'), 'payment_timeout', blob)
    .then(data => {
      if (data) {
        state.pendingPaymentEmotion = {
          emotion:        data.emotion        || '',
          intensity:      data.intensity      || '',
          description:    data.description    || '',
          assist_response: data.assist_response || '',
        };
      }
    })
    .catch(e => console.warn('[payment] emotion capture failed:', e));
}
