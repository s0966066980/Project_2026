// @ts-check

import { fetchJson } from '../httpClient.js';

/** @typedef {import('../contracts/api-v1-catalog').CatalogItemDTO} CatalogItemDTO */
/** @typedef {import('../contracts/api-v1-catalog').CatalogItemListDTO} CatalogItemListDTO */
/** @typedef {import('../contracts/api-v1-catalog').CatalogItemWriteDTO} CatalogItemWriteDTO */
/** @typedef {import('../contracts/api-v1-catalog').CatalogAvailabilityDTO} CatalogAvailabilityDTO */
/** @typedef {import('../contracts/api-v1-catalog').CatalogAvailabilityCommandDTO} CatalogAvailabilityCommandDTO */

/**
 * The one client for the catalog capability's `/api/v1/catalog` contract.
 *
 * Feature code does not write transport: the shapes here come from
 * `contracts/api-v1-catalog.ts`, which is generated from the schema the server
 * publishes, so a field renamed on the server fails the drift gate instead of
 * silently reaching a customer.
 *
 * @param {{ baseUrl?: string, headers?: () => Record<string, string> }} [options]
 */
export function createCatalogClient({ baseUrl = '', headers = () => ({}) } = {}) {
  const root = `${baseUrl}/api/v1/catalog`;

  /** @param {string} path @param {RequestInit} [init] */
  async function envelope(path, init = {}) {
    /** @type {{data: any}} */
    const body = await fetchJson(`${root}${path}`, { ...init, headers: { ...headers(), ...(init.headers || {}) } });
    return body.data;
  }

  return {
    /**
     * @param {{ includeRetired?: boolean }} [options]
     * @returns {Promise<CatalogItemListDTO>}
     */
    listItems({ includeRetired = false } = {}) {
      const params = new URLSearchParams({ include_retired: String(includeRetired) });
      return envelope(`/items?${params.toString()}`);
    },

    /** @param {string} itemId @returns {Promise<CatalogItemDTO>} */
    getItem(itemId) {
      return envelope(`/items/${encodeURIComponent(itemId)}`);
    },

    /** @param {CatalogItemWriteDTO} item @returns {Promise<CatalogItemDTO>} */
    createItem(item) {
      return envelope('/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item),
      });
    },

    /** @param {string} itemId @param {CatalogItemWriteDTO} changes @returns {Promise<CatalogItemDTO>} */
    updateItem(itemId, changes) {
      return envelope(`/items/${encodeURIComponent(itemId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(changes),
      });
    },

    /** Retirement is a state of the item, so it is addressed as one. */
    /** @param {string} itemId @returns {Promise<CatalogItemDTO>} */
    retireItem(itemId) {
      return envelope(`/items/${encodeURIComponent(itemId)}/retirement`, { method: 'POST' });
    },

    /** @param {string} itemId @returns {Promise<CatalogItemDTO>} */
    restoreItem(itemId) {
      return envelope(`/items/${encodeURIComponent(itemId)}/retirement`, { method: 'DELETE' });
    },

    /** @param {string} itemId @param {File|Blob} file @returns {Promise<CatalogItemDTO>} */
    uploadItemImage(itemId, file) {
      const form = new FormData();
      form.append('file', file);
      return envelope(`/items/${encodeURIComponent(itemId)}/image`, { method: 'PUT', body: form });
    },

    /** @returns {Promise<CatalogAvailabilityDTO>} */
    getAvailability() {
      return envelope('/availability');
    },

    /** @param {CatalogAvailabilityCommandDTO} command @returns {Promise<CatalogAvailabilityDTO>} */
    saveAvailability(command) {
      return envelope('/availability', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(command),
      });
    },
  };
}
