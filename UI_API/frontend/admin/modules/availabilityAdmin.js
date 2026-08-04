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
  hasPermission = () => false,
  confirmAction = message => window.confirm(message),
}) {
  let availabilityRows = [];
  let categories = [];
  let dialogMode = 'create';

  function canWriteCatalog() {
    return hasPermission('catalog.items.write') || hasPermission('*');
  }

  function canReadCatalog() {
    return canWriteCatalog() || hasPermission('catalog.items.read') || hasPermission('catalog.availability.read') || hasPermission('*');
  }

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

  function syncCategoryFilter(selected) {
    const select = getElement('availabilityCategoryFilter');
    if (!select) return;
    const current = selected || select.value || '';
    const options = ['<option value="">全部類別</option>']
      .concat(categories.map(cat => `<option value="${escapeHtml(cat)}" ${cat === current ? 'selected' : ''}>${escapeHtml(cat)}</option>`));
    select.innerHTML = options.join('');
    const datalist = getElement('catalogCategoryOptions');
    if (datalist) {
      datalist.innerHTML = categories.map(cat => `<option value="${escapeHtml(cat)}"></option>`).join('');
    }
  }

  function filteredAvailabilityRows() {
    const query = getValue('availabilitySearch').toLowerCase();
    const status = getValue('availabilityStatusFilter');
    const category = getValue('availabilityCategoryFilter');
    return availabilityRows.filter(row => {
      if (status && row.status !== status) return false;
      if (category && String(row.category || '') !== category) return false;
      if (!query) return true;
      return [row.id, row.name, row.category, row.description].some(value => String(value || '').toLowerCase().includes(query));
    });
  }

  function imageCell(row) {
    const src = String(row.image || '').trim();
    if (!src) {
      return '<div class="recommendation-muted" style="width:48px;height:48px;display:grid;place-items:center;background:#f2f4f8;border-radius:10px">—</div>';
    }
    return `<img src="${escapeHtml(src)}" alt="" style="width:48px;height:48px;object-fit:cover;border-radius:10px;background:#f2f4f8" loading="lazy">`;
  }

  function renderAvailabilityRows() {
    const body = getElement('availabilityTableBody');
    if (!body) return;
    const rows = filteredAvailabilityRows();
    const summary = getElement('availabilitySummary');
    if (summary) summary.textContent = `${rows.length} / ${availabilityRows.length} 個品項`;
    const showActions = canWriteCatalog();
    const actionsHeader = getElement('catalogActionsHeader');
    if (actionsHeader) actionsHeader.style.display = showActions ? '' : 'none';
    const addBtn = getElement('catalogAddItemBtn');
    if (addBtn) addBtn.style.display = showActions ? '' : 'none';
    const retiredWrap = getElement('availabilityShowRetiredWrap');
    if (retiredWrap) retiredWrap.style.display = showActions ? 'inline-flex' : 'none';

    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="${showActions ? 7 : 6}" class="adm-empty">沒有符合條件的商品。</td></tr>`;
      return;
    }
    body.innerHTML = rows.map(row => {
      const timeBadge = row.time_unavailable
        ? '<span class="availability-badge time">目前時段不可供應</span>'
        : '<span class="recommendation-muted">—</span>';
      const retired = Boolean(row.retired);
      const price = row.price != null ? `$${escapeHtml(String(row.price))}` : '—';
      const actions = showActions
        ? `<td style="white-space:nowrap">`
          + `<button type="button" class="refresh-btn catalog-edit-btn" data-item-id="${escapeHtml(row.id)}">編輯</button> `
          + (retired
            ? `<button type="button" class="refresh-btn catalog-restore-btn" data-item-id="${escapeHtml(row.id)}">還原</button>`
            : `<button type="button" class="refresh-btn catalog-retire-btn" data-item-id="${escapeHtml(row.id)}">刪除</button>`)
          + `</td>`
        : '';
      return '<tr' + (retired ? ' style="opacity:.65"' : '') + '>'
        + `<td>${imageCell(row)}</td>`
        + `<td><div style="font-weight:800;color:#1a2233">${escapeHtml(row.name || row.id)}</div>`
        + `<div class="recommendation-muted" style="font-family:monospace">${escapeHtml(row.id)}</div>`
        + (retired ? '<div class="availability-badge disabled">已退役</div>' : '')
        + `</td>`
        + `<td>${escapeHtml(row.category || '—')}</td>`
        + `<td style="font-weight:800">${price}</td>`
        + `<td><select class="availability-status-select" data-item-id="${escapeHtml(row.id)}" ${retired ? 'disabled' : ''}>`
        + ['normal', 'low_stock', 'sold_out', 'disabled'].map(status =>
          `<option value="${status}" ${row.status === status ? 'selected' : ''}>${availabilityStatusLabel(status)}</option>`).join('')
        + `</select> <span class="availability-badge ${escapeHtml(row.status || 'normal')}">${escapeHtml(availabilityStatusLabel(row.status))}</span></td>`
        + `<td>${timeBadge}</td>`
        + actions
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
    body.querySelectorAll('.catalog-edit-btn').forEach(btn => {
      btn.addEventListener('click', () => openEditDialog(btn.getAttribute('data-item-id')));
    });
    body.querySelectorAll('.catalog-retire-btn').forEach(btn => {
      btn.addEventListener('click', () => retireItem(btn.getAttribute('data-item-id')));
    });
    body.querySelectorAll('.catalog-restore-btn').forEach(btn => {
      btn.addEventListener('click', () => restoreItem(btn.getAttribute('data-item-id')));
    });
  }

  async function loadAvailability() {
    if (!canReadCatalog()) return;
    const body = getElement('availabilityTableBody');
    if (body) body.innerHTML = '<tr><td colspan="7" class="adm-empty">載入中…</td></tr>';
    try {
      const includeRetired = canWriteCatalog() && getElement('availabilityShowRetired')?.checked;
      const res = await fetch(`${apiBaseUrl}/api/availability`, { headers: adminHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      let items = Array.isArray(data.items) ? data.items : [];
      if (includeRetired) {
        const catalogRes = await fetch(`${apiBaseUrl}/api/menu/items?include_retired=true`, { headers: adminHeaders() });
        if (catalogRes.ok) {
          const catalog = await catalogRes.json();
          const activeById = Object.fromEntries(items.map(row => [row.id, row]));
          items = (catalog.items || []).map(item => {
            const active = activeById[item.id];
            return {
              ...item,
              status: active?.status || 'disabled',
              time_unavailable: active?.time_unavailable || false,
              retired: Boolean(item.retired),
            };
          });
          categories = Array.isArray(catalog.categories) ? catalog.categories : [];
        }
      } else {
        categories = Array.isArray(data.categories) && data.categories.length
          ? data.categories
          : [...new Set(items.map(row => row.category).filter(Boolean))].sort();
      }
      availabilityRows = items;
      setAvailabilityForm(data);
      syncCategoryFilter();
      renderAvailabilityRows();
    } catch (e) {
      availabilityRows = [];
      if (body) body.innerHTML = `<tr><td colspan="7" class="adm-empty" style="color:#e84040">載入失敗：${escapeHtml(e.message)}</td></tr>`;
    }
  }

  async function saveAvailability() {
    const btn = getElement('availabilitySaveBtn');
    if (btn) btn.disabled = true;
    const statusIds = status => availabilityRows.filter(row => !row.retired && row.status === status).map(row => row.id);
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
      categories = Array.isArray(data.categories) ? data.categories : categories;
      setAvailabilityForm(data);
      syncCategoryFilter();
      renderAvailabilityRows();
      alertUser('供應設定已儲存');
    } catch (e) {
      alertUser(`儲存失敗：${e.message}`);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function openCreateDialog() {
    dialogMode = 'create';
    setValue('catalogEditItemId', '');
    setValue('catalogItemName', '');
    setValue('catalogItemCategory', getValue('availabilityCategoryFilter') || '');
    setValue('catalogItemPrice', '');
    setValue('catalogItemDescription', '');
    setValue('catalogItemImageUrl', '');
    const file = getElement('catalogItemImageFile');
    if (file) file.value = '';
    const title = getElement('catalogItemDialogTitle');
    if (title) title.textContent = '新增商品';
    getElement('catalogItemDialog')?.showModal?.();
  }

  function openEditDialog(itemId) {
    const row = availabilityRows.find(item => item.id === itemId);
    if (!row) return;
    dialogMode = 'edit';
    setValue('catalogEditItemId', row.id);
    setValue('catalogItemName', row.name || '');
    setValue('catalogItemCategory', row.category || '');
    setValue('catalogItemPrice', String(row.price || ''));
    setValue('catalogItemDescription', row.description || '');
    setValue('catalogItemImageUrl', String(row.image || '').startsWith('http') ? row.image : '');
    const file = getElement('catalogItemImageFile');
    if (file) file.value = '';
    const title = getElement('catalogItemDialogTitle');
    if (title) title.textContent = `編輯商品 · ${row.id}`;
    getElement('catalogItemDialog')?.showModal?.();
  }

  async function saveCatalogItem(event) {
    event?.preventDefault?.();
    if (!canWriteCatalog()) {
      alertUser('需要主管權限才能編輯商品');
      return;
    }
    const itemId = getValue('catalogEditItemId');
    const payload = {
      name: getValue('catalogItemName'),
      category: getValue('catalogItemCategory'),
      price: Number(getValue('catalogItemPrice')),
      description: getValue('catalogItemDescription'),
    };
    const imageUrl = getValue('catalogItemImageUrl');
    if (imageUrl) payload.image = imageUrl;
    const btn = getElement('catalogItemSaveBtn');
    if (btn) btn.disabled = true;
    try {
      let savedId = itemId;
      if (dialogMode === 'create') {
        const res = await fetch(`${apiBaseUrl}/api/menu/items`, {
          method: 'POST',
          headers: adminHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data?.detail?.message || data?.detail || `HTTP ${res.status}`);
        savedId = data.item?.id;
      } else {
        const res = await fetch(`${apiBaseUrl}/api/menu/items/${encodeURIComponent(itemId)}`, {
          method: 'PUT',
          headers: adminHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data?.detail?.message || data?.detail || `HTTP ${res.status}`);
        savedId = data.item?.id || itemId;
      }
      const fileInput = getElement('catalogItemImageFile');
      const file = fileInput?.files?.[0];
      if (file && savedId) {
        const form = new FormData();
        form.append('file', file);
        const uploadRes = await fetch(`${apiBaseUrl}/api/menu/items/${encodeURIComponent(savedId)}/image`, {
          method: 'POST',
          headers: adminHeaders(),
          body: form,
        });
        const uploadData = await uploadRes.json().catch(() => ({}));
        if (!uploadRes.ok) throw new Error(uploadData?.detail?.message || uploadData?.detail || `上傳失敗 HTTP ${uploadRes.status}`);
      }
      getElement('catalogItemDialog')?.close?.();
      await loadAvailability();
      alertUser(dialogMode === 'create' ? '商品已新增' : '商品已更新');
    } catch (e) {
      alertUser(`儲存商品失敗：${e.message}`);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function retireItem(itemId) {
    if (!canWriteCatalog()) return;
    if (!confirmAction('確定要刪除（退役）此商品？kiosk 將無法再點購，之後可還原。')) return;
    try {
      const res = await fetch(`${apiBaseUrl}/api/menu/items/${encodeURIComponent(itemId)}/retire`, {
        method: 'POST',
        headers: adminHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadAvailability();
    } catch (e) {
      alertUser(`刪除失敗：${e.message}`);
    }
  }

  async function restoreItem(itemId) {
    if (!canWriteCatalog()) return;
    try {
      const res = await fetch(`${apiBaseUrl}/api/menu/items/${encodeURIComponent(itemId)}/restore`, {
        method: 'POST',
        headers: adminHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadAvailability();
    } catch (e) {
      alertUser(`還原失敗：${e.message}`);
    }
  }

  function bindUi() {
    getElement('availabilityCategoryFilter')?.addEventListener('change', renderAvailabilityRows);
    getElement('availabilityShowRetired')?.addEventListener('change', () => loadAvailability());
    getElement('catalogAddItemBtn')?.addEventListener('click', openCreateDialog);
    getElement('catalogItemCancelBtn')?.addEventListener('click', () => getElement('catalogItemDialog')?.close?.());
    getElement('catalogItemForm')?.addEventListener('submit', saveCatalogItem);
  }

  bindUi();

  return {
    loadAvailability,
    saveAvailability,
    renderAvailabilityRows,
  };
}
