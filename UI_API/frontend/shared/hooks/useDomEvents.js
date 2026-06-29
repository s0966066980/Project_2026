// @ts-check

/**
 * @template {Event} EventType
 * @param {EventTarget | null | undefined} target
 * @param {string} eventName
 * @param {(event: EventType) => void} handler
 * @param {AddEventListenerOptions | boolean} [options]
 * @returns {() => void}
 */
export function addDomEventListener(target, eventName, handler, options) {
  if (!target) return () => {};
  const listener = /** @type {EventListener} */ (handler);
  target.addEventListener(eventName, listener, options);
  return () => target.removeEventListener(eventName, listener, options);
}

/**
 * @param {() => void} handler
 * @returns {() => void}
 */
export function useDomReady(handler) {
  if (document.readyState === 'loading') {
    return addDomEventListener(document, 'DOMContentLoaded', handler);
  }
  handler();
  return () => {};
}
