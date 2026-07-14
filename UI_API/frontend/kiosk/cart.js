// @ts-check

import { resolveItemPrice } from './menuVisuals.js';

/** @typedef {import('../types.d.ts').CartAction} CartAction */
/** @typedef {import('../types.d.ts').CartItem} CartItem */
/** @typedef {import('../types.d.ts').CartManager} CartManager */
/** @typedef {import('../types.d.ts').CartManagerOptions} CartManagerOptions */
/** @typedef {import('../types.d.ts').MenuItem} MenuItem */

/**
 * @param {CartManagerOptions} options
 * @returns {CartManager}
 */
export function createCartManager({ ui, escapeHTML, findMenuItems, onCartChange, t, lang = () => 'zh', getVisual }) {
  /** @type {Record<string, CartItem>} */
  const cart = {};
  /** @type {{ status: "idle" | "pending" | "ready" | "failed", total: number | null, version: string }} */
  let quoteState = { status: 'idle', total: null, version: '' };

  function invalidateQuote() {
    quoteState = { status: 'idle', total: null, version: '' };
  }
  /**
   * @param {string} key
   * @param {string} [fallback]
   * @returns {string}
   */
  const translateCartText = (key, fallback = key) => (typeof t === 'function' ? t(key) : fallback);

  // 購物車品項圖：優先用 item.image，否則依 MCD id 推導本地圖片，最後退回 emoji。
  // 與菜單卡片相同邏輯（getMenuVisual），避免常點／再點一次等未帶 image 的品項變空白。
  /**
   * @param {MenuItem} item
   * @returns {import('../types.d.ts').MenuVisual}
   */
  function resolveVisual(item) {
    if (typeof getVisual === 'function') return getVisual(item);
    const id = String(item.id || '').toUpperCase();
    return {
      image: item.image || (id.startsWith('MCD') ? `/static/menu_images/${id}.jpg` : ''),
      emoji: '🍔',
    };
  }

  /** @param {MenuItem} item */
  function addToCart(item) {
    if (!item.id) return;
    const existingItem = cart[item.id];
    if (existingItem) {
      existingItem.quantity += 1;
      if (item.applied_offer_id) {
        existingItem.price = item.price;
        existingItem.original_price = item.original_price;
        existingItem.applied_offer_id = item.applied_offer_id;
        existingItem.offer_ids = item.offer_ids;
        existingItem.promotion_title = item.promotion_title;
      }
    } else {
      cart[item.id] = { ...item, id: item.id, quantity: 1 };
    }
    const card = document.getElementById(`menu-${item.id}`);
    if (card) {
      card.classList.add('selected');
      setTimeout(() => card.classList.remove('selected'), 250);
    }
    invalidateQuote();
    renderCart('cart_change');
  }

  /**
   * @param {MenuItem} item
   * @param {number} [requestedQuantity]
   */
  function addToCartByQuantity(item, requestedQuantity = 1) {
    const normalizedQuantity = Math.max(1, Math.min(10, Number(requestedQuantity) || 1));
    for (let index = 0; index < normalizedQuantity; index++) addToCart(item);
  }

  /**
   * @param {string} id
   * @param {number} delta
   */
  function updateCartQty(id, delta) {
    const item = cart[id];
    if (!item) return;
    item.quantity += delta;
    if (item.quantity <= 0) delete cart[id];
    invalidateQuote();
    renderCart('cart_change');
  }

  /** @param {string} id */
  function deleteCartItem(id) {
    delete cart[id];
    invalidateQuote();
    renderCart('cart_change');
  }

  /**
   * @param {CartAction[]} [actions]
   * @returns {string[]}
   */
  function applyCartActions(actions = []) {
    /** @type {string[]} */
    const applied = [];
    (Array.isArray(actions) ? actions : []).forEach(action => {
      if (!action || action.action !== 'add') return;
      if (!action.id) return;
      const item = findMenuItems([action.id])[0];
      if (!item) return;
      const quantity = Math.max(1, Math.min(10, Number(action.quantity) || 1));
      addToCartByQuantity(item, quantity);
      applied.push(`${item.name} x${quantity}`);
    });
    return applied;
  }

  /** @returns {void} */
  /** @param {"cart_change" | "quote_applied" | "quote_pending" | "quote_failed"} [reason] */
  function renderCart(reason = 'cart_change') {
    const keys = Object.keys(cart);
    if (!keys.length) {
      ui.cartList.innerHTML = `
        <div class="cart-empty">
          <div class="cart-bag"><i class="fas fa-shopping-bag"></i></div>
          <h4 class="text-2xl font-extrabold mt-4" style="color:var(--text)">${escapeHTML(translateCartText('cartEmptyTitle', '購物車是空的'))}</h4>
          <p class="text-base" style="color:var(--text2)">${escapeHTML(translateCartText('cartEmptySub', '快去選擇喜愛的餐點吧！'))}</p>
        </div>`;
      ui.checkoutBtn.disabled = true;
      ui.totalPrice.textContent = '$0';
      quoteState = { status: 'idle', total: null, version: '' };
      ui.cartCountBadge.textContent = translateCartText('cartCount', '共 {count} 項').replace('{count}', '0');
      onCartChange?.(getCartItems(), reason);
      return;
    }

    ui.checkoutBtn.disabled = quoteState.status !== 'ready';
    let total = 0;
    let quantity = 0;
    ui.cartList.innerHTML = '';
    keys.forEach(id => {
      const item = cart[id];
      if (!item) return;
      const itemPrice = resolveItemPrice(item);
      total += itemPrice * item.quantity;
      quantity += item.quantity;
      const priceLabel = `$${itemPrice}`;
      const originalPrice = Number(item.original_price || 0);
      const promotionNote = item.applied_offer_id
        ? `<span class="cart-promotion-note">${escapeHTML(item.promotion_title || '活動優惠已套用')}</span>`
        : '';
      const originalPriceLabel = item.applied_offer_id && originalPrice > itemPrice
        ? `<span class="cart-original-price">$${originalPrice}</span>`
        : '';
      ui.cartList.innerHTML += `
        <div class="cart-item p-4 flex justify-between items-center">
          <div class="kiosk-cart-product">
            ${(() => { const v = resolveVisual(item); return `
            ${v.image ? `<img src="${escapeHTML(v.image)}" alt="${escapeHTML(item.name)}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">` : ''}
            <span class="cart-photo-fallback" style="display:${v.image ? 'none' : 'flex'}">${escapeHTML(v.emoji || '🍔')}</span>`; })()}
          </div>
          <div class="min-w-0 flex-1 mr-2">
            <p class="font-bold text-base truncate" style="color:var(--text)">${escapeHTML(item.name)}</p>
            <p class="text-sm font-extrabold mt-1" style="color:var(--accent)">${originalPriceLabel}${escapeHTML(priceLabel)}</p>
            ${promotionNote}
          </div>
          <div class="flex items-center gap-1.5">
            <div class="flex items-center rounded-xl border px-1 h-9" style="background:var(--surface2);border-color:var(--border)">
              <button onclick="updateCartQty('${id}',-1)" class="w-7 font-bold text-lg leading-none" style="color:var(--text2)">-</button>
              <span class="w-6 text-center text-sm font-bold" style="color:var(--text)">${item.quantity}</span>
              <button onclick="updateCartQty('${id}',1)" class="w-7 font-bold text-lg leading-none" style="color:var(--text2)">+</button>
            </div>
            <button onclick="deleteCartItem('${id}')" class="w-8 h-8 flex items-center justify-center rounded-xl text-xs" style="color:var(--border)" onmouseover="this.style.color='var(--accent)'" onmouseout="this.style.color='var(--border)'"><i class="fas fa-trash"></i></button>
          </div>
        </div>`;
    });
    const quotedTotal = quoteState.status === 'ready' && quoteState.total !== null ? quoteState.total : total;
    ui.totalPrice.textContent = quoteState.status === 'pending'
      ? '價格確認中'
      : (quoteState.status === 'failed' ? '請重新確認價格' : `$${quotedTotal}`);
    ui.cartCountBadge.textContent = translateCartText('cartCount', '共 {count} 項').replace('{count}', String(quantity));
    onCartChange?.(getCartItems(), reason);
  }

  /** @returns {string[]} */
  function getCartIds() {
    return Object.keys(cart);
  }

  /** @returns {CartItem[]} */
  function getCartItems() {
    return Object.values(cart).map(item => ({ ...item }));
  }

  /** @returns {number} */
  function getCartTotal() {
    if (quoteState.status === 'ready' && quoteState.total !== null) return quoteState.total;
    return getCartItems().reduce((sum, item) => sum + resolveItemPrice(item) * Number(item.quantity || 0), 0);
  }

  function markQuotePending() {
    if (!Object.keys(cart).length) return;
    quoteState = { status: 'pending', total: null, version: '' };
    renderCart('quote_pending');
  }

  function markQuoteFailed() {
    if (!Object.keys(cart).length) return;
    quoteState = { status: 'failed', total: null, version: '' };
    renderCart('quote_failed');
  }

  /** @param {import('../types.d.ts').CartQuote} quote */
  function applyServerQuote(quote) {
    (quote.items || []).forEach(line => {
      const item = cart[line.item_id];
      if (!item) return;
      item.price = line.effective_unit_price;
      item.effective_price = line.effective_unit_price;
      item.base_price = line.base_unit_price;
      item.original_price = line.discount_unit_total > 0 ? line.base_unit_price : undefined;
      item.discount = line.discount_unit_total;
      item.applied_offer_id = line.activity_id || undefined;
      item.promotion_title = line.activity_name || undefined;
      item.offer_ids = line.activity_id ? [line.activity_id] : undefined;
    });
    quoteState = {
      status: 'ready',
      total: Number(quote.total || 0),
      version: String(quote.quote_version || ''),
    };
    renderCart('quote_applied');
  }

  function getQuoteState() {
    return { ...quoteState };
  }

  /** @returns {void} */
  function clearCart() {
    Object.keys(cart).forEach(id => { delete cart[id]; });
    invalidateQuote();
    renderCart('cart_change');
  }

  return {
    addToCart,
    addToCartByQuantity,
    updateCartQty,
    deleteCartItem,
    applyCartActions,
    renderCart,
    getCartIds,
    getCartItems,
    getCartTotal,
    clearCart,
    markQuotePending,
    markQuoteFailed,
    applyServerQuote,
    getQuoteState,
  };
}
