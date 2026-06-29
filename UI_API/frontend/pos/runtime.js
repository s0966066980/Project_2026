// @ts-check

/** @typedef {import('../types.d.ts').PointOfSaleRuntime} PointOfSaleRuntime */

/** @type {PointOfSaleRuntime} */
export const posRuntime = {};

/**
 * @param {Partial<PointOfSaleRuntime>} values
 * @returns {void}
 */
export function configurePointOfSaleRuntime(values) {
  Object.assign(posRuntime, values);
}

/**
 * @template {keyof PointOfSaleRuntime} DependencyName
 * @param {DependencyName} name
 * @returns {NonNullable<PointOfSaleRuntime[DependencyName]>}
 */
export function getRequiredRuntimeDependency(name) {
  const value = posRuntime[name];
  if (value == null) {
    throw new Error(`POS runtime dependency is not configured: ${name}`);
  }
  return /** @type {NonNullable<PointOfSaleRuntime[DependencyName]>} */ (value);
}
