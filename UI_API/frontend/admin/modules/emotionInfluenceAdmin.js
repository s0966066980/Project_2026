/** @typedef {Record<string, any>} EmotionLog */

const INFLUENCE_EVENT_TYPE = 'voice_llm_influence';
const MEDIA_ONLY_VARIANT = 'media_only';
const MEDIA_PLUS_STT_VARIANT = 'media_plus_stt';

/** @param {EmotionLog} row */
function rowTime(row) {
  const parsed = Date.parse(String(row.timestamp || ''));
  return Number.isFinite(parsed) ? parsed : Number(row.observed_at_ms || 0);
}

/** @param {unknown} value */
function nonnegativeNumber(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? Math.max(0, number) : 0;
}

/** @param {number} value @param {number} [digits] */
function rounded(value, digits = 0) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

/** @param {number[]} values @param {number} [digits] */
function average(values, digits = 0) {
  return values.length
    ? rounded(values.reduce((sum, value) => sum + value, 0) / values.length, digits)
    : 0;
}

/** @param {EmotionLog} row */
function descriptionLength(row) {
  const stored = Number(row.description_character_count);
  if (Number.isFinite(stored) && stored >= 0) return stored;
  return String(row.description || '').length;
}

/** @param {EmotionLog | null} current @param {EmotionLog} candidate */
function latestRow(current, candidate) {
  return !current || rowTime(candidate) >= rowTime(current) ? candidate : current;
}

/** @param {EmotionLog[]} rows */
function buildInputCohort(rows) {
  const successful = rows.filter(row => row.status === 'ok');
  const complete = successful.filter(row => row.emotion && row.intensity && row.facial && row.vocal);
  return {
    sampleCount: rows.length,
    successfulCount: successful.length,
    successRate: rows.length ? Math.round((successful.length / rows.length) * 100) : 0,
    completeCount: complete.length,
    completeRate: rows.length ? Math.round((complete.length / rows.length) * 100) : 0,
    averageLatencyMs: average(rows.map(row => nonnegativeNumber(row.evidence_latency_ms)).filter(Boolean)),
    averageDescriptionCharacters: average(rows.map(descriptionLength).filter(Boolean)),
  };
}

/**
 * Build same-recording A/B pairs and retain explicitly identified single-plan runs.
 * @param {EmotionLog[]} logs
 */
