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
 * @property {{
 *   getMenu: () => Promise<MenuItem[]>,
 *   getMenuPriceProjections?: (cartItemIds?: string[], sessionId?: string) => Promise<import('../../types.d.ts').MenuPriceProjection[]>
 * }} api
 * @property {{ menuData: MenuItem[], kioskScreen: string, kioskActiveGroup: string, kioskActiveFilter: string }} state
 * @property {{
 *   menuGrid: HTMLElement,
 *   kioskTitle?: HTMLElement | null,
 *   kioskSubtitle?: HTMLElement | null,
 *   kioskBackBtn?: HTMLElement | null,
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
 * @property {() => void} updateKioskCartSummary
 * @property {() => string} [getSessionId]
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
  updateKioskCartSummary,
  getSessionId = () => '',
  onCategorySwitchRepeat,
}) {
  /** @type {Promise<MenuItem[]> | null} */
  let menuLoadPromise = null;
  let hasLoadedRemoteMenu = false;

  /** @param {import('../../types.d.ts').MenuPriceProjection[]} projections */
  function applyPriceProjections(projections) {
    const byId = new Map((projections || []).map(projection => [String(projection.item_id), projection]));
    const menuNames = new Map(state.menuData.map(item => [String(item.id), String(item.name || item.id)]));
    state.menuData = state.menuData.map(item => {
      const projection = byId.get(String(item.id));
      if (!projection) return item;
      const requiredNames = projection.required_cart_item_ids.map(id => menuNames.get(String(id)) || String(id));
      return {
        ...item,
        price: projection.effective_price,
        base_price: projection.base_price,
        effective_price: projection.effective_price,
        original_price: projection.discount > 0 ? projection.base_price : undefined,
        discount: projection.discount,
        applied_offer_id: projection.conditional ? undefined : projection.activity_id,
        promotion_title: projection.activity_name,
        price_conditional: projection.conditional,
        conditional_price: Number(projection.conditional_price || 0),
        price_condition_text: projection.conditional
          ? `需先加入：${requiredNames.join('、')}，即可享 $${Number(projection.conditional_price || 0)}`
          : '',
      };
    });
  }

  /** @param {string[]} [cartItemIds] */
  async function refreshPriceProjections(cartItemIds = []) {
    if (typeof api.getMenuPriceProjections !== 'function' || !state.menuData.length) return;
    const projections = await api.getMenuPriceProjections(cartItemIds, getSessionId());
    applyPriceProjections(projections);
    renderMenu();
  }

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
      try {
        await refreshPriceProjections([]);
      } catch {
        // 菜單仍可瀏覽，但價格投影失敗時不宣稱有優惠。
      }
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
    ui.kioskBackBtn?.classList.add('hidden');
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
    ui.kioskBackBtn?.classList.remove('hidden');
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

    items.forEach(item => {
      const visual = getMenuVisual(item);
      const row = document.createElement('div');
      row.id = `menu-${item.id}`;
      row.className = 'kiosk-menu-row';
      const currentPrice = formatItemPrice(item, getLanguage());
      const basePrice = Number(item.base_price || item.original_price || 0);
      const effectivePrice = Number(item.effective_price || item.price || 0);
      const originalPrice = !item.price_conditional && basePrice > effectivePrice
        ? `<span class="kiosk-menu-original-price">$${basePrice}</span>`
        : '';
      const activityText = item.price_conditional
        ? item.price_condition_text
        : item.promotion_title;
      row.innerHTML = `
        <div class="kiosk-menu-photo">
          <img src="${escapeHTML(visual.image)}" alt="${escapeHTML(item.name)}" onerror="this.style.display='none';this.nextElementSibling.style.display='block'">
          <span class="menu-photo-fallback">${escapeHTML(visual.emoji)}</span>
        </div>
        <div class="kiosk-menu-copy">
          <h3>${escapeHTML(item.name)}</h3>
          <strong>${originalPrice}<span>${escapeHTML(currentPrice)}</span></strong>
          ${activityText ? `<small class="kiosk-menu-activity">${escapeHTML(activityText)}</small>` : ''}
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
    refreshPriceProjections,
  };
}
