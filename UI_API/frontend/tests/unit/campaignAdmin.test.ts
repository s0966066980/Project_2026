import { describe, expect, it } from 'vitest';

import { campaignMatchesFilter, createCampaignAdmin } from '../../admin/modules/campaignAdmin.js';

function controller() {
  return createCampaignAdmin({
    apiBaseUrl: '',
    adminHeaders: () => ({}),
    getElement: () => null,
    loadMenu: async () => ({}),
    getMenuItems: () => [],
  });
}

describe('活動管理中文標示', () => {
  it('不直接顯示英文狀態或呈現位置代碼', () => {
    const admin = controller();

    expect(admin.statusLabel('active')).toBe('進行中');
    expect(admin.statusLabel('unexpected_internal_value')).toBe('未知狀態');
    expect(admin.placementLabel('kiosk_cart_banner')).toBe('購物車活動區');
    expect(admin.placementLabel('private_function_name')).toBe('未知位置');
  });

  it('預設目前檢視不會混入已結束與已封存活動', () => {
    expect(campaignMatchesFilter({ status: 'active', payload: { name: '進行中' } }, '', 'current')).toBe(true);
    expect(campaignMatchesFilter({ status: 'draft', payload: { name: '草稿' } }, '', 'current')).toBe(true);
    expect(campaignMatchesFilter({ status: 'ended', payload: { name: '舊活動' } }, '', 'current')).toBe(false);
    expect(campaignMatchesFilter({ status: 'archived', payload: { name: '舊封存' } }, '', 'current')).toBe(false);
    expect(campaignMatchesFilter({ status: 'ended', payload: { name: '舊活動' } }, '', 'history')).toBe(true);
  });
});
