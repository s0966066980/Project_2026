const API = window.location.origin;
const CIRC = 2 * Math.PI * 49; // donut circumference

// ── Date in topbar ──
const dateEl = document.getElementById('topbar-date');
if (dateEl) {
  dateEl.textContent = new Date().toLocaleDateString('zh-TW', {
    year: 'numeric', month: '2-digit', day: '2-digit',
  });
}

// ── Sidebar navigation ──
document.querySelectorAll('.nav-item[data-page]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-item[data-page]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const page = btn.dataset.page;
    document.querySelectorAll('[id^="page-"]').forEach(el => {
      el.style.display = el.id === `page-${page}` ? '' : 'none';
    });
    const titles = { stats: '狀態統計', rag: 'RAG 設定' };
    const titleEl = document.getElementById('page-title');
    if (titleEl) titleEl.textContent = titles[page] || page;
    if (page === 'stats') loadStats();
  });
});

// ── Helpers ──
function setText(id, v) {
  const el = document.getElementById(id);
  if (el) el.textContent = v;
}

function emptyRow(tbody, msg, color) {
  tbody.textContent = '';
  const tr = document.createElement('tr');
  const td = document.createElement('td');
  td.colSpan = 5;
  td.className = 'adm-empty';
  if (color) td.style.color = color;
  td.textContent = msg;
  tr.appendChild(td);
  tbody.appendChild(tr);
}

// ── Stats loader ──
async function loadStats() {
  try {
    const res = await fetch(`${API}/api/session_stats`);
    const data = await res.json();
    if (data.status !== 'success') throw new Error('api error');

    const total    = data.total_sessions ?? 0;
    const clicks   = data.total_ai_push_cart_clicks ?? 0;
    const success  = data.success_sessions ?? 0;
    const fail     = data.failure_sessions ?? 0;
    const rate     = data.success_rate ?? 0;
    const score    = data.cumulative_score ?? 0;
    const failRate = total > 0 ? Math.round((fail / total) * 100) : 0;

    // Donut
    const pct = Math.round(rate * 100);
    setText('d-rate', pct + '%');
    setText('d-success', String(success));
    setText('d-fail', String(fail));
    setText('d-score', (score >= 0 ? '+' : '') + score);
    const fill = document.getElementById('donut-fill');
    if (fill) fill.setAttribute('stroke-dasharray', `${(pct / 100) * CIRC} ${CIRC}`);

    // Stat cards
    setText('s-total', String(total));
    setText('s-clicks', String(clicks));
    setText('s-fail', String(fail));
    setText('s-fail-rate', failRate + '%');

    // Top-3 by cart item frequency
    const sessions = data.sessions || [];
    renderTop3(sessions);
    renderTable(sessions);

  } catch {
    const tbody = document.getElementById('s-tbody');
    if (tbody) emptyRow(tbody, '載入失敗，請重新整理。', '#e84040');
  }
}

function renderTop3(sessions) {
  const box = document.getElementById('top3-list');
  if (!box) return;

  // Count how often each item appears in successful sessions' carts
  const freq = {};
  sessions.forEach(s => {
    if (s.ai_push_success && Array.isArray(s.final_cart_ids)) {
      s.final_cart_ids.forEach(id => { freq[id] = (freq[id] || 0) + 1; });
    }
  });

  const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 3);
  if (!sorted.length) {
    box.textContent = '';
    const empty = document.createElement('div');
    empty.style.cssText = 'color:#adb5c9;font-size:12px';
    empty.textContent = '尚無成功點餐紀錄。';
    box.appendChild(empty);
    return;
  }

  const maxCount = sorted[0][1];
  const rankClass = ['r1', 'r2', 'r3'];
  box.textContent = '';
  sorted.forEach(([id, count], i) => {
    const item = document.createElement('div');
    item.className = 'top3-item';

    const rank = document.createElement('div');
    rank.className = `top3-rank ${rankClass[i] || 'r3'}`;
    rank.textContent = String(i + 1);

    const img = document.createElement('img');
    img.className = 'top3-img';
    img.alt = id;
    img.src = `https://www.mcdonalds.com.tw/uploads/product/${id}.png`;
    img.onerror = () => { img.style.display = 'none'; };

    const info = document.createElement('div');
    info.className = 'top3-bar-wrap';

    const name = document.createElement('div');
    name.className = 'top3-name';
    name.textContent = id;

    const cnt = document.createElement('div');
    cnt.className = 'top3-count';
    cnt.textContent = `加購 ${count} 次`;

    const track = document.createElement('div');
    track.className = 'top3-bar-track';
    const fill = document.createElement('div');
    fill.className = 'top3-bar-fill';
    fill.style.width = Math.round((count / maxCount) * 100) + '%';
    track.appendChild(fill);

    info.append(name, cnt, track);
    item.append(rank, img, info);
    box.appendChild(item);
  });
}

function renderTable(sessions) {
  const tbody = document.getElementById('s-tbody');
  if (!tbody) return;
  if (!sessions.length) { emptyRow(tbody, '尚無點餐紀錄。'); return; }

  tbody.textContent = '';
  sessions.forEach(s => {
    const tr = document.createElement('tr');

    const tdTs = document.createElement('td');
    tdTs.textContent = s.timestamp
      ? new Date(s.timestamp).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
      : '—';

    const tdSid = document.createElement('td');
    tdSid.style.cssText = 'font-family:monospace;color:#8494b0';
    tdSid.textContent = '…' + String(s.session_id || '').slice(-8);

    const tdClicks = document.createElement('td');
    tdClicks.style.cssText = 'font-weight:700;text-align:center';
    tdClicks.textContent = String(s.ai_push_cart_count ?? 0);

    const tdResult = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = s.ai_push_success ? 'badge-ok' : 'badge-no';
    badge.textContent = s.ai_push_success ? '✓ 成功' : '✗ 未加購';
    tdResult.appendChild(badge);

    const tdCart = document.createElement('td');
    tdCart.style.cssText = 'color:#6b7a99;font-size:11px';
    tdCart.textContent = (s.final_cart_ids || []).join(', ') || '—';

    tr.append(tdTs, tdSid, tdClicks, tdResult, tdCart);
    tbody.appendChild(tr);
  });
}

// ── Init ──
document.getElementById('refreshBtn')?.addEventListener('click', loadStats);
loadStats();
setInterval(loadStats, 15000);
