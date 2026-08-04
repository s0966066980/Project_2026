// @ts-check

/**
 * @param {Element | null | undefined} element
 * @returns {void}
 */
export function showFlexElement(element) {
  element?.classList.replace('hidden', 'flex');
}

/**
 * @param {Element | null | undefined} element
 * @returns {void}
 */
export function hideFlexElement(element) {
  element?.classList.replace('flex', 'hidden');
}
