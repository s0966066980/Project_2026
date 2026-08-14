const text = value => String(value ?? '').trim();

const TERMINAL_LABELS = Object.freeze({
  completed: '完成',
  transcription_failed: 'STT 失敗',
  assistant_failed: '助理失敗',
  playback_failed: '播放失敗',
});

const RAG_LABELS = Object.freeze({ hit: '命中', miss: '未命中', not_run: '尚未執行' });

function formatTime(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? text(value) || '—' : parsed.toLocaleString('zh-TW', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

/**
 * The evidence rows as the Admin browser shows them: metadata only, never
 * conversation text.
 *
 * Typed because `records = []` alone infers `never[]`, which rejects every
 * real row a caller passes.
 *
 * @param {{
 *   records?: Record<string, any>[],
 *   page?: Record<string, any>,
 *   reconciliation?: Record<string, any>,
 *   error?: string,
 *   loading?: boolean,
 * }} [input]
 */
export function buildVoiceEvidenceView({ records = [], page = {}, reconciliation = {}, error = '', loading = false } = {}) {
  const rows = (records || []).map(record => ({
    evidenceId: text(record.evidence_id),
    voiceTurnId: text(record.voice_turn_id) || '—',
    observedAt: formatTime(record.observed_at),
    terminal: TERMINAL_LABELS[text(record.terminal_status)] || text(record.terminal_status) || '未知',
    failure: text(record.failure_type) || '—',
    rag: RAG_LABELS[text(record.rag_outcome)] || '未知',
    content: record.has_transcript || record.has_assistant_text ? '已保留去識別化內容' : '無文字內容',
    projection: text(record.projection_status) === 'projected' ? '已同步' : '待同步',
  }));
  const reconciliationStatus = text(reconciliation?.status);
  const reconciliationMessage = {
    awaiting_projection: `已有 ${Number(reconciliation?.awaiting_projection || 0)} 筆語音回合已接受，正在等待同步。`,
    permanent_projection_failure: `有 ${Number(reconciliation?.permanent_projection_failure || 0)} 筆語音回合投影失敗，請檢查服務後重試。`,
  }[reconciliationStatus] || '';
  return {
    rows,
    empty: !loading && !error && rows.length === 0 && !reconciliationMessage,
    emptyLabel: '選定日期沒有可顯示的語音紀錄。若剛完成語音回合，請稍後重新整理。',
    status: error ? `語音紀錄查詢失敗：${text(error)}；請重新整理或稍後再試。` : loading ? '正在讀取語音紀錄…' : reconciliationMessage,
    statusTone: error || reconciliationStatus === 'permanent_projection_failure' ? 'attention' : loading ? 'loading' : '',
    hasMore: Boolean(page?.has_more),
  };
}

function element(root, id) {
  return root?.getElementById?.(id) || document.getElementById(id);
}

function localDayBounds(day) {
  const start = new Date(`${day}T00:00:00`);
  const end = new Date(start.getTime() + 24 * 60 * 60 * 1000);
  return { observed_from: start.toISOString(), observed_to: end.toISOString() };
}

export function createVoiceEvidenceAdmin({ client, root = document } = {}) {
  const state = { records: [], page: {}, reconciliation: {}, error: '', loading: false, cursor: null };

  function selectedDay() {
    return text(element(root, 'voiceEvidenceDate')?.value) || new Date().toISOString().slice(0, 10);
  }

  function render() {
    const view = buildVoiceEvidenceView(state);
    const status = element(root, 'voiceEvidenceStatus');
    if (status) {
      status.textContent = view.status;
      status.className = `voice-evidence-status${view.statusTone ? ` ${view.statusTone}` : ''}`;
    }
    const body = element(root, 'voiceEvidenceBody');
    if (body) {
      body.innerHTML = view.rows.map(row => `
        <tr>
          <td>${row.observedAt}</td>
          <td><code>${row.voiceTurnId}</code></td>
          <td>${row.terminal}</td>
          <td>${row.failure}</td>
          <td>${row.rag}</td>
          <td>${row.content}</td>
          <td>${row.projection}</td>
        </tr>`).join('') || `<tr><td colspan="7" class="adm-empty">${view.emptyLabel}</td></tr>`;
    }
    const more = element(root, 'voiceEvidenceLoadMore');
    if (more) more.hidden = !view.hasMore;
  }

  async function refresh({ append = false } = {}) {
    if (!append) {
      state.records = [];
      state.cursor = null;
    }
    state.loading = true;
    state.error = '';
    render();
    try {
      const response = await client.list({
        ...localDayBounds(selectedDay()),
        terminal_status: text(element(root, 'voiceEvidenceTerminalFilter')?.value),
        failure_type: text(element(root, 'voiceEvidenceFailureFilter')?.value),
        rag_outcome: text(element(root, 'voiceEvidenceRagFilter')?.value),
        limit: 50,
        ...(state.cursor || {}),
      });
      state.records = append ? [...state.records, ...(response.records || [])] : (response.records || []);
      state.page = response.page || {};
      state.reconciliation = response.reconciliation || {};
      state.cursor = state.page.next_cursor || null;
    } catch (error) {
      state.error = error?.message || String(error);
      state.page = {};
    } finally {
      state.loading = false;
      render();
    }
  }

  function bind() {
    const date = element(root, 'voiceEvidenceDate');
    if (date && !date.value) date.value = new Date().toISOString().slice(0, 10);
    element(root, 'voiceEvidenceRefresh')?.addEventListener('click', () => refresh());
    element(root, 'voiceEvidenceLoadMore')?.addEventListener('click', () => refresh({ append: true }));
    ['voiceEvidenceDate', 'voiceEvidenceTerminalFilter', 'voiceEvidenceFailureFilter', 'voiceEvidenceRagFilter']
      .forEach(id => element(root, id)?.addEventListener('change', () => refresh()));
  }

  return { bind, refresh, render, getState: () => ({ ...state }) };
}
