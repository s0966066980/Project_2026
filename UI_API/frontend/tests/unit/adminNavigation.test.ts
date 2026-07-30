import { describe, expect, it } from 'vitest';

import { canViewAdminPage } from '../../admin/modules/adminNavigation.js';
import { RECOMMENDATION_REASON_LABELS, zhLabel } from '../../admin/modules/zhTWLabels.js';

describe('管理後台權限導覽', () => {
  it('一般活動人員只會取得被授權的工作頁面', () => {
    const permissions = ['campaigns.read', 'campaigns.write', 'catalog.availability.read'];

    expect(canViewAdminPage(permissions, 'promotions')).toBe(true);
    expect(canViewAdminPage(permissions, 'availability')).toBe(true);
    expect(canViewAdminPage(permissions, 'settings')).toBe(false);
    expect(canViewAdminPage(permissions, 'health')).toBe(false);
  });

  it('未知內部代碼不會直接顯示給員工', () => {
    expect(zhLabel(RECOMMENDATION_REASON_LABELS, 'member_usual')).toBe('會員常點');
    expect(zhLabel(RECOMMENDATION_REASON_LABELS, 'internal_function_x')).toBe('未知項目');
  });

  it('推薦成效人員可從整併後的營運總覽查看資料', () => {
    const permissions = ['recommendations.effectiveness.read'];

    expect(canViewAdminPage(permissions, 'stats')).toBe(true);
  });

  it('營運讀取人員看得到健康狀態，但不因此取得系統測試頁', () => {
    const permissions = ['operations.read'];

    expect(canViewAdminPage(permissions, 'health')).toBe(true);
    expect(canViewAdminPage(permissions, 'test')).toBe(false);
  });

  it('受限管理員只看到被授權的營運總覽與供應狀態', () => {
    const permissions = [
      'recommendations.effectiveness.read',
      'catalog.availability.read',
      'catalog.availability.write',
    ];

    expect(canViewAdminPage(permissions, 'stats')).toBe(true);
    expect(canViewAdminPage(permissions, 'availability')).toBe(true);
    expect(canViewAdminPage(permissions, 'health')).toBe(false);
    expect(canViewAdminPage(permissions, 'members')).toBe(false);
    expect(canViewAdminPage(permissions, 'rag')).toBe(false);
    expect(canViewAdminPage(permissions, 'settings')).toBe(false);
  });
});
