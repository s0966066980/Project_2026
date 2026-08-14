const DEFAULT_PUSH_PROMPT =
  '你是麥當勞自助點餐機的 AI 推播助手。' +
  '只能從菜單白名單選 1 個餐點，不能發明不存在的餐點。' +
  '輸出純 JSON：{"recommendation_id":"MCDxxx","push_text":"繁體中文促購短句"}。';

import {
  createDiagnosticClient,
  createOperationsClient,
  createPushCopyClient,
} from '../../shared/api/capabilityClients.js';

/**
 * Each tab owns a disjoint set of settings keys, so saving one never rewrites another.
 * @type {Record<string, string[]>}
 */
const TAB_KEYS = {
  ai: ['LLM_ROUTING_POLICY', 'MODEL_NAME', 'VOICE_ASSIST_MODEL',
    'NIM_MODEL_NAME', 'NIM_VOICE_MODEL', 'NIM_CUSTOM_TEXT_MODELS', 'NIM_CUSTOM_VOICE_MODELS',
    'OLLAMA_TEMPERATURE', 'OLLAMA_NUM_PREDICT'],
  push: ['AI_PUSH_SCOPE_MODE', 'AI_PUSH_SCOPE_CATEGORIES', 'AI_PUSH_REFRESH_SEC',
    'AI_PUSH_EXCLUDE_SEEN', 'AI_PUSH_PREFETCH', 'AI_PUSH_TEXT_MIN', 'AI_PUSH_TEXT_MAX'],
  voice: ['STT_PROVIDER', 'STT_MODEL', 'STT_API_URL', 'TTS_PROVIDER', 'EDGE_TTS_VOICE',
    'TTS_API_URL', 'TTS_VOICE'],
  prompt: ['VOICE_ASSIST_SYSTEM_PROMPT', 'AI_PUSH_SYSTEM_PROMPT'],
};

/** @type {Record<string, string>} */
const TAB_LABELS = {
  ai: 'AI 模型', push: 'AI 推播規則', voice: '語音輸入輸出',
  prompt: '系統指令與關鍵詞',
};

/** @param {unknown} value */
function text(value) { return String(value ?? '').trim(); }

/** @param {string} raw */
/**
 * @param {{
 *   apiBaseUrl: string,
 *   adminHeaders: () => Record<string, string>,
 *   getElement: (id: string) => any,
 *   loadOllamaModels: () => Promise<any>,
 *   confirmAction?: (message: string) => boolean
 * }} options
 */
