// =========================================================
// 付款倒數 Modal：15 秒倒數 → 失敗畫面／人員協助。
// =========================================================
import { ui } from '../shared/ui.js';
import { state } from './state.js';
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
  if (ui.paymentCountdownAssistButton) ui.paymentCountdownAssistButton.disabled = false;
  ui.paymentCountdownBackdrop?.classList.remove('hidden');
  ui.paymentCountdownModal?.classList.remove('hidden');
  showPaymentCountdownSection('counting');
  startPaymentCountdown();
}

export function closePaymentCountdown() {
  if (state.paymentCountdownTimer) { clearInterval(state.paymentCountdownTimer); state.paymentCountdownTimer = null; }
  ui.paymentCountdownBackdrop?.classList.add('hidden');
  ui.paymentCountdownModal?.classList.add('hidden');
  state.paymentCountdownCartIds = [];
}

function startPaymentCountdown() {
  if (state.paymentCountdownTimer) clearInterval(state.paymentCountdownTimer);
  let secondsLeft = PAYMENT_COUNTDOWN_TOTAL_SECONDS;

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
