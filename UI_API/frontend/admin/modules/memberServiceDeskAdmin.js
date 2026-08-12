/** @typedef {Record<string, any>} AnyRecord */

import { createMemberClient } from '../../shared/api/capabilityClients.js';

function money(value) {
  return `$${Number(value || 0).toLocaleString('zh-TW')}`;
}

function dateText(value, fallback = '—') {
  if (!value) return fallback;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value).slice(0, 16).replace('T', ' ') : date.toLocaleString('zh-TW');
}

/** @param {unknown} values */
function tagText(values) {
  return Array.isArray(values) && values.length ? values.join('、') : '尚未記錄';
}

/** @param {string} raw */
function parseTags(raw) {
  return [...new Set(String(raw || '').split(/[,，\n]/).map(value => value.trim()).filter(Boolean))];
}

/**
 * Member service and personalization workflow behind one interface.
 * @param {{
 *   apiBaseUrl: string,
 *   adminHeaders: () => Record<string, string>,
 *   getElement: (id: string) => HTMLElement | null,
 *   escapeHtml: (value: any) => string,
 *   hasPermission: (permission: string) => boolean,
 * }} options
 */
export function createMemberServiceDeskAdmin({
  apiBaseUrl,
  adminHeaders,
  getElement,
  escapeHtml,
  hasPermission,
}) {
  const memberClient = createMemberClient({ baseUrl: apiBaseUrl, headers: adminHeaders });
  let page = 1;
  let pageSize = 25;
  let total = 0;
  let selectedMemberRef = '';
  let bound = false;
  let searchTimer;

  function renderPager() {
    const label = getElement('memberPaginationLabel');
    if (label) label.textContent = total ? `第 ${page} 頁，共 ${total} 位會員` : '沒有符合條件的會員';
    const previous = /** @type {HTMLButtonElement | null} */ (getElement('memberPreviousPage'));
    const next = /** @type {HTMLButtonElement | null} */ (getElement('memberNextPage'));
    if (previous) previous.disabled = page <= 1;
    if (next) next.disabled = page * pageSize >= total;
  }

  /** @param {AnyRecord[]} rows */
  function renderList(rows) {
    const body = getElement('memberTableBody');
    if (!body) return;
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="6" class="adm-empty">沒有符合條件的會員。</td></tr>';
      return;
    }
    body.innerHTML = rows.map(row => `
      <tr class="${selectedMemberRef === row.member_ref ? 'member-row-selected' : ''}">
        <td><div class="member-person"><b>${escapeHtml(row.nickname || '未命名會員')}</b><span>${escapeHtml(row.phone_masked || '')}</span></div></td>
        <td>${Number(row.visit_count || 0)} 次</td>
        <td>${money(row.total_spend)}</td>
        <td>${escapeHtml(dateText(row.created_at).slice(0, 10))}</td>
        <td><code>${escapeHtml(row.member_ref || '')}</code></td>
        <td><button class="view-btn" type="button" data-member-ref="${escapeHtml(row.member_ref || '')}">服務</button></td>
      </tr>
    `).join('');
    body.querySelectorAll('[data-member-ref]').forEach(button => {
      button.addEventListener('click', () => openMember(button.getAttribute('data-member-ref') || ''));
    });
  }

  async function load() {
    const query = String(/** @type {HTMLInputElement | null} */ (getElement('memberSearch'))?.value || '').trim();
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      q: query,
      sort_by: 'created_at',
      sort_order: 'desc',
    });
    const payload = await memberClient.list(Object.fromEntries(params.entries()));
    const rows = Array.isArray(payload?.data) ? payload.data : [];
    total = Number(payload?.pagination?.total || 0);
    renderList(rows);
    renderPager();
    const stats = getElement('memberStatCards');
    if (stats) {
      stats.innerHTML = `<div class="member-stat"><b>${total.toLocaleString('zh-TW')}</b><span>符合條件的會員</span><small>資料由伺服器分頁查詢</small></div>`;
    }
  }

  /** @param {AnyRecord} detail */
  function renderDetail(detail) {
    const panel = getElement('memberDetailPanel');
    if (!panel) return;
    const verified = detail.verified_preferences || {};
    const inferred = detail.inferred_preferences || {};
    const favoriteItems = inferred.favorite_items || detail.favorites_ranked || [];
    const categories = inferred.categories || detail.categories_ranked || [];
    const recentOrders = (detail.orders || []).slice(0, 5);
    const canWrite = hasPermission('members.write');
    const canDelete = hasPermission('members.delete');
    panel.classList.remove('hidden');
    panel.innerHTML = `
      <div class="member-detail-head"><div><h2>${escapeHtml(detail.nickname || '未命名會員')}</h2><small>${escapeHtml(detail.phone_masked || '')}</small></div><span class="member-status active">服務中</span></div>
      <section class="member-service-now">
        <div class="member-section-title">現在可以怎麼服務</div>
        <p><b>會員已確認的過敏資訊：</b>${escapeHtml(tagText(verified.allergies))}</p>
        <p><b>會員已確認的飲食偏好：</b>${escapeHtml(tagText(verified.dietary_preferences))}</p>
        <p><b>服務備註：</b>${escapeHtml(verified.service_notes || '尚未記錄')}</p>
        <small>以上內容標示為「會員確認」，不會與訂單推論混為一談。</small>
      </section>
      ${canWrite ? `<section class="member-verified-editor">
        <div class="member-section-title">記錄會員確認資訊</div>
        <label>過敏資訊<input id="memberVerifiedAllergies" value="${escapeHtml((verified.allergies || []).join('、'))}" placeholder="例如：花生、牛奶"></label>
        <label>飲食偏好<input id="memberVerifiedDietary" value="${escapeHtml((verified.dietary_preferences || []).join('、'))}" placeholder="例如：不吃辣、蛋奶素"></label>
        <label>確認喜愛品項 ID<input id="memberVerifiedFavorites" value="${escapeHtml((verified.favorite_item_ids || []).join('、'))}"></label>
        <label>服務備註<textarea id="memberVerifiedNotes" maxlength="500">${escapeHtml(verified.service_notes || '')}</textarea></label>
        <button id="memberVerifiedSave" class="view-btn" type="button">儲存確認資訊</button>
      </section>` : ''}
      <div class="member-section-title">由完成訂單推論的偏好</div>
      <p class="recommendation-card-description">這些是系統推論，不代表會員親自確認。</p>
      <div class="member-inferred-grid">
        <div><b>常點品項</b><span>${favoriteItems.length ? favoriteItems.slice(0, 5).map(item => escapeHtml(item.name || item.id || '')).join('、') : '尚無資料'}</span></div>
        <div><b>偏好分類</b><span>${categories.length ? categories.slice(0, 5).map(item => escapeHtml(item.category || '')).join('、') : '尚無資料'}</span></div>
      </div>
      <div class="member-section-title">最近訂單</div>
      ${recentOrders.length ? recentOrders.map(order => `<div class="order-row"><div class="order-row-top"><span>${escapeHtml(dateText(order.timestamp))}</span><b>${money(order.total)}</b></div><div class="order-items">${escapeHtml((order.items || []).map(item => item.name || item.id || '').join('、') || '—')}</div></div>`).join('') : '<p class="muted">尚無訂單</p>'}
      ${canDelete ? `<div class="member-danger"><button class="member-clear-btn" type="button">刪除點餐紀錄</button><button class="member-delete-btn" type="button">刪除會員帳戶</button></div>` : ''}
    `;
    getElement('memberVerifiedSave')?.addEventListener('click', saveVerifiedPreferences);
    panel.querySelector('.member-clear-btn')?.addEventListener('click', () => requestSensitiveAction('records', detail));
    panel.querySelector('.member-delete-btn')?.addEventListener('click', () => requestSensitiveAction('account', detail));
  }

  async function openMember(memberRef) {
    selectedMemberRef = memberRef;
    renderDetail(await memberClient.detail(memberRef));
  }

  async function saveVerifiedPreferences() {
    if (!selectedMemberRef) return;
    const value = id => String(/** @type {HTMLInputElement | HTMLTextAreaElement | null} */ (getElement(id))?.value || '');
    await memberClient.saveVerifiedPreferences(selectedMemberRef, {
      allergies: parseTags(value('memberVerifiedAllergies')),
      dietary_preferences: parseTags(value('memberVerifiedDietary')),
      favorite_item_ids: parseTags(value('memberVerifiedFavorites')),
      service_notes: value('memberVerifiedNotes'),
    });
    await openMember(selectedMemberRef);
  }

  /** @param {'records' | 'account'} kind @param {AnyRecord} detail */
  async function requestSensitiveAction(kind, detail) {
    const target = detail.nickname || detail.phone_masked || selectedMemberRef;
    if (!window.confirm(`再次確認：要${kind === 'records' ? '刪除點餐紀錄' : '刪除會員帳戶'}「${target}」嗎？此操作會留下稽核紀錄。`)) return;
    if (kind === 'records') await memberClient.clearRecords(selectedMemberRef);
    else await memberClient.remove(selectedMemberRef);
    if (kind === 'account') {
      selectedMemberRef = '';
      const panel = getElement('memberDetailPanel');
      if (panel) panel.innerHTML = '<div class="member-detail-empty">會員帳戶已刪除。</div>';
    } else {
      await openMember(selectedMemberRef);
    }
    await load();
  }

  async function exportMaskedCsv() {
    const url = URL.createObjectURL(await memberClient.exportCsv());
    const link = document.createElement('a');
    link.href = url;
    link.download = 'members_export.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  function bind() {
    if (bound) return;
    bound = true;
    const search = /** @type {HTMLInputElement | null} */ (getElement('memberSearch'));
    search?.addEventListener('input', () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => {
        page = 1;
        load().catch(() => {});
      }, 250);
    });
    getElement('memberPreviousPage')?.addEventListener('click', () => {
      if (page > 1) {
        page -= 1;
        load().catch(() => {});
      }
    });
    getElement('memberNextPage')?.addEventListener('click', () => {
      if (page * pageSize < total) {
        page += 1;
        load().catch(() => {});
      }
    });
    const exportButton = getElement('memberExportBtn');
    if (exportButton) {
      exportButton.toggleAttribute('hidden', !hasPermission('members.export'));
      exportButton.addEventListener('click', () => exportMaskedCsv().catch(() => {}));
    }
  }

  return { bind, load, openMember, saveVerifiedPreferences, requestSensitiveAction };
}
