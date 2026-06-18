// =========================================================
// 猶豫彈窗：被動語音命中關鍵詞時推薦單品（由 app.js 的被動語音流程驅動）。
// =========================================================
import { getMenuVisual, formatItemPrice } from './menu_visuals.js';
import { state } from './state.js';
import { itemMatchesSubFilter, KIOSK_GROUPS, getKioskLang } from './app.js';

export function getChoiceHesitationModal() {
  return document.getElementById('choiceHesitationModal');
}

export function isChoiceHesitationVisible() {
  return !getChoiceHesitationModal()?.classList.contains('hidden');
}

export function hideChoiceHesitationModal(resetIdle = false) {
  const modal = getChoiceHesitationModal();
  modal?.classList.add('hidden');
  modal?.setAttribute('aria-hidden', 'true');
  state.currentChoiceHesitationItem = null;
  state._passiveLastTriggerAt = 0;  // modal 關閉後立即允許下一次被動語音觸發
  if (resetIdle) {
    state.lastCartAddAt = Date.now();
  }
}

export function getChoiceHesitationCandidates() {
  const pricedItems = state.menuData.filter(item => item && item.id && Number(item.price || 0) > 0);
  if (!pricedItems.length) return [];
  if (state.kioskScreen === 'menu') {
    const group = KIOSK_GROUPS.find(row => row.id === state.kioskActiveGroup);
    const allowed = new Set(group?.categories || []);
    let scoped = pricedItems.filter(item => allowed.has(String(item.category || '')));
    if (state.kioskActiveFilter && state.kioskActiveFilter !== '全部') {
      scoped = scoped.filter(item => itemMatchesSubFilter(item, state.kioskActiveFilter));
    }
    if (scoped.length) return scoped;
  }
  const preferredCategories = new Set(['超值全餐', '極選系列', '點心']);
  const preferred = pricedItems.filter(item => preferredCategories.has(String(item.category || '')));
  return preferred.length ? preferred : pricedItems;
}

export function pickChoiceHesitationItem() {
  const candidates = getChoiceHesitationCandidates();
  if (!candidates.length) return null;
  const pool = candidates.length > 1 && state.currentChoiceHesitationItem
    ? candidates.filter(item => item.id !== state.currentChoiceHesitationItem.id)
    : candidates;
  return pool[Math.floor(Math.random() * pool.length)] || candidates[0];
}

export function renderChoiceHesitationItem(item) {
  const modal = getChoiceHesitationModal();
  if (!modal || !item) return;
  const visual = getMenuVisual(item);
  const nameEl = document.getElementById('choiceHesitationName');
  const priceEl = document.getElementById('choiceHesitationPrice');
  const reasonEl = document.getElementById('choiceHesitationReason');
  const imageEl = document.getElementById('choiceHesitationImage');
  const fallbackEl = document.getElementById('choiceHesitationFallback');
  if (nameEl) nameEl.textContent = item.name || '推薦餐點';
  if (priceEl) priceEl.textContent = formatItemPrice(item, getKioskLang());
  if (reasonEl) reasonEl.textContent = item.description || '先試試這份熱門餐點。';
  if (fallbackEl) {
    fallbackEl.textContent = visual.emoji || '🍔';
    fallbackEl.style.display = visual.image ? 'none' : 'block';
  }
  if (imageEl) {
    imageEl.style.display = visual.image ? 'block' : 'none';
    imageEl.src = visual.image || '';
    imageEl.alt = item.name || '推薦餐點';
    imageEl.onerror = () => {
      imageEl.style.display = 'none';
      if (fallbackEl) fallbackEl.style.display = 'block';
    };
  }
}
