// =========================================================
// 會員流程：選擇頁 → 手機登入 → (查無→快速註冊) → 完成回呼。
// onResolved(member|null)：member 物件代表已登入會員，null 代表訪客。
// =========================================================
import * as api from '../shared/apiClient.js';
import { state } from './state.js';
import { getRequiredRuntimeDependency } from './runtime.js';
import { getMenuVisual, formatItemPrice, resolveItemPrice } from './menuVisuals.js';
import { completeGuestOrderingChoice } from './guestOrdering.js';

const $ = (id) => document.getElementById(id);
let memberPhoneNumber = '';
let onMemberResolved = null;
let entryHooks = {};
let memberLookupOutcome = '';
const LOGIN_HINT_DEFAULT = '輸入完整 10 碼後按「下一步」';
const REGISTER_HINT_DEFAULT = '輸入暱稱即可完成（可留空）';

function show(element) { element?.classList.remove('hidden'); element?.setAttribute('aria-hidden', 'false'); }
function hide(element) { element?.classList.add('hidden'); element?.setAttribute('aria-hidden', 'true'); }

function hideAll() {
  ['memberChoiceOverlay', 'memberLoginOverlay', 'memberRegisterOverlay'].forEach((id) => hide($(id)));
}

function setHint(id, message, isError = false) {
  const element = $(id);
  if (!element) return;
  element.textContent = message;
  element.classList.toggle('member-hint-error', isError);
}

function setButtonBusy(id, busy, busyLabel, idleLabel) {
  const button = $(id);
  if (!button) return;
  button.disabled = busy;
  button.textContent = busy ? busyLabel : idleLabel;
}

export function getMember() { return state.member; }

export function isMemberFlowVisible() {
  return ['memberChoiceOverlay', 'memberLoginOverlay', 'memberRegisterOverlay']
    .some((id) => !$(id)?.classList.contains('hidden'));
}

function resolve(member) {
  hideAll();
  state.member = member || null;
  if (!member) {
    memberPhoneNumber = '';
    if ($('memberNicknameInput')) $('memberNicknameInput').value = '';
    ['memberConsentInput', 'memberOrderHistoryConsent', 'memberPersonalizationConsent'].forEach(id => {
      if ($(id)) $(id).checked = false;
    });
  }
  const resolveCallback = onMemberResolved;
  onMemberResolved = null;
  resolveCallback?.(state.member);
}

function renderPhone() {
  const element = $('memberPhoneDisplay');
  if (element) element.textContent = memberPhoneNumber || '';
  const next = $('memberLoginNext');
  if (next) next.disabled = memberPhoneNumber.length !== 10;
}

function renderRegisterConsent() {
  const consentInput = $('memberConsentInput');
  const done = $('memberRegisterDone');
  if (done) done.disabled = !consentInput?.checked;
}

function onKey(k) {
  if (k === 'clear') memberPhoneNumber = '';
  else if (k === 'back') memberPhoneNumber = memberPhoneNumber.slice(0, -1);
  else if (/^\d$/.test(k) && memberPhoneNumber.length < 10) memberPhoneNumber += k;
  setHint('memberLoginHint', LOGIN_HINT_DEFAULT);
  const next = $('memberLoginNext');
  if (next) next.textContent = '下一步 →';
  renderPhone();
}

