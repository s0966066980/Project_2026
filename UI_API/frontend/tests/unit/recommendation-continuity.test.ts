import { describe, expect, it } from 'vitest';

import {
  recommendationEligibility,
  recommendationRefreshAction,
  PLACEHOLDER_RECOMMENDATION_SOURCES,
  isServerAuthoredRecommendation,
} from '../../kiosk/recommendationContinuity.js';

const visibleMenu = {
  featureEnabled: true,
  barPresent: true,
  kioskActive: true,
  documentVisible: true,
  paymentOpen: false,
  cartOpen: false,
  eligibleItemCount: 1,
};

describe('passive recommendation continuity', () => {
  it('temporarily hides only for explicit UI blockers', () => {
    expect(recommendationEligibility(visibleMenu)).toEqual({ eligible: true, reason: 'eligible' });
    // Voice mode and the recommendation are separate features: the reply
    // bubble sits at the top of the screen at z-index 9000, the recommendation
    // bar at the bottom at 50, and suppressing one for the other protected
    // nothing. `voiceActive` is no longer part of the state at all — passing
    // it changes nothing, which is the assertion.
    const whileTalking = { ...visibleMenu, voiceActive: true };
    expect(recommendationEligibility(whileTalking)).toEqual({ eligible: true, reason: 'eligible' });
    expect(recommendationEligibility({ ...visibleMenu, cartOpen: true }).reason).toBe('cart_open');
    expect(recommendationEligibility({ ...visibleMenu, paymentOpen: true }).reason).toBe('payment_open');
  });

  it('keeps scheduling while a request is already in flight', () => {
    expect(recommendationRefreshAction({ eligible: true, requestInFlight: true, hasCurrent: true }))
      .toBe('show_current_and_retry');
    expect(recommendationRefreshAction({ eligible: false, requestInFlight: false, hasCurrent: true }))
      .toBe('hide_and_retry');
  });
});

describe('placeholder recommendation sources', () => {
  it('treats every locally chosen source as unauthored', () => {
    PLACEHOLDER_RECOMMENDATION_SOURCES.forEach((source) => {
      expect(isServerAuthoredRecommendation(source)).toBe(false);
    });
  });

  it('treats a server source as authored', () => {
    expect(isServerAuthoredRecommendation('ai_push')).toBe(true);
    expect(isServerAuthoredRecommendation('campaign')).toBe(true);
  });

  // A missing source is not evidence that the server chose the item, so it is
  // excluded with the placeholders rather than quietly counted.
  it('treats a blank or padded source conservatively', () => {
    expect(isServerAuthoredRecommendation('')).toBe(false);
    expect(isServerAuthoredRecommendation('   ')).toBe(false);
    expect(isServerAuthoredRecommendation('  local_default  ')).toBe(false);
    expect(isServerAuthoredRecommendation('  ai_push  ')).toBe(true);
  });
});
