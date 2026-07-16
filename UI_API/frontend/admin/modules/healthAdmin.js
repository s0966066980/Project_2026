/** @typedef {Record<string, any>} AnyRecord */

/** @param {string | null | undefined} status */
function healthLabel(status) {
  if (status === 'ok') return '正常';
  if (status === 'degraded') return '異常';
  if (status === 'skipped') return '未啟用';
  if (status === 'failed' || status === 'not_ready') return '未就緒';
  if (status === 'ready') return '已就緒';
  return status || '未知';
}

export const HEALTH_SERVICE_GUIDE = Object.freeze({
  postgres: {
    label: 'PostgreSQL 商業資料庫',
    requirement: '正式環境必要',
    purpose: '保存會員、訂單、活動與營運資料，是 pilot / staging / production 的商業資料唯一來源。',
    impact: '不可用時不得以 JSON 靜默接手；正式結帳與管理寫入應停止並告警。',
    action: '確認 DATABASE_URL、migration 與資料庫連線。',
  },
  rag: {
    label: 'RAG / Chroma 知識索引',
    requirement: '選用，不阻擋結帳',
    purpose: '把管理員核准的知識提供給語音與推薦回答；Chroma 是查詢索引，來源文件才是可重建原始資料。',
    impact: '不可用時回答缺少補充知識，但點餐與結帳仍應繼續。',
    action: '在 RAG 知識庫確認來源選取、保存路徑與最後重建結果。',
  },
  rag_alerts: {
    label: 'RAG 維運警示',
    requirement: '使用 RAG 時建議',
    purpose: '記錄驗證失敗、部分重建失敗與 Chroma 健康異常，供管理員追蹤而不阻塞顧客流程。',
    impact: '警示未處理不會直接中斷服務，但可能代表索引內容過期或不完整。',
    action: '到 RAG 頁查看錯誤、知悉或解決警示。',
  },
  recommendation_events: {
    label: '推薦成效事件',
    requirement: '分析用，非即時必要',
    purpose: '保存曝光、點擊、加入購物車與成交事件，用來評估推薦是否有效。',
    impact: '不可用時推薦仍可運作，但無法可靠判斷成效或歸因。',
    action: '確認事件持久化來源與近期是否持續收到事件。',
  },
  runtime_logs: {
    label: 'Runtime 維運記錄',
    requirement: '維運建議',
    purpose: '保留脫敏後的執行與錯誤記錄，供故障排查、容量與保留週期檢查。',
    impact: '記錄異常通常不阻擋顧客流程，但會降低問題追查能力。',
    action: '檢查不可解析檔案、磁碟空間與 LOG_RETENTION_DAYS。',
  },
});

/** @param {AnyRecord} checks */
export function healthServiceView(checks = {}) {
  return Object.entries(HEALTH_SERVICE_GUIDE).map(([key, guide]) => {
    const check = checks[key] || {};
    let evidence = check.message || check.reason || '尚未取得檢查結果';
    if (key === 'postgres' && !check.message && !check.reason) evidence = `backend=${check.backend || '—'}；migration=${check.schema_migration_count ?? '—'}`;
    if (key === 'rag') evidence = `Chroma 文件 ${check.doc_count ?? 0} 筆；正式選取 ${check.selected_source_count ?? 0} 筆；collection=${check.collection_name || '—'}`;
    if (key === 'rag_alerts') evidence = `未處理 ${check.open_count ?? 0} 筆；已知悉 ${check.acknowledged_count ?? 0} 筆`;
    if (key === 'recommendation_events') evidence = `可讀取 ${check.sampled_records ?? 0} 筆；近期抽樣 ${check.recent_records ?? 0} 筆`;
    if (key === 'runtime_logs') evidence = `${Array.isArray(check.logs) ? check.logs.length : 0} 個檔案；保留 ${check.retention_days ?? 0} 天`;
    return { key, status: check.status || 'skipped', evidence, ...guide };
  });
}

/** @param {AnyRecord} readiness */
export function readinessView(readiness = {}) {
  /** @type {Record<string, [string, string]>} */
  const labels = {
    database: ['資料庫連線', '正式環境必須能連線，且不可回退到 JSON。'],
    migration: ['資料庫版本', '所有 forward migration 必須完整且順序一致。'],
    commercial_scope: ['商業資料範圍', '門市／租戶 scope 必須明確，避免跨店資料。'],
    shared_infrastructure: ['共用基礎設施', '多程序部署時確認 rate limit、session 與事件協調。'],
  };
  return Object.entries(readiness.required_checks || {}).map(([key, check]) => ({
    key,
    label: labels[key]?.[0] || key,
    purpose: labels[key]?.[1] || '應用程式啟動必要檢查。',
    status: check?.status || 'skipped',
    detail: check?.error_code || check?.reason || (check?.status === 'ok' ? '檢查通過' : '未提供細節'),
  }));
}

