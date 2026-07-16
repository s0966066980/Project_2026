/**
 * @typedef {{variant_id?: string, impressions?: number, clicks?: number, add_to_carts?: number}} EffectivenessBreakdown
 * @typedef {{
 *   controlLabel: string,
 *   variantLabel: string,
 *   controlSample: number,
 *   variantSample: number,
 *   controlRate: number,
 *   variantRate: number,
 *   differencePoints: number,
 *   conclusion: string
 * }} StrategyComparison
 */

const STRATEGY_VARIANT_LABELS = Object.freeze({
  control: '控制組（加權隨機推薦）',
  ranked: '最高分排序組',
});

/** @param {unknown} variant */
export function strategyVariantLabel(variant) {
  const key = String(variant || '').trim();
  return STRATEGY_VARIANT_LABELS[/** @type {keyof typeof STRATEGY_VARIANT_LABELS} */ (key)] || (key ? `自訂策略組（${key}）` : '未設定分組');
}

/**
 * Convert the authoritative effectiveness comparison into display-safe values.
 * Unsegmented traffic is deliberately excluded: it is not a strategy experiment.
 *
 * @param {{breakdowns?: EffectivenessBreakdown[], comparisons?: Record<string, unknown>[]} | null | undefined} report
 * @returns {StrategyComparison[]}
 */
export function strategyComparisonView(report) {
  const breakdowns = new Map((Array.isArray(report?.breakdowns) ? report.breakdowns : [])
    .map(row => [String(row?.variant_id || '').trim(), row]));
  return (Array.isArray(report?.comparisons) ? report.comparisons : [])
    .filter(row => {
      const control = String(row?.control_variant || '').trim();
      const variant = String(row?.variant_id || '').trim();
      return control && variant && ![control, variant].includes('未設定分組');
    })
    .map(row => {
      const controlVariant = String(row.control_variant);
      const variantId = String(row.variant_id);
      return {
        controlLabel: strategyVariantLabel(controlVariant),
        variantLabel: strategyVariantLabel(variantId),
        controlSample: Number(row.control_sample || breakdowns.get(controlVariant)?.impressions || 0),
        variantSample: Number(row.variant_sample || breakdowns.get(variantId)?.impressions || 0),
        controlRate: Math.round(Number(row.control_purchase_rate || 0) * 1000) / 10,
        variantRate: Math.round(Number(row.variant_purchase_rate || 0) * 1000) / 10,
        differencePoints: Math.round(Number(row.purchase_rate_difference || 0) * 1000) / 10,
        conclusion: String(row.conclusion || ''),
      };
    });
}
