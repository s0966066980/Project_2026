// @ts-check

/**
 * @param {{status?: number, requestId?: string, message?: string}|unknown} error
 */
export function describeEmotionApiError(error) {
  const value = /** @type {{status?: number, requestId?: string, message?: string}} */ (error || {});
  const status = Number(value.status || 0);
  const suffix = value.requestId ? `（Request ID: ${value.requestId}）` : '';
  if (!status) return `無法連線至服務，請確認後端狀態後重試${suffix}`;
  if (status === 401) return `裝置驗證已失效，請完成裝置設定後重試${suffix}`;
  if (status === 403) return `此裝置沒有執行情緒分析的權限${suffix}`;
  if (status === 422) return `請求格式不正確，請檢查設定值或錄製內容${suffix}`;
  if (status === 429) return `分析請求過於頻繁，請稍後重試${suffix}`;
  if (status === 503) return `模型服務尚未就緒，請確認 R1-Omni 與 GPU 狀態${suffix}`;
  if (status >= 500) return `情緒分析服務暫時失敗（HTTP ${status}）${suffix}`;
  return `情緒分析請求失敗（HTTP ${status}）${suffix}`;
}

/**
 * @param {{name?: string, message?: string}|unknown} error
 * @param {'camera'|'microphone'|'recorder'|'media'|string} [source]
 */
export function classifyEmotionMediaError(error, source = 'media') {
  const value = /** @type {{name?: string}} */ (error || {});
  if (value.name === 'EmptyMediaError') return '錄製內容為空，沒有可分析的影音，請重新錄製。';
  if (source === 'recorder' || value.name === 'NotSupportedError') return '此瀏覽器不支援需要的影音錄製格式，請改用最新版 Chrome 或 Edge。';
  const device = source === 'microphone' ? '麥克風' : source === 'camera' ? '攝影機' : '攝影機與麥克風';
  if (value.name === 'NotFoundError' || value.name === 'DevicesNotFoundError') return `找不到可用的${device}，請確認裝置已連接。`;
  if (value.name === 'NotAllowedError' || value.name === 'PermissionDeniedError') return `${device}權限被拒絕，請在瀏覽器網站設定中允許後重試。`;
  if (value.name === 'NotReadableError' || value.name === 'TrackStartError') return `${device}目前被其他程式占用，請關閉占用程式後重試。`;
  return `無法啟用${device}，請檢查裝置與瀏覽器權限後重試。`;
}

/**
 * Parse JSON while preserving HTTP status and request ID for actionable UI errors.
 * @param {Response|any} response
 */
export async function parseEmotionResponse(response) {
  /** @type {Record<string, any>} */
  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  if (!response.ok) {
    const requestId = response.headers?.get?.('x-request-id') || data?.request_id || '';
    const error = new Error(String(data?.detail || data?.message || `HTTP ${response.status}`));
    Object.assign(error, { status: response.status, requestId });
    throw error;
  }
  return data;
}

/**
 * Load each section independently so one unavailable endpoint never blanks the
 * rest of the console.
 *
 * @param {{
 *   requests: Record<string, () => Promise<unknown>>,
 *   onState: (section: string, state: {status: 'loading'|'ready'|'error', data?: unknown, message?: string, error?: unknown}) => void
 * }} options
 */
export function createEmotionSectionLoader({ requests, onState }) {
  /** @param {string} section */
  async function refresh(section) {
    const request = requests[section];
    if (!request) return;
    onState(section, { status: 'loading' });
    try {
      const data = await request();
      onState(section, { status: 'ready', data });
    } catch (error) {
      onState(section, { status: 'error', message: describeEmotionApiError(error), error });
    }
  }

  async function refreshAll() {
    await Promise.all(Object.keys(requests).map(refresh));
  }

  return { refresh, refreshAll };
}
