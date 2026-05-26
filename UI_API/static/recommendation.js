export function createRecommendationManager({
  ui,
  escapeHTML,
  isPosActive,
  getFeatures,
  findMenuItems,
  addToCart,
  sessionPushedIds,
}) {
  let currentCard = null;
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

  function clearPushCard() {
    if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
    if (currentCard) {
      currentCard.classList.add('push-fade-out');
      const card = currentCard;
      currentCard = null;
      setTimeout(() => card.remove(), 400);
    }
    ui.floatPush.replaceChildren();
  }

  function clearAllPushCards() { clearPushCard(); }

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

  function showPushCard(items, reason, ollamaResult) {
    if (!isPosActive()) return;
    const itemList = (Array.isArray(items) ? items : [items]).filter(Boolean).slice(0, 3);
    if (!itemList.length) return;

    clearPushCard();

    const card = document.createElement('div');
    card.className = 'push-card';

    const total = itemList.reduce((s, item) => s + Number(item.price || 0), 0);
    const finalText = _extractReason(ollamaResult) || reason || '';
    const names = itemList.map(i => i.name || '').filter(Boolean).join('、');
    const priceText = itemList.length > 1 ? `組合 $${total}` : `$${Number(itemList[0].price || 0)}`;

    // Header row
    const header = document.createElement('div');
    header.className = 'push-card-header';
    const titleEl = document.createElement('span');
    titleEl.className = 'push-card-title';
    titleEl.textContent = '為您推薦';
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'push-close-btn';
    closeBtn.setAttribute('aria-label', '關閉');
    const closeIcon = document.createElement('i');
    closeIcon.className = 'fas fa-times';
    closeBtn.appendChild(closeIcon);
    closeBtn.onclick = clearPushCard;
    header.appendChild(titleEl);
    header.appendChild(closeBtn);

    const nameEl = document.createElement('div');
    nameEl.className = 'push-item-names';
    nameEl.textContent = names;

    const priceEl = document.createElement('div');
    priceEl.className = 'push-item-price';
    priceEl.textContent = priceText;

    const reasonEl = document.createElement('p');
    reasonEl.className = 'push-reason';
    reasonEl.textContent = finalText;

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'push-add-btn btn-primary';
    const cartIcon = document.createElement('i');
    cartIcon.className = 'fas fa-cart-plus';
    addBtn.appendChild(cartIcon);
    addBtn.appendChild(document.createTextNode(
      itemList.length > 1 ? ` 加入這組 $${total}` : ' 加入購物車'
    ));
    addBtn.onclick = () => {
      itemList.forEach(item => addToCart(item));
      clearPushCard();
    };

    card.appendChild(header);
    card.appendChild(nameEl);
    card.appendChild(priceEl);
    card.appendChild(reasonEl);
    card.appendChild(addBtn);
    ui.floatPush.appendChild(card);
    currentCard = card;

    dismissTimer = setTimeout(clearPushCard, 5000);
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