async function submitLogin() {
  if (memberPhoneNumber.length !== 10) return;
  if (memberLookupOutcome) {
    await entryHooks.onMemberRetry?.();
    memberLookupOutcome = '';
  }
  const sessionId = getRequiredRuntimeDependency('sessionId');
  setHint('memberLoginHint', '正在登入…');
  setButtonBusy('memberLoginNext', true, '登入中…', '下一步 →');
  try {
    const res = await api.memberLogin(sessionId, memberPhoneNumber);
    if (res && res.found && res.member) {
      await entryHooks.onMemberFound?.(res.member);
      resolve(res.member);
      return;
    }
    await entryHooks.onMemberNotFound?.();
    memberLookupOutcome = 'not_found';
    setHint('memberLoginHint', '查無會員。您可以修正電話、註冊會員，或改用訪客點餐。', true);
    $('memberLoginRegister')?.classList.remove('hidden');
  } catch {
    memberLookupOutcome = 'unavailable';
    try { await entryHooks.onMemberUnavailable?.(); } catch { /* retain the recoverable login UI */ }
    setHint('memberLoginHint', '登入服務暫時無法使用，請重試或改以訪客點餐。', true);
    const next = $('memberLoginNext');
    if (next) next.textContent = '重試';
  } finally {
    const next = $('memberLoginNext');
    if (next) {
      next.disabled = memberPhoneNumber.length !== 10;
      if (next.textContent === '登入中…') next.textContent = '下一步 →';
    }
  }
}

async function submitRegister() {
  const consentInput = $('memberConsentInput');
  if (!consentInput?.checked) {
    renderRegisterConsent();
    return;
  }
  const nickname = String($('memberNicknameInput')?.value || '').trim();
  const sessionId = getRequiredRuntimeDependency('sessionId');
  setHint('memberRegisterHint', '正在建立會員資料…');
  setButtonBusy('memberRegisterDone', true, '註冊中…', '完成註冊並開始點餐 →');
  try {
    await entryHooks.onRegistrationStarted?.();
    const res = await api.memberRegister(sessionId, memberPhoneNumber, nickname, {
      necessaryTermsAccepted: true,
      orderHistoryConsent: Boolean($('memberOrderHistoryConsent')?.checked),
      personalizationConsent: Boolean($('memberPersonalizationConsent')?.checked),
    });
    if (!res?.ok || !res?.member) throw new Error(res?.error || 'registration failed');
    await entryHooks.onRegistered?.(res.member);
    resolve(res.member);
  } catch {
    setHint('memberRegisterHint', '會員註冊尚未完成，請重試或改以訪客點餐。', true);
    const done = $('memberRegisterDone');
    if (done) done.textContent = '重試註冊';
  } finally {
    renderRegisterConsent();
  }
}

export function showMemberChoice(onResolved, { preserveInput = false, hooks } = {}) {
  onMemberResolved = onResolved;
  // Hooks are the only way this overlay reaches the server. Overwriting them with an
  // empty object silently disconnects guest and member choices, so a caller that omits
  // them keeps the previous set and is reported instead of being quietly accepted.
  if (hooks) entryHooks = hooks;
  else console.error('[member] showMemberChoice 缺少 entry hooks，沿用前一組。');
  memberLookupOutcome = '';
  $('memberLoginRegister')?.classList.add('hidden');
  if (!preserveInput) memberPhoneNumber = '';
  setHint('memberLoginHint', LOGIN_HINT_DEFAULT);
  const next = $('memberLoginNext');
  if (next) next.textContent = '下一步 →';
  ['memberChoiceGuest'].forEach(id => {
    const button = $(id);
    if (button) {
      button.disabled = false;
      button.removeAttribute('aria-busy');
    }
  });
  renderPhone();
  hideAll();
  show($('memberChoiceOverlay'));
}

async function submitGuestOrdering(buttonId, hintId) {
  const button = $(buttonId);
  if (!button || button.disabled) return;
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  if (hintId) setHint(hintId, '正在進入訪客點餐…');
  const accepted = await completeGuestOrderingChoice({
    chooseGuest: entryHooks.onGuest,
    onAccepted: () => resolve(null),
    onRejected: () => {
      if (hintId) setHint(hintId, '暫時無法進入點餐，請確認連線後重試。', true);
    },
  });
  if (!accepted) {
    button.disabled = false;
    button.removeAttribute('aria-busy');
  }
}

