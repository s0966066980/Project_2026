import {
  CAMPAIGN_PLACEMENT_LABELS as RECOMMENDATION_SURFACE_LABELS,
  RECOMMENDATION_EVENT_LABELS,
  RECOMMENDATION_REASON_LABELS,
  zhLabel,
} from './zhTWLabels.js';
import { strategyComparisonView } from './recommendationStrategyComparison.js';

function recommendationLabel(map, key) {
  return zhLabel(map, key, '其他／未分類');
}

function recommendationCount(counts, eventType) {
  return Number(counts?.[eventType] || 0);
}

function recommendationRate(part, total) {
  const denom = Number(total || 0);
  if (!denom) return '0%';
  return `${Math.round((Number(part || 0) / denom) * 1000) / 10}%`;
}

function recommendationOfferIds(event) {
  const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {};
  const raw = metadata.offer_ids || metadata.offer_id || event?.offer_ids || [];
  const rows = Array.isArray(raw) ? raw : String(raw || '').split(',');
  return rows.map(row => String(row || '').trim()).filter(Boolean);
}

function recommendationMetadata(event) {
  return event?.metadata && typeof event.metadata === 'object' ? event.metadata : {};
}

function recommendationVariantKey(event) {
  const metadata = recommendationMetadata(event);
  const experimentId = String(metadata.experiment_id || event?.experiment_id || '').trim();
  const variantId = String(metadata.variant_id || event?.variant_id || '').trim();
  if (!variantId) return '';
  return experimentId ? `${experimentId}:${variantId}` : variantId;
}

function buildRecommendationStats(events) {
  const typeCounts = {};
  const surfaceCounts = {};
  const sourceCounts = {};
  const offerCounts = {};
  const variantCounts = {};
  events.forEach(event => {
    if (!event || typeof event !== 'object') return;
    const eventType = String(event.event_type || 'unknown');
    const surface = String(event.surface || 'unknown');
    const source = String(event.source || 'unknown');
    typeCounts[eventType] = (typeCounts[eventType] || 0) + 1;
    surfaceCounts[surface] = surfaceCounts[surface] || {};
    surfaceCounts[surface][eventType] = (surfaceCounts[surface][eventType] || 0) + 1;
    sourceCounts[source] = sourceCounts[source] || {};
    sourceCounts[source][eventType] = (sourceCounts[source][eventType] || 0) + 1;
    recommendationOfferIds(event).forEach(offerId => {
      offerCounts[offerId] = offerCounts[offerId] || {};
      offerCounts[offerId][eventType] = (offerCounts[offerId][eventType] || 0) + 1;
    });
    const variantKey = recommendationVariantKey(event);
    if (variantKey) {
      variantCounts[variantKey] = variantCounts[variantKey] || {};
      variantCounts[variantKey][eventType] = (variantCounts[variantKey][eventType] || 0) + 1;
    }
  });
  return { typeCounts, surfaceCounts, sourceCounts, offerCounts, variantCounts };
}

function eventTagClass(eventType) {
  if (eventType === 'recommendation_checked_out') return 'recommendation-tag checked';
  if (eventType === 'recommendation_ignored') return 'recommendation-tag ignored';
  return 'recommendation-tag';
}

