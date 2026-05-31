const API = window.location.origin;
const CIRC = 2 * Math.PI * 49;

// ── Menu cache (for name/image lookup) ──
let menuCache = {};

async function loadMenu() {
  try {
    const res = await fetch(`${API}/api/menu`);
    const items = await res.json();
    if (Array.isArray(items)) {
      items.forEach(item => {
        if (item.id) menuCache[item.id] = item;
      });
    }
  } catch { /* 靜默失敗，用 ID fallback */ }
}

function menuName(id)  { return menuCache[id]?.name  || id; }
function menuImage(id) { return menuCache[id]?.image || ''; }

// ── Date in topbar ──
const dateEl = document.getElementById('topbar-date');
if (dateEl) {
  dateEl.textContent = new Date().toLocaleDateString('zh-TW', {
    year: 'numeric', month: '2-digit', day: '2-digit',
  });
}

// ── Admin token helper ──
function adminToken() {
  const params = new URLSearchParams(window.location.search);
  const t = params.get('token') || params.get('admin_token') || sessionStorage.getItem('admin_demo_token') || '';
  if (t) sessionStorage.setItem('admin_demo_token', t);
  return t;
}
function adminHeaders(extra = {}) {
  const t = adminToken();
  return t ? { ...extra, 'X-Admin-Token': t } : extra;
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
    const titles = { stats: '狀態統計', settings: '功能設定', rag: 'RAG 知識庫' };
    const titleEl = document.getElementById('page-title');
    if (titleEl) titleEl.textContent = titles[page] || page;
    if (page === 'stats') loadStats();
    if (page === 'settings') loadSettings();
    if (page === 'rag') loadRagDocs();
  });
});

// ── Helpers ──
function setText(id, v) {
  const el = document.getElementById(id);
  if (el) el.textContent = v;
}

const SOURCE_LABELS = {
  ai_push:          'AI推播',
  choice_hesitation:'猶豫視窗',
  voice_assist:     '語音點餐',
  manual:           '手動',
  menu_card:        '手動',
};

function sourceLabel(src) {
  return SOURCE_LABELS[src] || '手動';
}

function emptyRow(tbody, msg, color) {
  tbody.textContent = '';
  const tr = document.createElement('tr');
  const td = document.createElement('td');
  td.colSpan = 6;
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

    const total   = data.total_sessions ?? 0;
    const clicks  = data.total_ai_push_cart_clicks ?? 0;
    const success = data.success_sessions ?? 0;
    const fail    = data.failure_sessions ?? 0;
    const rate    = data.success_rate ?? 0;
    const score   = data.cumulative_score ?? 0;
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
    setText('s-total',     String(total));
    setText('s-clicks',    String(clicks));
    setText('s-fail',      String(fail));
    setText('s-fail-rate', failRate + '%');

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

  // 統計所有 session 購物車各品項出現頻率（含手動、語音、AI推播）
  const freq = {};
  sessions.forEach(s => {
    if (Array.isArray(s.final_cart_ids)) {
      s.final_cart_ids.forEach(id => { freq[id] = (freq[id] || 0) + 1; });
    }
  });

  const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 3);
  box.textContent = '';

  if (!sorted.length) {
    const empty = document.createElement('div');
    empty.style.cssText = 'color:#adb5c9;font-size:12px';
    empty.textContent = '尚無點餐紀錄。';
    box.appendChild(empty);
    return;
  }

  const maxCount = sorted[0][1];
  const rankClass = ['r1', 'r2', 'r3'];

  sorted.forEach(([id, count], i) => {
    const item = document.createElement('div');
    item.className = 'top3-item';

    const rank = document.createElement('div');
    rank.className = `top3-rank ${rankClass[i] || 'r3'}`;
    rank.textContent = String(i + 1);

    const imgUrl = menuImage(id);
    if (imgUrl) {
      const img = document.createElement('img');
      img.className = 'top3-img';
      img.alt = menuName(id);
      img.src = imgUrl;
      img.onerror = () => { img.style.display = 'none'; };
      item.appendChild(rank);
      item.appendChild(img);
    } else {
      item.appendChild(rank);
    }

    const info = document.createElement('div');
    info.className = 'top3-bar-wrap';

    const name = document.createElement('div');
    name.className = 'top3-name';
    name.textContent = menuName(id);

    const cnt = document.createElement('div');
    cnt.className = 'top3-count';
    cnt.textContent = `出現 ${count} 次`;

    const track = document.createElement('div');
    track.className = 'top3-bar-track';
    const barFill = document.createElement('div');
    barFill.className = 'top3-bar-fill';
    barFill.style.width = Math.round((count / maxCount) * 100) + '%';
    track.appendChild(barFill);

    info.append(name, cnt, track);
    item.appendChild(info);
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
      ? new Date(s.timestamp).toLocaleString('zh-TW', {
          month: '2-digit', day: '2-digit',
          hour: '2-digit', minute: '2-digit',
        })
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
    const names = (s.final_cart_ids || []).map(id => menuName(id));
    tdCart.textContent = names.join('、') || '—';

    // 加入方式欄：聚合每個品項的來源
    const tdSource = document.createElement('td');
    tdSource.style.cssText = 'font-size:11px';
    const sources = s.cart_sources || [];
    if (sources.length) {
      const sourceMap = {};
      sources.forEach(({ id, source }) => {
        if (!id) return;
        if (!sourceMap[id]) sourceMap[id] = new Set();
        sourceMap[id].add(sourceLabel(source));
      });
      const parts = (s.final_cart_ids || []).map(id => {
        const labels = sourceMap[id] ? [...sourceMap[id]].join('/') : '手動';
        return `${menuName(id)}（${labels}）`;
      });
      tdSource.style.color = '#4b5679';
      tdSource.textContent = parts.join('、') || '—';
    } else {
      tdSource.style.color = '#adb5c9';
      tdSource.textContent = '—';
    }

    tr.append(tdTs, tdSid, tdClicks, tdResult, tdCart, tdSource);
    tbody.appendChild(tr);
  });
}

