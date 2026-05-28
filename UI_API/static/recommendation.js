export function createRecommendationManager({
  ui,
  isPosActive,
  getFeatures,
  findMenuItems,
  addToCart,
  sessionPushedIds,
}) {
  let currentTicker = null;
  let dismissTimer = null;
  let _currentResolve = null;   // 修復：外部 clearTicker 時立即 resolve ticker Promise

  function clearTicker() {
    if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
    // 立即 resolve 任何待中的 ticker Promise，防止 startRecommendLoop 凍結
    const res = _currentResolve;
    _currentResolve = null;
    res?.();
    if (!ui.recommendTicker) return;
    if (currentTicker) {
      currentTicker.classList.add('ticker-fade-out');
      const t = currentTicker;
      currentTicker = null;
      setTimeout(() => { t.remove(); ui.recommendTicker?.replaceChildren(); }, 400);
    } else {
      ui.recommendTicker?.replaceChildren();
    }
  }

  function clearHesitationCard() {
    ui.floatPush?.replaceChildren();
  }

  function clearAllPushCards() {
    clearTicker();
    clearHesitationCard();
  }

  function showPushNotice(text) {
    if (!isPosActive() || !ui.floatPush) return;
    ui.floatPush.replaceChildren();
    const card = document.createElement('div');
    card.className = 'push-card push-notice';
    const p = document.createElement('p');
    p.className = 'push-notice-text';
    p.textContent = text;
    card.appendChild(p);
    ui.floatPush.appendChild(card);
    setTimeout(() => ui.floatPush?.replaceChildren(), 4000);
  }

  // 跑馬燈推薦（#recommendTicker）
  // 回傳 Promise，跑馬燈播完或關閉後 resolve。
  function showPushCard(items, reason) {
    if (!isPosActive() || !ui.recommendTicker) return Promise.resolve();
    const itemList = (Array.isArray(items) ? items : [items]).filter(Boolean).slice(0, 3);
    if (!itemList.length) return Promise.resolve();

    clearTicker();  // 清除前一個（同時 resolve 前一個 Promise）

    const names = itemList.map(i => i.name || '').filter(Boolean).join('、');
    const total = itemList.reduce((s, item) => s + Number(item.price || 0), 0);
    const priceText = itemList.length > 1 ? `組合 $${total}` : `$${Number(itemList[0].price || 0)}`;
    const scrollText = [names, reason, priceText].filter(Boolean).join('　·　');

    const bar = document.createElement('div');
    bar.className = 'recommend-ticker-bar';

    const label = document.createElement('span');
    label.className = 'recommend-ticker-label';
    label.textContent = '⭐ 為您推薦';

    const scrollWrap = document.createElement('div');
    scrollWrap.className = 'recommend-ticker-scroll';
    const scrollEl = document.createElement('span');
    scrollEl.className = 'recommend-ticker-text';
    scrollEl.textContent = scrollText;
    scrollWrap.appendChild(scrollEl);

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'recommend-ticker-add';
    const cartIcon = document.createElement('i');
    cartIcon.className = 'fas fa-cart-plus';
    addBtn.appendChild(cartIcon);
    addBtn.appendChild(document.createTextNode(' 加入'));

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'recommend-ticker-close';
    closeBtn.setAttribute('aria-label', '關閉');
    const closeIcon = document.createElement('i');
    closeIcon.className = 'fas fa-times';
    closeBtn.appendChild(closeIcon);

    bar.append(label, scrollWrap, addBtn, closeBtn);
    ui.recommendTicker.replaceChildren(bar);
    currentTicker = bar;

    return new Promise((resolve) => {
      _currentResolve = resolve;
      function finish() {
        if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
        _currentResolve = null;
        clearTicker();   // 視覺清理（res?.() 因 _currentResolve=null 已是 no-op）
        resolve();
      }
      addBtn.onclick = () => { itemList.forEach(item => addToCart(item)); finish(); };
      closeBtn.onclick = finish;
      scrollEl.addEventListener('animationend', finish, { once: true });
      dismissTimer = setTimeout(finish, 19500); // 保底逾時
    });
  }

  function displayRecommendation(data) {
    if (!getFeatures().recommend || !isPosActive()) return Promise.resolve();
    const ids = data.recommendation_ids || [];
    if (!ids.length) return Promise.resolve();
    const items = findMenuItems(ids);
    if (!items.length) return Promise.resolve();
    items.forEach(item => sessionPushedIds.add(item.id));
    return showPushCard(items, data.reason || '');
  }

  return { showPushCard, clearAllPushCards, clearHesitationCard, displayRecommendation, showPushNotice };
}
