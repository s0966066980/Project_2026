// @ts-check

/** @typedef {import('../../types.d.ts').MenuItem} MenuItem */

/**
 * @typedef {object} KioskGroup
 * @property {string} id
 * @property {string} label
 * @property {string} labelEn
 * @property {string} image
 * @property {string[]} categories
 * @property {number} [featuredLimit]
 */

/**
 * @typedef {object} KioskMenuControllerOptions
 * @property {{ getMenu: () => Promise<MenuItem[]> }} api
 * @property {{ menuData: MenuItem[], kioskScreen: string, kioskActiveGroup: string, kioskActiveFilter: string }} state
 * @property {{
 *   menuGrid: HTMLElement,
 *   kioskTitle?: HTMLElement | null,
 *   kioskSubtitle?: HTMLElement | null,
 *   kioskBackBtn?: HTMLElement | null,
 *   kioskSearchBtn?: HTMLElement | null,
 *   kioskSectionHead?: HTMLElement | null
 * }} ui
 * @property {(value: unknown) => string} escapeHTML
 * @property {(item: MenuItem) => { image: string, emoji: string }} getMenuVisual
 * @property {(item: MenuItem, lang?: string) => string} formatItemPrice
 * @property {KioskGroup[]} groups
 * @property {() => string} getLanguage
 * @property {(key: string) => string} translate
 * @property {(filter: string) => string} translateFilter
 * @property {(group: KioskGroup) => string} translateGroup
 * @property {(item: MenuItem, source?: string) => void} showItemConfirmModal
 * @property {() => Record<string, unknown> | null} [getActivePromotionOffer]
 * @property {(offer: Record<string, unknown>) => void} [onPromotionPick]
 * @property {() => void} updateKioskCartSummary
 * @property {(groupId: string, filter: string) => void} onCategorySwitchRepeat
 */

/**
 * Owns Kiosk menu loading, category navigation, filtering, and DOM rendering.
 * The main app passes dependencies in so this controller stays reusable and easy to test.
 *
 * @param {KioskMenuControllerOptions} options
 */
