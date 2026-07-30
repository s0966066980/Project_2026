import { describe, expect, it } from 'vitest';

import {
  adminLoginErrorMessage,
  llmTestErrorMessage,
} from '../../admin/features/apiErrors.js';

describe('Admin API error messages', () => {
  it('separates network failures from invalid manager credentials', () => {
    expect(adminLoginErrorMessage(0)).toContain('API 服務');
    expect(adminLoginErrorMessage(401)).toContain('主管密碼錯誤');
    expect(adminLoginErrorMessage(403)).toContain('沒有主管權限');
  });

  it('separates expired manager access from LLM provider failures', () => {
    expect(llmTestErrorMessage(0)).toContain('API 服務');
    expect(llmTestErrorMessage(401)).toContain('主管登入已失效');
    expect(llmTestErrorMessage(403)).toContain('LLM 測試權限');
    expect(llmTestErrorMessage(503)).toContain('LLM 服務暫時不可用');
  });
});
