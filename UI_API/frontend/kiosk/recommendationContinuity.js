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
 *   paymentOpen: boolean,
 *   cartOpen: boolean,
 *   eligibleItemCount: number,
 * }} state
 */
export function recommendationEligibility(state) {
  if (!state.featureEnabled) return { eligible: false, reason: 'feature_disabled' };
  if (!state.barPresent) return { eligible: false, reason: 'surface_missing' };
  if (!state.kioskActive || !state.documentVisible) return { eligible: false, reason: 'kiosk_inactive' };
  // Voice used to suppress the recommendation. They are separate features on
  // separate parts of the screen — the reply bubble is anchored to the top at
  // z-index 9000, the recommendation bar to the bottom at 50 — so nothing was
  // being protected from anything. A customer talking to the assistant can
  // still be shown a recommendation, and it still counts as an impression
  // because it really was shown.
  if (state.paymentOpen) return { eligible: false, reason: 'payment_open' };
  if (state.cartOpen) return { eligible: false, reason: 'cart_open' };
  if (state.eligibleItemCount < 1) return { eligible: false, reason: 'no_eligible_items' };
  return { eligible: true, reason: 'eligible' };
}

/**
 * Sources the kiosk assigns to an item it picked itself when the recommendation API
 * gave it nothing usable. The events still report — suppressing them would leave the
 * later add-to-cart and checkout events with no source record — so operational
 * reporting excludes them by source instead (ADR-0054).
 */
export const PLACEHOLDER_RECOMMENDATION_SOURCES = Object.freeze(['local_default', 'local_fallback']);

/**
 * A blank source is not evidence that the server chose the item, so it is excluded
 * with the placeholders rather than counted.
 *
 * @param {string} source
 * @returns {boolean}
 */
export function isServerAuthoredRecommendation(source) {
  const normalized = String(source || '').trim();
  return Boolean(normalized) && !PLACEHOLDER_RECOMMENDATION_SOURCES.includes(normalized);
}

/** @param {{eligible: boolean, requestInFlight: boolean, hasCurrent: boolean}} state */
export function recommendationRefreshAction(state) {
  if (!state.eligible) return 'hide_and_retry';
  if (state.requestInFlight) return state.hasCurrent ? 'show_current_and_retry' : 'retry';
  return state.hasCurrent ? 'show_current_and_fetch' : 'show_fallback_and_fetch';
}