export function createKioskMenuController({
  api,
  state,
  ui,
  escapeHTML,
  getMenuVisual,
  formatItemPrice,
  groups,
  getLanguage,
  translate,
  translateFilter,
  translateGroup,
  showItemConfirmModal,
  getActivePromotionOffer,
  onPromotionPick,
  updateKioskCartSummary,
  onCategorySwitchRepeat,
}) {
  /** @type {Promise<MenuItem[]> | null} */
  let menuLoadPromise = null;
  let hasLoadedRemoteMenu = false;

  async function loadMenu() {
    if (hasLoadedRemoteMenu && state.menuData.length) {
      renderMenu();
      return;
    }
    if (menuLoadPromise) {
      await menuLoadPromise;
      renderMenu();
      return;
    }
    try {
      menuLoadPromise = api.getMenu();
      state.menuData = await menuLoadPromise;
      hasLoadedRemoteMenu = true;
    } catch {
      hasLoadedRemoteMenu = false;
      state.menuData = [
        { id: 'MCD001', name: '測試大麥克', price: 100, category: '超值全餐', description: '後端未連線，這是預設測試資料。' },
        { id: 'MCD002', name: '測試薯條', price: 60, category: '點心', description: '請確認 http://127.0.0.1:9000 已啟動。' },
      ];
    } finally {
      menuLoadPromise = null;
    }
    renderMenu();
  }

  function renderMenu() {
    if (state.kioskScreen === 'categories') {
      renderKioskCategories();
      return;
    }
    renderKioskMenuItems();
  }

  function renderKioskCategories() {
    state.kioskScreen = 'categories';
    document.getElementById('view-kiosk')?.classList.remove('kiosk-screen-menu');
    document.getElementById('view-kiosk')?.classList.add('kiosk-screen-categories');
    state.kioskActiveGroup = '';
    state.kioskActiveFilter = '全部';
    ui.menuGrid.innerHTML = '';
    ui.menuGrid.className = 'kiosk-category-grid';
    if (ui.kioskTitle) ui.kioskTitle.textContent = '';
    if (ui.kioskSubtitle) ui.kioskSubtitle.textContent = translate('chooseCategorySub');
    document.getElementById('kioskLogo')?.classList.remove('hidden');
    document.getElementById('kioskLangBtn')?.classList.remove('hidden');
    ui.kioskBackBtn?.classList.add('hidden');
    ui.kioskSearchBtn?.classList.add('hidden');
    ui.kioskSectionHead?.classList.add('hidden');

    const heading = document.createElement('div');
    heading.className = 'kiosk-category-heading';
    heading.textContent = translate('chooseCategory');
    const fragment = document.createDocumentFragment();
    fragment.appendChild(heading);

    groups.forEach(group => {
      const card = document.createElement('button');
      card.className = 'kiosk-category-card';
      card.type = 'button';
      card.onclick = () => showMenuGroup(group.id);
      card.innerHTML = `
        <img src="${group.image}" alt="${escapeHTML(translateGroup(group))}" onerror="this.style.display='none'">
        <strong>${escapeHTML(translateGroup(group))}</strong>`;
      fragment.appendChild(card);
    });
    ui.menuGrid.appendChild(fragment);
    updateKioskCartSummary();
  }

  /**
   * @param {string} groupId
   * @param {string} [filter]
   */
  function showMenuGroup(groupId, filter = '全部') {
    const switchingInMenu = state.kioskScreen === 'menu' && (state.kioskActiveGroup !== groupId || state.kioskActiveFilter !== filter);
    state.kioskScreen = 'menu';
    state.kioskActiveGroup = groupId;
    state.kioskActiveFilter = filter;
    if (switchingInMenu) {
      onCategorySwitchRepeat(groupId, filter);
    }
    renderMenu();
  }

  /**
   * @param {string} groupId
   * @returns {MenuItem[]}
   */
  function groupItems(groupId) {
    const group = groups.find(candidate => candidate.id === groupId) || groups[1] || groups[0];
    if (!group) return [];
    const allowed = new Set((group.categories || []).map(String));
    const items = state.menuData.filter(item => allowed.has(String(item.category || '')));
    return group.featuredLimit ? items.slice(0, group.featuredLimit) : items;
  }

  /**
   * @param {MenuItem} item
   * @param {string} filter
   * @returns {boolean}
   */
  function itemMatchesSubFilter(item, filter) {
    if (!filter || filter === '全部') return true;
    const name = String(item.name || '').replace(/鷄/g, '雞');
    if (filter === '牛肉系列') return /牛|安格斯|大麥克|吉事|四盎司/.test(name);
    if (filter === '雞肉系列') return /雞|脆|辣/.test(name);
    if (filter === '魚肉系列') return /魚/.test(name);
    if (filter === '安格斯系列') return /安格斯/.test(name);
    if (filter === '早餐系列') return String(item.category || '') === '早餐' || /滿福|鬆餅|薯餅/.test(name);
    if (filter === '點心飲料') return /薯|派|湯|茶|可樂|咖啡|那堤|奶茶/.test(name);
    return true;
  }

  /**
   * @param {string} groupId
   * @returns {string[]}
   */
  function subFiltersForGroup(groupId) {
    if (groupId === 'value' || groupId === 'recommended') return ['全部', '牛肉系列', '雞肉系列', '魚肉系列'];
    if (groupId === 'premium') return ['全部', '安格斯系列', '雞肉系列'];
    if (groupId === 'single' || groupId === 'drinks') return ['全部', '點心飲料'];
    if (groupId === 'breakfast') return ['全部', '早餐系列'];
    return ['全部'];
  }

  function renderKioskMenuItems() {
    document.getElementById('view-kiosk')?.classList.remove('kiosk-screen-categories');
    document.getElementById('view-kiosk')?.classList.add('kiosk-screen-menu');
    const group = groups.find(candidate => candidate.id === state.kioskActiveGroup) || groups[1] || groups[0];
    if (!group) return;
    const filters = subFiltersForGroup(group.id);
    const items = groupItems(group.id).filter(item => itemMatchesSubFilter(item, state.kioskActiveFilter));
    ui.menuGrid.innerHTML = '';
    ui.menuGrid.className = 'kiosk-menu-list';
    if (ui.kioskTitle) ui.kioskTitle.textContent = translateGroup(group);
    if (ui.kioskSubtitle) ui.kioskSubtitle.textContent = translate('addHint');
    document.getElementById('kioskLogo')?.classList.add('hidden');
    document.getElementById('kioskLangBtn')?.classList.add('hidden');
    ui.kioskBackBtn?.classList.remove('hidden');
    ui.kioskSearchBtn?.classList.remove('hidden');
    ui.kioskSectionHead?.classList.add('hidden');

    const tabs = document.createElement('div');
    tabs.className = 'kiosk-menu-tabs';
    tabs.innerHTML = filters.map(filter => `
      <button type="button" class="${filter === state.kioskActiveFilter ? 'active' : ''}" data-filter="${escapeHTML(filter)}">
        ${escapeHTML(translateFilter(filter))}
      </button>`).join('');
    tabs.querySelectorAll('button').forEach(button => {
      button.addEventListener('click', () => showMenuGroup(group.id, button.dataset.filter || '全部'));
    });
    const fragment = document.createDocumentFragment();
    fragment.appendChild(tabs);

    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'kiosk-empty-menu';
      empty.textContent = translate('emptyCategory');
      fragment.appendChild(empty);
      ui.menuGrid.appendChild(fragment);
      return;
    }

    const activeOffer = typeof getActivePromotionOffer === 'function' ? getActivePromotionOffer() : null;
    if (activeOffer && Number(activeOffer?.pricing?.promotion_price || 0) > 0) {
      const firstItemId = Array.isArray(activeOffer.item_ids) ? activeOffer.item_ids[0] : '';
      const offerItem = items.find(item => item.id === firstItemId) || items.find(item => activeOffer.categories?.includes?.(item.category));
      if (offerItem) {
        const visual = getMenuVisual(offerItem);
        const ad = activeOffer.ad || {};
        const pricing = activeOffer.pricing || {};
        const promotionPrice = Number(pricing.promotion_price || 0);
        const originalPrice = Number(pricing.original_price || offerItem.price || 0);
        const card = document.createElement('div');
        card.className = 'kiosk-menu-row kiosk-promotion-card';
        card.innerHTML = `
          <div class="kiosk-menu-photo">
            <img src="${visual.image}" alt="${escapeHTML(offerItem.name)}" onerror="this.style.display='none';this.nextElementSibling.style.display='block'">
            <span class="menu-photo-fallback">${visual.emoji}</span>
          </div>
          <div class="kiosk-menu-copy">
            <span class="kiosk-promotion-badge">${escapeHTML(ad.headline || (activeOffer.member_only ? '會員限定' : '活動優惠'))}</span>
            <h3>${escapeHTML(ad.copy || activeOffer.title || offerItem.name)}</h3>
            <strong><span class="kiosk-promotion-original">$${originalPrice}</span> $${promotionPrice}</strong>
          </div>
          <button class="kiosk-add-btn" type="button" aria-label="${escapeHTML(ad.cta || translate('addToCart'))}">${escapeHTML(ad.cta || '加入優惠')}</button>`;
        card.querySelector('.kiosk-add-btn')?.addEventListener('click', event => {
          event.stopPropagation();
          if (typeof onPromotionPick === 'function') onPromotionPick(activeOffer);
          else showItemConfirmModal(offerItem);
        });
        card.addEventListener('click', () => {
          if (typeof onPromotionPick === 'function') onPromotionPick(activeOffer);
          else showItemConfirmModal(offerItem);
        });
        fragment.appendChild(card);
      }
    }

    items.forEach(item => {
      const visual = getMenuVisual(item);
      const row = document.createElement('div');
      row.id = `menu-${item.id}`;
      row.className = 'kiosk-menu-row';
      row.innerHTML = `
        <div class="kiosk-menu-photo">
          <img src="${visual.image}" alt="${escapeHTML(item.name)}" onerror="this.style.display='none';this.nextElementSibling.style.display='block'">
          <span class="menu-photo-fallback">${visual.emoji}</span>
        </div>
        <div class="kiosk-menu-copy">
          <h3>${escapeHTML(item.name)}</h3>
          <strong>${escapeHTML(formatItemPrice(item, getLanguage()))}</strong>
        </div>
        <button class="kiosk-add-btn" type="button" aria-label="${escapeHTML(translate('addToCart'))}"><i class="fas fa-plus"></i></button>`;
      row.querySelector('.kiosk-add-btn')?.addEventListener('click', event => {
        event.stopPropagation();
        showItemConfirmModal(item);
      });
      row.addEventListener('click', () => showItemConfirmModal(item));
      fragment.appendChild(row);
    });
    ui.menuGrid.appendChild(fragment);
  }

  return {
    loadMenu,
    renderMenu,
    renderKioskCategories,
    showMenuGroup,
    itemMatchesSubFilter,
  };
}
