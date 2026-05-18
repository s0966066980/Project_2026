export function createCartManager({ ui, escapeHTML, findMenuItems }) {
  const cart = {};

  function addToCart(item) {
    cart[item.id] ? cart[item.id].quantity++ : (cart[item.id] = { ...item, quantity: 1 });
    const card = document.getElementById(`menu-${item.id}`);
    if (card) {
      card.classList.add('selected');
      setTimeout(() => card.classList.remove('selected'), 250);
    }
    renderCart();
  }

  function addToCartByQuantity(item, quantity = 1) {
    const qty = Math.max(1, Math.min(10, Number(quantity) || 1));
    for (let i = 0; i < qty; i++) addToCart(item);
  }

  function updateCartQty(id, delta) {
    if (!cart[id]) return;
    cart[id].quantity += delta;
    if (cart[id].quantity <= 0) delete cart[id];
    renderCart();
  }

  function deleteCartItem(id) {
    delete cart[id];
    renderCart();
  }

  function applyCartActions(actions = []) {
    const applied = [];
    (Array.isArray(actions) ? actions : []).forEach(action => {
      if (!action || action.action !== 'add') return;
      const item = findMenuItems([action.id])[0];
      if (!item) return;
      const qty = Math.max(1, Math.min(10, Number(action.quantity) || 1));
      addToCartByQuantity(item, qty);
      applied.push(`${item.name} x${qty}`);
    });
    return applied;
  }

  function renderCart() {
    const keys = Object.keys(cart);
    if (!keys.length) {
      ui.cartList.innerHTML = `
        <div class="cart-empty">
          <div class="cart-bag"><i class="fas fa-shopping-bag"></i></div>
          <h4 class="text-2xl font-extrabold mt-4" style="color:var(--text)">購物車是空的</h4>
          <p class="text-base" style="color:var(--text2)">快去選擇喜愛的餐點吧！</p>
        </div>`;
      ui.checkoutBtn.disabled = true;
      ui.totalPrice.textContent = '$0';
      ui.cartCountBadge.textContent = '共 0 項';
      return;
    }

    ui.checkoutBtn.disabled = false;
    let total = 0;
    let qty = 0;
    ui.cartList.innerHTML = '';
    keys.forEach(id => {
      const item = cart[id];
      total += item.price * item.quantity;
      qty += item.quantity;
      ui.cartList.innerHTML += `
        <div class="cart-item p-4 flex justify-between items-center">
          <div class="min-w-0 flex-1 mr-2">
            <p class="font-bold text-base truncate" style="color:var(--text)">${escapeHTML(item.name)}</p>
            <p class="text-sm font-extrabold mt-1" style="color:var(--accent)">$${escapeHTML(item.price)}</p>
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
    ui.cartCountBadge.textContent = `共 ${qty} 項`;
  }

  function getCartIds() {
    return Object.keys(cart);
  }

  function getCartItems() {
    return Object.values(cart).map(item => ({ ...item }));
  }

  function getCartTotal() {
    return getCartItems().reduce((sum, item) => sum + Number(item.price || 0) * Number(item.quantity || 0), 0);
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
  };
}
