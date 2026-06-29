// =========================================================
// 會員流程：選擇頁 → 手機登入 → (查無→快速註冊) → 完成回呼。
// onResolved(member|null)：member 物件代表已登入會員，null 代表訪客。
// =========================================================
import * as api from '../shared/apiClient.js';
import { state } from './state.js';
import { getRequiredRuntimeDependency } from './runtime.js';
import { getMenuVisual, formatItemPrice } from './menuVisuals.js';

const $ = (id) => document.getElementById(id);
let memberPhoneNumber = '';
let onMemberResolved = null;

function show(element) { element?.classList.remove('hidden'); element?.setAttribute('aria-hidden', 'false'); }
function hide(element) { element?.classList.add('hidden'); element?.setAttribute('aria-hidden', 'true'); }

function hideAll() {
  ['memberChoiceOverlay', 'memberLoginOverlay', 'memberRegisterOverlay'].forEach((id) => hide($(id)));
}

export function getMember() { return state.member; }

export function isMemberFlowVisible() {
  return ['memberChoiceOverlay', 'memberLoginOverlay', 'memberRegisterOverlay']
    .some((id) => !$(id)?.classList.contains('hidden'));
}

function resolve(member) {
  hideAll();
  state.member = member || null;
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

function onKey(k) {
  if (k === 'clear') memberPhoneNumber = '';
  else if (k === 'back') memberPhoneNumber = memberPhoneNumber.slice(0, -1);
  else if (/^\d$/.test(k) && memberPhoneNumber.length < 10) memberPhoneNumber += k;
  renderPhone();
}

async function submitLogin() {
  if (memberPhoneNumber.length !== 10) return;
  const sessionId = getRequiredRuntimeDependency('sessionId');
  const res = await api.memberLogin(sessionId, memberPhoneNumber).catch(() => ({ found: false }));
  if (res && res.found && res.member) {
    resolve(res.member);
  } else {
    $('memberRegisterPhone').textContent = memberPhoneNumber;
    $('memberNicknameInput').value = '';
    hideAll();
    show($('memberRegisterOverlay'));
  }
}

async function submitRegister() {
  const nickname = String($('memberNicknameInput')?.value || '').trim();
  const sessionId = getRequiredRuntimeDependency('sessionId');
  const res = await api.memberRegister(sessionId, memberPhoneNumber, nickname).catch(() => null);
  resolve(res && res.ok ? res.member : null);
}

export function showMemberChoice(onResolved) {
  onMemberResolved = onResolved;
  memberPhoneNumber = '';
  renderPhone();
  hideAll();
  show($('memberChoiceOverlay'));
}

// 事件綁定（模組載入時註冊一次；元素不存在則略過）
$('memberChoiceMember')?.addEventListener('click', () => { hideAll(); show($('memberLoginOverlay')); renderPhone(); });
$('memberChoiceGuest')?.addEventListener('click', () => resolve(null));
$('memberLoginBack')?.addEventListener('click', () => { hideAll(); show($('memberChoiceOverlay')); });
$('memberLoginSkip')?.addEventListener('click', () => resolve(null));
$('memberLoginNext')?.addEventListener('click', submitLogin);
$('memberRegisterBack')?.addEventListener('click', () => { hideAll(); show($('memberLoginOverlay')); });
$('memberRegisterSkip')?.addEventListener('click', () => resolve(null));
$('memberRegisterDone')?.addEventListener('click', submitRegister);
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
  getRequiredRuntimeDependency('cartManager').addToCart({ id: item.id, name: item.name, price: Number(item.price || 0), image: item.image || '' });
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
    if (order.is_success === false) {
      const failed = document.createElement('span');
      failed.className = 'member-history-failed';
      failed.textContent = '未完成';
      date.appendChild(failed);
    }
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
