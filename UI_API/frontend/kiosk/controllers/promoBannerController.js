// @ts-check

import { createTouchId, observeVisibleImpression } from '../../shared/touchEventClient.js';

/**
 * @typedef {object} PromoBannerControllerOptions
 * @property {{ getPosPromotionBanners: (surface?: string) => Promise<Record<string, unknown>> }} api
 * @property {HTMLElement | null} root
 * @property {(value: unknown) => string} escapeHTML
 * @property {{ id: string, label: string, categories: string[] }[]} groups
 * @property {(groupId: string) => void} showMenuGroup
 * @property {(itemId: string) => void} showItemById
 * @property {string} [surface]
 * @property {string} [variant]
 * @property {(promotion: Record<string, unknown>) => void} [onPromotionCta]
 * @property {() => void} [onRecommendationTarget]
 * @property {(eventType: "impression" | "click", promotion: Record<string, unknown>, impressionId: string) => void} [onTouch]
 */

/**
 * Owns the Kiosk home promotion banner. It never blocks menu rendering.
 *
 * @param {PromoBannerControllerOptions} options
 */
export function createPromoBannerController({
  api,
  root,
  escapeHTML,
  groups,
  showMenuGroup,
  showItemById,
  surface = 'pos_home_banner',
  variant = 'home',
  onPromotionCta,
  onRecommendationTarget,
  onTouch,
}) {
  /** @type {Record<string, unknown>[]} */
  let items = [];
  let activeIndex = 0;
  /** @type {number | null} */
  let rotationTimer = null;
  let activeImpressionId = '';
  /** @type {null | (() => void)} */
  let stopImpressionTracking = null;

  function stopRotation() {
    if (rotationTimer) {
      window.clearTimeout(rotationTimer);
      rotationTimer = null;
    }
  }

  function clear() {
    if (!root) return;
    stopRotation();
    stopImpressionTracking?.();
    stopImpressionTracking = null;
    root.textContent = '';
    root.classList.add('hidden');
  }

  /**
   * @param {unknown} raw
   * @returns {Record<string, unknown>[]}
   */
  function normalizeItems(raw) {
    const rows = raw && typeof raw === 'object' && Array.isArray(raw.items) ? raw.items : [];
    return rows.filter(row => row && typeof row === 'object').map(row => /** @type {Record<string, unknown>} */ (row));
  }

  /**
   * @param {unknown} value
   * @returns {string}
   */
  function text(value) {
    return String(value || '').trim();
  }

  /**
   * @param {Record<string, unknown>} item
   * @returns {number}
   */
  function rotationSeconds(item) {
    const seconds = Number(item.rotation_seconds || 6);
    return Math.max(2, Math.min(120, Number.isFinite(seconds) ? seconds : 6));
  }

  /**
   * @param {Record<string, unknown>} item
   * @returns {string}
   */
  function priceBlock(item) {
    const originalPrice = Number(item.original_price || 0);
    const promoPrice = Number(item.promo_price || 0);
    const saveText = text(item.save_text);
    if (!originalPrice && !promoPrice && !saveText) return '';
    return `
      <div class="pos-promo-price">
        ${originalPrice ? `<span class="pos-promo-original">原價 $${originalPrice}</span>` : ''}
        ${promoPrice ? `<strong><span>特價</span> $${promoPrice}</strong>` : ''}
        ${saveText ? `<em>${escapeHTML(saveText)}</em>` : ''}
      </div>`;
  }

  /**
   * @param {string} value
   * @returns {string}
   */
  function dateLabel(value) {
    const raw = text(value);
    if (!raw) return '';
    const date = raw.slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return raw;
    return `${date.slice(5, 7)}/${date.slice(8, 10)}`;
  }

  /**
   * @param {Record<string, unknown>} item
   * @returns {string}
   */
  function dateBlock(item) {
    const start = dateLabel(item.start_at);
    const end = dateLabel(item.end_at);
    const range = start && end ? `${start} - ${end}` : (start || end || '依現場公告');
    return `
      <div class="pos-promo-date-card">
        <span><i class="fas fa-calendar-alt"></i> 活動期間</span>
        <strong>${escapeHTML(range)}</strong>
        <small>${escapeHTML(text(item.legal_text) || '活動依門市供應狀態為準')}</small>
      </div>`;
  }

  /**
   * @param {Record<string, unknown>} item
   * @returns {void}
   */
  function activateTarget(item) {
    const targetType = text(item.target_type) || 'none';
    const targetValue = text(item.target_value);
    if (targetType === 'category' && targetValue) {
      const group = groups.find(candidate => candidate.id === targetValue || candidate.label === targetValue || candidate.categories.includes(targetValue));
      if (group) showMenuGroup(group.id);
      return;
    }
    if (targetType === 'item' && targetValue) {
      showItemById(targetValue);
      return;
    }
    if (targetType === 'recommendation') {
      onRecommendationTarget?.();
    }
  }

  /**
   * @param {Record<string, unknown>} item
   * @returns {void}
   */
  function handleCta(item) {
    if (typeof onPromotionCta === 'function') {
      onPromotionCta(item);
      return;
    }
    activateTarget(item);
  }

  function scheduleRotation() {
    stopRotation();
    if (items.length <= 1) return;
    const item = items[Math.max(0, Math.min(activeIndex, items.length - 1))];
    rotationTimer = window.setTimeout(() => {
      activeIndex = (activeIndex + 1) % items.length;
      render();
    }, rotationSeconds(item) * 1000);
  }

  function render() {
    if (!root) return;
    if (!items.length) {
      clear();
      return;
    }
    const item = items[Math.max(0, Math.min(activeIndex, items.length - 1))];
    stopImpressionTracking?.();
    stopImpressionTracking = null;
    activeImpressionId = createTouchId('impression');
    const theme = text(item.theme) || 'gold';
    root.classList.remove('hidden');
    root.dataset.variant = variant;
    root.innerHTML = `
      <button class="pos-promo-banner pos-promo-theme-${escapeHTML(theme)}" type="button">
        <span class="pos-promo-shape pos-promo-shape-left"></span>
        <span class="pos-promo-shape pos-promo-shape-right"></span>
        <span class="pos-promo-dot-pattern"></span>
        <div class="pos-promo-copy">
          <span class="pos-promo-badge">${escapeHTML(text(item.badge) || '今日推薦')}</span>
          <h2>${escapeHTML(text(item.title))}</h2>
          <p class="pos-promo-subtitle">${escapeHTML(text(item.subtitle) || text(item.description))}</p>
          ${text(item.description) && text(item.description) !== text(item.subtitle) ? `<p class="pos-promo-description">${escapeHTML(text(item.description))}</p>` : ''}
        </div>
        <div class="pos-promo-side">
          ${priceBlock(item)}
          <div class="pos-promo-action">
            ${dateBlock(item)}
            <span class="pos-promo-cta" role="button" tabindex="0">${escapeHTML(text(item.cta_text) || '立即查看')}</span>
          </div>
        </div>
      </button>
      ${items.length > 1 ? `<div class="pos-promo-dots">${items.map((_, index) => `<button class="${index === activeIndex ? 'active' : ''}" type="button" aria-label="活動 ${index + 1}" data-index="${index}"></button>`).join('')}</div>` : ''}`;

    const cta = root.querySelector('.pos-promo-cta');
    cta?.addEventListener('click', event => {
      event.stopPropagation();
      onTouch?.('click', item, activeImpressionId);
      handleCta(item);
    });
    cta?.addEventListener('keydown', event => {
      if (!(event instanceof KeyboardEvent)) return;
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      onTouch?.('click', item, activeImpressionId);
      handleCta(item);
    });
    root.querySelectorAll('.pos-promo-dots button').forEach(button => {
      button.addEventListener('click', event => {
        event.stopPropagation();
        activeIndex = Number(button.getAttribute('data-index') || 0);
        render();
      });
    });
    const banner = root.querySelector('.pos-promo-banner');
    if (banner) {
      stopImpressionTracking = observeVisibleImpression(banner, {
        onVisible: () => onTouch?.('impression', item, activeImpressionId),
      });
    }
    scheduleRotation();
  }

  async function load() {
    if (!root) return;
    try {
      const response = await api.getPosPromotionBanners(surface);
      items = normalizeItems(response);
      activeIndex = 0;
      render();
    } catch (error) {
      console.warn('[pos promotion banner failed]', error);
      clear();
    }
  }

  return {
    load,
    render,
    clear,
    stopRotation,
  };
}