export function createRecommendationEventsAdmin({
  apiBaseUrl,
  adminHeaders,
  getElement,
  getValue,
  escapeHtml,
  formatDate,
  loadMenu,
  menuName,
  onSummary = () => {},
}) {
  let recommendationEventsLoadPromise = null;
  let recommendationDashboardEvents = [];
  let effectivenessReport = null;

  function formatMoney(value) {
    return `$${Number(value || 0).toLocaleString('zh-TW')}`;
  }

  function renderEffectivenessNotice(message = '', isError = false) {
    const box = getElement('recommendationEffectivenessNotice');
    if (!box) return;
    box.textContent = message;
    box.classList.toggle('error', isError);
    box.hidden = !message;
  }

  async function loadEffectiveness() {
    const params = new URLSearchParams();
    const surface = getValue('recommendationSurfaceFilter');
    const audience = getValue('recommendationAudienceFilter');
    const since = getValue('recommendationSince');
    const until = getValue('recommendationUntil');
    if (surface) params.set('placement', surface);
    if (audience) params.set('audience', audience);
    if (since) params.set('since', `${since}T00:00:00+08:00`);
    if (until) params.set('until', `${until}T23:59:59+08:00`);
    const res = await fetch(`${apiBaseUrl}/api/v1/recommendation-effectiveness?${params.toString()}`, {
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`成效服務回應 ${res.status}`);
    const payload = await res.json();
    effectivenessReport = payload?.data || null;
    const warnings = [];
    if (effectivenessReport?.sample_warning) warnings.push(effectivenessReport.sample_warning);
    if (effectivenessReport?.incomplete_events) {
      warnings.push(`${effectivenessReport.incomplete_events} 筆舊事件缺少完整追蹤編號，未納入精準歸因。`);
    }
    if (effectivenessReport?.provisional_attributions) {
      warnings.push(`${effectivenessReport.provisional_attributions} 筆訂單尚未完成，營收暫不計入。`);
    }
    strategyComparisonView(effectivenessReport).forEach(comparison => {
      const difference = comparison.differencePoints;
      warnings.push(`${comparison.variantLabel} 相較 ${comparison.controlLabel} 的購買率觀察差異為 ${difference >= 0 ? '+' : ''}${difference} 個百分點；${comparison.conclusion}。`);
    });
    renderEffectivenessNotice(warnings.join(' '));
  }

  async function loadTodaySummary() {
    const now = new Date();
    const start = new Date(now);
    start.setHours(0, 0, 0, 0);
    const params = new URLSearchParams({
      since: start.toISOString(),
      until: now.toISOString(),
    });
    const res = await fetch(`${apiBaseUrl}/api/v1/recommendation-effectiveness?${params.toString()}`, {
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`成效服務回應 ${res.status}`);
    const payload = await res.json();
    const report = payload?.data || {};
    const summary = {
      impressions: Number(report.impressions || 0),
      purchases: Number(report.purchases || 0),
      ignored: Number(report.ignored || 0),
      purchaseRate: Number(report.purchase_rate || 0),
      ignoreRate: Number(report.ignore_rate || 0),
      sampleWarning: String(report.sample_warning || ''),
    };
    onSummary(summary);
    return summary;
  }

  function filteredRecommendationEvents() {
    const eventType = getValue('recommendationEventTypeFilter');
    const surface = getValue('recommendationSurfaceFilter');
    const audience = getValue('recommendationAudienceFilter');
    const sessionQuery = getValue('recommendationSessionFilter').toLowerCase();
    return recommendationDashboardEvents.filter(event => {
      if (eventType && event.event_type !== eventType) return false;
      if (surface && event.surface !== surface) return false;
      const eventAudience = event.is_member || event.audience === 'member' ? 'member' : 'guest';
      if (audience && eventAudience !== audience) return false;
      if (sessionQuery && !String(event.session_id || '').toLowerCase().includes(sessionQuery)) return false;
      return true;
    });
  }

  function renderRecommendationKpis(events, stats) {
    const box = getElement('recommendationKpis');
    if (!box) return;
    const counts = stats.typeCounts;
    const shown = recommendationCount(counts, 'recommendation_shown');
    const added = recommendationCount(counts, 'recommendation_added_to_cart');
    const checked = recommendationCount(counts, 'recommendation_checked_out');
    const report = effectivenessReport;
    const cards = report ? [
      ['有效曝光', report.impressions, '在畫面上看到至少 1 秒'],
      ['完成購買', report.purchases, '由推薦歸因的已完成訂單'],
      ['購買率', `${Math.round(Number(report.purchase_rate || 0) * 1000) / 10}%`, '有效曝光後完成購買'],
      ['推薦營收', formatMoney(report.attributed_revenue), '只計已完成訂單'],
    ] : [
      ['曝光', shown, '有效曝光服務尚未載入'],
      ['加入購物車', added, recommendationRate(added, shown)],
      ['完成購買', checked, recommendationRate(checked, shown)],
      ['觀察購買率', recommendationRate(checked, shown), `${events.length} 筆舊事件資料`],
    ];
    box.innerHTML = cards
      .map(([label, value, sub]) => `<div class="recommendation-kpi"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span><small>${escapeHtml(sub)}</small></div>`)
      .join('');

  }

  function renderRecommendationCountRows(containerId, groupedCounts, labelMap, emptyText) {
    const box = getElement(containerId);
    if (!box) return;
    const rows = Object.entries(groupedCounts || {})
      .map(([key, counts]) => ({
        key,
        counts,
        total: Object.values(counts || {}).reduce((sum, value) => sum + Number(value || 0), 0),
      }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 8);
    if (!rows.length) {
      box.innerHTML = `<div class="adm-empty">${escapeHtml(emptyText)}</div>`;
      return;
    }
    box.innerHTML = '<div class="recommendation-row head"><b>名稱</b><span>有效曝光</span><span>點擊推薦</span><span>加入購物車</span><span>完成購買</span><span>忽略推薦</span></div>'
      + rows.map(row => '<div class="recommendation-row">'
        + `<b>${escapeHtml(recommendationLabel(labelMap, row.key))}</b>`
        + `<span>${recommendationCount(row.counts, 'recommendation_shown')}</span>`
        + `<span>${recommendationCount(row.counts, 'recommendation_clicked')}</span>`
        + `<span>${recommendationCount(row.counts, 'recommendation_added_to_cart')}</span>`
        + `<span>${recommendationCount(row.counts, 'recommendation_checked_out')}</span>`
        + `<span>${recommendationCount(row.counts, 'recommendation_ignored')}</span>`
        + '</div>')
        .join('');
  }

  function renderRecommendationVariantRows(containerId, report) {
    const box = getElement(containerId);
    if (!box) return;
    if (!report) {
      box.innerHTML = '<div class="adm-empty">精準成效載入後才會顯示策略差異。</div>';
      return;
    }
    const rows = strategyComparisonView(report);
    if (!rows.length) {
      box.innerHTML = '<div class="adm-empty">尚未啟用策略實驗或只有一個分組，因此沒有版本差異。</div>';
      return;
    }
    box.innerHTML = rows.map(row => {
      const difference = `${row.differencePoints >= 0 ? '+' : ''}${row.differencePoints} 個百分點`;
      const tone = row.differencePoints > 0 ? 'positive' : (row.differencePoints < 0 ? 'negative' : 'neutral');
      return '<article class="recommendation-comparison">'
        + `<div class="recommendation-comparison-head"><b>${escapeHtml(row.variantLabel)} <span>對照</span> ${escapeHtml(row.controlLabel)}</b><strong class="${tone}">${escapeHtml(difference)}</strong></div>`
        + '<div class="recommendation-comparison-metrics">'
        + `<span><small>${escapeHtml(row.controlLabel)}購買率</small><b>${row.controlRate}%</b><em>${row.controlSample} 次有效曝光</em></span>`
        + `<span><small>${escapeHtml(row.variantLabel)}購買率</small><b>${row.variantRate}%</b><em>${row.variantSample} 次有效曝光</em></span>`
        + '</div>'
        + `<p>${escapeHtml(row.conclusion || '僅顯示觀察差異。')}</p>`
        + '</article>';
    }).join('');
  }

  function renderRecommendationSurfaceOptions(events) {
    const select = getElement('recommendationSurfaceFilter');
    if (!select) return;
    const current = select.value;
    const surfaces = [...new Set(events.map(event => String(event.surface || '')).filter(Boolean))].sort();
    select.textContent = '';
    const all = document.createElement('option');
    all.value = '';
    all.textContent = '全部入口';
    select.appendChild(all);
    surfaces.forEach(surface => {
      const option = document.createElement('option');
      option.value = surface;
      option.textContent = recommendationLabel(RECOMMENDATION_SURFACE_LABELS, surface);
      option.selected = surface === current;
      select.appendChild(option);
    });
  }

  function renderRecommendationEventTable(events) {
    const body = getElement('recommendationEventBody');
    if (!body) return;
    const summary = getElement('recommendationEventSummary');
    if (summary) summary.textContent = `顯示 ${events.length} 筆 / 載入 ${recommendationDashboardEvents.length} 筆`;
    if (!events.length) {
      body.innerHTML = '<tr><td colspan="9" class="adm-empty">沒有符合條件的推薦事件。</td></tr>';
      return;
    }
    body.innerHTML = events
      .slice()
      .sort((a, b) => String(b.timestamp || '').localeCompare(String(a.timestamp || '')))
      .slice(0, 200)
      .map(event => {
        const offerText = recommendationOfferIds(event).join(', ') || '—';
        const reasons = Array.isArray(event.reasons)
          ? event.reasons.slice(0, 2).map(reason => recommendationLabel(RECOMMENDATION_REASON_LABELS, reason)).join('、')
          : '';
        const audience = event.is_member || event.audience === 'member' ? 'member' : 'guest';
        return '<tr>'
          + `<td>${escapeHtml(formatDate(event.timestamp))}</td>`
          + `<td style="font-family:monospace;color:#8494b0">…${escapeHtml(String(event.session_id || '').slice(-8))}</td>`
          + `<td><span class="recommendation-tag ${audience}">${audience === 'member' ? '會員' : '訪客'}</span></td>`
          + `<td><span class="${eventTagClass(event.event_type)}">${escapeHtml(recommendationLabel(RECOMMENDATION_EVENT_LABELS, event.event_type))}</span></td>`
          + `<td>${escapeHtml(recommendationLabel(RECOMMENDATION_SURFACE_LABELS, event.surface))}</td>`
          + `<td>${escapeHtml(recommendationLabel(RECOMMENDATION_SURFACE_LABELS, event.source))}</td>`
          + `<td>${escapeHtml(event.item_name || menuName(event.item_id) || event.item_id || '—')}</td>`
          + `<td style="font-family:monospace;color:#5a6a8a">${escapeHtml(offerText)}</td>`
          + `<td class="recommendation-muted">${escapeHtml(reasons || '—')}</td>`
          + '</tr>';
      })
      .join('');
  }

  function renderRecommendationDashboard() {
    const events = filteredRecommendationEvents();
    const stats = buildRecommendationStats(events);
    renderRecommendationKpis(events, stats);
    renderRecommendationCountRows('recommendationSurfaceStats', stats.surfaceCounts, RECOMMENDATION_SURFACE_LABELS, '尚無推薦入口資料。');
    renderRecommendationCountRows('recommendationSourceStats', stats.sourceCounts, RECOMMENDATION_SURFACE_LABELS, '尚無推薦來源資料。');
    renderRecommendationCountRows('recommendationOfferStats', stats.offerCounts, {}, '尚無 offer 追蹤資料。');
    renderRecommendationVariantRows('recommendationVariantStats', effectivenessReport);
    renderRecommendationEventTable(events);
  }

  async function loadRecommendationEvents() {
    if (recommendationEventsLoadPromise) return recommendationEventsLoadPromise;
    recommendationEventsLoadPromise = (async () => {
      const body = getElement('recommendationEventBody');
      if (body) body.innerHTML = '<tr><td colspan="9" class="adm-empty">載入中…</td></tr>';
      try {
        await loadMenu();
        const limit = getValue('recommendationLimit') || '200';
        const params = new URLSearchParams({ limit });
        const sessionId = getValue('recommendationSessionFilter');
        if (sessionId) params.set('session_id', sessionId);
        const [res, effectivenessResult] = await Promise.all([
          fetch(`${apiBaseUrl}/api/v1/recommendations?page=1&page_size=${Math.min(Number(limit) || 100, 100)}`, { headers: adminHeaders() }),
          loadEffectiveness().then(() => null).catch(error => error),
        ]);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        recommendationDashboardEvents = Array.isArray(data.data) ? data.data : [];
        if (effectivenessResult instanceof Error) {
          effectivenessReport = null;
          renderEffectivenessNotice(`精準成效暫時無法載入：${effectivenessResult.message}。下方改顯示舊事件趨勢。`, true);
        }
        renderRecommendationSurfaceOptions(recommendationDashboardEvents);
        renderRecommendationDashboard();
      } catch (e) {
        recommendationDashboardEvents = [];
        effectivenessReport = null;
        onSummary({ error: true });
        if (body) body.innerHTML = `<tr><td colspan="9" class="adm-empty" style="color:#e84040">載入失敗：${escapeHtml(e.message)}</td></tr>`;
      }
    })().finally(() => {
      recommendationEventsLoadPromise = null;
    });
    return recommendationEventsLoadPromise;
  }

  return {
    loadTodaySummary,
    loadRecommendationEvents,
    renderRecommendationDashboard,
  };
}
