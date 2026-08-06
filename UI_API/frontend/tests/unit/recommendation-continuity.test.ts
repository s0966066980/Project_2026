import { describe, expect, it } from 'vitest';

import {
  recommendationEligibility,
  recommendationRefreshAction,
} from '../../kiosk/recommendationContinuity.js';

const visibleMenu = {
  featureEnabled: true,
  barPresent: true,
  kioskActive: true,
  documentVisible: true,
  voiceActive: false,
  paymentOpen: false,
  cartOpen: false,
  eligibleItemCount: 1,
};

describe('passive recommendation continuity', () => {
  it('temporarily hides only for explicit UI blockers', () => {
    expect(recommendationEligibility(visibleMenu)).toEqual({ eligible: true, reason: 'eligible' });
    expect(recommendationEligibility({ ...visibleMenu, voiceActive: true }).reason).toBe('voice_active');
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
