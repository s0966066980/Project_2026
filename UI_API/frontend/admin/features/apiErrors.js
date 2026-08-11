// @ts-check

/**
 * Return a bounded Traditional Chinese message for Admin LLM diagnostic APIs.
 *
 * @param {number} status
 * @returns {string}
 */
export function llmTestErrorMessage(status) {
  if (!status) return '無法連線至 API 服務，請確認後端已啟動。';
  if (status === 401) return '裝置驗證已失效，請完成裝置設定後再試。';
  if (status === 403) return '此裝置沒有 Admin LLM 測試權限。';
  if (status === 422) return 'LLM 測試資料格式錯誤，請重新整理頁面後再試。';
  if (status === 429) return 'LLM 測試請求過於頻繁，請稍後再試。';
  if (status >= 500) return `LLM 服務暫時不可用（HTTP ${status}），請稍後再試。`;
  return `LLM 請求失敗（HTTP ${status}），請稍後再試。`;
}
