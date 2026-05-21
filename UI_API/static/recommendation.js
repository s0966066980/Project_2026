function pushItemNames(items = []) {
  return (Array.isArray(items) ? items : [items])
    .filter(Boolean)
    .map(item => item.name)
    .filter(Boolean)
    .join('、');
}

function extractOllamaDescription(ollamaResult = '', variant = '') {
  const clean = (text) => String(text || '')
    .replace(/^(推薦理由|搭配建議|A\s*版|B\s*版|AI\s*推薦)\s*[:：\-]?\s*/i, '')
    .replace(/["{}[\]]/g, '')
    .trim();
  if (!ollamaResult) return '';
  try {
    const parsed = JSON.parse(ollamaResult);
    if (variant === 'A' && parsed.variant_a) return clean(parsed.variant_a.reason || parsed.variant_a.description || '');
    if (variant === 'B' && parsed.variant_b) return clean(parsed.variant_b.reason || parsed.variant_b.description || '');
    return clean(parsed.reason || parsed.description || parsed.ai_response || '');
  } catch {
    return clean(ollamaResult);
  }
}

export function createRecommendationManager({
  ui,
  escapeHTML,
  isPosActive,
  getFeatures,
  findMenuItems,
  addToCart,
  sessionPushedIds,
  sessionPushedVariants,
}) {
  let currentPushCards = [];

  function clearAllPushCards() {
    ui.floatPush.innerHTML = '';
    ui.floatPush.classList.remove('ab-mode');
    currentPushCards = [];
  }

  function showPushNotice(text) {
    if (!isPosActive()) return;
    const card = document.createElement('div');
    card.className = 'push-card';
    card.innerHTML = `<p class="text-[15px] leading-relaxed font-semibold" style="color:var(--text)">${escapeHTML(text)}</p>`;
    ui.floatPush.appendChild(card);
    setTimeout(() => {
      card.classList.add('fade-out');
      setTimeout(() => card.remove(), 1800);
    }, 2600);
  }

  function showPushCard(items, reason, variant = '', ollamaResult = '') {
    if (!isPosActive()) return;
    const itemList = (Array.isArray(items) ? items : [items]).filter(Boolean).slice(0, 3);
    if (!itemList.length) return;

    const card = document.createElement('div');
    card.className = 'push-card';

    const total = itemList.reduce((sum, item) => sum + Number(item.price || 0), 0);
    const finalText = extractOllamaDescription(ollamaResult, variant) || reason;
    const itemNames = pushItemNames(itemList);
    const priceText = itemList.length > 1
      ? `組合 $${total}`
      : `$${Number(itemList[0].price || 0)}`;

    card.innerHTML = `
      <div class="flex items-center justify-end mb-2">
        <button type="button" data-close-push style="color:var(--text2)" class="text-xs opacity-60 hover:opacity-100"><i class="fas fa-times"></i></button>
      </div>
      <div class="push-items">${escapeHTML(itemNames)}</div>
      <div class="push-price">${escapeHTML(priceText)}</div>
      <p class="push-message">${escapeHTML(finalText)}</p>
      <button type="button" data-add-push class="btn-primary w-full py-2 text-sm rounded-xl">
        <i class="fas fa-cart-plus mr-1"></i> ${itemList.length > 1 ? `加入這組 $${total}` : '加入購物車'}
      </button>`;
    card.querySelector('[data-close-push]').onclick = () => card.classList.add('fade-out');
    card.querySelector('[data-add-push]').onclick = () => {
      itemList.forEach(addToCart);
      card.classList.add('fade-out');
    };

    ui.floatPush.appendChild(card);
    currentPushCards.push(card);

    setTimeout(() => {
      card.classList.add('fade-out');
      setTimeout(() => {
        card.remove();
        currentPushCards = currentPushCards.filter(existing => existing !== card);
      }, 1800);
    }, 9000);
  }

  function displayRecommendation(data) {
    const features = getFeatures();
    if (!features.recommend || !isPosActive()) return;

    if (features.abTest && data.mode === 'ab') {
      clearAllPushCards();
      ui.floatPush.classList.add('ab-mode');
      const parseCard = (variantData) => {
        const ids = variantData.recommendation_ids || [];
        if (!ids.length || variantData.error) return;
        const items = findMenuItems(ids);
        if (items.length) {
          showPushCard(items, variantData.reason, variantData.variant, variantData.ollama_result || '');
          items.forEach(item => {
            sessionPushedIds.add(item.id);
            if (variantData.variant === 'A' || variantData.variant === 'B') {
              sessionPushedVariants[variantData.variant].add(item.id);
            }
          });
        }
      };
      parseCard(data.variant_a);
      parseCard(data.variant_b);
      return;
    }

    const ids = data.recommendation_ids || [];
    if (!ids.length) return;
    const items = findMenuItems(ids);
    if (!items.length) return;
    clearAllPushCards();
    showPushCard(items, data.reason, data.variant || '', data.ollama_result || '');
    items.forEach(item => {
      sessionPushedIds.add(item.id);
      const variantKey = data.variant === 'A' || data.variant === 'B' ? data.variant : 'single';
      sessionPushedVariants[variantKey].add(item.id);
    });
  }

  return {
    showPushCard,
    clearAllPushCards,
    displayRecommendation,
    showPushNotice,
  };
}
