// @ts-check

const FEATURE_SCHEMA_VERSION = 'voice-emotion-20260721';
const FEATURE_DEFAULTS = Object.freeze({
  voiceAssist: true,
  recommend: true,
  multiLang: true,
});
const FEATURE_KEYS = Object.freeze(Object.keys(FEATURE_DEFAULTS));

/** @param {Location} location */
export function resolveKioskAppMode(location) {
  if (location.port === '9001' || location.pathname.startsWith('/admin')) return 'admin';
  return 'kiosk';
}

/** @param {Location} location */
export function buildKioskSessionId(location) {
  const requested = new URLSearchParams(location.search).get('session_id');
  const safeRequested = String(requested || '').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 80);
  return safeRequested || `kiosk_${Math.random().toString(36).slice(2, 11)}`;
}

/**
 * @param {Storage} storage
 * @param {boolean} demoPublic
 * @returns {Record<string, boolean>}
 */
export function loadKioskFeatures(storage, demoPublic) {
  try {
    const versionMatches = storage.getItem('kiosk_feat_version') === FEATURE_SCHEMA_VERSION;
    const hasSavedFeatures = Boolean(storage.getItem('kiosk_feat'));
    const saved = JSON.parse(storage.getItem('kiosk_feat') || '{}');
    const savedFeatures = saved && typeof saved === 'object'
      ? Object.fromEntries(FEATURE_KEYS.filter(key => typeof saved[key] === 'boolean').map(key => [key, saved[key]]))
      : {};
    const features = { ...FEATURE_DEFAULTS, ...savedFeatures };
    const shouldApplyDemoDefaults = demoPublic && (!hasSavedFeatures || !versionMatches);
    if (!versionMatches || shouldApplyDemoDefaults) {
      if (shouldApplyDemoDefaults) {
        features.voiceAssist = true;
        features.recommend = true;
      }
      saveKioskFeatures(storage, features);
    }
    return features;
  } catch {
    return { ...FEATURE_DEFAULTS };
  }
}

/** @param {Storage} storage @param {Record<string, boolean>} features */
export function saveKioskFeatures(storage, features) {
  storage.setItem('kiosk_feat', JSON.stringify(features));
  storage.setItem('kiosk_feat_version', FEATURE_SCHEMA_VERSION);
}
