// =========================================================
// 會員流程：選擇頁 → 手機登入 → (查無→快速註冊) → 完成回呼。
// onResolved(member|null)：member 物件代表已登入會員，null 代表訪客。
// =========================================================
import * as api from '../shared/api.js';
import { state } from './state.js';
import { sessionId, cartManager } from './app.js';
import { getMenuVisual, formatItemPrice } from './menu_visuals.js';

const $ = (id) => document.getElementById(id);
let _phone = '';
let _onResolved = null;

function show(el) { el?.classList.remove('hidden'); el?.setAttribute('aria-hidden', 'false'); }
function hide(el) { el?.classList.add('hidden'); el?.setAttribute('aria-hidden', 'true'); }

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
  const cb = _onResolved;
  _onResolved = null;
  cb?.(state.member);
}

function renderPhone() {
  const el = $('memberPhoneDisplay');
  if (el) el.textContent = _phone || '';
  const next = $('memberLoginNext');
  if (next) next.disabled = _phone.length !== 10;
}

function onKey(k) {
  if (k === 'clear') _phone = '';
  else if (k === 'back') _phone = _phone.slice(0, -1);
  else if (/^\d$/.test(k) && _phone.length < 10) _phone += k;
  renderPhone();
}

async function submitLogin() {
  if (_phone.length !== 10) return;
  const res = await api.memberLogin(sessionId, _phone).catch(() => ({ found: false }));
  if (res && res.found && res.member) {
    resolve(res.member);
  } else {
    $('memberRegisterPhone').textContent = _phone;
    $('memberNicknameInput').value = '';
    hideAll();
    show($('memberRegisterOverlay'));
  }
}

async function submitRegister() {
  const nickname = String($('memberNicknameInput')?.value || '').trim();
  const res = await api.memberRegister(sessionId, _phone, nickname).catch(() => null);
  resolve(res && res.ok ? res.member : null);
}

export function showMemberChoice(onResolved) {
  _onResolved = onResolved;
  _phone = '';
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
  const bar = $('memberMenuBar');
  const m = state.member;
  if (!bar) return;
  if (!m) { bar.classList.add('hidden'); return; }
  bar.classList.remove('hidden');
  $('memberMenuAvatar').textContent = (m.nickname || '會員').slice(0, 1);
  $('memberMenuName').textContent = `歡迎回來，${m.nickname || '會員'} 👋`;
  $('memberMenuMeta').textContent = `第 ${m.visit_count + 1} 次光臨 · 會員`;

  const row = $('memberUsualsRow');
  row.textContent = '';
  const usuals = Array.isArray(m.usuals) ? m.usuals : [];
  if (!usuals.length) {
    const empty = document.createElement('div');
    empty.className = 'member-usuals-empty';
    empty.textContent = '首次點餐後，這裡會出現您的常點 ✨';
    empty.style.cssText = 'font-size:12px;color:#9a8978;padding:6px 2px';
    row.appendChild(empty);
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
      const el = document.createElement('img');
      el.src = visual.image; el.alt = item.name || '';
      el.onerror = () => { img.textContent = visual.emoji || '🍔'; };
      img.appendChild(el);
    } else {
      img.textContent = visual.emoji || '🍔';
    }

    const name = document.createElement('div');
    name.className = 'member-usual-name';
    name.textContent = item.name || '';

    const price = document.createElement('div');
    price.className = 'member-usual-price';
    price.textContent = formatItemPrice(item);

    card.append(count, img, name, price);
    card.addEventListener('click', () => {
      // cart.js 的 addToCart(item) 接收單一 item 物件（以 item.id 為 key），不是位置參數。
      cartManager.addToCart({ id: item.id, name: item.name, price: Number(item.price || 0) });
    });
    row.appendChild(card);
  });
}
