import { beforeEach, describe, expect, it } from 'vitest';

import { createCartManager } from '../../kiosk/cart.js';

function makeCart() {
  const ui = {
    cartList: { innerHTML: '' },
    checkoutBtn: { disabled: false },
    totalPrice: { textContent: '' },
    cartCountBadge: { textContent: '' },
  };
  return createCartManager({
    ui: ui as any,
    escapeHTML: (value: unknown) => String(value),
    findMenuItems: (ids: string[] = []) => ids.map(id => ({ id, name: `Item ${id}`, price: 50 })),
    onCartChange: () => {},
    t: (key: string) => key,
  });
}

describe('public kiosk cart contract', () => {
  beforeEach(() => {
    globalThis.document = { getElementById: () => null } as unknown as Document;
  });

  it('applies bounded assistant actions and exposes a stable total', () => {
    const cart = makeCart();
    expect(cart.applyCartActions([{ action: 'add', id: 'coffee', quantity: 99 }])).toEqual(['Item coffee x10']);
    expect(cart.getCartItems()).toHaveLength(1);
    expect(cart.getCartItems()[0]?.quantity).toBe(10);
    expect(cart.getCartTotal()).toBe(500);
  });

  it('invalidates a server quote when the cart changes', () => {
    const cart = makeCart();
    cart.addToCart({ id: 'coffee', name: 'Coffee', price: 50 });
    cart.applyServerQuote({
      total: 40,
      subtotal: 40,
      option_total: 0,
      discount_total: 0,
      tax_total: 0,
      currency: 'TWD',
      quote_version: 'v1',
      items: [],
    } as any);
    expect(cart.getQuoteState()).toMatchObject({ status: 'ready', total: 40 });
    cart.updateCartQty('coffee', 1);
    expect(cart.getQuoteState().status).toBe('idle');
  });
});
