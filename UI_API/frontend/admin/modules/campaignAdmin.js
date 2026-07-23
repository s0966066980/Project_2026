import { CAMPAIGN_PLACEMENT_LABELS, CAMPAIGN_STATUS_LABELS, zhLabel } from './zhTWLabels.js';

const DRAFT_KEY = 'project2026_campaign_draft_v1';
const OBJECTIVE_LABELS = {
  promote_item: '提升指定餐點銷售', increase_add_on: '增加搭配加購',
  increase_order_value: '提高每筆消費', member_return: '鼓勵會員回購', clear_inventory: '協助庫存銷售',
};

/** @param {unknown} value */
function text(value) { return String(value ?? '').trim(); }

const CURRENT_CAMPAIGN_STATUSES = new Set(['draft', 'review', 'scheduled', 'active', 'paused']);
const HISTORICAL_CAMPAIGN_STATUSES = new Set(['ended', 'archived']);

/** @param {any} row @param {string} query @param {string} statusFilter */
export function campaignMatchesFilter(row, query, statusFilter) {
  const normalizedQuery = text(query).toLocaleLowerCase('zh-TW');
  if (normalizedQuery && !text(row?.payload?.name).toLocaleLowerCase('zh-TW').includes(normalizedQuery)) return false;
  if (statusFilter === 'current') return CURRENT_CAMPAIGN_STATUSES.has(text(row?.status));
  if (statusFilter === 'history') return HISTORICAL_CAMPAIGN_STATUSES.has(text(row?.status));
  return !statusFilter || row?.status === statusFilter;
}

/**
 * @param {{
 *   apiBaseUrl: string,
 *   adminHeaders: () => Record<string, string>,
 *   getElement: (id: string) => any,
 *   loadMenu: () => Promise<any>,
 *   getMenuItems: () => any[],
 *   hasPermission?: (permission: string) => boolean,
 *   confirmAction?: (message: string) => boolean
 * }} options
 */
