import { describe, expect, it } from 'vitest';

import { isServerAuthoredTouch } from '../../shared/touchEventClient.js';

describe('commercial touch authority', () => {
  it('accepts a recommendation the server decided', () => {
    expect(isServerAuthoredTouch({ decision_id: 'decision_123' })).toBe(true);
  });

  it('accepts a campaign the server authored', () => {
    expect(isServerAuthoredTouch({ campaign_id: 'campaign_7' })).toBe(true);
  });

  // The kiosk picks a local placeholder when the recommendation API is unreachable.
  // It keeps the surface from going blank, but nothing on the server chose it.
  it('rejects a touch carrying neither a decision nor a campaign', () => {
    expect(isServerAuthoredTouch({ placement: 'ai_push', item_id: 'item_1' })).toBe(false);
  });

  it('rejects blank and whitespace-only identifiers', () => {
    expect(isServerAuthoredTouch({ decision_id: '', campaign_id: '' })).toBe(false);
    expect(isServerAuthoredTouch({ decision_id: '   ' })).toBe(false);
  });

  it('rejects missing details entirely', () => {
    expect(isServerAuthoredTouch({})).toBe(false);
  });
});
