// @ts-check

/**
 * Checkout's browser-facing projection seam.
 *
 * The server owns the quote, order number, and final pricing snapshot.  The
 * kiosk app is responsible for DOM and interaction wiring; this module keeps
 * the data-shaping rules in one small, testable interface.
 */

export const PENDING_ORDER_NUMBER_LABEL = '付款完成後產生';

/** @param {any} item */
function prepMinutesFor(item) {
  return Number(item.prep_time_minutes || item.prep_minutes || 0);
}

/**
 * @param {any} item
 * @param {(item: any) => number} resolvePrice
 */
function toCompletionItem(item, resolvePrice) {
  return {
    name: item.name || item.id || '',
    quantity: Number(item.qty || item.quantity || 1),
    price: resolvePrice(item),
  };
}

/**
 * @param {any} quote
 * @returns {{items: any[], prepMinutes: number, subtotal: number, serviceFee: number, total: number}}
 */
export function checkoutQuoteSummary(quote = null) {
  const items = Array.isArray(quote?.pricing?.cart_items) ? quote.pricing.cart_items : [];
  return {
    items,
    prepMinutes: Math.max(0, ...items.map(prepMinutesFor)),
    subtotal: Number(quote?.pricing?.subtotal || 0),
    serviceFee: Number(quote?.pricing?.fee_total || 0),
    total: Number(quote?.pricing?.total || 0),
  };
}

/**
 * Only the server can provide a pickup number and pricing snapshot.
 *
 * @param {any} order
 * @param {string} fallbackSessionId
 */
export function confirmedOrderResult(order, fallbackSessionId = '') {
  return {
    orderNumber: order?.pickup_number || 0,
    sessionId: order?.session_id || fallbackSessionId,
    pricing: order?.pricing || null,
  };
}

/**
 * Prefer the server's final quote for the completion screen. Local cart data
 * is only a rendering fallback for an incomplete response payload.
 *
 * @param {any} orderData
 * @param {any[]} fallbackItems
 * @param {(item: any) => number} resolvePrice
 */
export function completionCartItems(orderData = {}, fallbackItems = [], resolvePrice) {
  const quotedItems = Array.isArray(orderData?.pricing?.cart_items) ? orderData.pricing.cart_items : [];
  const rawItems = quotedItems.length ? quotedItems : fallbackItems;
  return rawItems.map(/** @param {any} item */ item => toCompletionItem(item, resolvePrice));
}