// ── Clear stats ──
async function clearStats() {
  const btn = document.getElementById('clearBtn');
  if (!confirm('確定清除所有點餐統計紀錄？此操作無法還原。')) return;
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`${API}/api/session_stats`, { method: 'DELETE' });
    const data = await res.json();
    if (data.status === 'success') await loadStats();
  } catch {
    alert('清除失敗，請重試。');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── Settings ──

function g(id) { return document.getElementById(id); }
function val(id) { return g(id)?.value?.trim() || ''; }
function setVal(id, v) { if (g(id)) g(id).value = v ?? ''; }
function showRow(id, visible) { g(id)?.classList.toggle('hidden', !visible); }

function onSttProviderChange() {
  const isApi = val('inp-stt-provider') === 'openai_compatible';
  showRow('row-stt-model', !isApi);
  showRow('row-stt-api',   isApi);
  showRow('row-stt-key',   isApi);
}

function onTtsProviderChange() {
  const p = val('inp-tts-provider');
  showRow('row-tts-edge-zh', p === 'edge');
  showRow('row-tts-edge-en', p === 'edge');
  showRow('row-tts-api',     p === 'openai_compatible');
  showRow('row-tts-key',     p === 'openai_compatible');
  showRow('row-tts-voice',   p === 'openai_compatible');
}

async function loadSettings() {
  try {
    const res = await fetch(`${API}/api/settings`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const s = await res.json();

    setVal('inp-voice-model',   s.VOICE_ASSIST_MODEL  || 'qwen3.5:4b');
    setVal('inp-stt-provider',  s.STT_PROVIDER        || 'faster_whisper');
    setVal('inp-stt-model',     s.STT_MODEL           || 'small');
    setVal('inp-stt-api-url',   s.STT_API_URL         || '');
    setVal('inp-stt-api-key',   s.STT_API_KEY         || '');
    setVal('inp-tts-provider',  s.TTS_PROVIDER        || 'edge');
    setVal('inp-tts-voice-zh',  s.EDGE_TTS_VOICE      || 'zh-TW-HsiaoChenNeural');
    setVal('inp-tts-voice-en',  s.EDGE_TTS_VOICE_EN   || 'en-US-JennyNeural');
    setVal('inp-tts-api-url',   s.TTS_API_URL         || '');
    setVal('inp-tts-api-key',   s.TTS_API_KEY         || '');
    setVal('inp-tts-voice',     s.TTS_VOICE           || 'alloy');
    // RAG
    setVal('inp-rag-enabled',   String(s.RAG_ENABLED  ?? false));
    setVal('inp-rag-threshold', s.RAG_SCORE_THRESHOLD ?? 0.5);
    setVal('inp-rag-top-k',     s.RAG_TOP_K           ?? 3);

    onSttProviderChange();
    onTtsProviderChange();
  } catch (e) {
    console.error('loadSettings failed', e);
  }
}

async function saveSettings() {
  const btn = g('saveSettingsBtn');
  const notice = g('settings-notice');
  if (btn) btn.disabled = true;
  if (notice) { notice.style.display = 'none'; }
  try {
    const body = {
      VOICE_ASSIST_MODEL:  val('inp-voice-model')  || 'qwen3.5:4b',
      STT_PROVIDER:        val('inp-stt-provider')  || 'faster_whisper',
      STT_MODEL:           val('inp-stt-model')     || 'small',
      STT_API_URL:         val('inp-stt-api-url'),
      STT_API_KEY:         val('inp-stt-api-key'),
      TTS_PROVIDER:        val('inp-tts-provider')  || 'edge',
      EDGE_TTS_VOICE:      val('inp-tts-voice-zh')  || 'zh-TW-HsiaoChenNeural',
      EDGE_TTS_VOICE_EN:   val('inp-tts-voice-en')  || 'en-US-JennyNeural',
      TTS_API_URL:         val('inp-tts-api-url'),
      TTS_API_KEY:         val('inp-tts-api-key'),
      TTS_VOICE:           val('inp-tts-voice')     || 'alloy',
      // RAG
      RAG_ENABLED:         val('inp-rag-enabled') === 'true',
      RAG_SCORE_THRESHOLD: parseFloat(val('inp-rag-threshold') || '0.5'),
      RAG_TOP_K:           parseInt(val('inp-rag-top-k') || '3', 10),
    };
    const res = await fetch(`${API}/api/settings`, {
      method: 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (notice) {
      notice.textContent = '✓ 儲存成功';
      notice.style.color = '#1db87a';
      notice.style.display = '';
      setTimeout(() => { notice.style.display = 'none'; }, 3000);
    }
  } catch (e) {
    if (notice) {
      notice.textContent = `✗ 儲存失敗：${e.message}`;
      notice.style.color = '#e84040';
      notice.style.display = '';
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── RAG ──

const RAG_TYPE_LABELS = {
  manual: '政策/規則', faq: 'FAQ', menu_supplement: '菜單補充',
};

function ragNotice(msg, ok = true) {
  const el = document.getElementById('rag-notice');
  if (!el) return;
  el.textContent = msg;
  el.style.color = ok ? '#1db87a' : '#e84040';
  el.style.display = '';
  setTimeout(() => { el.style.display = 'none'; }, 3000);
}

async function loadRagDocs() {
  try {
    const res = await fetch(`${API}/api/rag/docs`, { headers: adminHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const docs = data.docs || [];
    const countEl = document.getElementById('rag-count');
    if (countEl) countEl.textContent = `(${docs.length})`;
    const list = document.getElementById('rag-list');
    if (!list) return;
    list.textContent = '';
    if (!docs.length) {
      list.innerHTML = '<div style="color:#adb5c9;font-size:13px;padding:12px 0">尚無知識文件。</div>';
      return;
    }
    docs.forEach(doc => {
      const card = document.createElement('div');
      card.style.cssText = 'background:#f8fafd;border:1px solid #edf0f7;border-radius:10px;padding:10px 14px;display:flex;gap:10px;align-items:flex-start';
      const body = document.createElement('div');
      body.style.cssText = 'flex:1;min-width:0';
      const tag = document.createElement('span');
      tag.style.cssText = 'font-size:10px;font-weight:700;color:#3b7aee;text-transform:uppercase;letter-spacing:.04em';
      tag.textContent = RAG_TYPE_LABELS[doc.source_type] || doc.source_type;
      const text = document.createElement('div');
      text.style.cssText = 'font-size:12px;color:#2d3a55;margin-top:4px;white-space:pre-wrap;line-height:1.5;max-height:80px;overflow:hidden;text-overflow:ellipsis';
      text.textContent = doc.content;
      body.append(tag, text);
      const del = document.createElement('button');
      del.style.cssText = 'flex-shrink:0;color:#e84040;background:none;border:none;cursor:pointer;font-size:14px;padding:2px 6px';
      const icon = document.createElement('i');
      icon.className = 'fas fa-trash';
      del.appendChild(icon);
      del.onclick = () => deleteRagDoc(doc.id);
      card.append(body, del);
      list.appendChild(card);
    });
  } catch (e) {
    ragNotice(`載入失敗：${e.message}`, false);
  }
}

async function addRagDoc() {
  const content = (document.getElementById('rag-content')?.value || '').trim();
  const type = document.getElementById('rag-type')?.value || 'manual';
  if (!content) { ragNotice('請輸入內容', false); return; }
  try {
    const res = await fetch(`${API}/api/rag/docs`, {
      method: 'POST',
      headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, source_type: type }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (document.getElementById('rag-content')) document.getElementById('rag-content').value = '';
    ragNotice('✓ 新增成功');
    await loadRagDocs();
  } catch (e) {
    ragNotice(`新增失敗：${e.message}`, false);
  }
}

async function deleteRagDoc(id) {
  if (!confirm('確定刪除這筆文件？')) return;
  try {
    const res = await fetch(`${API}/api/rag/docs/${encodeURIComponent(id)}`, {
      method: 'DELETE', headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    ragNotice('✓ 已刪除');
    await loadRagDocs();
  } catch (e) {
    ragNotice(`刪除失敗：${e.message}`, false);
  }
}

async function clearRagDocs() {
  if (!confirm('確定清空全部 RAG 文件？此操作無法還原。')) return;
  try {
    const res = await fetch(`${API}/api/rag/docs`, {
      method: 'DELETE', headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    ragNotice('✓ 已清空');
    await loadRagDocs();
  } catch (e) {
    ragNotice(`清空失敗：${e.message}`, false);
  }
}

// expose to inline handlers
window.onSttProviderChange = onSttProviderChange;
window.onTtsProviderChange = onTtsProviderChange;
window.saveSettings = saveSettings;
window.addRagDoc = addRagDoc;
window.deleteRagDoc = deleteRagDoc;
window.clearRagDocs = clearRagDocs;

// ── Init ──
document.getElementById('refreshBtn')?.addEventListener('click', loadStats);
document.getElementById('clearBtn')?.addEventListener('click', clearStats);

// 先載入菜單對照表，再載入統計
loadMenu().then(loadStats);
setInterval(loadStats, 15000);
