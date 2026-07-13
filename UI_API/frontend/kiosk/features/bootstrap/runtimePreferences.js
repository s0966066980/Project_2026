// @ts-check

const FEATURE_SCHEMA_VERSION = 'event-triggered-20260519';
const FEATURE_DEFAULTS = Object.freeze({
  emotion: true,
  voiceAssist: true,
  recommend: true,
  eventTriggeredMultimodal: true,
  multiLang: true,
});

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
    const features = { ...FEATURE_DEFAULTS, ...(saved && typeof saved === 'object' ? saved : {}) };
    const shouldApplyDemoDefaults = demoPublic && (!hasSavedFeatures || !versionMatches);
    if (!versionMatches || shouldApplyDemoDefaults) {
      if (shouldApplyDemoDefaults) {
        features.voiceAssist = true;
        features.recommend = true;
        features.eventTriggeredMultimodal = true;
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