export function createSettingsAdmin({ apiBaseUrl, adminHeaders, getElement, loadOllamaModels, confirmAction = message => window.confirm(message) }) {
  const operationsClient = createOperationsClient({ baseUrl: apiBaseUrl, headers: adminHeaders });
  const diagnosticClient = createDiagnosticClient({ baseUrl: apiBaseUrl, headers: adminHeaders });
  const pushCopyClient = createPushCopyClient({ baseUrl: apiBaseUrl, headers: adminHeaders });
  /** @type {any} */
  let loaded = {};
  let activeTab = 'ai';
  /** @type {Record<string, boolean>} */
  const dirty = {};
  let busy = false;
  // NIM Model Catalog fetched through the versioned Operations client; Custom NIM Model Entries the
  // operator has added on top of it (persisted alongside NIM_MODEL_NAME / NIM_VOICE_MODEL).
  /** @type {string[]} */ let nimTextCatalog = [];
  /** @type {string[]} */ let nimVoiceCatalog = [];
  /** @type {string[]} */ let customTextModels = [];
  /** @type {string[]} */ let customVoiceModels = [];
  // 推播範圍選定的類別；以陣列保存順序，畫面以 chip 呈現。
  /** @type {string[]} */ let pushScopeCategories = [];
  // 推薦詞管理分頁的資料，只在進入該分頁時載入。
  /** @type {{items: any[], categories: string[], offers: any[], textMin: number, textMax: number, loaded: boolean}} */
  let copyState = { items: [], categories: [], offers: [], textMin: 18, textMax: 34, loaded: false };
  let editingItemId = '';

  /** @param {string} id */
  function value(id) { return text(getElement(id)?.value); }
  /** @param {string} id @param {unknown} next */
  function setValue(id, next) { if (getElement(id)) getElement(id).value = next ?? ''; }

  // ── 分頁 ────────────────────────────────────────────────
  /** @param {string} tab */
  function showTab(tab) {
    if (tab === activeTab) return;
    if (dirty[activeTab] && !confirmAction(`「${TAB_LABELS[activeTab]}」有未儲存的變更，離開後會遺失。仍要切換嗎？`)) return;
    if (dirty[activeTab]) { restoreTab(activeTab); markDirty(activeTab, false); }
    activeTab = tab;
    document.querySelectorAll('[data-settings-tab]').forEach(node => {
      const button = /** @type {HTMLElement} */ (node);
      const selected = button.dataset.settingsTab === tab;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-selected', String(selected));
    });
    document.querySelectorAll('[data-settings-panel]').forEach(node => {
      const panel = /** @type {HTMLElement} */ (node);
      panel.hidden = panel.dataset.settingsPanel !== tab;
      panel.classList.toggle('active', panel.dataset.settingsPanel === tab);
    });
    if (tab === 'history') loadHistory();
    if (tab === 'ai') refreshRuntimeState();
    if (tab === 'brain') globalThis.loadDiagnosticWorkbench?.();
    // 兩個分頁都需要這份資料：推薦詞管理要列表，推播規則要可選的類別清單。
    if (tab === 'copy' || tab === 'push') loadCopy();
    // 進分頁就先看一次批次狀態：上一次的產生可能仍在背景跑，關過分頁也要能接回進度。
    if (tab === 'copy') void pollBatch();
  }

  /** @param {string} tab @param {boolean} isDirty */
  function markDirty(tab, isDirty) {
    dirty[tab] = isDirty;
    const marker = document.querySelector(`[data-settings-tab="${tab}"] .settings-unsaved`);
    if (marker) /** @type {HTMLElement} */ (marker).hidden = !isDirty;
  }

  /** @param {string} tab @param {string} message @param {'ok'|'error'|''} [kind] */
  function setSaveMessage(tab, message, kind = '') {
    const node = document.querySelector(`[data-save-msg="${tab}"]`);
    if (!node) return;
    node.textContent = message;
    node.className = `settings-save-msg${kind ? ` ${kind}` : ''}`;
  }

  /** @param {string} tab */
  function clearErrors(tab) {
    (TAB_KEYS[tab] || []).forEach(/** @param {string} key */ key => {
      const node = document.querySelector(`[data-error-for="${key}"]`);
      if (node) node.textContent = '';
    });
  }

  /** @param {any[]} errors */
  function renderErrors(errors = []) {
    errors.forEach(error => {
      const key = text(error.path).split('.').pop();
      const node = key && document.querySelector(`[data-error-for="${key}"]`);
      if (node) node.textContent = text(error.message) || '請檢查此欄位。';
    });
  }

  // ── NIM 模型目錄 ─────────────────────────────────────────
  /** @param {string} selectId @param {string[]} catalog @param {string[]|undefined} customList @param {string} currentValue */
  function populateNimSelect(selectId, catalog, customList, currentValue) {
    const sel = getElement(selectId);
    if (!sel) return;
    sel.textContent = '';
    const seen = new Set();
    let matched = false;
    [...catalog, ...(Array.isArray(customList) ? customList : [])].forEach(model => {
      const id = text(model);
      if (!id || seen.has(id)) return;
      seen.add(id);
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = id;
      if (id === currentValue) { opt.selected = true; matched = true; }
      sel.appendChild(opt);
    });
    if (!matched && currentValue) {
      const opt = document.createElement('option');
      opt.value = currentValue;
      opt.textContent = `${currentValue}（未在清單中）`;
      opt.selected = true;
      sel.insertBefore(opt, sel.firstChild);
    }
  }

  /**
   * The diagnostic panel offers the same catalog plus a trailing 「自訂…」 sentinel. A model
   * typed behind that sentinel is a one-shot Diagnostic Provider Override — it is deliberately
   * not added to customVoiceModels, so trying a model never writes to the settings document.
   * @param {string} currentValue
   */
  function populateDiagnosticNimSelect(currentValue) {
    const select = getElement('test-inp-nim-model');
    if (!select) return;
    populateNimSelect('test-inp-nim-model', nimVoiceCatalog, customVoiceModels, currentValue);
    const custom = document.createElement('option');
    custom.value = '__custom__';
    custom.textContent = '自訂…';
    select.appendChild(custom);
    getElement('test-inp-nim-model-custom')?.setAttribute('hidden', '');
  }

  /** @param {'text'|'voice'} kind */
  function addCustomNimModel(kind) {
    const isVoice = kind === 'voice';
    const inputId = isVoice ? 'inp-nim-voice-model-custom' : 'inp-nim-model-custom';
    const selectId = isVoice ? 'inp-nim-voice-model' : 'inp-nim-model';
    const catalog = isVoice ? nimVoiceCatalog : nimTextCatalog;
    const list = isVoice ? customVoiceModels : customTextModels;
    const raw = text(getElement(inputId)?.value);
    if (!raw) return;
    if (!list.includes(raw)) list.push(raw);
    setValue(inputId, '');
    populateNimSelect(selectId, catalog, list, raw);
    // The diagnostic dropdown reads the same voice list, so a model added here has to appear
    // there immediately — otherwise it stays invisible to diagnostics until the next reload.
    if (isVoice) populateDiagnosticNimSelect(value('test-inp-nim-model') || raw);
    markDirty('ai', true);
  }

  // ── 就緒指示 ─────────────────────────────────────────────
  /** @param {'ok'|'warn'|'err'} kind @param {string} label */
  function pill(kind, label) {
    const span = document.createElement('span');
    span.className = `ready-pill ${kind}`;
    span.textContent = label;
    return span;
  }

  /** @param {string} elementId @param {Array<Node|string>} parts */
  function renderReady(elementId, parts) {
    const node = getElement(elementId);
    if (!node) return;
    node.textContent = '';
    parts.forEach(part => node.append(part));
  }

  async function refreshRuntimeState() {
    try {
      const readiness = await operationsClient.llmRouting();
      renderReady('llmLocalReady', readiness.local.ready
        ? [pill('ok', 'Ollama 服務在線'), `模型 ${text(readiness.local.model)}`]
        : [pill(readiness.local.used ? 'err' : 'warn', 'Ollama 無法連線'), text(readiness.local.detail)]);
      renderReady('llmCloudReady', readiness.cloud.ready
        ? [pill('ok', '金鑰已設定'), `環境變數 ${text(readiness.cloud.credential_env)}`]
        : [pill(readiness.cloud.used ? 'err' : 'warn', '金鑰未設定'), text(readiness.cloud.detail)]);
      nimTextCatalog = Array.isArray(readiness.nim_text_model_catalog) ? readiness.nim_text_model_catalog : nimTextCatalog;
      nimVoiceCatalog = Array.isArray(readiness.nim_voice_model_catalog) ? readiness.nim_voice_model_catalog : nimVoiceCatalog;
      populateNimSelect('inp-nim-model', nimTextCatalog, customTextModels, value('inp-nim-model') || loaded.NIM_MODEL_NAME || '');
      populateNimSelect('inp-nim-voice-model', nimVoiceCatalog, customVoiceModels, value('inp-nim-voice-model') || loaded.NIM_VOICE_MODEL || '');
      // 模型診斷送的是語音模式提示詞，因此沿用語音那一份 NIM 目錄與已儲存的語音模型，
      // 讓「診斷測的」與「顧客實際會用的」是同一個模型，不必憑記憶重打型號。
      populateDiagnosticNimSelect(value('test-inp-nim-model') || loaded.NIM_VOICE_MODEL || '');
    } catch {
      renderReady('llmLocalReady', [pill('warn', '無法取得就緒狀態')]);
      renderReady('llmCloudReady', []);
    }
    await refreshTraffic();
  }

  async function refreshTraffic() {
    const stats = getElement('llmTrafficStats');
    const note = getElement('llmTrafficNote');
    if (!stats) return;
    let traffic;
    try {
      traffic = await operationsClient.llmTraffic();
    } catch {
      stats.textContent = '無法取得實際請求統計。';
      if (note) note.hidden = true;
      return;
    }
    stats.textContent = '';
    /** @type {Record<string, string>} */
    const labels = { ollama: '本機 Ollama', nvidia_nim: '雲端 NVIDIA NIM' };
    const entries = Object.entries(traffic.providers || {});
    if (!entries.length) {
      stats.textContent = '本次啟動後尚未有任何 AI 請求。';
    } else {
      entries.forEach(([provider, count]) => {
        const box = document.createElement('div');
        box.className = 'settings-live-stat';
        const number = document.createElement('b');
        number.textContent = String(count);
        const caption = document.createElement('span');
        caption.textContent = labels[provider] || provider;
        box.append(number, caption);
        stats.appendChild(box);
      });
      const fallbackBox = document.createElement('div');
      fallbackBox.className = 'settings-live-stat';
      const fallbackCount = document.createElement('b');
      fallbackCount.textContent = String(traffic.fallbacks || 0);
      const fallbackCaption = document.createElement('span');
      fallbackCaption.textContent = '退回其他提供者';
      fallbackBox.append(fallbackCount, fallbackCaption);
      stats.appendChild(fallbackBox);
    }
    if (note) {
      const message = mismatchMessage(value('inp-llm-policy'), traffic.providers || {});
      note.textContent = message;
      note.hidden = !message;
    }
  }

  // ── AI 推播規則 ──────────────────────────────────────────
  function scopeMode() {
    const checked = document.querySelector('input[name="push-scope"]:checked');
    return text(/** @type {HTMLInputElement|null} */ (checked)?.value) || 'all';
  }

  /** @param {string} mode */
  function setScopeMode(mode) {
    document.querySelectorAll('input[name="push-scope"]').forEach(node => {
      const radio = /** @type {HTMLInputElement} */ (node);
      radio.checked = radio.value === mode;
    });
  }

  function renderScopeCategories() {
    const box = getElement('push-scope-chips');
    if (box) {
      box.textContent = '';
      pushScopeCategories.forEach(name => {
        const chip = document.createElement('span');
        chip.className = 'setting-chip';
        chip.append(name);
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = '×';
        remove.setAttribute('aria-label', `移除 ${name}`);
        remove.addEventListener('click', () => {
          pushScopeCategories = pushScopeCategories.filter(row => row !== name);
          renderScopeCategories();
          markDirty('push', true);
        });
        chip.appendChild(remove);
        box.appendChild(chip);
      });
    }
    const picker = getElement('inp-push-scope-add');
    if (picker) {
      picker.textContent = '';
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = '＋ 加入類別…';
      picker.appendChild(placeholder);
      copyState.categories
        .filter(name => !pushScopeCategories.includes(name))
        .forEach(name => {
          const option = document.createElement('option');
          option.value = name;
          option.textContent = name;
          picker.appendChild(option);
        });
    }
  }

  // ── 推薦詞管理 ───────────────────────────────────────────
  async function loadCopy(force = false) {
    if (copyState.loaded && !force) { renderCopyRows(); return; }
    const body = getElement('copy-tbody');
    if (body) body.textContent = '';
    try {
      const data = await pushCopyClient.list();
      copyState = {
        items: Array.isArray(data.items) ? data.items : [],
        categories: Array.isArray(data.categories) ? data.categories : [],
        offers: Array.isArray(data.offers) ? data.offers : [],
        textMin: Number(data.text_min) || 18,
        textMax: Number(data.text_max) || 34,
        loaded: true,
      };
      renderScopeCategories();
      const filter = getElement('copy-filter-category');
      if (filter) {
        const previous = filter.value;
        filter.textContent = '';
        const all = document.createElement('option');
        all.value = '';
        all.textContent = '全部類別';
        filter.appendChild(all);
        copyState.categories.forEach(name => {
          const option = document.createElement('option');
          option.value = name;
          option.textContent = name;
          filter.appendChild(option);
        });
        filter.value = previous;
      }
      renderCopyRows();
    } catch (error) {
      if (body) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 7;
        cell.style.cssText = 'text-align:center;color:var(--danger);height:60px';
        cell.textContent = `推薦詞載入失敗：${/** @type {any} */ (error).message}`;
        row.appendChild(cell);
        body.appendChild(row);
      }
    }
  }

  function filteredCopyItems() {
    const keyword = text(getElement('copy-search')?.value).toLowerCase();
    const category = text(getElement('copy-filter-category')?.value);
    const status = text(getElement('copy-filter-status')?.value);
    return copyState.items.filter(row => {
      if (category && row.category !== category) return false;
      if (status === 'new' && !row.is_new_item) return false;
      if (status && status !== 'new' && row.effective_status !== status) return false;
      if (!keyword) return true;
      return `${row.name} ${row.item_id}`.toLowerCase().includes(keyword);
    });
  }

  /** @param {string} label @param {'live'|'non'|'warn'} kind */
  function copyPill(label, kind) {
    const span = document.createElement('span');
    span.className = `copy-pill ${kind}`;
    span.textContent = label;
    return span;
  }

  function renderCopyRows() {
    const body = getElement('copy-tbody');
    if (!body) return;
    const rows = filteredCopyItems();
    const summary = getElement('copy-summary');
    if (summary) {
      const missing = copyState.items.filter(row => row.effective_status === 'description_fallback').length;
      summary.textContent = `顯示 ${rows.length} / ${copyState.items.length} 項${missing ? `　尚未撰寫 ${missing} 項` : ''}`;
    }
    body.textContent = '';
    if (!rows.length) {
      const empty = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 7;
      cell.style.cssText = 'text-align:center;color:var(--text2);height:60px';
      cell.textContent = '沒有符合條件的品項。';
      empty.appendChild(cell);
      body.appendChild(empty);
      return;
    }
    rows.forEach(row => {
      const tr = document.createElement('tr');
      const name = document.createElement('td');
      name.textContent = row.name;
      const id = document.createElement('td');
      id.className = 'copy-mono';
      id.textContent = row.item_id;
      const category = document.createElement('td');
      category.textContent = row.category;
      const copy = document.createElement('td');
      copy.className = 'copy-text';
      copy.title = row.effective_text;
      copy.textContent = row.effective_text || '（尚未撰寫，且菜單也沒有描述）';
      if (row.effective_status === 'description_fallback') copy.style.color = 'var(--text2)';
      const campaign = document.createElement('td');
      if (row.campaign_copy && row.campaign_live) campaign.appendChild(copyPill('進行中', 'live'));
      else if (row.campaign_copy) campaign.appendChild(copyPill('活動已結束', 'warn'));
      else campaign.appendChild(copyPill('無', 'non'));
      const isNew = document.createElement('td');
      isNew.textContent = row.is_new_item ? (row.new_until ? `✓ 至 ${row.new_until}` : '✓') : '—';
      const action = document.createElement('td');
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'refresh-btn';
      edit.textContent = '編輯';
      edit.addEventListener('click', () => toggleCopyEditor(row.item_id));
      action.appendChild(edit);
      tr.append(name, id, category, copy, campaign, isNew, action);
      body.appendChild(tr);
      if (editingItemId === row.item_id) body.appendChild(buildCopyEditorRow(row));
    });
  }

  // ── 一鍵產生推薦詞 ───────────────────────────────────────
  let batchPollTimer = 0;

  /** @param {any} batch */
  function renderBatchProgress(batch) {
    const box = getElement('copy-batch-progress');
    if (!box) return;
    if (!batch) { box.hidden = true; box.textContent = ''; return; }
    const running = ['pending', 'running'].includes(String(batch.status));
    box.hidden = false;
    box.textContent = '';

    const head = document.createElement('div');
    const label = batch.mode === 'regenerate' ? '重產推薦詞' : '補齊缺漏推薦詞';
    const statusText = running
      ? `${label}進行中：${batch.processed} / ${batch.total}`
      : `${label}已結束：成功 ${batch.succeeded} 筆${batch.failed ? `、失敗 ${batch.failed} 筆` : ''}`;
    head.textContent = statusText;
    head.style.fontWeight = '650';

    const bar = document.createElement('div');
    bar.className = 'copy-batch-bar';
    const fill = document.createElement('i');
    fill.style.width = `${Math.min(100, Number(batch.percent) || 0)}%`;
    bar.appendChild(fill);

    box.append(head, bar);
    if (running) {
      const note = document.createElement('div');
      note.className = 'copy-batch-note';
      note.textContent = '可以關掉這個分頁去做別的事，產生會在背景繼續，回來還看得到進度。';
      box.appendChild(note);
    }
    if (batch.last_error) {
      const note = document.createElement('div');
      note.className = 'copy-batch-note error';
      note.textContent = `最後一筆錯誤：${batch.last_error}`;
      box.appendChild(note);
    }
  }

  async function pollBatch() {
    window.clearTimeout(batchPollTimer);
    let batch = null;
    try {
      batch = (await pushCopyClient.batch()).batch;
    } catch {
      return;   // 輪詢失敗不打擾操作者，下次進分頁再試
    }
    renderBatchProgress(batch);
    if (batch && ['pending', 'running'].includes(String(batch.status))) {
      batchPollTimer = window.setTimeout(pollBatch, 3000);
    } else if (batch) {
      // 批次結束後把新產生的文案載回列表，否則畫面還停在舊內容。
      await loadCopy(true);
    }
  }

  /** @param {'fill_missing'|'regenerate'} mode */
  async function startBatch(mode) {
    /** @type {{mode: string, item_ids?: string[]}} */
    const body = { mode };
    if (mode === 'regenerate') {
      const rows = filteredCopyItems();
      if (!rows.length) return window.alert('目前篩選結果沒有品項可以重產。');
      if (!confirmAction(`將重新產生 ${rows.length} 個品項的常態推薦詞，已經人工修改過的內容會被覆蓋。確定要繼續嗎？`)) return;
      body.item_ids = rows.map(row => row.item_id);
    }
    try {
      const result = await pushCopyClient.startBatch(body);
      renderBatchProgress(result.batch);
      void pollBatch();
    } catch (error) {
      window.alert(/** @type {any} */ (error).message);
    }
  }

  /** @param {string} itemId */
  function toggleCopyEditor(itemId) {
    editingItemId = editingItemId === itemId ? '' : itemId;
    renderCopyRows();
  }

  /** @param {any} row */
  function buildCopyEditorRow(row) {
    const tr = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 7;
    cell.style.padding = '0 11px';

    const box = document.createElement('div');
    box.className = 'copy-editor';

    const baseLabel = document.createElement('label');
    baseLabel.textContent = `常態推薦詞（必填．永遠有效．不得含促銷用語）`;
    const baseText = document.createElement('textarea');
    baseText.className = 'setting-input';
    baseText.value = row.base_copy || row.description || '';
    const baseCount = document.createElement('div');
    baseCount.className = 'copy-count';
    const updateCount = () => {
      const length = text(baseText.value).length;
      const bad = length > 0 && (length < copyState.textMin || length > copyState.textMax);
      baseCount.textContent = `${length} 字（建議 ${copyState.textMin}–${copyState.textMax} 字）`;
      baseCount.classList.toggle('over', bad);
    };
    baseText.addEventListener('input', updateCount);
    updateCount();

    const campaignLabel = document.createElement('label');
    campaignLabel.textContent = '活動推薦詞（選填．活動結束後自動改回常態推薦詞）';
    const offerSelect = document.createElement('select');
    offerSelect.className = 'setting-input';
    const noOffer = document.createElement('option');
    noOffer.value = '';
    noOffer.textContent = '不綁定活動';
    offerSelect.appendChild(noOffer);
    copyState.offers.forEach(offer => {
      const option = document.createElement('option');
      option.value = offer.offer_id;
      option.textContent = offer.title || offer.offer_id;
      if (offer.offer_id === row.campaign_offer_id) option.selected = true;
      offerSelect.appendChild(option);
    });
    // 綁定的活動可能已經結束而不在目前清單中；保留它才不會在儲存時被悄悄清掉。
    if (row.campaign_offer_id && !copyState.offers.some(o => o.offer_id === row.campaign_offer_id)) {
      const stale = document.createElement('option');
      stale.value = row.campaign_offer_id;
      stale.textContent = `${row.campaign_offer_id}（已結束）`;
      stale.selected = true;
      offerSelect.appendChild(stale);
    }
    const campaignText = document.createElement('textarea');
    campaignText.className = 'setting-input';
    campaignText.value = row.campaign_copy || '';

    const newWrap = document.createElement('label');
    newWrap.style.cssText = 'display:flex;align-items:center;gap:8px;font-weight:600';
    const newCheck = document.createElement('input');
    newCheck.type = 'checkbox';
    newCheck.checked = Boolean(row.is_new_item);
    const newUntil = document.createElement('input');
    newUntil.type = 'date';
    newUntil.className = 'setting-input';
    newUntil.style.width = '160px';
    newUntil.value = row.new_until || '';
    newWrap.append(newCheck, '新品', newUntil, '（到期後自動不再算新品）');

    const message = document.createElement('div');
    message.className = 'setting-error';

    const actions = document.createElement('div');
    actions.className = 'copy-editor-actions';
    const genBase = document.createElement('button');
    genBase.type = 'button';
    genBase.className = 'refresh-btn';
    genBase.textContent = '產生常態推薦詞';
    const genCampaign = document.createElement('button');
    genCampaign.type = 'button';
    genCampaign.className = 'refresh-btn';
    genCampaign.textContent = '產生活動推薦詞';
    const save = document.createElement('button');
    save.type = 'button';
    save.className = 'refresh-btn settings-primary';
    save.textContent = '儲存';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'refresh-btn';
    cancel.textContent = '取消';

    /** @param {'base'|'campaign'} slot @param {HTMLButtonElement} button */
    async function generate(slot, button) {
      message.textContent = '';
      button.disabled = true;
      const original = button.textContent;
      button.textContent = '產生中…';
      try {
        const result = await pushCopyClient.generate(row.item_id, { slot, campaign_offer_id: offerSelect.value });
        if (slot === 'base') { baseText.value = result.push_text; updateCount(); }
        else campaignText.value = result.push_text;
        if (Array.isArray(result.unverified_terms) && result.unverified_terms.length) {
          message.textContent = `產生的內容含促銷用語（${result.unverified_terms.join('、')}），儲存前請修掉。`;
        }
      } catch (error) {
        message.textContent = /** @type {any} */ (error).message;
      } finally {
        button.disabled = false;
        button.textContent = original;
      }
    }

    genBase.addEventListener('click', () => generate('base', genBase));
    genCampaign.addEventListener('click', () => generate('campaign', genCampaign));
    cancel.addEventListener('click', () => toggleCopyEditor(row.item_id));
    save.addEventListener('click', async () => {
      message.textContent = '';
      save.disabled = true;
      try {
        await pushCopyClient.save(row.item_id, {
          base_copy: text(baseText.value),
          campaign_copy: text(campaignText.value),
          campaign_offer_id: text(offerSelect.value),
          is_new_item: newCheck.checked,
          new_until: text(newUntil.value),
        });
        editingItemId = '';
        await loadCopy(true);
      } catch (error) {
        message.textContent = /** @type {any} */ (error).message;
      } finally {
        save.disabled = false;
      }
    });

    actions.append(genBase, genCampaign, cancel, save);
    box.append(baseLabel, baseText, baseCount, campaignLabel, offerSelect, campaignText, newWrap, message, actions);
    cell.appendChild(box);
    tr.appendChild(cell);
    return tr;
  }

  // ── 讀取與寫回 ───────────────────────────────────────────
  /** @param {any} settings */
  function restoreForm(settings) {
    setValue('inp-llm-policy', settings.LLM_ROUTING_POLICY || 'local_first');
    customTextModels = Array.isArray(settings.NIM_CUSTOM_TEXT_MODELS) ? [...settings.NIM_CUSTOM_TEXT_MODELS] : [];
    customVoiceModels = Array.isArray(settings.NIM_CUSTOM_VOICE_MODELS) ? [...settings.NIM_CUSTOM_VOICE_MODELS] : [];
    populateNimSelect('inp-nim-model', nimTextCatalog, customTextModels, settings.NIM_MODEL_NAME || '');
    populateNimSelect('inp-nim-voice-model', nimVoiceCatalog, customVoiceModels, settings.NIM_VOICE_MODEL || '');
    populateDiagnosticNimSelect(settings.NIM_VOICE_MODEL || '');
    setValue('test-inp-nim-model-custom', '');
    setValue('inp-nim-model-custom', '');
    setValue('inp-nim-voice-model-custom', '');
    setValue('inp-temperature', settings.OLLAMA_TEMPERATURE ?? 0.8);
    setValue('inp-num-predict', settings.OLLAMA_NUM_PREDICT ?? 2048);
    setValue('inp-voice-prompt-zh', settings.VOICE_ASSIST_SYSTEM_PROMPT || '');
    setValue('inp-push-prompt', settings.AI_PUSH_SYSTEM_PROMPT || DEFAULT_PUSH_PROMPT);
    setValue('inp-push-text-min', settings.AI_PUSH_TEXT_MIN ?? 18);
    setValue('inp-push-text-max', settings.AI_PUSH_TEXT_MAX ?? 34);
    setScopeMode(settings.AI_PUSH_SCOPE_MODE || 'all');
    pushScopeCategories = Array.isArray(settings.AI_PUSH_SCOPE_CATEGORIES) ? [...settings.AI_PUSH_SCOPE_CATEGORIES] : [];
    renderScopeCategories();
    setValue('inp-push-refresh', settings.AI_PUSH_REFRESH_SEC ?? 15);
    if (getElement('inp-push-exclude-seen')) getElement('inp-push-exclude-seen').checked = settings.AI_PUSH_EXCLUDE_SEEN !== false;
    if (getElement('inp-push-prefetch')) getElement('inp-push-prefetch').checked = settings.AI_PUSH_PREFETCH !== false;
    setValue('inp-stt-provider', settings.STT_PROVIDER || 'faster_whisper');
    setValue('inp-stt-model', settings.STT_MODEL || 'small');
    setValue('inp-stt-api-url', settings.STT_API_URL || '');
    setValue('inp-tts-provider', settings.TTS_PROVIDER || 'edge');
    setValue('inp-tts-voice-zh', settings.EDGE_TTS_VOICE || 'zh-TW-HsiaoChenNeural');
    setValue('inp-tts-api-url', settings.TTS_API_URL || '');
    setValue('inp-tts-voice', settings.TTS_VOICE || 'alloy');
    updateSttFields();
    updateTtsFields();
  }

  /** @param {string} tab */
  function restoreTab(tab) {
    restoreForm(loaded);
    clearErrors(tab);
    setSaveMessage(tab, '');
  }

  /** @param {string} tab */
  function payloadFor(tab) {
    if (tab === 'ai') {
      return {
        LLM_ROUTING_POLICY: value('inp-llm-policy') || 'local_first',
        MODEL_NAME: value('inp-model-name') || 'qwen3.5:4b',
        VOICE_ASSIST_MODEL: value('inp-voice-model') || 'qwen3.5:4b',
        NIM_MODEL_NAME: value('inp-nim-model') || 'meta/llama-3.1-8b-instruct',
        NIM_VOICE_MODEL: value('inp-nim-voice-model') || 'meta/llama-3.1-8b-instruct',
        NIM_CUSTOM_TEXT_MODELS: customTextModels,
        NIM_CUSTOM_VOICE_MODELS: customVoiceModels,
        OLLAMA_TEMPERATURE: Number(value('inp-temperature') || '0.8'),
        OLLAMA_NUM_PREDICT: Number(value('inp-num-predict') || '2048'),
      };
    }
    if (tab === 'push') {
      return {
        AI_PUSH_SCOPE_MODE: scopeMode(),
        AI_PUSH_SCOPE_CATEGORIES: pushScopeCategories,
        AI_PUSH_REFRESH_SEC: Number(value('inp-push-refresh') || '15'),
        AI_PUSH_EXCLUDE_SEEN: Boolean(getElement('inp-push-exclude-seen')?.checked),
        AI_PUSH_PREFETCH: Boolean(getElement('inp-push-prefetch')?.checked),
        AI_PUSH_TEXT_MIN: Number(value('inp-push-text-min') || '18'),
        AI_PUSH_TEXT_MAX: Number(value('inp-push-text-max') || '34'),
      };
    }
    if (tab === 'voice') {
      return {
        STT_PROVIDER: value('inp-stt-provider') || 'faster_whisper',
        STT_MODEL: value('inp-stt-model') || 'small',
        STT_API_URL: value('inp-stt-api-url'),
        TTS_PROVIDER: value('inp-tts-provider') || 'edge',
        EDGE_TTS_VOICE: value('inp-tts-voice-zh') || 'zh-TW-HsiaoChenNeural',
        TTS_API_URL: value('inp-tts-api-url'),
        TTS_VOICE: value('inp-tts-voice') || 'alloy',
      };
    }
    if (tab === 'prompt') {
      const push = value('inp-push-prompt');
      return {
        VOICE_ASSIST_SYSTEM_PROMPT: value('inp-voice-prompt-zh'),
        AI_PUSH_SYSTEM_PROMPT: push === DEFAULT_PUSH_PROMPT ? '' : push,
      };
    }
    return {};
  }

  /** @param {string} tab */
  async function saveTab(tab) {
    if (busy) return;
    busy = true;
    const button = document.querySelector(`[data-settings-save="${tab}"]`);
    if (button) { /** @type {HTMLButtonElement} */ (button).disabled = true; }
    clearErrors(tab);
    setSaveMessage(tab, '儲存中…');
    try {
      await operationsClient.patchSettings(payloadFor(tab));
      loaded = { ...loaded, ...payloadFor(tab) };
      markDirty(tab, false);
      setSaveMessage(tab, `「${TAB_LABELS[tab]}」已儲存`, 'ok');
      if (tab === 'ai') await refreshRuntimeState();
    } catch (error) {
      const caught = /** @type {any} */ (error);
      renderErrors(caught.fieldErrors || []);
      setSaveMessage(tab, `儲存失敗：${caught.message}`, 'error');
    } finally {
      busy = false;
      if (button) { /** @type {HTMLButtonElement} */ (button).disabled = false; }
    }
  }

  // ── 連線測試 ─────────────────────────────────────────────
  async function testConnectivity() {
    const button = getElement('llmTestBtn');
    const output = getElement('llmTestOut');
    if (!output) return;
    if (button) { button.disabled = true; button.textContent = '測試中…'; }
    output.hidden = false;
    output.textContent = '測試中…';
    try {
      const result = await operationsClient.llmConnectivityTest();
      output.textContent = '';
      /** @type {Record<string, string>} */
      const labels = { ollama: '本機 Ollama', nvidia_nim: '雲端 NVIDIA NIM' };
      (result.results || []).forEach(/** @param {any} row */ row => {
        const line = document.createElement('div');
        line.className = 'line';
        line.append(pill(row.ok ? 'ok' : 'err', labels[row.provider] || row.provider));
        const detail = document.createElement('span');
        detail.textContent = row.ok
          ? `${text(row.model)} · 回應 ${row.latency_ms} ms`
          : text(row.detail) || '無法連線。';
        line.appendChild(detail);
        output.appendChild(line);
      });
      if (result.summary) {
        const summary = document.createElement('div');
        summary.className = 'line';
        summary.style.color = '#96650a';
        summary.style.fontWeight = '600';
        summary.textContent = `→ ${result.summary}`;
        output.appendChild(summary);
      }
    } catch (error) {
      output.textContent = `測試失敗：${/** @type {any} */ (error).message}`;
    } finally {
      if (button) { button.disabled = false; button.textContent = '重新測試'; }
    }
  }

  // ── 變更歷史 ─────────────────────────────────────────────
  async function loadHistory() {
    const box = getElement('settingsHistory');
    if (!box) return;
    box.textContent = '載入中…';
    let rows = [];
    try {
      rows = (await operationsClient.settingsVersions()).versions || [];
    } catch (error) {
      box.textContent = `變更歷史載入失敗：${/** @type {any} */ (error).message}`;
      return;
    }
    box.textContent = '';
    if (!rows.length) {
      box.textContent = '目前沒有設定版本記錄。（JSON 儲存模式不保留版本歷史。）';
      return;
    }
    const table = document.createElement('table');
    const head = document.createElement('thead');
    const headRow = document.createElement('tr');
    ['版本', '時間', '操作者', '變更內容', ''].forEach(label => {
      const cell = document.createElement('th');
      cell.textContent = label;
      headRow.appendChild(cell);
    });
    head.appendChild(headRow);
    const body = document.createElement('tbody');
    rows.forEach(/** @param {any} row */ row => {
      const tr = document.createElement('tr');
      const version = document.createElement('td');
      const versionText = document.createElement('b');
      versionText.textContent = String(row.version);
      version.appendChild(versionText);
      const when = document.createElement('td');
      when.textContent = text(row.created_at).replace('T', ' ').slice(0, 16);
      const actor = document.createElement('td');
      actor.textContent = text(row.actor_id) ? `…${text(row.actor_id).slice(-8)}` : '未記錄';
      const diff = document.createElement('td');
      diff.className = 'diff';
      (row.changes || []).forEach(/** @param {any} change */ change => {
        const line = document.createElement('div');
        const before = document.createElement('s');
        before.textContent = JSON.stringify(change.before ?? null);
        const after = document.createElement('em');
        after.textContent = JSON.stringify(change.after ?? null);
        line.append(`${change.key} `, before, ' → ', after);
        diff.appendChild(line);
      });
      if (!diff.childElementCount) diff.textContent = '（與前一版本相同）';
      const action = document.createElement('td');
      const rollback = document.createElement('button');
      rollback.type = 'button';
      rollback.className = 'refresh-btn';
      rollback.textContent = '回滾至此';
      rollback.addEventListener('click', () => rollbackTo(row.version));
      action.appendChild(rollback);
      tr.append(version, when, actor, diff, action);
      body.appendChild(tr);
    });
    table.append(head, body);
    box.appendChild(table);
  }

  /** @param {number} version */
  async function rollbackTo(version) {
    if (!confirmAction(`確定將設定回滾至版本 ${version}？系統會建立一個新版本，不會刪除既有版本。`)) return;
    try {
      await operationsClient.rollbackSettingsVersion(version);
      await load();
      await loadHistory();
    } catch (error) {
      window.alert(`回滾失敗：${/** @type {any} */ (error).message}`);
    }
  }

  // ── 條件欄位 ─────────────────────────────────────────────
  function updateSttFields() {
    const api = value('inp-stt-provider') === 'openai_compatible';
    getElement('row-stt-model')?.classList.toggle('hidden', api);
    getElement('row-stt-api')?.classList.toggle('hidden', !api);
  }

  function updateTtsFields() {
    const provider = value('inp-tts-provider');
    getElement('row-tts-edge-zh')?.classList.toggle('hidden', provider !== 'edge');
    getElement('row-tts-api')?.classList.toggle('hidden', provider !== 'openai_compatible');
    getElement('row-tts-voice')?.classList.toggle('hidden', provider !== 'openai_compatible');
  }

  async function load() {
    try {
      loaded = await operationsClient.settings();
    } catch (error) {
      setSaveMessage('ai', `設定載入失敗：${/** @type {any} */ (error).message}`, 'error');
      return;
    }
    await loadOllamaModels();
    restoreForm(loaded);
    Object.keys(TAB_KEYS).forEach(tab => markDirty(tab, false));
    await refreshRuntimeState();
  }

  function bind() {
    document.querySelectorAll('[data-settings-tab]').forEach(node => {
      const button = /** @type {HTMLElement} */ (node);
      button.addEventListener('click', () => showTab(button.dataset.settingsTab || 'ai'));
    });
    document.querySelectorAll('[data-settings-save]').forEach(node => {
      const button = /** @type {HTMLElement} */ (node);
      button.addEventListener('click', () => saveTab(button.dataset.settingsSave || 'ai'));
    });
    document.querySelectorAll('[data-settings-reset]').forEach(node => {
      const button = /** @type {HTMLElement} */ (node);
      button.addEventListener('click', () => {
        const tab = button.dataset.settingsReset || 'ai';
        restoreTab(tab);
        markDirty(tab, false);
      });
    });
    document.querySelectorAll('[data-settings-panel]').forEach(node => {
      const panel = /** @type {HTMLElement} */ (node);
      const tab = panel.dataset.settingsPanel || '';
      if (!(tab in TAB_KEYS)) return;
      panel.addEventListener('input', () => markDirty(tab, true));
      panel.addEventListener('change', () => markDirty(tab, true));
    });
    getElement('btn-nim-model-add')?.addEventListener('click', () => addCustomNimModel('text'));
    getElement('btn-nim-voice-model-add')?.addEventListener('click', () => addCustomNimModel('voice'));
    getElement('inp-push-scope-add')?.addEventListener('change', /** @param {Event} event */ event => {
      const picker = /** @type {HTMLSelectElement} */ (event.target);
      const chosen = text(picker.value);
      if (!chosen) return;
      if (!pushScopeCategories.includes(chosen)) pushScopeCategories.push(chosen);
      picker.value = '';
      // 選了類別卻停在別的範圍模式，儲存後不會生效——直接幫忙切過去。
      setScopeMode('categories');
      renderScopeCategories();
      markDirty('push', true);
    });
    getElement('copy-reload')?.addEventListener('click', () => loadCopy(true));
    getElement('copy-fill-missing')?.addEventListener('click', () => startBatch('fill_missing'));
    getElement('copy-regenerate')?.addEventListener('click', () => startBatch('regenerate'));
    ['copy-search', 'copy-filter-category', 'copy-filter-status'].forEach(id => {
      getElement(id)?.addEventListener('input', renderCopyRows);
      getElement(id)?.addEventListener('change', renderCopyRows);
    });
    getElement('inp-stt-provider')?.addEventListener('change', updateSttFields);
    getElement('inp-tts-provider')?.addEventListener('change', updateTtsFields);
    getElement('llmTestBtn')?.addEventListener('click', testConnectivity);
    window.addEventListener('beforeunload', event => {
      if (Object.values(dirty).some(Boolean)) event.preventDefault();
    });
  }

  return { bind, load, showTab, refreshRuntimeState };
}

/** @param {string} policy @param {Record<string, number>} providers */
export function mismatchMessage(policy, providers) {
  const local = Number(providers.ollama || 0);
  const cloud = Number(providers.nvidia_nim || 0);
  if (!local && !cloud) return '';
  if (policy === 'cloud_only' && local) {
    return '目前策略為「僅雲端」，但仍有請求由本機回答，代表設定尚未生效或服務需要重啟。';
  }
  if (policy === 'local_only' && cloud) {
    return '目前策略為「僅本機」，但仍有請求送往雲端，請立即確認設定是否生效。';
  }
  if ((policy === 'cloud_first' || policy === 'cloud_only') && !cloud) {
    return '目前策略偏好雲端，但沒有任何請求由雲端回答。通常是金鑰未設定或雲端無法連線——請按下方「測試連線」確認。';
  }
  return '';
}
