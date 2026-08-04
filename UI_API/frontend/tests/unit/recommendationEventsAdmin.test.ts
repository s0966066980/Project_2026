import { describe, expect, it } from 'vitest';

import { strategyComparisonView, strategyVariantLabel } from '../../admin/modules/recommendationStrategyComparison.js';

describe('推薦策略版本比較', () => {
  it('只在精準成效有真實比較組時顯示差異', () => {
    expect(strategyComparisonView({ breakdowns: [{ variant_id: '未設定分組', impressions: 3 }], comparisons: [] })).toEqual([]);

    expect(strategyComparisonView({
      breakdowns: [
        { variant_id: 'control', impressions: 120, clicks: 12, add_to_carts: 8 },
        { variant_id: 'ranked', impressions: 130, clicks: 20, add_to_carts: 15 },
      ],
      comparisons: [{
        control_variant: 'control', variant_id: 'ranked', control_sample: 120, variant_sample: 130,
        control_purchase_rate: 0.1, variant_purchase_rate: 0.14, purchase_rate_difference: 0.04,
        conclusion: '可持續觀察此差異',
      }],
    })).toEqual([expect.objectContaining({
      controlLabel: '控制組（加權隨機推薦）',
      variantLabel: '最高分排序組',
      differencePoints: 4,
    })]);
  });

  it('實驗分組只顯示完整中文名稱', () => {
    expect(strategyVariantLabel('control')).toBe('控制組（加權隨機推薦）');
    expect(strategyVariantLabel('ranked')).toBe('最高分排序組');
    expect(strategyVariantLabel('variant-b')).toBe('自訂策略組（variant-b）');
    expect(strategyVariantLabel('')).toBe('未設定分組');
  });
});
