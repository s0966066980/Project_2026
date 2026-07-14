import {
  CAMPAIGN_PLACEMENT_LABELS as RECOMMENDATION_SURFACE_LABELS,
  RECOMMENDATION_EVENT_LABELS,
  RECOMMENDATION_REASON_LABELS,
  zhLabel,
} from './zhTWLabels.js';

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
  alertUser = message => window.alert(message),
  confirmAction = message => window.confirm(message),
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
    (effectivenessReport?.comparisons || []).forEach(comparison => {
      const difference = Math.round(Number(comparison.purchase_rate_difference || 0) * 1000) / 10;
      warnings.push(`${comparison.variant_id} 相較 ${comparison.control_variant} 的購買率觀察差異為 ${difference >= 0 ? '+' : ''}${difference} 個百分點；${comparison.conclusion}。`);
    });
    renderEffectivenessNotice(warnings.join(' '));
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
    const clicked = recommendationCount(counts, 'recommendation_clicked');
    const added = recommendationCount(counts, 'recommendation_added_to_cart');
    const checked = recommendationCount(counts, 'recommendation_checked_out');
    const ignored = recommendationCount(counts, 'recommendation_ignored');
    const report = effectivenessReport;
    const cards = report ? [
      ['有效曝光', report.impressions, '畫面可見至少 1 秒'],
      ['點擊', report.clicks, `${Math.round(Number(report.click_through_rate || 0) * 1000) / 10}% 曝光後點擊`],
      ['加入購物車', report.add_to_carts, `${Math.round(Number(report.add_to_cart_rate || 0) * 1000) / 10}% 曝光後加購`],
      ['完成購買', report.purchases, `${Math.round(Number(report.purchase_rate || 0) * 1000) / 10}% 曝光後購買`],
      ['歸因營收', formatMoney(report.attributed_revenue), '只計已完成訂單'],
      ['優惠金額', formatMoney(report.attributed_discount), '已完成訂單折扣'],
      ['資料待補', report.incomplete_events, '舊事件或欄位缺漏'],
    ] : [
      ['目前事件', events.length, '暫用舊事件統計'],
      ['曝光', shown, '有效曝光服務尚未載入'],
      ['點擊', clicked, recommendationRate(clicked, shown)],
      ['加入購物車', added, recommendationRate(added, shown)],
      ['完成購買', checked, recommendationRate(checked, shown)],
      ['忽略', ignored, recommendationRate(ignored, shown)],
      ['追蹤活動', Object.keys(stats.offerCounts).length, '活動數量'],
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
    box.innerHTML = '<div class="recommendation-row head"><b>名稱</b><span>曝</span><span>點</span><span>加</span><span>成</span><span>忽</span></div>'
      + rows.map(row => `<div class="recommendation-row" title="${escapeHtml(row.key)}">`
        + `<b>${escapeHtml(recommendationLabel(labelMap, row.key))}</b>`
        + `<span>${recommendationCount(row.counts, 'recommendation_shown')}</span>`
        + `<span>${recommendationCount(row.counts, 'recommendation_clicked')}</span>`
        + `<span>${recommendationCount(row.counts, 'recommendation_added_to_cart')}</span>`
        + `<span>${recommendationCount(row.counts, 'recommendation_checked_out')}</span>`
        + `<span>${recommendationCount(row.counts, 'recommendation_ignored')}</span>`
        + '</div>')
        .join('');
  }

  function renderRecommendationVariantRows(containerId, groupedCounts, emptyText) {
    const box = getElement(containerId);
    if (!box) return;
    const rows = Object.entries(groupedCounts || {})
      .map(([key, counts]) => ({
        key,
        counts,
        shown: recommendationCount(counts, 'recommendation_shown'),
        total: Object.values(counts || {}).reduce((sum, value) => sum + Number(value || 0), 0),
      }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 8);
    if (!rows.length) {
      box.innerHTML = `<div class="adm-empty">${escapeHtml(emptyText)}</div>`;
      return;
    }
    box.innerHTML = '<div class="recommendation-strategy-row head"><b>版本</b><span>曝</span><span>點</span><span>加</span><span>成</span><span>忽</span><span>成率</span></div>'
      + rows.map(row => {
        const checked = recommendationCount(row.counts, 'recommendation_checked_out');
        return `<div class="recommendation-strategy-row" title="${escapeHtml(row.key)}">`
          + `<b>${escapeHtml(row.key)}</b>`
          + `<span>${row.shown}</span>`
          + `<span>${recommendationCount(row.counts, 'recommendation_clicked')}</span>`
          + `<span>${recommendationCount(row.counts, 'recommendation_added_to_cart')}</span>`
          + `<span>${checked}</span>`
          + `<span>${recommendationCount(row.counts, 'recommendation_ignored')}</span>`
          + `<span>${recommendationRate(checked, row.shown)}</span>`
          + '</div>';
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
    renderRecommendationVariantRows('recommendationVariantStats', stats.variantCounts, '尚無策略版本資料。');
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
        if (body) body.innerHTML = `<tr><td colspan="9" class="adm-empty" style="color:#e84040">載入失敗：${escapeHtml(e.message)}</td></tr>`;
      }
    })().finally(() => {
      recommendationEventsLoadPromise = null;
    });
    return recommendationEventsLoadPromise;
  }

  async function clearRecommendationEvents() {
    if (!confirmAction('確定清除所有推薦事件？此操作無法還原。')) return;
    const btn = getElement('recommendationClearBtn');
    if (btn) btn.disabled = true;
    try {
      const res = await fetch(`${apiBaseUrl}/api/recommendation_events`, { method: 'DELETE', headers: adminHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      recommendationDashboardEvents = [];
      renderRecommendationSurfaceOptions([]);
      renderRecommendationDashboard();
    } catch (e) {
      alertUser(`清除失敗：${e.message}`);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  return {
    loadRecommendationEvents,
    clearRecommendationEvents,
    renderRecommendationDashboard,
  };
}