export function buildEmotionInfluenceViewModel(logs = []) {
  const rows = Array.isArray(logs) ? logs.filter(row => row && typeof row === 'object') : [];
  const analyses = rows.filter(row => (
    row.event_type === 'voice_mode_ended'
    && [MEDIA_ONLY_VARIANT, MEDIA_PLUS_STT_VARIANT].includes(String(row.analysis_variant || ''))
  ));
  const influences = rows.filter(row => row.event_type === INFLUENCE_EVENT_TYPE);
  const successfulAnalyses = analyses.filter(row => row.status === 'ok');
  const structurallyCompleteAnalyses = successfulAnalyses.filter(row => (
    row.emotion && row.intensity && row.facial && row.vocal && row.description
  ));
  const withStt = analyses.filter(row => row.analysis_variant === MEDIA_PLUS_STT_VARIANT);
  const mediaOnly = analyses.filter(row => row.analysis_variant === MEDIA_ONLY_VARIANT);

  /** @type {Map<string, {id: string, sessionId: string, timestamp: number, mediaOnly: EmotionLog | null, withStt: EmotionLog | null}>} */
  const pairMap = new Map();
  analyses.forEach(row => {
    const pairId = String(row.comparison_pair_id || '').trim();
    if (!pairId) return;
    const sessionId = String(row.session_id || '');
    const key = `${sessionId}\u0000${pairId}`;
    const pair = pairMap.get(key) || {
      id: pairId,
      sessionId,
      timestamp: 0,
      mediaOnly: null,
      withStt: null,
    };
    pair.timestamp = Math.max(pair.timestamp, rowTime(row));
    if (row.analysis_variant === MEDIA_ONLY_VARIANT) {
      pair.mediaOnly = latestRow(pair.mediaOnly, row);
    }
    if (row.analysis_variant === MEDIA_PLUS_STT_VARIANT) {
      pair.withStt = latestRow(pair.withStt, row);
    }
    pairMap.set(key, pair);
  });

  const pairs = [...pairMap.values()]
    .filter(pair => pair.mediaOnly && pair.withStt)
    .map(pair => {
      const media = /** @type {EmotionLog} */ (pair.mediaOnly);
      const stt = /** @type {EmotionLog} */ (pair.withStt);
      const influence = influences.find(row => (
        String(row.session_id || '') === pair.sessionId
        && (
          String(row.referenced_comparison_pair_id || '') === pair.id
          || (
            String(row.emotion_round_id || '') === String(stt.emotion_round_id || '')
            && String(row.voice_turn_id || '') === String(stt.voice_turn_id || '')
          )
        )
      )) || null;
      return {
        ...pair,
        mediaOnly: media,
        withStt: stt,
        influence,
        emotionChanged: Boolean(media.emotion && stt.emotion && media.emotion !== stt.emotion),
        intensityChanged: Boolean(media.intensity && stt.intensity && media.intensity !== stt.intensity),
        confidenceDelta: rounded(nonnegativeNumber(stt.confidence) - nonnegativeNumber(media.confidence), 2),
        latencyDeltaMs: rounded(nonnegativeNumber(stt.evidence_latency_ms) - nonnegativeNumber(media.evidence_latency_ms)),
        descriptionDelta: descriptionLength(stt) - descriptionLength(media),
      };
    })
    .sort((a, b) => b.timestamp - a.timestamp);
  const singleRuns = [...pairMap.values()]
    .filter(pair => Boolean(pair.mediaOnly) !== Boolean(pair.withStt))
    .sort((a, b) => b.timestamp - a.timestamp);

  const emotionChangedCount = pairs.filter(pair => pair.emotionChanged).length;
  const appliedCount = influences.filter(row => (
    row.influence_status === 'applied'
    && row.emotion_reference_used
    && [MEDIA_ONLY_VARIANT, MEDIA_PLUS_STT_VARIANT].includes(row.referenced_analysis_variant)
  )).length;
  const runCount = pairs.length + singleRuns.length;
  const confidenceDeltas = pairs.map(pair => pair.confidenceDelta);
  const latencyDeltas = pairs.map(pair => pair.latencyDeltaMs);
  const descriptionLengths = analyses.map(descriptionLength).filter(Boolean);
  /** @type {Map<string, {id: string, sessionId: string, timestamp: number, analyses: EmotionLog[]}>} */
  const roundMap = new Map();
  analyses.forEach(row => {
    const id = String(row.emotion_round_id || '').trim();
    if (!id) return;
    const sessionId = String(row.session_id || '');
    const key = `${sessionId}\u0000${id}`;
    const round = roundMap.get(key) || { id, sessionId, timestamp: 0, analyses: [] };
    round.timestamp = Math.max(round.timestamp, rowTime(row));
    round.analyses.push(row);
    roundMap.set(key, round);
  });
  const rounds = [...roundMap.values()]
    .map(round => ({ ...round, analyses: round.analyses.sort((a, b) => rowTime(b) - rowTime(a)) }))
    .sort((a, b) => b.timestamp - a.timestamp);
  return {
    analyses,
    influences,
    pairs,
    singleRuns,
    rounds,
    latestRound: rounds[0] || null,
    inputComparison: {
      withStt: buildInputCohort(withStt),
      mediaOnly: buildInputCohort(mediaOnly),
      paired: {
        sampleCount: pairs.length,
        emotionChangedCount,
        emotionChangedRate: pairs.length ? Math.round((emotionChangedCount / pairs.length) * 100) : 0,
        averageConfidenceDelta: average(confidenceDeltas, 2),
        averageLatencyDeltaMs: average(latencyDeltas),
      },
    },
    metrics: {
      analysisCount: analyses.length,
      successfulAnalysisCount: successfulAnalyses.length,
      structurallyCompleteAnalysisCount: structurallyCompleteAnalyses.length,
      pairCount: pairs.length,
      runCount,
      emotionChangedCount,
      averageConfidenceDelta: average(confidenceDeltas, 2),
      averageLatencyMs: average(analyses.map(row => nonnegativeNumber(row.evidence_latency_ms)).filter(Boolean)),
      descriptionAverage: average(descriptionLengths),
      descriptionMin: descriptionLengths.length ? Math.min(...descriptionLengths) : 0,
      descriptionMax: descriptionLengths.length ? Math.max(...descriptionLengths) : 0,
      influenceCount: influences.length,
      appliedCount,
      appliedRate: runCount ? Math.round((appliedCount / runCount) * 100) : 0,
      incompleteAnalysisCount: analyses.length - structurallyCompleteAnalyses.length,
      roundCount: rounds.length,
    },
  };
}

