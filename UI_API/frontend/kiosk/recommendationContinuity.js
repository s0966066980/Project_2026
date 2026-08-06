// @ts-check

/**
 * Keep recommendation visibility decisions independent from network state.
 * A temporary UI blocker hides the current card but must not discard it.
 *
 * @param {{
 *   featureEnabled: boolean,
 *   barPresent: boolean,
 *   kioskActive: boolean,
 *   documentVisible: boolean,
 *   voiceActive: boolean,
 *   paymentOpen: boolean,
 *   cartOpen: boolean,
 *   eligibleItemCount: number,
 * }} state
 */
export function recommendationEligibility(state) {
  if (!state.featureEnabled) return { eligible: false, reason: 'feature_disabled' };
  if (!state.barPresent) return { eligible: false, reason: 'surface_missing' };
  if (!state.kioskActive || !state.documentVisible) return { eligible: false, reason: 'kiosk_inactive' };
  if (state.voiceActive) return { eligible: false, reason: 'voice_active' };
  if (state.paymentOpen) return { eligible: false, reason: 'payment_open' };
  if (state.cartOpen) return { eligible: false, reason: 'cart_open' };
  if (state.eligibleItemCount < 1) return { eligible: false, reason: 'no_eligible_items' };
  return { eligible: true, reason: 'eligible' };
}

/** @param {{eligible: boolean, requestInFlight: boolean, hasCurrent: boolean}} state */
export function recommendationRefreshAction(state) {
  if (!state.eligible) return 'hide_and_retry';
  if (state.requestInFlight) return state.hasCurrent ? 'show_current_and_retry' : 'retry';
  return state.hasCurrent ? 'show_current_and_fetch' : 'show_fallback_and_fetch';
}