export function createCampaignAdmin({ apiBaseUrl, adminHeaders, getElement, loadMenu, getMenuItems, hasPermission = () => false, confirmAction = message => window.confirm(message) }) {
  /** @type {any[]} */
  let rows = [];
  /** @type {any} */
  let current = null;
  let step = 1;
  let dirty = false;
  let busy = false;
  /** @type {ReturnType<typeof setTimeout>|undefined} */
  let saveTimer;

  /** @param {string} id */
  function value(id) { return getElement(id)?.value ?? ''; }
  /** @param {string} id @param {unknown} next */
  function setValue(id, next) { if (getElement(id)) getElement(id).value = next ?? ''; }
  function menuItems() { return (getMenuItems?.() || []).filter(item => item?.id); }
  function selectedMenuItem() { return menuItems().find(item => text(item.id) === value('campaignItem')); }

  /** @param {string} path @param {RequestInit} [options] @returns {Promise<any>} */
  async function request(path, options = {}) {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      ...options,
      headers: { ...adminHeaders(), ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = /** @type {Error & {code?: string, fieldErrors?: any[]}} */ (new Error(body?.detail?.message || body?.error?.message || `系統回應 ${response.status}`));
      error.code = body?.detail?.code || body?.error?.code || 'request_failed';
      error.fieldErrors = body?.detail?.field_errors || [];
      throw error;
    }
    return body?.data;
  }

  /** @param {unknown} status */
  function statusLabel(status) { return zhLabel(CAMPAIGN_STATUS_LABELS, status, '未知狀態'); }
  /** @param {unknown} placement */
  function placementLabel(placement) { return zhLabel(CAMPAIGN_PLACEMENT_LABELS, placement, '未知位置'); }

  function fillMenuOptions() {
    const targets = [getElement('campaignItem'), getElement('campaignRequiredItem')];
    targets.forEach((select, index) => {
      if (!select) return;
      const selected = select.value;
      select.textContent = '';
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = index ? '請選擇需要先購買的餐點' : '請選擇優惠餐點';
      select.appendChild(placeholder);
      menuItems().forEach(item => {
        const option = document.createElement('option');
        option.value = text(item.id);
        option.textContent = `${text(item.name) || '未命名餐點'}（$${Number(item.price || 0)}）`;
        option.selected = option.value === selected;
        select.appendChild(option);
      });
    });
  }

  function payloadFromForm() {
    const ruleType = value('campaignRuleType') || 'fixed_item_price';
    const required = value('campaignRequiredItem');
    return {
      name: text(value('campaignName')),
      objective: value('campaignObjective') || 'promote_item',
      audience: value('campaignAudience') || 'all',
      schedule: { starts_at: value('campaignStart'), ends_at: value('campaignEnd') },
      promotion_rules: [{
        type: ruleType,
        item_ids: value('campaignItem') ? [value('campaignItem')] : [],
        required_cart_item_ids: ruleType === 'add_on_fixed_price' && required ? [required] : [],
        promotion_price: Number(value('campaignPrice') || 0),
      }],
      placements: [...document.querySelectorAll('input[name="campaignPlacement"]:checked')].map(input => /** @type {HTMLInputElement} */ (input).value),
      creatives: {
        badge: text(value('campaignBadge')),
        title: text(value('campaignName')),
        description: text(value('campaignDescription')),
        cta: text(value('campaignCta')) || '立即查看',
        theme: value('campaignTheme') || 'gold',
      },
    };
  }

  function saveLocalDraft() {
    if (!dirty || current) return;
    localStorage.setItem(DRAFT_KEY, JSON.stringify(payloadFromForm()));
    const state = getElement('campaignSaveState');
    if (state) state.textContent = '已自動暫存在此裝置';
  }

  /** @param {any} [payload] */
  function restoreForm(payload = {}) {
    const rule = payload.promotion_rules?.[0] || {};
    const schedule = payload.schedule || {};
    const creative = payload.creatives || {};
    setValue('campaignName', payload.name || '');
    setValue('campaignObjective', payload.objective || 'promote_item');
    setValue('campaignAudience', payload.audience || 'all');
    setValue('campaignStart', text(schedule.starts_at).slice(0, 16));
    setValue('campaignEnd', text(schedule.ends_at).slice(0, 16));
    setValue('campaignRuleType', rule.type || 'fixed_item_price');
    setValue('campaignItem', rule.item_ids?.[0] || '');
    setValue('campaignRequiredItem', rule.required_cart_item_ids?.[0] || '');
    setValue('campaignPrice', rule.promotion_price || '');
    setValue('campaignBadge', creative.badge || '');
    setValue('campaignDescription', creative.description || '');
    setValue('campaignCta', creative.cta || '立即查看');
    setValue('campaignTheme', creative.theme || 'gold');
    const placements = new Set(payload.placements || ['menu_card', 'item_detail']);
    document.querySelectorAll('input[name="campaignPlacement"]').forEach(rawInput => {
      const input = /** @type {HTMLInputElement} */ (rawInput);
      input.checked = placements.has(input.value);
    });
    updateRuleVisibility();
    updatePriceHelp();
  }

  function clearErrors() {
    document.querySelectorAll('[data-error-for]').forEach(node => { node.textContent = ''; });
  }

  /** @param {any[]} [errors] */
  function renderErrors(errors = []) {
    clearErrors();
    errors.forEach(error => {
      const node = document.querySelector(`[data-error-for="${CSS.escape(text(error.path))}"]`);
      if (node) node.textContent = text(error.message) || '請檢查此欄位。';
    });
    const first = errors[0];
    if (first) {
      const node = document.querySelector(`[data-error-for="${CSS.escape(text(first.path))}"]`);
      /** @type {HTMLElement|null} */ (node?.previousElementSibling || null)?.focus();
    }
  }

  /** @param {string|number} nextStep */
  function setStep(nextStep) {
    step = Math.max(1, Math.min(5, Number(nextStep) || 1));
    document.querySelectorAll('[data-campaign-step]').forEach(rawTab => {
      const tab = /** @type {HTMLElement} */ (rawTab);
      tab.classList.toggle('active', Number(tab.dataset.campaignStep) === step);
    });
    document.querySelectorAll('[data-campaign-panel]').forEach(rawPanel => {
      const panel = /** @type {HTMLElement} */ (rawPanel);
      panel.classList.toggle('active', Number(panel.dataset.campaignPanel) === step);
    });
    if (getElement('campaignPreviousBtn')) getElement('campaignPreviousBtn').disabled = step === 1;
    if (getElement('campaignNextBtn')) getElement('campaignNextBtn').disabled = step === 5;
    if (step >= 4) preview().catch(() => {});
  }

  function updateRuleVisibility() {
    const conditional = value('campaignRuleType') === 'add_on_fixed_price';
    if (getElement('campaignRequiredField')) getElement('campaignRequiredField').style.display = conditional ? '' : 'none';
  }

  function updatePriceHelp() {
    const item = selectedMenuItem();
    const price = Number(value('campaignPrice') || 0);
    const base = Number(item?.price || 0);
    const help = getElement('campaignPriceHelp');
    if (!help) return;
    help.textContent = item ? `原價 $${base}${price > 0 ? `，預計現省 $${Math.max(0, base - price)}` : ''}` : '選擇餐點後會顯示原價。';
  }

  /** @param {any} result */
  function renderPreview(result) {
    renderErrors(result.field_errors || []);
    const box = getElement('campaignPricePreview');
    if (box) {
      box.textContent = '';
      (/** @type {any[]} */ (result.price_previews || [])).forEach(price => {
        const card = document.createElement('div');
        card.className = 'campaign-preview-card';
        const title = document.createElement('b');
        title.textContent = text(price.item_name) || '優惠餐點';
        const detail = document.createElement('p');
        detail.textContent = `原價 $${price.base_price} → 優惠價 $${price.effective_price}，現省 $${price.savings}${price.conditional ? '（符合搭配條件後）' : ''}`;
        card.append(title, detail);
        box.appendChild(card);
      });
    }
    const summary = getElement('campaignReviewSummary');
    if (summary) summary.textContent = result.valid ? result.summary : '還有欄位需要修正，修正後才能發布。';
    const conflicts = getElement('campaignConflictList');
    if (conflicts) {
      conflicts.textContent = '';
      (/** @type {any[]} */ (result.conflicts || [])).forEach(conflict => {
        const notice = document.createElement('div');
        notice.className = 'recommendation-notice';
        notice.textContent = conflict.message;
        conflicts.appendChild(notice);
      });
      if (!result.conflicts?.length) {
        const ok = document.createElement('div');
        ok.className = 'recommendation-notice';
        ok.textContent = '未發現同期間、同餐點的活動衝突。';
        conflicts.appendChild(ok);
      }
    }
  }

  async function preview() {
    const body = { ...payloadFromForm(), campaign_id: current?.campaign_id || '' };
    const result = await request('/api/v1/campaigns/preview', { method: 'POST', body: JSON.stringify(body) });
    renderPreview(result);
    return result;
  }

  /** @param {any} [snapshot] */
  function openWizard(snapshot = null) {
    current = snapshot;
    const saved = !snapshot ? JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null') : null;
    restoreForm(snapshot?.payload || saved || {});
    dirty = false;
    if (getElement('campaignWizardTitle')) getElement('campaignWizardTitle').textContent = snapshot ? `編輯「${snapshot.payload?.name || '活動'}」` : '建立活動';
    if (getElement('campaignSaveState')) getElement('campaignSaveState').textContent = snapshot ? `目前版本 ${snapshot.version}・${statusLabel(snapshot.status)}` : (saved ? '已恢復此裝置的未完成草稿' : '尚未儲存');
    getElement('campaignWizard').hidden = false;
    getElement('page-promotions')?.classList.add('campaign-editing');
    getElement('page-promotions')?.scrollTo({ top: 0 });
    clearErrors();
    setStep(1);
    getElement('campaignName')?.focus();
  }

  function closeWizard() {
    saveLocalDraft();
    getElement('campaignWizard').hidden = true;
    getElement('page-promotions')?.classList.remove('campaign-editing');
    current = null;
  }

  async function saveDraft() {
    if (busy) return null;
    busy = true;
    const button = getElement('campaignSaveDraftBtn');
    if (button) { button.disabled = true; button.textContent = '儲存中…'; }
    try {
      const payload = payloadFromForm();
      const saved = current
        ? await request(`/api/v1/campaigns/${encodeURIComponent(current.campaign_id)}/draft`, { method: 'PUT', body: JSON.stringify({ ...payload, expected_version: current.version }) })
        : await request('/api/v1/campaigns', { method: 'POST', body: JSON.stringify(payload) });
      current = saved;
      dirty = false;
      localStorage.removeItem(DRAFT_KEY);
      if (getElement('campaignSaveState')) getElement('campaignSaveState').textContent = `草稿已儲存・版本 ${saved.version}`;
      await loadCampaigns();
      return saved;
    } catch (error) {
      const caught = /** @type {any} */ (error);
      renderErrors(caught.fieldErrors || []);
      if (getElement('campaignSaveState')) getElement('campaignSaveState').textContent = `儲存失敗：${caught.message}`;
      return null;
    } finally {
      busy = false;
      if (button) { button.disabled = false; button.textContent = '儲存草稿'; }
    }
  }

  /** @param {any} snapshot @param {string} targetStatus */
  async function transition(snapshot, targetStatus) {
    return request(`/api/v1/campaigns/${encodeURIComponent(snapshot.campaign_id)}/transition`, {
      method: 'POST', body: JSON.stringify({ target_status: targetStatus, expected_version: snapshot.version }),
    });
  }

  async function publish() {
    if (busy) return;
    busy = true;
    const button = getElement('campaignPublishBtn');
    if (button) { button.disabled = true; button.textContent = '檢查中…'; }
    try {
      const result = await preview();
      setStep(5);
      if (!result.valid) return;
      if (result.conflicts?.length && !confirmAction('系統發現重疊活動。價格會自動採顧客最優惠方案，仍要繼續發布嗎？')) return;
      busy = false;
      let saved = await saveDraft();
      busy = true;
      if (!saved) return;
      if (button) button.textContent = '發布中…';
      saved = await transition(saved, 'review');
      const start = new Date(saved.payload?.schedule?.starts_at || 0);
      saved = await transition(saved, start.getTime() > Date.now() ? 'scheduled' : 'active');
      current = saved;
      if (getElement('campaignSaveState')) getElement('campaignSaveState').textContent = `發布完成・${statusLabel(saved.status)}・版本 ${saved.version}`;
      await loadCampaigns();
    } catch (error) {
      const caught = /** @type {any} */ (error);
      renderErrors(caught.fieldErrors || []);
      if (getElement('campaignSaveState')) getElement('campaignSaveState').textContent = `發布失敗：${caught.message}`;
    } finally {
      busy = false;
      if (button) { button.disabled = false; button.textContent = '檢查並發布'; }
    }
  }

  /** @param {any} snapshot */
  function ruleSummary(snapshot) {
    const rule = snapshot.payload?.promotion_rules?.[0] || {};
    const item = menuItems().find(row => text(row.id) === text(rule.item_ids?.[0]));
    const itemName = text(item?.name) || '指定餐點';
    return rule.type === 'add_on_fixed_price' ? `${itemName}符合搭配條件時 $${rule.promotion_price}` : `${itemName}優惠價 $${rule.promotion_price}`;
  }

  /** @param {any} snapshot @param {string} targetStatus */
  async function lifecycleAction(snapshot, targetStatus) {
    if (busy) return;
    const question = /** @type {Record<string, string>} */ ({ paused: '確定暫停此活動？顧客畫面會停止套用優惠。', ended: '確定結束此活動？', archived: '確定封存此活動？封存後不可重新啟用。', active: '確定重新啟用此活動？' })[targetStatus];
    if (question && !confirmAction(question)) return;
    busy = true;
    try { await transition(snapshot, targetStatus); await loadCampaigns(); }
    catch (error) { window.alert(`操作失敗：${/** @type {any} */ (error).message}`); }
    finally { busy = false; }
  }

  /** @param {HTMLElement} container @param {string} label @param {() => void} handler @param {boolean} [danger] */
  function addAction(container, label, handler, danger = false) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    if (danger) button.classList.add('campaign-danger');
    button.addEventListener('click', handler);
    container.appendChild(button);
  }

  function renderList() {
    const query = text(value('campaignSearch')).toLocaleLowerCase('zh-TW');
    const status = value('campaignStatusFilter') || 'current';
    const visible = rows.filter(row => campaignMatchesFilter(row, query, status));
    const list = getElement('campaignList');
    if (!list) return;
    list.textContent = '';
    if (!visible.length) {
      const empty = document.createElement('div');
      empty.className = 'adm-empty campaign-empty';
      empty.textContent = status === 'current' && !query
        ? '目前沒有進行中、已排程或待處理的活動。'
        : (status === 'history' && !query ? '尚無已結束或已封存的活動。' : '沒有符合條件的活動。');
      list.appendChild(empty);
      return;
    }
    visible.forEach(snapshot => {
      const card = document.createElement('article'); card.className = 'campaign-card';
      const header = document.createElement('header');
      const title = document.createElement('h3'); title.textContent = text(snapshot.payload?.name) || '未命名活動';
      const badge = document.createElement('span'); badge.className = `promotion-status ${snapshot.status}`; badge.textContent = statusLabel(snapshot.status);
      header.append(title, badge);
      const summary = document.createElement('p'); summary.textContent = `${/** @type {Record<string, string>} */ (OBJECTIVE_LABELS)[snapshot.payload?.objective] || '其他活動目標'}・${snapshot.payload?.audience === 'member' ? '僅限會員' : '所有顧客'}・${ruleSummary(snapshot)}`;
      const placements = document.createElement('p'); placements.textContent = `顯示於：${(snapshot.payload?.placements || []).map(placementLabel).join('、') || '尚未設定'}`;
      const actor = text(snapshot.payload?.updated_by);
      const version = document.createElement('p'); version.textContent = `版本 ${snapshot.version}・影響 ${snapshot.payload?.placements?.length || 0} 個顧客畫面・操作人員編號 ${actor ? `…${actor.slice(-8)}` : '未記錄'}`;
      const schedule = document.createElement('p'); schedule.textContent = `${snapshot.payload?.schedule?.starts_at || '未設定開始'} 至 ${snapshot.payload?.schedule?.ends_at || '未設定結束'}`;
      const actions = document.createElement('div'); actions.className = 'campaign-card-actions';
      if (['draft', 'review', 'paused', 'ended'].includes(snapshot.status) && hasPermission('campaigns.write')) {
        addAction(actions, '查看與編輯', () => openWizard(snapshot));
      }
      if (hasPermission('campaigns.publish')) {
        if (['active', 'scheduled'].includes(snapshot.status)) addAction(actions, '暫停', () => lifecycleAction(snapshot, 'paused'));
        if (snapshot.status === 'paused') addAction(actions, '重新啟用', () => lifecycleAction(snapshot, 'active'));
        if (['active', 'scheduled', 'paused'].includes(snapshot.status)) addAction(actions, '結束', () => lifecycleAction(snapshot, 'ended'), true);
        if (['draft', 'ended', 'paused'].includes(snapshot.status)) addAction(actions, '封存', () => lifecycleAction(snapshot, 'archived'), true);
      }
      card.append(header, summary, placements, version, schedule, actions); list.appendChild(card);
    });
  }

  function renderKpis() {
    const box = getElement('campaignKpis'); if (!box) return;
    const counts = { active: 0, scheduled: 0, draft: 0, ended: 0 };
    rows.forEach(row => {
      const keyed = /** @type {Record<string, number>} */ (counts);
      if (row.status in counts) keyed[row.status] = (keyed[row.status] || 0) + 1;
    });
    box.textContent = '';
    [['進行中', counts.active], ['已排程', counts.scheduled], ['草稿／待處理', counts.draft + rows.filter(row => row.status === 'review').length], ['已結束', counts.ended]].forEach(([label, count]) => {
      const card = document.createElement('div'); card.className = 'campaign-kpi';
      const number = document.createElement('b'); number.textContent = String(count);
      const textNode = document.createElement('span'); textNode.textContent = String(label);
      card.append(number, textNode); box.appendChild(card);
    });
  }

  async function loadCampaigns() {
    if (getElement('campaignCreateBtn')) getElement('campaignCreateBtn').hidden = !hasPermission('campaigns.write');
    if (getElement('campaignSaveDraftBtn')) getElement('campaignSaveDraftBtn').hidden = !hasPermission('campaigns.write');
    if (getElement('campaignPublishBtn')) getElement('campaignPublishBtn').hidden = !hasPermission('campaigns.publish');
    await loadMenu(); fillMenuOptions();
    const list = getElement('campaignList'); if (list) list.textContent = '載入中…';
    try { rows = await request('/api/v1/campaigns'); renderKpis(); renderList(); }
    catch (error) { if (list) list.textContent = `活動載入失敗：${/** @type {any} */ (error).message}`; }
  }

  function bind() {
    getElement('campaignCreateBtn')?.addEventListener('click', () => openWizard());
    getElement('campaignCloseBtn')?.addEventListener('click', closeWizard);
    getElement('campaignRefreshBtn')?.addEventListener('click', loadCampaigns);
    getElement('campaignSearch')?.addEventListener('input', renderList);
    getElement('campaignStatusFilter')?.addEventListener('change', renderList);
    getElement('campaignPreviousBtn')?.addEventListener('click', () => setStep(step - 1));
    getElement('campaignNextBtn')?.addEventListener('click', () => setStep(step + 1));
    getElement('campaignSaveDraftBtn')?.addEventListener('click', saveDraft);
    getElement('campaignPublishBtn')?.addEventListener('click', publish);
    getElement('campaignRuleType')?.addEventListener('change', updateRuleVisibility);
    getElement('campaignItem')?.addEventListener('change', updatePriceHelp);
    getElement('campaignPrice')?.addEventListener('input', updatePriceHelp);
    document.querySelectorAll('[data-campaign-step]').forEach(rawTab => {
      const tab = /** @type {HTMLElement} */ (rawTab);
      tab.addEventListener('click', () => setStep(tab.dataset.campaignStep || '1'));
    });
    getElement('campaignWizard')?.addEventListener('input', () => { dirty = true; clearTimeout(saveTimer); saveTimer = setTimeout(saveLocalDraft, 500); });
    window.addEventListener('beforeunload', event => { if (dirty) { saveLocalDraft(); event.preventDefault(); } });
  }

  return { bind, loadCampaigns, renderList, openWizard, statusLabel, placementLabel };
}
