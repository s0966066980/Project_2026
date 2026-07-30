// @ts-check

/**
 * Return a bounded Traditional Chinese message for manager-login failures.
 * Status 0 represents a network failure where no HTTP response was received.
 *
 * @param {number} status
 * @returns {string}
 */
export function adminLoginErrorMessage(status) {
  if (!status) return '無法連線至 API 服務，請確認後端已啟動。';
  if (status === 401) return '主管密碼錯誤，請重新輸入。';
  if (status === 403) return '此帳號沒有主管權限。';
  if (status === 422) return '登入資料格式錯誤，請重新整理頁面後再試。';
  if (status >= 500) return `登入服務暫時不可用（HTTP ${status}），請稍後再試。`;
  return `主管登入失敗（HTTP ${status}），請稍後再試。`;
}

/**
 * Return a bounded Traditional Chinese message for Admin LLM diagnostic APIs.
 *
 * @param {number} status
 * @returns {string}
 */
export function llmTestErrorMessage(status) {
  if (!status) return '無法連線至 API 服務，請確認後端已啟動。';
  if (status === 401) return '主管登入已失效，請重新解鎖主管模式後再試。';
  if (status === 403) return '目前帳號沒有主管 LLM 測試權限。';
  if (status === 422) return 'LLM 測試資料格式錯誤，請重新整理頁面後再試。';
  if (status === 429) return 'LLM 測試請求過於頻繁，請稍後再試。';
  if (status >= 500) return `LLM 服務暫時不可用（HTTP ${status}），請稍後再試。`;
  return `LLM 請求失敗（HTTP ${status}），請稍後再試。`;
}