// 事件綁定（模組載入時註冊一次；元素不存在則略過）
$('memberChoiceMember')?.addEventListener('click', async () => {
  if (state.member) {
    await entryHooks.onMemberMode?.();
    await entryHooks.onMemberFound?.(state.member);
    resolve(state.member);
    return;
  }
  await entryHooks.onMemberMode?.();
  hideAll();
  setHint('memberLoginHint', LOGIN_HINT_DEFAULT);
  const next = $('memberLoginNext');
  if (next) next.textContent = '下一步 →';
  show($('memberLoginOverlay'));
  renderPhone();
});
$('memberChoiceGuest')?.addEventListener('click', () => submitGuestOrdering('memberChoiceGuest', 'memberChoiceHint'));
$('memberLoginBack')?.addEventListener('click', async () => {
  await entryHooks.onReturnToMode?.();
  hideAll(); show($('memberChoiceOverlay'));
});
$('memberLoginNext')?.addEventListener('click', submitLogin);
$('memberLoginRegister')?.addEventListener('click', () => {
  $('memberRegisterPhone').textContent = memberPhoneNumber;
  $('memberNicknameInput').value = '';
  if ($('memberConsentInput')) $('memberConsentInput').checked = false;
  if ($('memberOrderHistoryConsent')) $('memberOrderHistoryConsent').checked = false;
  if ($('memberPersonalizationConsent')) $('memberPersonalizationConsent').checked = false;
  setHint('memberRegisterHint', `這支號碼 ${memberPhoneNumber} 還不是會員，${REGISTER_HINT_DEFAULT}`);
  renderRegisterConsent();
  hideAll();
  show($('memberRegisterOverlay'));
});
$('memberRegisterBack')?.addEventListener('click', async () => {
  await entryHooks.onMemberRetry?.();
  hideAll();
  setHint('memberLoginHint', LOGIN_HINT_DEFAULT);
  const next = $('memberLoginNext');
  if (next) next.textContent = '下一步 →';
  show($('memberLoginOverlay'));
});
$('memberRegisterDone')?.addEventListener('click', submitRegister);
$('memberConsentInput')?.addEventListener('change', renderRegisterConsent);
renderRegisterConsent();
$('memberKeypad')?.addEventListener('click', (e) => {
  const k = e.target?.getAttribute?.('data-k');
  if (k) onKey(k);
});

export function renderMemberMenuHeader() {
  // 點餐歷史紀錄按鈕：會員一律顯示於底部欄（彈窗內含常點 + 歷史訂單），訪客則隱藏。
  const historyBtn = $('kioskHistoryBtn');
  historyBtn?.classList.toggle('hidden', !state.member);
}

function addItemToCart(item) {
  // cart.js 的 addToCart(item) 接收單一 item 物件（以 item.id 為 key），不是位置參數。
  // 帶上 image（常點有；歷史訂單品項無，cart.js 會依 MCD id 推導本地圖）。
  getRequiredRuntimeDependency('cartManager').addToCart({ id: item.id, name: item.name, price: resolveItemPrice(item), image: item.image || '' });
}

function renderUsualsGrid() {
  const grid = $('memberUsualsGrid');
  if (!grid) return;
  grid.textContent = '';
  const usuals = Array.isArray(state.member?.usuals) ? state.member.usuals : [];
  if (!usuals.length) {
    const empty = document.createElement('div');
    empty.className = 'member-modal-empty';
    empty.textContent = '首次點餐後，這裡會出現您的常點 ✨';
    grid.appendChild(empty);
    return;
  }
  usuals.forEach((item) => {
    const visual = getMenuVisual(item);
    const card = document.createElement('div');
    card.className = 'member-usual-card';

    const count = document.createElement('span');
    count.className = 'member-usual-count';
    count.textContent = `×${item.count}`;

    const img = document.createElement('div');
    img.className = 'member-usual-img';
    if (visual.image) {
      const imageElement = document.createElement('img');
      imageElement.src = visual.image;
      imageElement.alt = item.name || '';
      imageElement.onerror = () => { img.textContent = visual.emoji || '🍔'; };
      img.appendChild(imageElement);
    } else {
      img.textContent = visual.emoji || '🍔';
    }

    const name = document.createElement('div');
    name.className = 'member-usual-name';
    name.textContent = item.name || '';

    const price = document.createElement('div');
    price.className = 'member-usual-price';
    price.textContent = formatItemPrice(item);

    const addBtn = document.createElement('button');
    addBtn.className = 'member-usual-add';
    addBtn.type = 'button';
    addBtn.textContent = '＋ 加入';

    card.append(count, img, name, price, addBtn);
    card.addEventListener('click', () => addItemToCart(item));
    grid.appendChild(card);
  });
}

