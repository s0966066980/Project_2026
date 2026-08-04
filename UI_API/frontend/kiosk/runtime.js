// @ts-check

/** @typedef {import('../types.d.ts').KioskRuntime} KioskRuntime */

/** @type {KioskRuntime} */
export const kioskRuntime = {};

/**
 * @param {Partial<KioskRuntime>} values
 * @returns {void}
 */
export function configureKioskRuntime(values) {
  Object.assign(kioskRuntime, values);
}

export const posRuntime = kioskRuntime;
export const configurePointOfSaleRuntime = configureKioskRuntime;

/**
 * @template {keyof KioskRuntime} DependencyName
 * @param {DependencyName} name
 * @returns {NonNullable<KioskRuntime[DependencyName]>}
 */
export function getRequiredRuntimeDependency(name) {
  const value = kioskRuntime[name];
  if (value == null) {
    throw new Error(`Kiosk runtime dependency is not configured: ${name}`);
  }
  return /** @type {NonNullable<KioskRuntime[DependencyName]>} */ (value);
}
