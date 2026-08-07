// @ts-check

/**
 * The four counts Batch P1 shows a store manager, each rendered with what it means.
 *
 * Every one of them excludes something a reader would otherwise assume was included,
 * so the caveat is part of the metric rather than a footnote somewhere else. The
 * server sends the definitions with the values; this module never writes its own.
 */

/** @typedef {{voice_turns_completed: number, recommendations_shown: number, campaign_cta_clicks: number, confirmed_order_amount: number, currency: string, window_days?: number, definitions: Record<string, string>}} OperationsOverviewData */
/** @typedef {{data: OperationsOverviewData | null, error: string, loading: boolean, updatedAt: number | null}} OverviewSource */

const METRIC_ORDER = /** @type {Array<[keyof OperationsOverviewData, string]>} */ ([
  ['voice_turns_completed', '語音成功'],
  ['recommendations_shown', '推薦次數'],
  ['campaign_cta_clicks', '活動點擊'],
  ['confirmed_order_amount', '已確認訂單金額'],
]);

/** @param {number} value */
function count(value) {
  return Number(value || 0).toLocaleString('zh-TW');
}

/** @param {number} value @param {string} currency */
function amount(value, currency) {
  return `${currency || 'TWD'} ${Number(value || 0).toLocaleString('zh-TW')}`;
}

/** @param {OverviewSource} source */
function lastSnapshot(source) {
  if (!source.updatedAt) return '沒有可用的快照';
  const time = new Date(source.updatedAt).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
  return `顯示 ${time} 的快照`;
}

/**
 * Build presentation state without touching the DOM.
 *
 * @param {{canRead: boolean, overview: OverviewSource}} input
 */
export function buildOperationsOverviewView({ canRead, overview }) {
  if (!canRead) {
    return {
      tone: 'ready',
      status: '沒有總覽權限',
      headline: '目前沒有可顯示的營運資料。',
      detail: '請管理員確認你的營運資料查看權限。',
      metrics: /** @type {Array<{label: string, value: string, hint: string}>} */ ([]),
    };
  }

  const data = overview.data;
  const windowLabel = data?.window_days === 1 ? '過去 24 小時' : `過去 ${Number(data?.window_days || 1)} 天`;

  if (overview.error) {
    return {
      tone: 'attention',
      status: '資料未更新',
      headline: data ? `${windowLabel}的數字可能已過時。` : '目前無法取得營運資料。',
      // A stale number presented as current is worse than an empty panel, so the
      // failure and the age of what is on screen are both stated.
      detail: `${overview.error}。${lastSnapshot(overview)}。`,
      metrics: data ? buildMetrics(data) : [],
    };
  }

  if (!data) {
    return {
      tone: 'loading',
      status: '正在整理資料',
      headline: '正在讀取營運總覽…',
      detail: '',
      metrics: [],
    };
  }

  return {
    tone: 'ready',
    status: '資料已更新',
    headline: `${windowLabel}的門市營運狀況。`,
    detail: '每個數字的計算範圍列在各自下方。',
    metrics: buildMetrics(data),
  };
}

/** @param {OperationsOverviewData} data */
function buildMetrics(data) {
  return METRIC_ORDER.map(([key, label]) => ({
    label,
    value: key === 'confirmed_order_amount'
      ? amount(Number(data[key]), String(data.currency || 'TWD'))
      : count(Number(data[key])),
    hint: String(data.definitions?.[String(key)] || ''),
  }));
}

/**
 * @param {{
 *   getElement: (id: string) => any,
 *   hasPermission: (permission: string) => boolean,
 *   loadOverview: () => Promise<OperationsOverviewData>,
 *   now?: () => number
 * }} options
 */
export function createOperationsOverviewAdmin({
  getElement,
  hasPermission,
  loadOverview,
  now = () => Date.now(),
}) {
  /** @type {OverviewSource} */
  const overview = { data: null, error: '', loading: false, updatedAt: null };
  /** @type {Promise<void> | undefined} */
  let refreshPromise;

  function render() {
    const status = getElement('operationsInsightStatus');
    const headline = getElement('operationsInsightHeadline');
    const detail = getElement('operationsInsightDetail');
    const metrics = getElement('operationsTodayMetrics');
    if (!status || !headline || !detail) return;

    const view = buildOperationsOverviewView({
      canRead: hasPermission('analytics.read'),
      overview,
    });
    status.className = `operations-insight-status ${view.tone}`;
    status.textContent = view.status;
    headline.textContent = view.headline;
    detail.textContent = view.detail;
    if (!metrics) return;
    metrics.textContent = '';
    view.metrics.forEach(entry => {
      const card = document.createElement('div');
      card.className = 'operations-today-metric';
      const value = document.createElement('b');
      const label = document.createElement('span');
      const hint = document.createElement('small');
      value.textContent = entry.value;
      label.textContent = entry.label;
      hint.textContent = entry.hint;
      card.append(value, label, hint);
      metrics.appendChild(card);
    });
  }

  async function refresh() {
    if (refreshPromise) return refreshPromise;
    if (!hasPermission('analytics.read')) {
      render();
      return;
    }
    overview.loading = true;
    render();
    refreshPromise = (async () => {
      try {
        overview.data = await loadOverview();
        overview.error = '';
        overview.updatedAt = now();
      } catch (error) {
        // The previous snapshot is deliberately kept so the panel can say how old
        // it is instead of going blank on a single failed poll.
        overview.error = error instanceof Error ? error.message : String(error || '讀取失敗');
      } finally {
        overview.loading = false;
        refreshPromise = undefined;
        render();
      }
    })();
    return refreshPromise;
  }

  return { render, refresh };
}
