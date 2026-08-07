// @ts-check

/**
 * Maintenance health: can a customer order right now, and if not, which service.
 *
 * Batch P1 removed the database topology, schema head, adapter coverage, runtime
 * log inventory and alert backlog this panel used to show. Those describe the
 * inside of the system; an operator standing at a stalled kiosk needs to know
 * which dependency stopped answering and how slow it is.
 */

/** @typedef {{key: string, label: string, status: string, latency_ms: number | null, observed_at: string, safe_error: string}} ServiceStatus */

/** @type {Record<string, string>} */
const STATUS_LABELS = {
  ok: '正常',
  degraded: '降級',
  down: '無回應',
  unknown: '未觀測',
  not_configured: '未設定',
};

/** @param {string} status */
export function healthLabel(status) {
  return STATUS_LABELS[String(status || '')] || '未知';
}

/** @param {number | null} latency */
function latencyText(latency) {
  return latency == null ? '—' : `${Number(latency).toLocaleString('zh-TW')} ms`;
}

/** @param {string} value */
function observedText(value) {
  if (!value) return '尚未觀測';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString('zh-TW');
}

/**
 * Build the rows without touching the DOM.
 *
 * @param {ServiceStatus[]} services
 */
export function serviceHealthView(services = []) {
  return services.map(service => ({
    key: service.key,
    label: service.label,
    status: service.status,
    statusLabel: healthLabel(service.status),
    latency: latencyText(service.latency_ms ?? null),
    observedAt: observedText(service.observed_at),
    safeError: service.safe_error || '',
  }));
}

/**
 * A single sentence an operator can act on.
 *
 * @param {ServiceStatus[]} services
 */
export function serviceHealthSummary(services = []) {
  if (!services.length) return { tone: 'skipped', headline: '尚未取得服務狀態。' };
  const down = services.filter(service => service.status === 'down');
  const degraded = services.filter(service => service.status === 'degraded');
  // Unconfigured is not a fault: the deployment simply does not run that service,
  // and reporting it as an outage would send someone to fix nothing.
  const unknown = services.filter(service => service.status === 'unknown');

  if (down.length) {
    return { tone: 'not_ready', headline: `${down.map(service => service.label).join('、')}沒有回應。` };
  }
  if (degraded.length) {
    return { tone: 'degraded', headline: `${degraded.map(service => service.label).join('、')}回應變慢或有錯誤。` };
  }
  if (unknown.length) {
    return { tone: 'skipped', headline: `${unknown.map(service => service.label).join('、')}尚未觀測到狀態。` };
  }
  return { tone: 'ok', headline: '四項服務都正常回應。' };
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
  /** @param {string} status */
  function pill(status) {
    return `<span class="health-status-pill ${escapeHtml(status || 'unknown')}">${escapeHtml(healthLabel(status))}</span>`;
  }

  /** @param {ServiceStatus[]} services */
  function render(services) {
    const box = getElement('healthCoreChecks');
    const summary = serviceHealthSummary(services);
    const statusEl = getElement('healthOverallStatus');
    if (statusEl) {
      statusEl.className = `health-status-pill ${summary.tone}`;
      statusEl.textContent = summary.headline;
    }
    if (!box) return;
    box.innerHTML = serviceHealthView(services).map(row => `
      <article class="health-service-card">
        <div class="health-service-head"><b>${escapeHtml(row.label)}</b>${pill(row.status)}</div>
        <dl>
          <div><dt>延遲</dt><dd>${escapeHtml(row.latency)}</dd></div>
          <div><dt>觀測時間</dt><dd>${escapeHtml(row.observedAt)}</dd></div>
          ${row.safeError ? `<div><dt>錯誤</dt><dd>${escapeHtml(row.safeError)}</dd></div>` : ''}
        </dl>
      </article>
    `).join('');
  }

  async function loadAdminHealth() {
    if (!hasPermission('operations.read')) {
      setText('healthGeneratedAt', '沒有維運健康查看權限');
      return;
    }
    try {
      const res = await fetch(`${apiBaseUrl}/api/v1/operations/service-health`, { headers: adminHeaders() });
      if (!res.ok) throw new Error(`維運健康讀取失敗（${res.status}）`);
      const body = await res.json();
      const services = /** @type {ServiceStatus[]} */ (body?.data?.services || []);
      render(services);
      setText('healthGeneratedAt', `更新於 ${new Date().toLocaleTimeString('zh-TW')}`);
    } catch (error) {
      const statusEl = getElement('healthOverallStatus');
      if (statusEl) {
        statusEl.className = 'health-status-pill not_ready';
        statusEl.textContent = error instanceof Error ? error.message : '維運健康讀取失敗';
      }
      setText('healthGeneratedAt', '本次更新失敗');
    }
  }

  return { loadAdminHealth, render };
}
