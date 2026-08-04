import { afterEach, describe, expect, it, vi } from 'vitest';

import { createCartManager } from '../../kiosk/cart.js';

function element() {
  return { innerHTML: '', textContent: '', disabled: false };
}

describe('Kiosk server quote', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('disables checkout while pending and applies the authoritative total', () => {
    vi.stubGlobal('document', { getElementById: () => null });
    const ui = {
      cartList: element(),
      checkoutBtn: element(),
      totalPrice: element(),
      cartCountBadge: element(),
    } as any;
    const manager = createCartManager({
      ui,
      escapeHTML: String,
      findMenuItems: () => [],
      getVisual: () => ({ image: '', emoji: '' }),
    });

    manager.addToCart({ id: 'fries', name: '薯條', price: 45 });
    manager.markQuotePending();
    expect(ui.checkoutBtn.disabled).toBe(true);
    expect(ui.totalPrice.textContent).toBe('價格確認中');

    manager.applyServerQuote({
      items: [{
        item_id: 'fries',
        name: '薯條',
        category: '點心',
        quantity: 1,
        base_unit_price: 45,
        effective_unit_price: 30,
        option_unit_total: 0,
        discount_unit_total: 15,
        activity_id: 'meal-fries',
        activity_name: '套餐加購薯條',
      }],
      subtotal: 45,
      option_total: 0,
      discount_total: 15,
      tax_total: 0,
      total: 30,
      currency: 'TWD',
      quote_version: 'checkout-v1',
    });

    expect(manager.getCartTotal()).toBe(30);
    expect(manager.getCartItems()[0]).toMatchObject({
      price: 30,
      original_price: 45,
      applied_offer_id: 'meal-fries',
    });
    expect(ui.checkoutBtn.disabled).toBe(false);
  });
});
