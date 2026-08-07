// @ts-check

/**
 * 只有元素連續達到指定可見比例與時間，才回報一次曝光。
 * @param {Element} element
 * @param {{
 *   onVisible: () => void,
 *   threshold?: number,
 *   dwellMs?: number,
 *   observerFactory?: (callback: IntersectionObserverCallback, options: IntersectionObserverInit) => Pick<IntersectionObserver, "observe" | "disconnect">
 * }} options
 * @returns {() => void}
 */
export function observeVisibleImpression(element, {
  onVisible,
  threshold = 0.5,
  dwellMs = 1000,
  observerFactory = (callback, observerOptions) => new IntersectionObserver(callback, observerOptions),
}) {
  /** @type {ReturnType<typeof setTimeout> | 0} */
  let timer = 0;
  let sent = false;
  const cancelTimer = () => {
    if (timer) globalThis.clearTimeout(timer);
    timer = 0;
  };
  const observer = observerFactory((entries) => {
    const entry = entries.find(candidate => candidate.target === element) || entries[0];
    if (!entry || !entry.isIntersecting || entry.intersectionRatio < threshold) {
      cancelTimer();
      return;
    }
    if (sent || timer) return;
    timer = globalThis.setTimeout(() => {
      timer = 0;
      if (sent) return;
      sent = true;
      onVisible();
      observer.disconnect();
    }, dwellMs);
  }, { threshold: [threshold] });
  observer.observe(element);
  return () => {
    cancelTimer();
    observer.disconnect();
  };
}

/**
 * A commercial touch may only be recorded when the server authored what the customer saw:
 * a recommendation decision, or a campaign. A surface the kiosk filled in by itself — the
 * local placeholder shown while the recommendation API is unreachable — carries neither,
 * and must stay out of commercial evidence rather than land as a low-quality row.
 *
 * @param {Record<string, unknown>} details
 */
export function isServerAuthoredTouch(details) {
  const decisionId = String(details?.decision_id ?? '').trim();
  const campaignId = String(details?.campaign_id ?? '').trim();
  return Boolean(decisionId || campaignId);
}

/** @param {string} prefix */
export function createTouchId(prefix) {
  const random = globalThis.crypto?.randomUUID?.().replaceAll('-', '') || Math.random().toString(16).slice(2);
  return `${prefix}_${random}`;
}
