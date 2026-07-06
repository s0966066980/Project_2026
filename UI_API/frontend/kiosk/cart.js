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
    renderCart();
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
    renderCart();
  }

  /** @param {string} id */
  function deleteCartItem(id) {
    delete cart[id];
    renderCart();
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
  function renderCart() {
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
      ui.cartCountBadge.textContent = translateCartText('cartCount', '共 {count} 項').replace('{count}', '0');
      onCartChange?.(getCartItems());
      return;
    }

    ui.checkoutBtn.disabled = false;
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
    ui.totalPrice.textContent = `$${total}`;
    ui.cartCountBadge.textContent = translateCartText('cartCount', '共 {count} 項').replace('{count}', String(quantity));
    onCartChange?.(getCartItems());
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
    return getCartItems().reduce((sum, item) => sum + resolveItemPrice(item) * Number(item.quantity || 0), 0);
  }

  /** @returns {void} */
  function clearCart() {
    Object.keys(cart).forEach(id => { delete cart[id]; });
    renderCart();
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
  };
}
