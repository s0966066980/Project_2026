// @ts-check

/** @typedef {import('../types.d.ts').LanguageCode} LanguageCode */
/** @typedef {import('../types.d.ts').MenuItem} MenuItem */
/** @typedef {import('../types.d.ts').MenuVisual} MenuVisual */

// =========================================================
// 菜單品項視覺呈現：分類圖示／emoji／圖片路徑 + 價格格式化。
// 純函式，無模組狀態（語言由呼叫端以參數傳入）。
// =========================================================

export const STORE_PRICE_FALLBACK = 100;

/**
 * @param {MenuItem | { price?: unknown, effective_price?: unknown }} item
 * @returns {number}
 */
export function resolveItemPrice(item) {
  const price = Number(item?.effective_price || item?.price || 0);
  return price > 0 ? price : STORE_PRICE_FALLBACK;
}

/**
 * @param {MenuItem} item
 * @returns {MenuVisual & { tag: string, icon: string }}
 */
export function getMenuVisual(item) {
  const id = String(item.id || '').toUpperCase();
  const category = String(item.category || '');
  const name = String(item.name || '');
  /** @type {Record<string, { tag: string, icon: string, emoji: string }>} */
  const categoryVisuals = {
    '超值全餐': { tag: '超值全餐', icon: 'fas fa-burger', emoji: '🍔' },
    '超值全餐配餐': { tag: '配餐', icon: 'fas fa-cubes-stacked', emoji: '🍟' },
    '極選系列': { tag: '推薦套餐', icon: 'fas fa-star', emoji: '🍔' },
    '1+1星級點': { tag: '1+1', icon: 'fas fa-plus', emoji: '✨' },
    '麥當勞分享盒': { tag: '分享盒', icon: 'fas fa-box', emoji: '📦' },
    'Happy Meal': { tag: 'Happy Meal', icon: 'fas fa-child-reaching', emoji: '🧒' },
    '早餐': { tag: '早餐', icon: 'fas fa-sun', emoji: '🥞' },
    '飲料': { tag: '飲料甜點', icon: 'fas fa-glass-water', emoji: '🥤' },
    'McCafé': { tag: 'McCafé', icon: 'fas fa-mug-hot', emoji: '☕' },
    '點心': { tag: '單點餐品', icon: 'fas fa-cookie-bite', emoji: '🍟' },
  };
  let fallback = categoryVisuals[category] || { tag: category || '精選餐點', icon: 'fas fa-utensils', emoji: '🍽️' };
  // 細項表情：依品名再校正一次預設 emoji，避免分享盒/1+1 全部變相同圖示。
  if (/薯條|薯餅/.test(name)) fallback = { ...fallback, emoji: '🍟' };
  else if (/雞翅|鷄翅|鷄塊|雞塊|麥脆/.test(name)) fallback = { ...fallback, emoji: '🍗' };
  else if (/咖啡|拿鐵|那堤|拿提|美式/.test(name)) fallback = { ...fallback, emoji: '☕' };
  else if (/可樂|雪碧|汽水/.test(name)) fallback = { ...fallback, emoji: '🥤' };
  else if (/茶/.test(name)) fallback = { ...fallback, emoji: '🍵' };
  else if (/沙拉|藜麥/.test(name)) fallback = { ...fallback, emoji: '🥗' };
  else if (/魚/.test(name)) fallback = { ...fallback, emoji: '🐟' };
  else if (/派/.test(name)) fallback = { ...fallback, emoji: '🥧' };
  else if (/玉米|湯/.test(name)) fallback = { ...fallback, emoji: '🌽' };
  else if (/鬆餅|滿福|焙果/.test(name)) fallback = { ...fallback, emoji: '🥞' };
  else if (/Happy Meal|快樂兒童餐/.test(name)) fallback = { ...fallback, emoji: '🧒' };
  return { ...fallback, image: item.image || (id.startsWith('MCD') ? `/static/menu_images/${id}.jpg` : '') };
}

/**
 * @param {MenuItem} item
 * @param {LanguageCode} [lang]
 * @returns {string}
 */
export function formatItemPrice(item, lang = 'zh') {
  return `$${resolveItemPrice(item)}`;
}

/**
 * @param {MenuItem} item
 * @returns {string}
 */
export function formatItemPriceDetail(item) {
  const effectivePrice = resolveItemPrice(item);
  const basePrice = Number(item.base_price || item.original_price || 0);
  if (item.price_conditional && Number(item.conditional_price || 0) > 0) {
    return `$${effectivePrice}；${item.price_condition_text || `符合活動條件可享 $${item.conditional_price}`}`;
  }
  if (basePrice > effectivePrice && item.promotion_title) {
    return `優惠價 $${effectivePrice}（原價 $${basePrice}） · ${item.promotion_title}`;
  }
  return `$${effectivePrice}`;
}
