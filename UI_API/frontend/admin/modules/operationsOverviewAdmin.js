/** @typedef {{data: any, error: string, loading: boolean, updatedAt: number | null}} OverviewSource */

/** @param {OverviewSource} state @param {boolean} allowed */
function visibleSource(state, allowed) {
  if (!allowed) return null;
  return state;
}

/** @param {string} label @param {OverviewSource} source */
function staleDetail(label, source) {
  if (!source.updatedAt) return `${label}無可用快照`;
  const time = new Date(source.updatedAt).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
  return `${label}保留 ${time} 成功快照`;
}

/**
 * Build presentation state without touching the DOM.
 * @param {{
 *   canReadStats: boolean,
 *   canReadRecommendations: boolean,
 *   stats: {data: any, error: string, loading: boolean, updatedAt: number | null},
 *   recommendations: {data: any, error: string, loading: boolean, updatedAt: number | null}
 * }} input
 */
export function buildOperationsOverviewView({
  canReadStats,
  canReadRecommendations,
  stats,
  recommendations,
}) {
  const visibleStats = visibleSource(stats, canReadStats);
  const visibleRecommendations = visibleSource(recommendations, canReadRecommendations);
  /** @type {OverviewSource[]} */
  const visible = [];
  if (visibleStats) visible.push(visibleStats);
  if (visibleRecommendations) visible.push(visibleRecommendations);
  const waiting = visible.some(source => source.loading || (!source.data && !source.error));
  const failed = visible.some(source => source.error);
  const recommendation = visibleRecommendations?.data;
  const limited = Boolean(recommendation?.provisional);
  const sentences = [];
  const staleDetails = [];
  if (visibleStats?.error) staleDetails.push(staleDetail('營運統計', visibleStats));
  if (visibleRecommendations?.error) staleDetails.push(staleDetail('推薦成效', visibleRecommendations));

  if (visibleStats?.data && !recommendation) {
    sentences.push(
      `本期共有 ${Number(visibleStats.data.total || 0).toLocaleString('zh-TW')} 次推播，`
      + `${Number(visibleStats.data.success || 0).toLocaleString('zh-TW')} 次帶動加購。`,
    );
  }
  if (recommendation) {
    /** @type {Record<string, string>} */
    const statusHeadlines = {
      insufficient_data: '今天的推薦資料還不足，先持續觀察。',
      on_target: '今天的推薦表現已達標。',
      below_purchase_target: '今天的推薦購買率未達目標。',
      high_ignore_rate: '今天的推薦購買率達標，但忽略率偏高。',
      below_target_and_high_ignore: '今天的推薦購買率與忽略率都需要留意。',
    };
    const targetStatus = String(recommendation.targetStatus || '');
    sentences.push(statusHeadlines[targetStatus]
      || `今天推薦被看見 ${Number(recommendation.impressions || 0).toLocaleString('zh-TW')} 次。`);
  }

  let detail = '請稍後重新整理，或請管理員確認查看權限。';
  let action = failed ? `部分來源更新失敗：${staleDetails.join('、')}。` : '可從下方推播概況開始查看。';
  if (recommendation) {
    const purchaseRate = Number(recommendation.purchaseRate || 0);
    const purchaseTarget = Number(recommendation.purchaseRateTarget || 0);
    const ignoreRate = Number(recommendation.ignoreRate || 0);
    const ignoreGuardrail = Number(recommendation.ignoreRateGuardrail || 0);
    detail = `購買率 ${Math.round(purchaseRate * 1000) / 10}%（目標 ${Math.round(purchaseTarget * 1000) / 10}%），`
      + `忽略率 ${Math.round(ignoreRate * 1000) / 10}%（警戒 ${Math.round(ignoreGuardrail * 1000) / 10}%）。`;
    if (failed) {
      action = `部分來源更新失敗：${staleDetails.join('、')}。`;
    } else if (recommendation.provisional) {
      action = '精準成效暫時無法載入，目前數字只用來看趨勢。';
    } else if (recommendation.targetStatus === 'insufficient_data') {
      action = '系統提醒目前樣本不足，先繼續收集，不用急著調整推薦策略。';
    } else if (recommendation.targetStatus === 'below_target_and_high_ignore') {
      action = '先檢查忽略率最高的推薦入口、商品供應與活動內容，再調整推薦策略。';
    } else if (recommendation.targetStatus === 'high_ignore_rate') {
      action = '先查看忽略率最高的推薦入口，確認商品、價格與出現時機是否合適。';
    } else if (recommendation.targetStatus === 'below_purchase_target') {
      action = '先比較各推薦入口的購買率，找出未帶動完成購買的畫面。';
    } else {
      action = '目前表現符合目標，持續留意忽略率與樣本量即可。';
    }
  } else if (visibleStats?.data) {
    detail = `推播成功率為 ${Math.round(Number(visibleStats.data.successRate || 0) * 100)}%。`;
  }

  if (!visible.length) {
    return {
      tone: 'ready',
      status: '沒有總覽權限',
      headline: '目前沒有可顯示的營運資料。',
      detail,
      action: '請管理員確認你的營運與推薦成效查看權限。',
      metrics: [],
    };
  }

  const needsAttention = recommendation && !['on_target', 'insufficient_data'].includes(recommendation.targetStatus);
  return {
    tone: failed || limited || needsAttention ? 'attention' : waiting ? 'loading' : 'ready',
    status: failed ? '部分資料未更新' : limited ? '暫用趨勢資料' : waiting ? '正在整理資料' : '資料已更新',
    headline: sentences.join(' ') || '目前沒有可顯示的營運資料。',
    detail,
    action,
    metrics: recommendation ? [
      { label: '有效曝光', value: Number(recommendation.impressions || 0).toLocaleString('zh-TW'), hint: '今天去重後的推薦曝光' },
      { label: '完成購買', value: Number(recommendation.purchases || 0).toLocaleString('zh-TW'), hint: '可歸因的完成訂單品項' },
      { label: '購買率', value: `${Math.round(Number(recommendation.purchaseRate || 0) * 1000) / 10}%`, hint: `主管目標 ${Math.round(Number(recommendation.purchaseRateTarget || 0) * 1000) / 10}%` },
      { label: '忽略率', value: `${Math.round(Number(recommendation.ignoreRate || 0) * 1000) / 10}%`, hint: `警戒值 ${Math.round(Number(recommendation.ignoreRateGuardrail || 0) * 1000) / 10}%` },
    ] : [],
  };
}

