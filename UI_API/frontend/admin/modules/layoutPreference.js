/**
 * 介面縮放偏好。
 *
 * 這是每個人、每台電腦各自的偏好（視力與螢幕尺寸本來就因人而異），因此存在瀏覽器而非後端設定：
 * 一個人把字調大不該讓其他管理員跟著變，也不該出現在設定變更歷史與回滾範圍裡。
 */

const STORAGE_KEY = 'admin.ui.zoom';
const MIN_PERCENT = 90;
const MAX_PERCENT = 150;
const DEFAULT_PERCENT = 100;

/** @param {unknown} value @returns {number} */
function clampPercent(value) {
  const percent = Math.round(Number(value));
  if (!Number.isFinite(percent)) return DEFAULT_PERCENT;
  return Math.min(MAX_PERCENT, Math.max(MIN_PERCENT, percent));
}

/** @returns {number} 目前偏好的縮放百分比。 */
export function readZoomPercent() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === null ? DEFAULT_PERCENT : clampPercent(stored);
  } catch {
    // 隱私模式或停用 storage 時仍要能使用後台，只是設定無法保存。
    return DEFAULT_PERCENT;
  }
}

/** @param {number} percent */
export function applyZoomPercent(percent) {
  const safe = clampPercent(percent);
  document.documentElement.style.setProperty('--ui-zoom', String(safe / 100));
  return safe;
}

/** @param {number} percent */
export function saveZoomPercent(percent) {
  const safe = clampPercent(percent);
  try {
    window.localStorage.setItem(STORAGE_KEY, String(safe));
  } catch {
    // 存不進去不影響本次瀏覽已套用的效果。
  }
  return safe;
}

/**
 * 在頁面剛載入時就套用，避免使用者先看到預設大小再跳成偏好大小。
 * @returns {number}
 */
export function initZoom() {
  return applyZoomPercent(readZoomPercent());
}

/**
 * 綁定「版面設定」分頁的控制項。
 * @param {(id: string) => HTMLElement | null} getElement
 */
export function bindLayoutPreference(getElement) {
  const slider = /** @type {HTMLInputElement | null} */ (getElement('inp-ui-zoom'));
  const output = getElement('out-ui-zoom');

  /** @param {number} percent @param {boolean} persist */
  function update(percent, persist) {
    const safe = persist ? saveZoomPercent(percent) : clampPercent(percent);
    applyZoomPercent(safe);
    if (slider) slider.value = String(safe);
    if (output) output.textContent = `${safe}%`;
  }

  update(readZoomPercent(), false);

  // 拖動時即時預覽，放開才寫入儲存，避免每一格都寫一次 localStorage。
  slider?.addEventListener('input', () => update(Number(slider.value), false));
  slider?.addEventListener('change', () => update(Number(slider.value), true));

  getElement('btn-ui-zoom-reset')?.addEventListener('click', () => update(DEFAULT_PERCENT, true));

  document.querySelectorAll('[data-ui-zoom]').forEach(node => {
    const button = /** @type {HTMLElement} */ (node);
    button.addEventListener('click', () => update(Number(button.dataset.uiZoom), true));
  });
}
