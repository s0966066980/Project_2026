// @ts-check

/** @typedef {import('../types.d.ts').MenuItem} MenuItem */

function asIds(value) {
  return Array.isArray(value) ? value.map(id => String(id || '').trim()).filter(Boolean) : [];
}

function itemVisual(item) {
  const id = String(item?.id || '').toUpperCase();
  return {
    image: String(item?.image || (id.startsWith('MCD') ? `/static/menu_images/${id}.jpg` : '')),
    emoji: String(item?.emoji || '🍔'),
  };
}

function money(value) {
  const amount = Number(value || 0);
  return Number.isFinite(amount) ? `$${amount}` : '$0';
}

export function createVoiceOrderDraftController({ getMenuItems, cartManager, escapeHTML, onConfirmed, onCancelled }) {
  const modal = document.getElementById('voiceOrderDraftModal');
  const itemsRoot = document.getElementById('voiceOrderDraftItems');
  const clarificationSection = document.getElementById('voiceOrderClarificationSection');
  const clarificationRoot = document.getElementById('voiceOrderClarificationItems');
  const recommendationSection = document.getElementById('voiceOrderRecommendationSection');
  const recommendationRoot = document.getElementById('voiceOrderRecommendationItems');
  const status = document.getElementById('voiceOrderDraftStatus');
  const confirm = document.getElementById('voiceOrderDraftConfirm');
  const draft = new Map();
  let clarificationIds = [];
  let recommendationIds = [];

  const menuItem = id => getMenuItems().find(item => String(item.id) === String(id));

  function renderProduct(item, mode = 'draft') {
    const visual = itemVisual(item);
    const row = draft.get(String(item.id));
    if (mode === 'draft') {
      const subtotal = Number(item.price || 0) * Number(row?.quantity || 1);
      return `<article class="voice-order-draft-item" data-draft-id="${escapeHTML(item.id)}">
        <label class="voice-order-draft-check">
          <input type="checkbox" data-draft-select ${row?.selected ? 'checked' : ''}>
          <span aria-hidden="true"><i class="fas fa-check"></i></span>
          <span class="sr-only">選取 ${escapeHTML(item.name || item.id)}</span>
        </label>
        <div class="voice-order-draft-photo">
          ${visual.image ? `<img src="${escapeHTML(visual.image)}" alt="${escapeHTML(item.name || '')}" onerror="this.hidden=true;this.nextElementSibling.hidden=false">` : ''}
          <span ${visual.image ? 'hidden' : ''}>${escapeHTML(visual.emoji)}</span>
        </div>
        <div class="voice-order-draft-info">
          <h3>${escapeHTML(item.name || item.id)}</h3>
          <p>${escapeHTML(item.description || item.category || '')}</p>
          <strong>${money(item.price)}／份</strong>
        </div>
        <div class="voice-order-draft-qty" aria-label="數量">
          <button type="button" data-draft-qty="-1" aria-label="減少數量">−</button>
          <b>${row?.quantity || 1}</b>
          <button type="button" data-draft-qty="1" aria-label="增加數量">＋</button>
        </div>
        <strong class="voice-order-draft-subtotal">${money(subtotal)}</strong>
        <button class="voice-order-draft-remove" type="button" data-draft-remove aria-label="移除 ${escapeHTML(item.name || item.id)}"><i class="fas fa-trash"></i></button>
      </article>`;
    }
    return `<button class="voice-order-draft-suggestion" type="button" data-${mode}-id="${escapeHTML(item.id)}">
      <span class="voice-order-draft-suggestion-photo">
        ${visual.image ? `<img src="${escapeHTML(visual.image)}" alt="" onerror="this.hidden=true;this.nextElementSibling.hidden=false">` : ''}
        <span ${visual.image ? 'hidden' : ''}>${escapeHTML(visual.emoji)}</span>
      </span>
      <span><b>${escapeHTML(item.name || item.id)}</b><small>${money(item.price)}</small></span>
      <i class="fas fa-plus"></i>
    </button>`;
  }

  function render() {
    const rows = [...draft.values()].map(row => menuItem(row.id)).filter(Boolean);
    itemsRoot.innerHTML = rows.length
      ? rows.map(item => renderProduct(item)).join('')
      : '<div class="voice-order-draft-empty">尚未選擇餐點，請從下方相近選項挑選。</div>';

    const clarifications = clarificationIds.map(menuItem).filter(item => item && !draft.has(String(item.id)));
    clarificationSection.classList.toggle('hidden', !clarifications.length);
    clarificationRoot.innerHTML = clarifications.map(item => renderProduct(item, 'clarification')).join('');

    const recommendations = recommendationIds.map(menuItem).filter(item => item && !draft.has(String(item.id)));
    recommendationSection.classList.toggle('hidden', !recommendations.length);
    recommendationRoot.innerHTML = recommendations.map(item => renderProduct(item, 'recommendation')).join('');
    const selectedCount = [...draft.values()].filter(row => row.selected).length;
    confirm.disabled = selectedCount === 0;
    confirm.innerHTML = `<i class="fas fa-cart-plus"></i> 確認加入購物車${selectedCount ? `（${selectedCount} 項）` : ''}`;
  }

  function close(reason = 'cancelled') {
    modal?.classList.add('hidden');
    modal?.setAttribute('aria-hidden', 'true');
    draft.clear();
    clarificationIds = [];
    recommendationIds = [];
    if (reason === 'cancelled') onCancelled?.();
  }

  function show(orderDraft) {
    draft.clear();
    (Array.isArray(orderDraft?.items) ? orderDraft.items : []).forEach(row => {
      const id = String(row?.id || '');
      if (!menuItem(id)) return;
      draft.set(id, { id, quantity: Math.max(1, Math.min(10, Number(row.quantity) || 1)), selected: false });
    });
    clarificationIds = asIds(orderDraft?.clarification_ids);
    recommendationIds = asIds(orderDraft?.recommendation_ids);
    if (!draft.size && !clarificationIds.length) return false;
    if (status) status.textContent = '';
    render();
    modal?.classList.remove('hidden');
    modal?.setAttribute('aria-hidden', 'false');
    return true;
  }

  modal?.addEventListener('click', event => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    if (target.closest('[data-voice-draft-cancel]')) return close('cancelled');
    const rowElement = target.closest('[data-draft-id]');
    const id = rowElement?.getAttribute('data-draft-id') || '';
    const row = draft.get(id);
    if (row && target.closest('[data-draft-qty]')) {
      row.quantity = Math.max(1, Math.min(10, row.quantity + Number(target.closest('[data-draft-qty]').getAttribute('data-draft-qty') || 0)));
      return render();
    }
    if (row && target.closest('[data-draft-remove]')) {
      draft.delete(id);
      return render();
    }
    const clarification = target.closest('[data-clarification-id]')?.getAttribute('data-clarification-id');
    if (clarification && menuItem(clarification)) {
      draft.set(clarification, { id: clarification, quantity: 1, selected: true });
      clarificationIds = [];
      return render();
    }
    const recommendation = target.closest('[data-recommendation-id]')?.getAttribute('data-recommendation-id');
    if (recommendation && menuItem(recommendation)) {
      draft.set(recommendation, { id: recommendation, quantity: 1, selected: false });
      return render();
    }
  });

  modal?.addEventListener('change', event => {
    const target = event.target instanceof HTMLInputElement ? event.target : null;
    if (!target?.matches('[data-draft-select]')) return;
    const id = target.closest('[data-draft-id]')?.getAttribute('data-draft-id') || '';
    const row = draft.get(id);
    if (!row) return;
    row.selected = target.checked;
    if (status) status.textContent = '';
    render();
  });

  confirm?.addEventListener('click', () => {
    const actions = [...draft.values()].filter(row => row.selected).map(row => ({ action: 'add', id: row.id, quantity: row.quantity }));
    if (!actions.length) {
      if (status) status.textContent = '請先勾選至少一項餐點。';
      return;
    }
    const applied = cartManager.applyCartActions(actions);
    onConfirmed?.(actions, applied);
    close('confirmed');
  });

  return { show, close, hasPending: () => Boolean(draft.size && !modal?.classList.contains('hidden')) };
}
