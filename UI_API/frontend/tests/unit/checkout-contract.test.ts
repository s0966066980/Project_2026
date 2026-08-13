import { describe, expect, it } from 'vitest';

import {
  PENDING_ORDER_NUMBER_LABEL,
  checkoutQuoteSummary,
  completionCartItems,
  confirmedOrderResult,
} from '../../kiosk/checkout.js';

describe('kiosk checkout projection', () => {
  it('projects the server quote without inventing checkout values', () => {
    const summary = checkoutQuoteSummary({
      pricing: {
        subtotal: 100,
        fee_total: 10,
        total: 110,
        cart_items: [{ id: 'coffee', name: 'Coffee', quantity: 2, prep_minutes: 4 }],
      },
    });

    expect(summary).toMatchObject({
      subtotal: 100,
      serviceFee: 10,
      total: 110,
      prepMinutes: 4,
    });
    expect(PENDING_ORDER_NUMBER_LABEL).toBe('付款完成後產生');
  });

  it('uses the server order identity and keeps an incomplete identity safe', () => {
    expect(confirmedOrderResult({ pickup_number: 7, session_id: 'server-session' }, 'browser-session')).toEqual({
      orderNumber: 7,
      sessionId: 'server-session',
      pricing: null,
    });
    expect(confirmedOrderResult({}, 'browser-session').sessionId).toBe('browser-session');
  });

  it('prefers final server pricing and falls back only when it is absent', () => {
    const price = (item: any) => Number(item.price || 0);
    expect(completionCartItems({ pricing: { cart_items: [{ id: 'server', name: 'Server', qty: 2, price: 35 }] } }, [{ id: 'local', price: 9 }], price))
      .toEqual([{ name: 'Server', quantity: 2, price: 35 }]);
    expect(completionCartItems({}, [{ id: 'local', price: 9 }], price))
      .toEqual([{ name: 'local', quantity: 1, price: 9 }]);
  });
});
