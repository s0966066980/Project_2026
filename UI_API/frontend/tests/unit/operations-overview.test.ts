import { describe, expect, it } from 'vitest';

import { buildOperationsOverviewView } from '../../admin/modules/operationsOverviewAdmin.js';

const overviewData = {
  voice_turns_completed: 12,
  recommendations_shown: 3535,
  campaign_cta_clicks: 7,
  confirmed_order_amount: 3250,
  currency: 'TWD',
  window_days: 1,
  definitions: {
    voice_turns_completed: '語音已產生並送出的次數，不是顧客實際聽到的次數',
    recommendations_shown: '不含 kiosk 在推薦服務失效時自行挑選的佔位品項',
    campaign_cta_clicks: '顧客實際點擊活動入口的次數',
    confirmed_order_amount: '已確認訂單的金額，不含未完成結帳的購物車',
  },
};

const loaded = (overrides = {}) => ({
  canRead: true,
  overview: { data: overviewData, error: '', loading: false, updatedAt: Date.now(), ...overrides },
});

describe('operations overview', () => {
  it('shows the four counts in a fixed order', () => {
    const view = buildOperationsOverviewView(loaded());

    expect(view.metrics.map(metric => metric.label)).toEqual([
      '語音成功', '推薦次數', '活動點擊', '已確認訂單金額',
    ]);
  });

  // The caveat is the difference between a number a manager can act on and one that
  // will be read as something it is not, so it renders with the value.
  it('renders each number with the definition the server sent', () => {
    const view = buildOperationsOverviewView(loaded());

    expect(view.metrics[0]?.hint).toContain('不是顧客實際聽到');
    expect(view.metrics[1]?.hint).toContain('佔位');
    expect(view.metrics[3]?.hint).toContain('已確認');
    expect(view.metrics.every(metric => metric.hint)).toBe(true);
  });

  it('never writes a definition of its own', () => {
    const view = buildOperationsOverviewView(loaded({
      data: { ...overviewData, definitions: {} },
    }));

    expect(view.metrics.map(metric => metric.hint)).toEqual(['', '', '', '']);
  });

  it('labels the amount with its currency and leaves counts unlabelled', () => {
    const view = buildOperationsOverviewView(loaded());

    expect(view.metrics[3]?.value).toBe('TWD 3,250');
    expect(view.metrics[1]?.value).toBe('3,535');
  });

  it('names the window it is reporting on', () => {
    expect(buildOperationsOverviewView(loaded()).headline).toContain('過去 24 小時');
    expect(
      buildOperationsOverviewView(loaded({ data: { ...overviewData, window_days: 7 } })).headline,
    ).toContain('過去 7 天');
  });

  // A stale number presented as current is worse than an empty panel.
  it('keeps the last snapshot on failure but says it may be out of date', () => {
    const view = buildOperationsOverviewView(loaded({ error: '營運總覽讀取失敗（503）' }));

    expect(view.tone).toBe('attention');
    expect(view.headline).toContain('可能已過時');
    expect(view.detail).toContain('503');
    expect(view.metrics).toHaveLength(4);
  });

  it('reports a first-load failure without inventing numbers', () => {
    const view = buildOperationsOverviewView({
      canRead: true,
      overview: { data: null, error: '連線失敗', loading: false, updatedAt: null },
    });

    expect(view.metrics).toEqual([]);
    expect(view.detail).toContain('沒有可用的快照');
  });

  it('shows nothing at all without permission', () => {
    const view = buildOperationsOverviewView({ ...loaded(), canRead: false });

    expect(view.metrics).toEqual([]);
    expect(view.status).toBe('沒有總覽權限');
  });

  it('waits rather than showing zeros before the first load', () => {
    const view = buildOperationsOverviewView({
      canRead: true,
      overview: { data: null, error: '', loading: true, updatedAt: null },
    });

    expect(view.tone).toBe('loading');
    expect(view.metrics).toEqual([]);
  });
});