function reorder(order) {
  (Array.isArray(order.items) ? order.items : []).forEach((it) => {
    for (let i = 0; i < (it.count || 1); i += 1) addItemToCart(it);
  });
}

function formatOrderDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function isOrderCompleted(order) {
  if (order && typeof order.order_status === 'string' && order.order_status) {
    return order.order_status === 'completed';
  }
  if (order && typeof order.is_completed === 'boolean') {
    return order.is_completed;
  }
  // 舊資料的 is_success 是 AI 推播命中率，不是訂單完成狀態。
  return true;
}

function renderHistoryList() {
  const list = $('memberHistoryList');
  if (!list) return;
  list.textContent = '';
  const history = Array.isArray(state.member?.history) ? state.member.history : [];
  if (!history.length) {
    const empty = document.createElement('div');
    empty.className = 'member-modal-empty';
    empty.textContent = '目前還沒有點餐紀錄 🧾';
    list.appendChild(empty);
    return;
  }
  history.forEach((order) => {
    const card = document.createElement('div');
    card.className = 'member-history-card';

    const top = document.createElement('div');
    top.className = 'member-history-top';
    const date = document.createElement('span');
    date.className = 'member-history-date';
    date.textContent = formatOrderDate(order.timestamp);
    const status = document.createElement('span');
    const completed = isOrderCompleted(order);
    status.className = `member-history-status ${completed ? 'is-completed' : 'is-incomplete'}`;
    status.textContent = completed ? '已完成' : '未完成';
    date.appendChild(status);
    const total = document.createElement('span');
    total.className = 'member-history-total';
    total.textContent = `$${Number(order.total || 0)}`;
    top.append(date, total);

    const items = document.createElement('div');
    items.className = 'member-history-items';
    const orderItems = Array.isArray(order.items) ? order.items : [];
    orderItems.forEach((it) => {
      const chip = document.createElement('span');
      chip.className = 'member-history-chip';
      chip.textContent = it.count > 1 ? `${it.name} ×${it.count}` : it.name;
      items.appendChild(chip);
    });

    card.append(top, items);

    if (orderItems.length) {
      const reorderBtn = document.createElement('button');
      reorderBtn.className = 'member-history-reorder';
      reorderBtn.type = 'button';
      reorderBtn.textContent = '↻ 再點一次';
      reorderBtn.addEventListener('click', () => { reorder(order); hide($('memberHistoryModal')); });
      card.appendChild(reorderBtn);
    }

    list.appendChild(card);
  });
}

function openHistoryModal() {
  const m = state.member;
  const sub = $('memberHistorySub');
  if (sub) sub.textContent = m ? `${m.nickname || '會員'} · 第 ${(m.visit_count || 0) + 1} 次光臨` : '';
  const hint = $('memberHistoryHint');
  const history = Array.isArray(m?.history) ? m.history : [];
  if (hint) hint.textContent = history.length ? `最近 ${history.length} 筆` : '';
  renderUsualsGrid();
  renderHistoryList();
  show($('memberHistoryModal'));
}

$('kioskHistoryBtn')?.addEventListener('click', openHistoryModal);
$('memberHistoryModal')?.addEventListener('click', (e) => {
  if (e.target?.closest?.('[data-close]')) hide($('memberHistoryModal'));
});
