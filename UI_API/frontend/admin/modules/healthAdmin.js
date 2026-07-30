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
    label: 'Runtime Persistence Profile',
    requirement: '所有 durable records 必要',
    purpose: '驗證實際 database adapter、去敏 endpoint、PostgreSQL 版本、schema、拓撲與 capability coverage。',
    impact: '不可用時不得切換 SQLite 或 JSON；需要 durable transaction 的操作必須停止。',
    action: '確認 DATABASE_BACKEND、DATABASE_TOPOLOGY、secret file、migration 與資料庫連線。',
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
    action: '確認最後事件時間、事件持久化來源與顧客流程是否真的有送出事件。',
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
    if (key === 'postgres' && !check.message && !check.reason) {
      const endpoint = check.endpoint || {};
      const connection = check.connection || {};
      const schema = check.schema || {};
      const coverage = check.adapter_coverage || {};
      evidence = `backend=${check.effective_backend || '—'}；topology=${check.topology || '—'}；endpoint=${endpoint.fingerprint || '—'}；PostgreSQL=${connection.server_major || '—'}；schema=${schema.head || '—'}；coverage=${coverage.covered ?? 0}/${coverage.registered ?? 0}`;
    }
    if (key === 'rag') evidence = `Chroma 文件 ${check.doc_count ?? 0} 筆；正式選取 ${check.selected_source_count ?? 0} 筆；collection=${check.collection_name || '—'}`;
    if (key === 'rag_alerts') evidence = `未處理 ${check.open_count ?? 0} 筆；已知悉 ${check.acknowledged_count ?? 0} 筆`;
    if (key === 'recommendation_events') evidence = `可讀取 ${check.sampled_records ?? 0} 筆；最新抽樣 ${check.latest_sampled_records ?? 0} 筆；最後事件 ${check.latest_event_at || '尚無有效時間'}`;
    if (key === 'runtime_logs') evidence = `${Array.isArray(check.logs) ? check.logs.length : 0} 個檔案；保留 ${check.retention_days ?? 0} 天`;
    return { key, status: check.status || 'skipped', evidence, ...guide };
  });
}

/** @param {AnyRecord} readiness */
export function readinessView(readiness = {}) {
  /** @type {Record<string, [string, string]>} */
  const labels = {
    database: ['Runtime Persistence Profile', '驗證有效 adapter、連線、PostgreSQL 18、拓撲與 capability coverage，且不可回退到其他儲存。'],
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

/** @param {AnyRecord} operational */
export function operationalHealthView(operational = {}) {
  /** @type {Record<string, {tone: string, label: string}>} */
  const states = {
    safe_to_operate: { tone: 'ok', label: '可以正常營運' },
    operate_with_degraded_features: { tone: 'degraded', label: '可以營運，但部分功能降級' },
    unsafe_to_operate: { tone: 'not_ready', label: '不可安全營運' },
  };
  /** @type {Record<string, string>} */
  const capabilityLabels = {
    available: '可用',
    degraded: '降級',
    unavailable: '不可用',
  };
  const current = states[operational.state] || { tone: 'skipped', label: '狀態未知' };
  return {
    ...current,
    headline: operational.headline || current.label,
    businessImpact: operational.business_impact || '尚未取得營運影響。',
    capabilities: (operational.capabilities || []).map(/** @param {AnyRecord} capability */ capability => ({
      ...capability,
      statusLabel: capabilityLabels[capability.status] || '未知',
    })),
    incidents: Array.isArray(operational.incidents) ? operational.incidents : [],
  };
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
 *   hasPermission?: (permission: string) => boolean,
 * }} options
 */
export function createHealthAdmin({
  apiBaseUrl,
  adminHeaders,
  getElement,
  setText,
  escapeHtml,
  hasPermission = () => false,
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

  /** @param {AnyRecord} operational */
  function renderOperational(operational) {
    const view = operationalHealthView(operational);
    const summary = getElement('healthOperationalSummary');
    if (summary) {
      summary.className = `health-operational-summary ${view.tone}`;
      summary.innerHTML = `<div><span>${escapeHtml(view.label)}</span><h2>${escapeHtml(view.headline)}</h2><p>${escapeHtml(view.businessImpact)}</p></div>`;
    }
    const capabilityBox = getElement('healthCapabilities');
    if (capabilityBox) {
      capabilityBox.innerHTML = view.capabilities.map(/** @param {AnyRecord} capability */ capability => `
        <div class="health-capability ${escapeHtml(capability.status)}">
          <b>${escapeHtml(capability.label)}</b><span>${escapeHtml(capability.statusLabel)}</span>
        </div>
      `).join('');
    }
    const incidentsBox = getElement('healthIncidents');
    if (!incidentsBox) return;
    if (!view.incidents.length) {
      incidentsBox.innerHTML = '<div class="adm-empty">目前沒有需要處理的營運事件。</div>';
      return;
    }
    const canAct = hasPermission('operations.write');
    incidentsBox.innerHTML = view.incidents.map(/** @param {AnyRecord} incident */ incident => `
      <article class="health-incident ${escapeHtml(incident.severity || 'warning')}">
        <div class="health-incident-head"><div><span>${incident.severity === 'critical' ? '必要功能' : '降級功能'}</span><b>${escapeHtml(incident.title)}</b></div><em>${escapeHtml(incident.status === 'escalated' ? '已升級' : incident.status === 'acknowledged' ? '已確認' : '待處理')}</em></div>
        <p><strong>營運影響</strong>${escapeHtml(incident.impact)}</p>
        <p><strong>建議檢查</strong>${escapeHtml(incident.suggested_action)}</p>
        <p><strong>負責角色</strong>${escapeHtml(incident.owner)}</p>
        ${canAct ? `<div class="health-incident-actions"><button type="button" data-health-action="acknowledge" data-incident-id="${escapeHtml(incident.incident_id)}">確認收到</button><button type="button" data-health-action="escalate" data-incident-id="${escapeHtml(incident.incident_id)}">升級處理</button></div>` : ''}
      </article>
    `).join('');
    incidentsBox.querySelectorAll('[data-health-action]').forEach(button => {
      button.addEventListener('click', () => performIncidentAction(
        button.getAttribute('data-incident-id') || '',
        button.getAttribute('data-health-action') || '',
      ).catch(error => {
        setText('healthGeneratedAt', error instanceof Error ? error.message : String(error));
      }));
    });
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
    renderOperational(data.operational || {});
    renderReadiness(data.readiness || {});
    renderHealthLogs(runtimeLogs);
  }

  /** @param {string} incidentId @param {string} action */
  async function performIncidentAction(incidentId, action) {
    if (!incidentId || !['acknowledge', 'escalate'].includes(action)) return;
    const res = await fetch(`${apiBaseUrl}/api/admin/health/incidents/${encodeURIComponent(incidentId)}/${action}`, {
      method: 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: '' }),
    });
    if (!res.ok) throw new Error(`事件更新失敗：HTTP ${res.status}`);
    renderAdminHealth(await res.json());
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
      renderOperational({
        state: 'unsafe_to_operate',
        headline: '無法取得維運健康資料',
        business_impact: '請通知值班技術人員確認後台連線；不要從此頁執行破壞性操作。',
        capabilities: [],
        incidents: [],
      });
      renderReadiness({});
      renderHealthLogs([]);
    }
  }

  return {
    loadAdminHealth,
    performIncidentAction,
    renderAdminHealth,
  };
}
