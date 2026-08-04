/**
 * Admin settings write path via typed API v1 client.
 * Does not call legacy fetch('/api/...') for new work.
 */
import { createApiV1Client } from '../../../shared/api/v1Client';

/**
 * @param {{ getBearerToken?: () => string }} [options]
 */
export function createSettingsApi(options = {}) {
  /** @type {import('../../../shared/api/v1Client').ApiV1ClientOptions} */
  const clientOptions = {};
  if (typeof options.getBearerToken === 'function') {
    clientOptions.getBearerToken = options.getBearerToken;
  }
  const client = createApiV1Client(clientOptions);

  return {
    /**
     * @returns {Promise<{ values: Record<string, unknown> }>}
     */
    async getSettings() {
      const response = await client.get('/settings');
      return response.data;
    },

    /**
     * @param {Record<string, unknown>} values
     * @param {{ idempotencyKey?: string }} [opts]
     * @returns {Promise<{ values: Record<string, unknown> }>}
     */
    async patchSettings(values, opts = {}) {
      const response = await client.patch('/settings', {
        values,
        idempotency_key: opts.idempotencyKey ?? null,
      });
      return response.data;
    },
  };
}
