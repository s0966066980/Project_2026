const AVAILABILITY_STATUS_LABELS = {
  normal: '正常',
  low_stock: '低庫存',
  sold_out: '售罄',
  disabled: '停用',
};

function availabilityStatusLabel(status) {
  return AVAILABILITY_STATUS_LABELS[status] || AVAILABILITY_STATUS_LABELS.normal;
}

export function createAvailabilityAdmin({
  apiBaseUrl,
  adminHeaders,
  getElement,
  getValue,
  setValue,
  escapeHtml,
  alertUser = message => window.alert(message),
}) {
  let availabilityRows = [];

  function setAvailabilityForm(data) {
    setValue('availabilityStoreId', data.store_id || 'default');
    setValue('availabilityServicePeriod', data.configured_service_period || data.service_period || 'auto');
    const periods = data.service_periods || {};
    setValue('availabilityBreakfastStart', periods.breakfast?.start || '05:00');
    setValue('availabilityBreakfastEnd', periods.breakfast?.end || '10:30');
    setValue('availabilityRegularStart', periods.regular?.start || '10:30');
    setValue('availabilityRegularEnd', periods.regular?.end || '23:59');
    const current = getElement('availabilityCurrentPeriod');
    if (current) current.textContent = `目前時段：${data.service_period === 'breakfast' ? '早餐' : '一般時段'}`;
  }

  function filteredAvailabilityRows() {
    const query = getValue('availabilitySearch').toLowerCase();
    const status = getValue('availabilityStatusFilter');
    return availabilityRows.filter(row => {
      if (status && row.status !== status) return false;
      if (!query) return true;
      return [row.id, row.name, row.category].some(value => String(value || '').toLowerCase().includes(query));
    });
  }

  function renderAvailabilityRows() {
    const body = getElement('availabilityTableBody');
    if (!body) return;
    const rows = filteredAvailabilityRows();
    const summary = getElement('availabilitySummary');
    if (summary) summary.textContent = `${rows.length} / ${availabilityRows.length} 個品項`;
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="4" class="adm-empty">沒有符合條件的餐點。</td></tr>';
      return;
    }
    body.innerHTML = rows.map(row => {
      const timeBadge = row.time_unavailable
        ? '<span class="availability-badge time">目前時段不可供應</span>'
        : '<span class="recommendation-muted">—</span>';
      return '<tr>'
        + `<td><div style="font-weight:800;color:#1a2233">${escapeHtml(row.name || row.id)}</div><div class="recommendation-muted" style="font-family:monospace">${escapeHtml(row.id)}</div></td>`
        + `<td>${escapeHtml(row.category || '—')}</td>`
        + `<td><select class="availability-status-select" data-item-id="${escapeHtml(row.id)}">`
        + ['normal', 'low_stock', 'sold_out', 'disabled'].map(status =>
          `<option value="${status}" ${row.status === status ? 'selected' : ''}>${availabilityStatusLabel(status)}</option>`).join('')
        + `</select> <span class="availability-badge ${escapeHtml(row.status || 'normal')}">${escapeHtml(availabilityStatusLabel(row.status))}</span></td>`
        + `<td>${timeBadge}</td>`
        + '</tr>';
    }).join('');
    body.querySelectorAll('.availability-status-select').forEach(select => {
      select.addEventListener('change', () => {
        const itemId = select.getAttribute('data-item-id');
        const row = availabilityRows.find(item => item.id === itemId);
        if (row) row.status = select.value || 'normal';
        renderAvailabilityRows();
      });
    });
  }

  async function loadAvailability() {
    const body = getElement('availabilityTableBody');
    if (body) body.innerHTML = '<tr><td colspan="4" class="adm-empty">載入中…</td></tr>';
    try {
      const res = await fetch(`${apiBaseUrl}/api/availability`, { headers: adminHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      availabilityRows = Array.isArray(data.items) ? data.items : [];
      setAvailabilityForm(data);
      renderAvailabilityRows();
    } catch (e) {
      availabilityRows = [];
      if (body) body.innerHTML = `<tr><td colspan="4" class="adm-empty" style="color:#e84040">載入失敗：${escapeHtml(e.message)}</td></tr>`;
    }
  }

  async function saveAvailability() {
    const btn = getElement('availabilitySaveBtn');
    if (btn) btn.disabled = true;
    const statusIds = status => availabilityRows.filter(row => row.status === status).map(row => row.id);
    const payload = {
      store_id: getValue('availabilityStoreId') || 'default',
      service_period: getValue('availabilityServicePeriod') || 'auto',
      service_periods: {
        breakfast: {
          start: getValue('availabilityBreakfastStart') || '05:00',
          end: getValue('availabilityBreakfastEnd') || '10:30',
        },
        regular: {
          start: getValue('availabilityRegularStart') || '10:30',
          end: getValue('availabilityRegularEnd') || '23:59',
        },
      },
      sold_out_item_ids: statusIds('sold_out'),
      low_stock_item_ids: statusIds('low_stock'),
      store_disabled_item_ids: statusIds('disabled'),
    };
    try {
      const res = await fetch(`${apiBaseUrl}/api/availability`, {
        method: 'POST',
        headers: adminHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      availabilityRows = Array.isArray(data.items) ? data.items : [];
      setAvailabilityForm(data);
      renderAvailabilityRows();
      alertUser('供應設定已儲存');
    } catch (e) {
      alertUser(`儲存失敗：${e.message}`);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  return {
    loadAvailability,
    saveAvailability,
    renderAvailabilityRows,
  };
}