/**
 * @param {{
 *   getElement: (id: string) => HTMLElement | null,
 *   escapeHtml: (value: any) => string,
 *   emotionLabel: (value: any) => string,
 *   intensityLabel: (value: any) => string,
 *   providerLabel: (value: any) => string,
 * }} options
 */
export function createEmotionInfluenceAdmin({
  getElement,
  escapeHtml,
  emotionLabel,
  intensityLabel,
  providerLabel,
}) {
  /** @param {unknown} value */
  function formatTime(value) {
    const date = new Date(String(value || ''));
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-TW', { hour12: false });
  }

  /** @param {EmotionLog} row @param {string} title */
  function analysisHtml(row, title) {
    const emotion = emotionLabel(row.emotion) || '未辨識';
    const intensity = intensityLabel(row.intensity);
    const confidence = nonnegativeNumber(row.confidence);
    const latency = nonnegativeNumber(row.evidence_latency_ms);
    const description = String(row.description || '');
    const failed = row.status !== 'ok';
    const stateLabel = row.status === 'incomplete' ? '欄位不完整' : (failed ? '無可用結果' : '五欄完整');
    return `<section class="emotion-analysis-step"><div class="emotion-step-marker ${failed ? 'error' : 'ok'}" aria-hidden="true"></div><div class="emotion-step-card">
      <div class="emotion-step-head"><div><b>${escapeHtml(title)}</b><small>${escapeHtml(providerLabel(row.provider))}</small></div><span class="emotion-state-pill ${failed ? 'error' : 'ok'}">${stateLabel}</span></div>
      <div class="emotion-step-meta"><span>延遲 ${latency ? `${Math.round(latency)} ms` : '—'}</span><span>信心 ${confidence ? `${Math.round(confidence * 100)}%` : '—'}</span><span>描述 ${descriptionLength(row)} 字</span></div>
      <dl class="emotion-evidence-grid">
        <div><dt>情緒／強度</dt><dd>${escapeHtml(emotion)}${intensity ? `／${escapeHtml(intensity)}` : ''}</dd></div>
        <div><dt>表情</dt><dd>${escapeHtml(row.facial || '—')}</dd></div>
        <div><dt>語調</dt><dd>${escapeHtml(row.vocal || '—')}</dd></div>
        <div><dt>點餐重點</dt><dd>${escapeHtml(description || '—')}</dd></div>
      </dl>
    </div></section>`;
  }

  /** @param {ReturnType<typeof buildEmotionInfluenceViewModel>} view */
  function renderKpis(view) {
    const box = getElement('emotion-influence-kpis');
    if (!box) return;
    const metrics = view.metrics;
    const cards = [
      [String(metrics.roundCount), '有情緒紀錄的點餐輪', '依 emotion round 分組'],
      [String(metrics.analysisCount), '情緒分析總數', '只統計語音結束分析'],
      [String(metrics.structurallyCompleteAnalysisCount), '五欄完整', '情緒／強度、表情、語調、點餐重點'],
      [String(metrics.incompleteAnalysisCount), '需要重測', '缺少任一必要欄位即不採用'],
    ];
    box.innerHTML = cards.map(([value, label, hint]) => `<article class="emotion-influence-kpi"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span><small>${escapeHtml(hint)}</small></article>`).join('');
  }

  /** @param {ReturnType<typeof buildEmotionInfluenceViewModel>} view */
  function renderCustomerContext(view) {
    const box = getElement('emotion-customer-analysis-context');
    if (!box) return;
    const round = view.latestRound;
    const button = getElement('emotion-customer-analyze-btn');
    if (!round) {
      box.innerHTML = '<div class="emotion-influence-empty"><b>尚無本輪點餐情緒紀錄</b><p>完成語音點餐分析後即可測試客人現況。</p></div>';
      if (button && 'disabled' in button) button.disabled = true;
      return;
    }
    const completeCount = round.analyses.filter(row => row.status === 'ok' && row.emotion && row.intensity && row.facial && row.vocal && row.description).length;
    box.innerHTML = `<div class="emotion-customer-round"><b>最新本輪：${escapeHtml(round.id)}</b><span>${completeCount}/${round.analyses.length} 筆五欄完整，可供 LLM 測試</span></div>`;
    if (button && 'disabled' in button) button.disabled = completeCount === 0;
  }

  /** @param {ReturnType<typeof buildEmotionInfluenceViewModel>} view */
  function renderPairs(view) {
    const box = getElement('emotion-influence-rounds');
    if (!box) return;
    const round = view.latestRound;
    if (!round) {
      box.innerHTML = '<div class="emotion-influence-empty"><b>尚無情緒分析結果</b><p>完成一次語音點餐後，這裡會顯示所選方案的判讀。</p></div>';
      return;
    }
    box.innerHTML = `<article class="emotion-round-card"><header class="emotion-round-head"><div><span>本輪情緒證據</span><h3>${escapeHtml(round.id)}</h3></div><small>${escapeHtml(formatTime(round.timestamp))}</small></header><div class="emotion-round-turns"><div class="emotion-pair-variants">${round.analyses.map((row, index) => analysisHtml(row, `情緒分析 ${index + 1}`)).join('')}</div></div></article>`;
  }

  /** @param {EmotionLog[]} logs */
  function render(logs = []) {
    const view = buildEmotionInfluenceViewModel(logs);
    renderKpis(view);
    renderCustomerContext(view);
    renderPairs(view);
    return view;
  }

  function renderLoading() {
    const kpis = getElement('emotion-influence-kpis');
    const comparison = getElement('emotion-customer-analysis-context');
    const pairs = getElement('emotion-influence-rounds');
    if (kpis) kpis.innerHTML = '<div class="emotion-influence-loading">正在彙整配對分析…</div>';
    if (comparison) comparison.innerHTML = '<div class="emotion-influence-loading">正在整理本輪情緒證據…</div>';
    if (pairs) pairs.innerHTML = '<div class="emotion-influence-loading">載入配對結果…</div>';
  }

  /** @param {unknown} error */
  function renderError(error) {
    const message = error instanceof Error ? error.message : String(error || '未知錯誤');
    const comparison = getElement('emotion-customer-analysis-context');
    const pairs = getElement('emotion-influence-rounds');
    if (comparison) comparison.innerHTML = '<div class="emotion-influence-empty error">無法載入本輪情緒證據。</div>';
    if (pairs) pairs.innerHTML = `<div class="emotion-influence-empty error"><b>配對結果載入失敗</b><p>${escapeHtml(message)}</p></div>`;
  }

  return { render, renderLoading, renderError };
}