/** @param {unknown} size */
function formatBytes(size) {
  const value = Number(size || 0);
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

/** @param {string | number | Date | null | undefined} value */
function formatHealthTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-TW');
}

/**
 * @param {{
 *   apiBaseUrl: string,
 *   adminHeaders: () => Record<string, string>,
 *   getElement: (id: string) => HTMLElement | null,
 *   setText: (id: string, value: string) => void,
 *   escapeHtml: (value: any) => string,
 * }} options
 */
export function createHealthAdmin({
  apiBaseUrl,
  adminHeaders,
  getElement,
  setText,
  escapeHtml,
}) {
  /** @param {string | null | undefined} status */
  function healthPillHtml(status) {
    return `<span class="health-status-pill ${escapeHtml(status || 'skipped')}">${escapeHtml(healthLabel(status))}</span>`;
  }

  /** @param {AnyRecord} checks */
  function renderHealthRows(checks) {
    const box = getElement('healthCoreChecks');
    if (!box) return;
    box.innerHTML = healthServiceView(checks).map(row => `
      <article class="health-service-card">
        <div class="health-service-head"><b>${escapeHtml(row.label)}</b><span>${healthPillHtml(row.status)}<em>${escapeHtml(row.requirement)}</em></span></div>
        <p>${escapeHtml(row.purpose)}</p>
        <dl><div><dt>目前證據</dt><dd>${escapeHtml(row.evidence)}</dd></div><div><dt>故障影響</dt><dd>${escapeHtml(row.impact)}</dd></div><div><dt>建議處置</dt><dd>${escapeHtml(row.action)}</dd></div></dl>
      </article>
    `).join('');
  }

  /** @param {AnyRecord} readiness */
  function renderReadiness(readiness) {
    const box = getElement('healthReadinessChecks');
    if (!box) return;
    const rows = readinessView(readiness);
    box.innerHTML = rows.length ? rows.map(row => `
      <div class="health-readiness-row"><div><b>${escapeHtml(row.label)}</b><span>${escapeHtml(row.purpose)}</span></div><div>${healthPillHtml(row.status)}<small>${escapeHtml(row.detail)}</small></div></div>
    `).join('') : '<div class="adm-empty">尚未取得 readiness 檢查。</div>';
  }

  /** @param {AnyRecord[]} logs */
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

  /** @param {AnyRecord} data */
  function renderAdminHealth(data = {}) {
    const checks = data.checks || {};
    const status = data.status || 'skipped';
    const statusEl = getElement('healthOverallStatus');
    if (statusEl) {
      statusEl.className = `health-status-pill ${status}`;
      statusEl.textContent = `整體${healthLabel(status)}`;
    }
    setText('healthGeneratedAt', data.generated_at ? `更新時間：${formatHealthTime(data.generated_at)}` : '尚未載入');

    /** @type {AnyRecord[]} */
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
    renderReadiness(data.readiness || {});
    renderHealthLogs(runtimeLogs);
  }

  async function loadAdminHealth() {
    try {
      setText('healthGeneratedAt', '載入中…');
      const res = await fetch(`${apiBaseUrl}/api/admin/health`, { headers: adminHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      renderAdminHealth(await res.json());
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      const statusEl = getElement('healthOverallStatus');
      if (statusEl) {
        statusEl.className = 'health-status-pill degraded';
        statusEl.textContent = '載入失敗';
      }
      setText('healthGeneratedAt', `載入失敗：${message}`);
      renderHealthRows({
        postgres: { status: 'skipped', reason: 'not loaded' },
        rag: { status: 'skipped', doc_count: 0 },
        rag_alerts: { status: 'skipped', open_count: 0, acknowledged_count: 0 },
        recommendation_events: { status: 'skipped', sampled_records: 0 },
        runtime_logs: { status: 'degraded', retention_days: 0 },
      });
      renderReadiness({});
      renderHealthLogs([]);
    }
  }

  return {
    loadAdminHealth,
    renderAdminHealth,
  };
}
