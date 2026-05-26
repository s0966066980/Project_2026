export function createRecommendationManager({
  ui,
  escapeHTML,
  isPosActive,
  getFeatures,
  findMenuItems,
  addToCart,
  sessionPushedIds,
}) {
  let currentCard = null;   // scenario card in #floatPush
  let currentTicker = null; // ticker bar in #recommendTicker
  let dismissTimer = null;

  function _extractReason(ollamaResult) {
    const clean = (t) => String(t || '')
      .replace(/^(推薦理由|搭配建議|AI\s*推薦)\s*[:：\-]?\s*/i, '')
      .replace(/["{}[\]]/g, '')
      .trim();
    if (!ollamaResult) return '';
    try {
      const parsed = JSON.parse(ollamaResult);
      return clean(parsed.reason || parsed.description || parsed.ai_response || '');
    } catch {
      return clean(ollamaResult);
    }
  }

  // ── 清除 scenario 卡片（#floatPush）──
  function clearPushCard() {
    if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
    if (currentCard) {
      currentCard.classList.add('push-fade-out');
      const c = currentCard;
      currentCard = null;
      setTimeout(() => c.remove(), 400);
    }
    ui.floatPush.replaceChildren();
  }

  // ── 清除跑馬燈（#recommendTicker）──
  function clearTicker() {
    if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
    if (!ui.recommendTicker) return;
    if (currentTicker) {
      currentTicker.classList.add('ticker-fade-out');
      const t = currentTicker;
      currentTicker = null;
      setTimeout(() => { t.remove(); ui.recommendTicker.replaceChildren(); }, 400);
    } else {
      ui.recommendTicker.replaceChildren();
    }
  }

  // ── 清除所有推播（scenario + ticker）──
  function clearAllPushCards() {
    clearPushCard();
    clearTicker();
  }

  // ── 通知訊息（#floatPush 小提示）──
  function showPushNotice(text) {
    if (!isPosActive()) return;
    clearPushCard();
    const card = document.createElement('div');
    card.className = 'push-card push-notice';
    const p = document.createElement('p');
    p.className = 'push-notice-text';
    p.textContent = text;
    card.appendChild(p);
    ui.floatPush.appendChild(card);
    currentCard = card;
    dismissTimer = setTimeout(clearPushCard, 4000);
  }

  // ── 為您推薦跑馬燈（#recommendTicker）──
  function showPushCard(items, reason, ollamaResult) {
    if (!isPosActive() || !ui.recommendTicker) return;
    const itemList = (Array.isArray(items) ? items : [items]).filter(Boolean).slice(0, 3);
    if (!itemList.length) return;

    clearTicker();  // 清舊跑馬燈

    const names = itemList.map(i => i.name || '').filter(Boolean).join('、');
    const total = itemList.reduce((s, item) => s + Number(item.price || 0), 0);
    const priceText = itemList.length > 1 ? `組合 $${total}` : `$${Number(itemList[0].price || 0)}`;
    const finalText = _extractReason(ollamaResult) || reason || '';
    // 跑馬燈文字：「品名　推薦理由　價格」，空白用全形空格分隔
    const scrollText = [names, finalText, priceText].filter(Boolean).join('　·　');

    const bar = document.createElement('div');
    bar.className = 'recommend-ticker-bar';

    // 左側標籤
    const label = document.createElement('span');
    label.className = 'recommend-ticker-label';
    const icon = document.createElement('i');
    icon.className = 'fas fa-star';
    label.appendChild(icon);
    label.appendChild(document.createTextNode(' 為您推薦'));

    // 滾動文字區
    const scrollWrap = document.createElement('div');
    scrollWrap.className = 'recommend-ticker-scroll';
    const scrollEl = document.createElement('span');
    scrollEl.className = 'recommend-ticker-text';
    scrollEl.textContent = scrollText;
    scrollWrap.appendChild(scrollEl);

    // 加入按鈕
    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'recommend-ticker-add';
    const cartIcon = document.createElement('i');
    cartIcon.className = 'fas fa-cart-plus';
    addBtn.appendChild(cartIcon);
    addBtn.appendChild(document.createTextNode(' 加入'));
    addBtn.onclick = () => {
      itemList.forEach(item => addToCart(item));
      clearTicker();
    };

    // 關閉按鈕
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'recommend-ticker-close';
    closeBtn.setAttribute('aria-label', '關閉');
    const closeIcon = document.createElement('i');
    closeIcon.className = 'fas fa-times';
    closeBtn.appendChild(closeIcon);
    closeBtn.onclick = clearTicker;

    bar.append(label, scrollWrap, addBtn, closeBtn);
    ui.recommendTicker.replaceChildren(bar);
    currentTicker = bar;

    dismissTimer = setTimeout(clearTicker, 8000);
  }

  function displayRecommendation(data) {
    const features = getFeatures();
    if (!features.recommend || !isPosActive()) return;
    const ids = data.recommendation_ids || [];
    if (!ids.length) return;
    const items = findMenuItems(ids);
    if (!items.length) return;
    showPushCard(items, data.reason || '', data.ollama_result || '');
    items.forEach(item => sessionPushedIds.add(item.id));
  }

  return {
    showPushCard,
    clearAllPushCards,
    displayRecommendation,
    showPushNotice,
  };
}
