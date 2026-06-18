// =========================================================
// 付款倒數 Modal：15 秒倒數 → Emotion-LLaMA 擷取 → 失敗畫面/人員協助。
// =========================================================
import * as api from '../shared/api.js';
import { ui } from '../shared/ui.js';
import { state } from './state.js';
import { capturePreEventClip } from './media.js';
import { sessionId, getRuntimeSettings, trackInteractionEvent, isPosMode } from './app.js';

const PAYMENT_CD_TOTAL = 15;        // 倒數總秒數
const PAYMENT_CD_CIRCUMFERENCE = 314.16;  // 2πr, r=50

export function _showPaymentCdSection(name) {
  // name: 'counting' | 'failed' | 'notified'
  ui.paymentCdCounting?.classList.toggle('hidden', name !== 'counting');
  ui.paymentCdFailed?.classList.toggle('hidden', name !== 'failed');
  ui.paymentCdNotified?.classList.toggle('hidden', name !== 'notified');
}

export function openPaymentCountdown(cartIds) {
  state._paymentCdCartIds = cartIds.slice();
  state._pendingPaymentEmotion = null;
  state._paymentEmotionPromise = null;
  ui.paymentCdBackdrop?.classList.remove('hidden');
  ui.paymentCdModal?.classList.remove('hidden');
  _showPaymentCdSection('counting');
  _startPaymentCountdown();
}

export function closePaymentCountdown() {
  if (state._paymentCdTimer) { clearInterval(state._paymentCdTimer); state._paymentCdTimer = null; }
  ui.paymentCdBackdrop?.classList.add('hidden');
  ui.paymentCdModal?.classList.add('hidden');
  state._pendingPaymentEmotion = null;
  state._paymentEmotionPromise = null;
  state._paymentCdCartIds = [];
}

function _startPaymentCountdown() {
  if (state._paymentCdTimer) clearInterval(state._paymentCdTimer);
  let secondsLeft = PAYMENT_CD_TOTAL;

  // 付款倒數擷取：在第 (TOTAL - paymentClipSec) 秒觸發，確保 buffer 有 paymentClipSec 秒的影像
  const paymentClipSec = Number(getRuntimeSettings().PAYMENT_EMOTION_CLIP_SEC) || 5.0;
  const captureAtRemaining = Math.max(1, Math.round(PAYMENT_CD_TOTAL - paymentClipSec));
  let captured = false;

  const updateUI = () => {
    if (ui.paymentCdNumber) ui.paymentCdNumber.textContent = String(secondsLeft);
    if (ui.paymentCdArc) {
      const elapsed = PAYMENT_CD_TOTAL - secondsLeft;
      ui.paymentCdArc.style.strokeDashoffset =
        String(PAYMENT_CD_CIRCUMFERENCE * (elapsed / PAYMENT_CD_TOTAL));
      const color = secondsLeft > 8 ? '#1db87a' : (secondsLeft > 3 ? '#f5871f' : '#e84040');
      ui.paymentCdArc.style.stroke = color;
    }
  };
  updateUI();

  state._paymentCdTimer = setInterval(() => {
    secondsLeft -= 1;
    updateUI();

    if (!captured && secondsLeft === captureAtRemaining
        && getRuntimeSettings().EMOTION_LLAMA_ENABLED
        && getRuntimeSettings().EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT !== false) {
      captured = true;
      _triggerPaymentEmotionCapture();
    }

    if (secondsLeft <= 0) {
      clearInterval(state._paymentCdTimer);
      state._paymentCdTimer = null;
      trackInteractionEvent({
        page_id: 'payment_page',
        event_type: 'payment_timeout',
        button_id: 'paymentCountdownModal',
        metadata: { cart_ids: state._paymentCdCartIds }
      });
      _showPaymentCdSection('failed');
    }
  }, 1000);
}

function _triggerPaymentEmotionCapture() {
  if (!isPosMode()) return;
  const blob = capturePreEventClip();
  if (!blob) return;
  state._paymentEmotionPromise = api.analyzeEmotionEvent(sessionId, 'payment_timeout', blob)
    .then(data => {
      if (data) {
        state._pendingPaymentEmotion = {
          emotion:        data.emotion        || '',
          intensity:      data.intensity      || '',
          description:    data.description    || '',
          assist_response: data.assist_response || '',
        };
      }
    })
    .catch(e => console.warn('[payment] emotion capture failed:', e));
}
