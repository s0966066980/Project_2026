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
  // 回傳 Promise，在跑馬燈播完並淡出後 resolve。
  function showPushCard(items, reason, ollamaResult, styleKey, styleLabel) {
    if (!isPosActive() || !ui.recommendTicker) return Promise.resolve();
    const itemList = (Array.isArray(items) ? items : [items]).filter(Boolean).slice(0, 3);
    if (!itemList.length) return Promise.resolve();

    clearTicker();

    const names = itemList.map(i => i.name || '').filter(Boolean).join('、');
    const total = itemList.reduce((s, item) => s + Number(item.price || 0), 0);
    const priceText = itemList.length > 1 ? `組合 $${total}` : `$${Number(itemList[0].price || 0)}`;
    const finalText = _extractReason(ollamaResult) || reason || '';
    const scrollText = [names, finalText, priceText].filter(Boolean).join('　·　');

    const bar = document.createElement('div');
    bar.className = 'recommend-ticker-bar';

    // 左側標籤（動態風格文字）
    const label = document.createElement('span');
    label.className = 'recommend-ticker-label';
    label.dataset.style = styleKey || 'popular';
    label.textContent = styleLabel || '⭐ 為您推薦';

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

    // 關閉按鈕
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

    // 回傳 Promise：跑馬燈動畫結束（或逾時）後 resolve
    return new Promise((resolve) => {
      function finish() {
        if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
        clearTicker();
        resolve();
      }

      addBtn.onclick = () => {
        itemList.forEach(item => addToCart(item));
        finish();
      };
      closeBtn.onclick = finish;

      // 動畫播完自動結束（18s）
      scrollEl.addEventListener('animationend', finish, { once: true });
      // 保底逾時（動畫若因隱藏頁面暫停則觸發此）
      dismissTimer = setTimeout(finish, 19500);
    });
  }

  function displayRecommendation(data) {
    const features = getFeatures();
    if (!features.recommend || !isPosActive()) return Promise.resolve();
    const ids = data.recommendation_ids || [];
    if (!ids.length) return Promise.resolve();
    const items = findMenuItems(ids);
    if (!items.length) return Promise.resolve();
    items.forEach(item => sessionPushedIds.add(item.id));
    return showPushCard(
      items,
      data.reason || '',
      data.ollama_result || '',
      data.recommendation_style || 'popular',
      data.recommendation_label || '⭐ 為您推薦',
    );
  }

  return {
    showPushCard,
    clearAllPushCards,
    displayRecommendation,
    showPushNotice,
  };
}
