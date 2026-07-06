function healthLabel(status) {
  if (status === 'ok') return '正常';
  if (status === 'degraded') return '異常';
  if (status === 'skipped') return '略過';
  return status || '未知';
}

function formatBytes(size) {
  const value = Number(size || 0);
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

function formatHealthTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-TW');
}

export function createHealthAdmin({
  apiBaseUrl,
  adminHeaders,
  getElement,
  setText,
  escapeHtml,
}) {
  function healthPillHtml(status) {
    return `<span class="health-status-pill ${escapeHtml(status || 'skipped')}">${escapeHtml(healthLabel(status))}</span>`;
  }

  function renderHealthRows(checks) {
    const box = getElement('healthCoreChecks');
    if (!box) return;
    const rows = [
      ['PostgreSQL', checks.postgres?.status, checks.postgres?.message || checks.postgres?.reason || `backend: ${checks.postgres?.backend || '—'}`],
      ['RAG / Chroma', checks.rag?.status, `文件 ${checks.rag?.doc_count ?? 0} 筆`],
      ['RAG Alerts', checks.rag_alerts?.status, `open ${checks.rag_alerts?.open_count ?? 0} / ack ${checks.rag_alerts?.acknowledged_count ?? 0}`],
      ['推薦事件', checks.recommendation_events?.status, `sample ${checks.recommendation_events?.sampled_records ?? 0}`],
      ['Runtime Logs', checks.runtime_logs?.status, `保留 ${checks.runtime_logs?.retention_days ?? 0} 天`],
    ];
    box.innerHTML = rows.map(([label, status, detail]) => `
      <div class="health-row">
        <b>${escapeHtml(label)}</b>
        <span>${healthPillHtml(status)} ${escapeHtml(detail)}</span>
      </div>
    `).join('');
  }

  function renderHealthLogs(logs = []) {
    const box = getElement('healthRuntimeLogs');
    if (!box) return;
    const rows = Array.isArray(logs) ? logs : [];
    if (!rows.length) {
      box.innerHTML = '<div class="adm-empty">尚無 runtime log 檔案。</div>';
      return;
    }
    box.innerHTML = rows.map(row => `
      <div class="health-log-item">
        <b title="${escapeHtml(row.name || '')}">${escapeHtml(row.name || 'unknown')}</b>
        <span>${Number(row.records || 0)}</span>
        <span>${escapeHtml(formatBytes(row.size_bytes))}</span>
      </div>
    `).join('');
  }

  function renderAdminHealth(data = {}) {
    const checks = data.checks || {};
    const status = data.status || 'skipped';
    const statusEl = getElement('healthOverallStatus');
    if (statusEl) {
      statusEl.className = `health-status-pill ${status}`;
      statusEl.textContent = `整體${healthLabel(status)}`;
    }
    setText('healthGeneratedAt', data.generated_at ? `更新時間：${formatHealthTime(data.generated_at)}` : '尚未載入');

    const runtimeLogs = checks.runtime_logs?.logs || [];
    const totalLogRecords = runtimeLogs.reduce((sum, row) => sum + Number(row.records || 0), 0);
    const kpis = [
      ['整體狀態', healthLabel(status), data.app?.environment || 'environment'],
      ['資料庫', healthLabel(checks.postgres?.status), data.app?.member_storage_backend || 'storage'],
      ['RAG 文件', checks.rag?.doc_count ?? 0, healthLabel(checks.rag?.status)],
      ['Open Alerts', checks.rag_alerts?.open_count ?? 0, 'RAG alerts'],
      ['Runtime Records', totalLogRecords, `${runtimeLogs.length} files`],
    ];
    const kpiBox = getElement('healthKpis');
    if (kpiBox) {
      kpiBox.innerHTML = kpis.map(([label, value, hint]) => `
        <div class="health-kpi"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span><small>${escapeHtml(hint)}</small></div>
      `).join('');
    }
    renderHealthRows(checks);
    renderHealthLogs(runtimeLogs);
  }

  async function loadAdminHealth() {
    try {
      setText('healthGeneratedAt', '載入中…');
      const res = await fetch(`${apiBaseUrl}/api/admin/health`, { headers: adminHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      renderAdminHealth(await res.json());
    } catch (e) {
      const statusEl = getElement('healthOverallStatus');
      if (statusEl) {
        statusEl.className = 'health-status-pill degraded';
        statusEl.textContent = '載入失敗';
      }
      setText('healthGeneratedAt', `載入失敗：${e.message}`);
      renderHealthRows({
        postgres: { status: 'skipped', reason: 'not loaded' },
        rag: { status: 'skipped', doc_count: 0 },
        rag_alerts: { status: 'skipped', open_count: 0, acknowledged_count: 0 },
        recommendation_events: { status: 'skipped', sampled_records: 0 },
        runtime_logs: { status: 'degraded', retention_days: 0 },
      });
      renderHealthLogs([]);
    }
  }

  return {
    loadAdminHealth,
    renderAdminHealth,
  };
}
