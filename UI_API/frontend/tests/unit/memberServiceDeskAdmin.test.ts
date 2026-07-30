import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const frontendRoot = resolve(__dirname, '../..');
const adminHtml = readFileSync(resolve(frontendRoot, 'admin/admin.html'), 'utf8');
const adminJs = readFileSync(resolve(frontendRoot, 'admin/admin.js'), 'utf8');
const memberModule = readFileSync(resolve(frontendRoot, 'admin/modules/memberServiceDeskAdmin.js'), 'utf8');

describe('會員服務台', () => {
  it('以 server-side 搜尋分頁取代載入全部會員', () => {
    expect(memberModule).toContain('/api/v1/members?');
    expect(memberModule).toContain("page_size: String(pageSize)");
    expect(adminHtml).toContain('id="memberPaginationLabel"');
    expect(adminJs).not.toContain("fetch('/api/members'");
  });

  it('分開呈現會員確認與訂單推論資訊', () => {
    expect(memberModule).toContain('會員已確認的過敏資訊');
    expect(memberModule).toContain('由完成訂單推論的偏好');
    expect(memberModule).toContain('/verified-preferences');
    expect(memberModule).toContain("hasPermission('members.write')");
    expect(memberModule).toContain("hasPermission('members.delete')");
  });
});
