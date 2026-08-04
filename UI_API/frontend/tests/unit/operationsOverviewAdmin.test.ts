import { describe, expect, it } from 'vitest';

import { buildOperationsOverviewView } from '../../admin/modules/operationsOverviewAdmin.js';

const emptySource = { data: null, error: '', loading: false, updatedAt: null };

describe('operations overview presentation', () => {
  it('keeps the last successful snapshot visible after one source fails', () => {
    const view = buildOperationsOverviewView({
      canReadStats: true,
      canReadRecommendations: true,
      stats: {
        data: { total: 10, success: 4, successRate: 0.4 },
        error: 'stats unavailable',
        loading: false,
        updatedAt: 100,
      },
      recommendations: {
        data: { impressions: 20, purchases: 3, purchaseRate: 0.15 },
        error: '',
        loading: false,
        updatedAt: 200,
      },
    });

    expect(view.status).toBe('部分資料未更新');
    expect(view.headline).not.toContain('10 次推播');
    expect(view.headline).toContain('20 次');
    expect(view.action).toContain('營運統計保留');
    expect(view.action).toContain('成功快照');
  });

  it('does not treat inaccessible sources as failures', () => {
    const view = buildOperationsOverviewView({
      canReadStats: false,
      canReadRecommendations: true,
      stats: { ...emptySource, error: 'must be ignored' },
      recommendations: {
        data: {
          impressions: 8,
          purchases: 1,
          purchaseRate: 0.125,
          ignoreRate: 0.25,
          purchaseRateTarget: 0.1,
          ignoreRateGuardrail: 0.35,
          targetStatus: 'insufficient_data',
        },
        error: '',
        loading: false,
        updatedAt: 200,
      },
    });

    expect(view.status).toBe('資料已更新');
    expect(view.headline).not.toContain('推播');
    expect(view.headline).toContain('資料還不足');
    expect(view.metrics).toHaveLength(4);
    expect(view.metrics?.[2]?.hint).toContain('主管目標 10%');
  });

  it('turns target and guardrail results into a direct action', () => {
    const view = buildOperationsOverviewView({
      canReadStats: false,
      canReadRecommendations: true,
      stats: emptySource,
      recommendations: {
        data: {
          impressions: 120,
          purchases: 8,
          purchaseRate: 0.0667,
          ignoreRate: 0.4,
          purchaseRateTarget: 0.1,
          ignoreRateGuardrail: 0.35,
          targetStatus: 'below_target_and_high_ignore',
        },
        error: '',
        loading: false,
        updatedAt: 200,
      },
    });

    expect(view.tone).toBe('attention');
    expect(view.headline).toContain('都需要留意');
    expect(view.detail).toContain('目標 10%');
    expect(view.detail).toContain('警戒 35%');
    expect(view.action).toContain('商品供應');
  });
});