/**
 * @param {{
 *   getElement: (id: string) => any,
 *   hasPermission: (permission: string) => boolean,
 *   loadStats: () => Promise<any>,
 *   loadRecommendations: () => Promise<any>,
 *   now?: () => number
 * }} options
 */
export function createOperationsOverviewAdmin({
  getElement,
  hasPermission,
  loadStats,
  loadRecommendations,
  now = () => Date.now(),
}) {
  /** @type {Record<'stats' | 'recommendations', OverviewSource>} */
  const sources = {
    stats: { data: null, error: '', loading: false, updatedAt: null },
    recommendations: { data: null, error: '', loading: false, updatedAt: null },
  };
  /** @type {Promise<PromiseSettledResult<any>[]> | undefined} */
  let refreshPromise;

  function render() {
    const status = getElement('operationsInsightStatus');
    const headline = getElement('operationsInsightHeadline');
    const detail = getElement('operationsInsightDetail');
    const action = getElement('operationsInsightAction');
    const metrics = getElement('operationsTodayMetrics');
    if (!status || !headline || !detail || !action) return;
    const view = buildOperationsOverviewView({
      canReadStats: hasPermission('operations.read'),
      canReadRecommendations: hasPermission('recommendations.effectiveness.read'),
      stats: sources.stats,
      recommendations: sources.recommendations,
    });
    status.className = `operations-insight-status ${view.tone}`;
    status.textContent = view.status;
    headline.textContent = view.headline;
    detail.textContent = view.detail;
    action.textContent = view.action;
    if (metrics) {
      metrics.textContent = '';
      view.metrics?.forEach(metric => {
        const card = document.createElement('div');
        card.className = 'operations-today-metric';
        const value = document.createElement('b');
        const label = document.createElement('span');
        const hint = document.createElement('small');
        value.textContent = metric.value;
        label.textContent = metric.label;
        hint.textContent = metric.hint;
        card.append(value, label, hint);
        metrics.appendChild(card);
      });
      metrics.hidden = !view.metrics?.length;
    }
  }

  /** @param {'stats' | 'recommendations'} name @param {any} summary */
  function updateSource(name, summary) {
    if (summary?.error) return failSource(name, summary.message || '載入失敗');
    sources[name].data = summary;
    sources[name].error = '';
    sources[name].updatedAt = now();
    render();
  }

  /** @param {'stats' | 'recommendations'} name @param {unknown} error */
  function failSource(name, error) {
    sources[name].error = error instanceof Error ? error.message : String(error || '載入失敗');
    render();
  }

  /** @param {any} summary */
  function updateStats(summary) {
    updateSource('stats', summary);
  }

  /** @param {any} summary */
  function updateRecommendations(summary) {
    updateSource('recommendations', summary);
  }

  async function refresh() {
    if (refreshPromise) return refreshPromise;
    const tasks = [];
    if (hasPermission('operations.read')) {
      sources.stats.loading = true;
      tasks.push(
        Promise.resolve().then(loadStats).catch(error => failSource('stats', error)).finally(() => {
          sources.stats.loading = false;
        }),
      );
    }
    if (hasPermission('recommendations.effectiveness.read')) {
      sources.recommendations.loading = true;
      tasks.push(
        Promise.resolve().then(loadRecommendations).catch(error => failSource('recommendations', error)).finally(() => {
          sources.recommendations.loading = false;
        }),
      );
    }
    render();
    refreshPromise = Promise.allSettled(tasks).finally(() => {
      refreshPromise = undefined;
      render();
    });
    return refreshPromise;
  }

  return {
    render,
    refresh,
    updateStats,
    updateRecommendations,
    failStats: /** @param {unknown} error */ error => failSource('stats', error),
    failRecommendations: /** @param {unknown} error */ error => failSource('recommendations', error),
  };
}
