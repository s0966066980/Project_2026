/** Store-scoped knowledge, one published retrieval method, and an ad hoc retrieval check. */

// @ts-check

/** @typedef {{id: string, label: string, icon?: string, description?: string, template?: string, use_case?: string, limitation?: string}} RagOption */
/** @typedef {{chunk_id: string, content: string}} RagChunk */
/** @typedef {{item_id: string, title: string, content: string, category: string, content_type: string, status: string, version: number, published_version?: number, updated_at: string, index_error?: string, row_revision?: number, chunks?: RagChunk[]}} RagItem */
/** @typedef {{id: string, label: string, icon: string, published_count?: number}} RagPopularCategory */
/** @typedef {{status: string, attempts?: number, result_ref?: string, last_error?: string}} RagRebuildJob */
/** @typedef {{categories: RagOption[], content_types: RagOption[], methods: RagOption[], top_k_values: number[], preset_version?: string}} RagMetadata */
/** @typedef {{items: RagItem[], popular_categories: RagPopularCategory[], counts: Record<string, number>, total: number, metadata?: RagMetadata}} RagKnowledge */
/** @typedef {{version: number, method: string, top_k: number, relevance_policy: string, status: string, published_at: string}} RagConfiguration */
/** @typedef {{configurations: RagConfiguration[], published: RagConfiguration | null}} RagConfigurations */
/** @typedef {{rank: number, title?: string, score?: number, category?: string, content_type?: string, chunk_id?: string, content?: string, match_types?: string[]}} RagRetrievalHit */
/** @typedef {{check_id?: string, total?: number, method?: string, top_k?: number, relevance_policy?: string, latency_ms?: number, fallback_used?: string, confirmed_at?: string, confirmation_eligible?: boolean, confirmation_reason?: string, results?: RagRetrievalHit[], snapshot?: {query: string, method: string, top_k: number, relevance_policy: string}}} RagRetrievalResult */
/** @typedef {{kind: 'item', item: RagItem | null, title: string, category: string, content_type: string, content: string, preview: RagChunk[], initialValues: {title: string, category: string, contentType: string, content: string}}} RagItemDrawer */
/** @typedef {RagItemDrawer} RagDrawer */
/** @typedef {HTMLElement & {value: string, checked: boolean, files: FileList | null, selectedOptions: HTMLCollectionOf<HTMLOptionElement>}} RagElement */
/** @typedef {{tab: string, category: string, status: string, search: string, loaded: boolean, knowledge: RagKnowledge, configurations: RagConfigurations, retrievalCheck: {draft: string, method: string, topK: number, relevancePolicy: string, inFlight: boolean, result: RagRetrievalResult | null, error: string, configurationVersion: number | null}, drawer: RagDrawer | null, selectedMethod: string, pollingStarted: boolean, boundRoot: HTMLElement | null, drawerReturnTarget: {action: string, itemId: string} | null}} RagState */
/** @typedef {Error & {code?: string, details?: {title?: string, item_id?: string}, status?: number}} RagApiError */
const TERMINAL_JOB_STATUSES = new Set(['succeeded', 'failed', 'dead_letter', 'cancelled']);
/** @type {Record<string, string>} */
const STATUS_LABELS = {
  draft: '草稿',
  indexing: '索引中',
  published: '已發布',
  index_failed: '索引失敗',
  retired: '已停用',
};
/** @type {Record<string, string>} */
const CONFIG_STATUS_LABELS = { ...STATUS_LABELS, superseded: '已取代' };
/** @type {Record<string, string>} */
const RELEVANCE_LABELS = {
  lenient: '寬鬆',
  balanced: '平衡',
  strict: '嚴格',
};
/** @type {Record<string, string>} */
const METHOD_LABELS = {
  bm25: 'BM25 關鍵字',
  dense: 'Dense 語意向量',
  hybrid_rrf: 'Hybrid RRF',
  hybrid_reranker: 'Hybrid + Reranker',
};
/** @type {RagMetadata} */
const FALLBACK_METADATA = {
  categories: /** @type {Array<[string, string, string]>} */ ([
    ['store_and_hours', '門市與營業資訊', 'store'],
    ['menu_and_products', '菜單與商品', 'utensils'],
    ['promotions', '優惠與活動', 'tag'],
    ['payment_and_invoice', '付款與發票', 'receipt'],
    ['membership', '會員與權益', 'user-check'],
    ['order_and_pickup', '訂單與取餐', 'bag-shopping'],
    ['delivery', '外送服務', 'truck'],
    ['nutrition_and_allergens', '營養與過敏原', 'wheat-awn'],
    ['other', '其他', 'folder'],
  ]).map(([id, label, icon]) => ({ id, label, icon })),
  content_types: /** @type {Array<[string, string]>} */ ([
    ['knowledge_article', '知識文章'],
    ['question_answer', '問答'],
    ['policy_rule', '政策規則'],
    ['operating_procedure', '作業流程'],
  ]).map(([id, label]) => ({ id, label, description: '' })),
  methods: Object.entries(METHOD_LABELS).map(([id, label]) => ({ id, label, use_case: '', limitation: '' })),
  top_k_values: [3, 5, 10],
};

/**
 * @param {{
 *   loadJob: () => Promise<RagRebuildJob | undefined>,
 *   sleep?: (milliseconds: number) => Promise<void>,
 *   intervalMs?: number,
 *   timeoutMs?: number,
 *   now?: () => number,
 *   onProgress?: (job: RagRebuildJob | undefined) => void
 * }} options
 */
export async function waitForRagRebuildJob({
  loadJob,
  sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds)),
  intervalMs = 1500,
  timeoutMs = 10 * 60 * 1000,
  now = () => Date.now(),
  onProgress = () => {},
}) {
  const startedAt = now();
  while (now() - startedAt <= timeoutMs) {
    const job = await loadJob();
    onProgress(job);
    if (job && TERMINAL_JOB_STATUSES.has(String(job.status || ''))) return job;
    await sleep(intervalMs);
  }
  throw new Error('背景工作逾時；請稍後重新整理狀態。');
}

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : String(error || '未知錯誤');
}

/**
 * @param {{
 *   apiBaseUrl: string,
 *   adminHeaders: () => Record<string, string>,
 *   getElement: (id: string) => RagElement | null,
 *   escapeHtml: (value: unknown) => string,
 *   hasPermission?: (permission: string) => boolean,
 *   confirmAction?: (message: string) => boolean,
 *   fetchImpl?: typeof fetch
 * }} options
 */
export function createRagAdmin({
  apiBaseUrl,
  adminHeaders,
  getElement,
  escapeHtml,
  hasPermission = () => false,
  confirmAction = message => window.confirm(message),
  fetchImpl = fetch,
}) {
  /** @type {RagState} */
  const state = {
    tab: 'knowledge',
    category: '',
    status: '',
    search: '',
    loaded: false,
    knowledge: { items: [], popular_categories: [], counts: {}, total: 0 },
    configurations: { configurations: [], published: null },
    retrievalCheck: {
      draft: '',
      method: '',
      topK: 5,
      relevancePolicy: 'balanced',
      inFlight: false,
      result: null,
      error: '',
      configurationVersion: null,
    },
    drawer: null,
    selectedMethod: '',
    pollingStarted: false,
    boundRoot: null,
    drawerReturnTarget: null,
  };

  /** @template T @param {string} path @param {RequestInit} [options] @returns {Promise<T>} */
  async function request(path, options = {}) {
    const response = await fetchImpl(`${apiBaseUrl}${path}`, {
      ...options,
      headers: {
        ...adminHeaders(),
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
    });
    const payload = /** @type {{data?: T, detail?: {message?: string, code?: string, details?: {title?: string, item_id?: string}}}} */ (await response.json().catch(() => ({})));
    if (!response.ok) {
      const detail = payload.detail || {};
      const error = /** @type {RagApiError} */ (new Error(detail.message || detail.code || `系統回應 ${response.status}`));
      error.code = detail.code || '';
      error.details = detail.details || {};
      error.status = response.status;
      throw error;
    }
    return /** @type {T} */ (payload.data ?? payload);
  }

  /** @returns {RagMetadata} */
  function meta() {
    // Categories and content types come from the knowledge list, which owns them.
    // Retrieval methods and Top-K remain local: they describe the configuration form,
    // not the store's data, and no retained endpoint publishes them.
    return { ...FALLBACK_METADATA, ...(state.knowledge.metadata || {}) };
  }
  /** @param {RagOption[]} list @param {string | undefined} id */
  function label(list, id) {
    return list.find(row => row.id === id)?.label || id || '—';
  }
  /** @param {Record<string, string>} labels @param {string | undefined} id @param {string} [fallback] */
  function mappedLabel(labels, id, fallback = '—') {
    const key = String(id || '');
    return labels[key] || key || fallback;
  }
  /** @param {string | undefined} name */
  function icon(name) {
    const safe = String(name || 'circle').replace(/[^a-z-]/g, '');
    return `<i class="fas fa-${safe}" aria-hidden="true"></i>`;
  }
  /** @param {number | undefined | null} value @param {string} [suffix] */
  function metric(value, suffix = '') {
    return value == null ? '—' : `${Number(value).toFixed(Number(value) < 10 ? 2 : 0)}${suffix}`;
  }

  /** @param {string | undefined} code */
  function confirmationReason(code) {
    /** @type {Record<string, string>} */
    const reasons = {
      retrieval_identity_changed: '檢索執行期間正式索引或設定已變更，請重新執行。',
      published_configuration_required: '尚未發布檢索設定，這次結果只能用於診斷。',
      published_configuration_mismatch: '這次使用的是診斷參數，不能確認為正式就緒證據。',
      fallback_result: '這次使用了備援檢索，可查看結果但不能確認為正式就緒證據。',
      result_required: '沒有檢索結果，不能確認為正式就緒證據。',
    };
    return code ? reasons[code] || '' : '';
  }

  /** @param {string} message @param {boolean} [error] */
  function notice(message, error = false) {
    document.querySelector('.rag-notice')?.remove();
    const node = document.createElement('div');
    node.className = `rag-notice${error ? ' error' : ''}`;
    node.setAttribute('role', error ? 'alert' : 'status');
    node.textContent = message;
    document.body.appendChild(node);
    window.setTimeout(() => node.remove(), 4200);
  }

  function statusHeader() {
    const counts = state.knowledge.counts || {};
    const published = /** @type {Partial<RagConfiguration>} */ (state.configurations.published || {});
    const publishing = Number(counts.indexing || 0) + Number(counts.resuming || 0);
    const failed = Number(counts.index_failed || 0) + Number(counts.publication_failed || 0);
    return `<div class="rag-status-grid">
      <article class="rag-status-card"><span>門市知識</span><strong>${Number(state.knowledge.total || 0)} 筆</strong><div class="rag-table-sub">已發布 ${Number(counts.published || 0)} · 草稿 ${Number(counts.draft || 0)}</div></article>
      <article class="rag-status-card"><span>已發布檢索方法</span><strong>${escapeHtml(mappedLabel(METHOD_LABELS, published.method, '尚未發布'))}</strong>${published.version ? `<div class="rag-table-sub">版本 v${Number(published.version)}</div>` : ''}</article>
      <article class="rag-status-card"><span>待完成發布</span><strong>${publishing} 筆</strong>${failed ? `<div class="rag-table-sub"><b class="rag-badge index_failed">${failed} 筆需要處理</b></div>` : ''}</article>
    </div>`;
  }

  function tabs() {
    /** @type {Array<[string, string]>} */
    const rows = [
      ['knowledge', '門市知識庫'],
      ['methods', '檢索方法'],
      ['tests', '測試與效能'],
    ];
    return `<div class="rag-tabs" role="tablist" aria-label="RAG 智慧工作室功能區">${rows.map(([id, text]) =>
      `<button class="rag-tab" role="tab" data-action="tab" data-tab="${id}" aria-selected="${state.tab === id}">${text}</button>`
    ).join('')}</div>`;
  }

  function filteredItems() {
    const query = state.search.toLocaleLowerCase();
    return state.knowledge.items.filter(row =>
      (!state.category || row.category === state.category)
      && (!state.status || row.status === state.status)
      && (!query || `${row.title} ${row.content} ${row.item_id}`.toLocaleLowerCase().includes(query))
    );
  }

  function knowledgeView() {
    const categories = meta().categories || [];
    const popular = state.knowledge.popular_categories || [];
    const rows = filteredItems();
    return `<div class="rag-mobile-note">手機版可使用全螢幕編輯面板新增與修改知識項目。</div>
      <div class="rag-toolbar">
        <div class="rag-toolbar-group">
          <input class="rag-search" id="rag-search" type="search" placeholder="搜尋標題、內容或知識 ID" value="${escapeHtml(state.search)}" aria-label="搜尋知識">
          <select class="rag-field" id="rag-status-filter" aria-label="狀態篩選">
            <option value="">所有狀態</option>
            ${Object.entries(STATUS_LABELS).map(([id, text]) => `<option value="${id}" ${state.status === id ? 'selected' : ''}>${text}</option>`).join('')}
          </select>
        </div>
        <div class="rag-toolbar-group">
          <button class="rag-secondary" type="button" data-action="refresh">${icon('rotate')} 重新整理</button>
        </div>
      </div>
      <div class="rag-category-row" aria-label="常用分類">
        <button class="rag-category-chip" data-action="category" data-category="" aria-pressed="${!state.category}">全部</button>
        ${popular.map(row => `<button class="rag-category-chip" data-action="category" data-category="${escapeHtml(row.id)}" aria-pressed="${state.category === row.id}">${icon(row.icon)} ${escapeHtml(row.label)} <span class="rag-code">${Number(row.published_count || 0)}</span></button>`).join('')}
        <select class="rag-field" id="rag-category-filter" aria-label="全部分類">
          <option value="">更多分類</option>
          ${categories.map(row => `<option value="${row.id}" ${state.category === row.id ? 'selected' : ''}>${escapeHtml(row.label)}</option>`).join('')}
        </select>
      </div>
      <section class="rag-panel">
        ${rows.length ? `<div class="rag-table-wrap"><table class="rag-table">
          <thead><tr><th>知識項目</th><th>分類</th><th>內容類型</th><th>狀態</th><th>版本</th><th>更新時間</th><th>操作</th></tr></thead>
          <tbody>${rows.map(row => `<tr>
            <td><div class="rag-table-title">${escapeHtml(row.title)}</div><div class="rag-table-sub rag-code">${escapeHtml(row.item_id)}</div></td>
            <td>${escapeHtml(label(categories, row.category))}</td>
            <td>${escapeHtml(label(meta().content_types || [], row.content_type))}</td>
            <td><span class="rag-badge ${escapeHtml(row.status)}">${escapeHtml(STATUS_LABELS[row.status] || row.status)}</span>${row.index_error ? `<div class="rag-table-sub">${escapeHtml(row.index_error)}</div>` : ''}</td>
            <td class="rag-code">v${Number(row.version)}${row.published_version ? ` / 正式 v${Number(row.published_version)}` : ''}</td>
            <td>${escapeHtml(new Date(row.updated_at).toLocaleString('zh-TW'))}</td>
            <td><div class="rag-row-actions">${['index_failed', 'publication_failed'].includes(String(row.status)) ? `<button class="rag-secondary" type="button" data-action="retry-item" data-item-id="${escapeHtml(row.item_id)}">重新索引</button>` : ''}<button class="rag-icon-button" type="button" data-action="edit" data-item-id="${escapeHtml(row.item_id)}" aria-label="編輯 ${escapeHtml(row.title)}">${icon('pen')}</button></div></td>
          </tr>`).join('')}</tbody>
        </table></div>` : `<div class="rag-empty"><strong>${state.knowledge.total ? '沒有符合篩選條件的知識' : '從第一筆可驗證知識開始'}</strong><p>${state.knowledge.total ? '調整分類、狀態或搜尋文字。' : '新增內容、發布檢索設定，再完成一次檢索確認即可啟用 RAG。'}</p><button class="rag-primary" type="button" data-action="add">新增知識</button></div>`}
      </section>`;
  }

  function methodsView() {
    const published = /** @type {Partial<RagConfiguration>} */ (state.configurations.published || {});
    const selectedMethod = state.selectedMethod || published.method || 'hybrid_rrf';
    return `<div class="rag-algorithm-grid">${(meta().methods || []).map(method => {
      return `<article class="rag-algorithm ${selectedMethod === method.id ? 'selected' : ''}">
        <div class="rag-toolbar"><div><h3>${escapeHtml(method.label)}</h3></div><div>${published.method === method.id ? '<span class="rag-badge published">已發布</span>' : ''}</div></div>
        <p><strong>適合：</strong>${escapeHtml(method.use_case)}</p>
        <p><strong>限制：</strong>${escapeHtml(method.limitation)}</p>
        <button class="rag-secondary" type="button" data-action="choose-method" data-method="${escapeHtml(method.id)}" style="margin-top:14px;width:100%">${selectedMethod === method.id ? '已選擇' : '選擇此方法'}</button>
      </article>`;
    }).join('')}</div>
    <section class="rag-panel rag-config-bar">
      <div class="rag-config-fields">
        <label class="rag-label">Top K<select class="rag-field" id="rag-config-top-k">${(meta().top_k_values || [3,5,10]).map(value => `<option ${Number(published.top_k || 5) === Number(value) ? 'selected' : ''}>${value}</option>`).join('')}</select></label>
        <label class="rag-label">相關性政策<select class="rag-field" id="rag-config-policy">
          <option value="lenient" ${published.relevance_policy === 'lenient' ? 'selected' : ''}>寬鬆</option>
          <option value="balanced" ${!published.relevance_policy || published.relevance_policy === 'balanced' ? 'selected' : ''}>平衡</option>
          <option value="strict" ${published.relevance_policy === 'strict' ? 'selected' : ''}>嚴格</option>
        </select></label>
        <div class="rag-label">預設版本<span class="rag-code">${escapeHtml(meta().preset_version || '—')}</span></div>
      </div>
      <button class="rag-primary" type="button" data-action="publish-config" ${hasPermission('rag.publish') ? '' : 'disabled'}>發布檢索設定</button>
    </section>
    ${state.configurations.configurations?.length ? `<section class="rag-panel" style="margin-top:14px"><div class="rag-table-wrap"><table class="rag-table"><thead><tr><th>版本</th><th>方法</th><th>Top K</th><th>政策</th><th>狀態</th><th>發布時間</th><th>操作</th></tr></thead><tbody>${state.configurations.configurations.map(row => `<tr><td class="rag-code">v${Number(row.version)}</td><td>${escapeHtml(mappedLabel(METHOD_LABELS, row.method))}</td><td>${Number(row.top_k)}</td><td>${escapeHtml(mappedLabel(RELEVANCE_LABELS, row.relevance_policy))}</td><td><span class="rag-badge ${row.status === 'published' ? 'published' : ''}">${escapeHtml(mappedLabel(CONFIG_STATUS_LABELS, row.status))}</span></td><td>${escapeHtml(new Date(row.published_at).toLocaleString('zh-TW'))}</td><td><div class="rag-row-actions">${row.status !== 'published' ? `<button class="rag-secondary" data-action="restore-config" data-version="${Number(row.version)}">重新發布</button>` : '<span class="rag-table-sub">目前使用中</span>'}${hasPermission('rag.publish') ? `<button class="rag-danger" data-action="delete-config" data-version="${Number(row.version)}" data-published="${row.status === 'published'}">${icon('trash')} 清除</button>` : ''}</div></td></tr>`).join('')}</tbody></table></div></section>` : ''}`;
  }

  /**
   * 目前實際會送出的檢索方法。workspace.method 為空時後端會沿用已發布設定，
   * 所以畫面必須顯示同一個值，否則下拉選單會停在清單第一項（BM25）而與實際執行不符。
   * @returns {string}
   */
  function effectiveTestMethod() {
    const published = /** @type {Partial<RagConfiguration>} */ (state.configurations.published || {});
    return state.retrievalCheck.method || String(published.method || '');
  }

  /**
   * 在目前知識量下必定無效的方法。BM25 靠 IDF 分辨文件，知識筆數極少時所有分數趨近 0，
   * 永遠達不到相關性門檻——此時回傳空結果並非設定錯誤，必須講清楚，否則只會看到「沒有結果」。
   * @param {string} method @returns {string}
   */
  function publishedItemCount() {
    return Number((state.knowledge.counts || {}).published || 0);
  }

  /** @returns {number} */
  function pendingPublishCount() {
    const counts = state.knowledge.counts || {};
    return Number(counts.indexing || 0) + Number(counts.resuming || 0);
  }

  /** @param {string} method @returns {string} */
  function methodIneffectiveReason(method) {
    const publishedItems = publishedItemCount();
    if (method === 'bm25' && publishedItems > 0 && publishedItems < 5) {
      return `BM25 以關鍵字稀有度評分，目前只有 ${publishedItems} 筆已發布知識，
        所有結果的分數都會趨近 0 而達不到門檻，因此幾乎必定查無結果。請改用 Hybrid RRF，或先增加知識筆數。`;
    }
    return '';
  }

  function adhocView() {
    const workspace = state.retrievalCheck;
    const result = workspace.result;
    const published = /** @type {Partial<RagConfiguration>} */ (state.configurations.published || {});
    const selectedMethod = effectiveTestMethod();
    const ineffectiveReason = methodIneffectiveReason(selectedMethod);
    const formalPrerequisites = publishedItemCount() > 0 && Boolean(published.version);
    const emptyGuidance = publishedItemCount() <= 0 && pendingPublishCount() > 0
      ? `有 ${pendingPublishCount()} 筆知識仍在索引中，完成後才會出現在檢索結果裡。`
      : publishedItemCount() <= 0
        ? '目前沒有 Published 知識。請先新增知識並等待索引完成。'
        : !published.version
          ? '尚未發布正式檢索設定。請先到「檢索方法」發布設定。'
          // 方法本身在目前知識量下就會失效時，講門檻等於把問題推給操作者去猜。
          : ineffectiveReason
            || '正式索引可用，但這個問題未達相關性門檻；請檢查問題用詞、知識內容與相關性政策。';
    const renderedHits = (result?.results || []).map(hit => `<article class="rag-result"><div class="rag-result-head"><strong>#${Number(hit.rank)} ${escapeHtml(hit.title || '未命名')}</strong><span class="rag-code">${metric(hit.score)}</span></div><div class="rag-table-sub">${escapeHtml(label(meta().categories || [], hit.category))} · ${escapeHtml(label(meta().content_types || [], hit.content_type))} · ${escapeHtml(hit.chunk_id || '')}</div><p>${escapeHtml(hit.content || '')}</p><details><summary class="rag-table-sub">分數明細</summary><pre class="rag-code">${escapeHtml(JSON.stringify({ match_types: hit.match_types, score: hit.score }, null, 2))}</pre></details></article>`).join('');
    return `<div class="rag-test-layout">
      <section class="rag-panel rag-test-form">
        <div class="rag-eyebrow">正式結果驗證</div><h2>即時檢索測試</h2>
        <p class="rag-table-sub">只查詢目前門市的 Published 知識，不產生 LLM 回答、不保存問題。只有使用正式設定、未發生備援且至少命中一筆，才能確認為正式就緒證據。</p>
        ${formalPrerequisites ? '' : `<div class="rag-inline-alert" role="status">${escapeHtml(emptyGuidance)}</div>`}
        ${formalPrerequisites && ineffectiveReason ? `<div class="rag-inline-alert" role="status">${escapeHtml(ineffectiveReason)}</div>` : ''}
        <label class="rag-label">測試問題<textarea class="rag-field" id="rag-test-query" maxlength="2000" placeholder="例如：早餐供應到幾點？">${escapeHtml(workspace.draft)}</textarea></label>
        <div class="rag-config-fields" style="margin-top:12px">
          <label class="rag-label">方法<select class="rag-field" id="rag-test-method">${(meta().methods || []).map(row => `<option value="${row.id}" ${selectedMethod === row.id ? 'selected' : ''}>${escapeHtml(row.label)}${published.method === row.id ? '（正式設定）' : ''}</option>`).join('')}</select></label>
          <label class="rag-label">Top K<select class="rag-field" id="rag-test-top-k">${(meta().top_k_values || [3,5,10]).map(value => `<option value="${Number(value)}" ${Number(workspace.topK) === Number(value) ? 'selected' : ''}>${Number(value)}</option>`).join('')}</select></label>
          <label class="rag-label">相關性政策<select class="rag-field" id="rag-test-policy">${Object.entries(RELEVANCE_LABELS).map(([id, text]) => `<option value="${id}" ${workspace.relevancePolicy === id ? 'selected' : ''}>${text}</option>`).join('')}</select></label>
        </div>
        <button class="rag-primary" type="button" data-action="run-test" style="margin-top:14px;width:100%" ${workspace.inFlight ? 'disabled' : ''}>${workspace.inFlight ? '檢索中…' : '執行檢索'}</button>
        ${published.version ? `<p class="rag-table-sub" style="margin-top:10px">正式設定 v${Number(published.version)} · ${escapeHtml(mappedLabel(METHOD_LABELS, published.method))} · Top ${Number(published.top_k)} · ${escapeHtml(mappedLabel(RELEVANCE_LABELS, published.relevance_policy))}</p>` : '<p class="rag-table-sub" style="margin-top:10px">尚未發布檢索設定；結果只能用於診斷。</p>'}
      </section>
      <section class="rag-panel">
        ${workspace.error ? `<div class="rag-empty"><strong>檢索失敗</strong><p>${escapeHtml(workspace.error)}</p></div>` : !result ? '<div class="rag-empty"><strong>結果會顯示在這裡</strong><p>包含執行快照、排名、分類、內容型態、區塊、分數與延遲。</p></div>' :
          `<div class="rag-toolbar" style="padding:14px 14px 0"><div><strong>${Number(result.total)} 筆結果</strong><div class="rag-table-sub">${escapeHtml(mappedLabel(METHOD_LABELS, result.method))} · Top ${Number(result.top_k)} · ${escapeHtml(mappedLabel(RELEVANCE_LABELS, result.relevance_policy))} · ${metric(result.latency_ms, 'ms')}${result.fallback_used ? ` · 備援 ${escapeHtml(result.fallback_used)}` : ''}</div><div class="rag-table-sub rag-code">${escapeHtml(result.check_id || '')}</div></div>${result.confirmed_at ? '<span class="rag-badge published">已確認為 RAG 就緒證據</span>' : result.confirmation_eligible && hasPermission('rag.publish') ? '<button class="rag-secondary" data-action="confirm-test">確認畫面結果</button>' : ''}</div>
          ${!result.confirmation_eligible ? `<div class="rag-table-sub" style="padding:0 14px 12px;color:var(--rag-amber)">${escapeHtml(confirmationReason(result.confirmation_reason))}</div>` : result.confirmation_eligible && !hasPermission('rag.publish') ? '<div class="rag-table-sub" style="padding:0 14px 12px">需要 rag.publish 權限才能建立 RAG 就緒確認。</div>' : ''}
          ${Number(result.total || 0) === 0 ? `<div class="rag-empty rag-empty-diagnostic"><strong>沒有檢索結果</strong><p>${escapeHtml(emptyGuidance)}</p><button class="rag-secondary" type="button" data-action="go-step" data-tab="${publishedItemCount() <= 0 ? 'knowledge' : !published.version ? 'methods' : 'knowledge'}">前往處理</button></div>` : `<div class="rag-result-list">${renderedHits}</div>`}`}
      </section>
    </div>`;
  }

  function rememberDrawerTrigger() {
    const active = typeof document === 'undefined' ? null : document.activeElement;
    const activeElement = /** @type {HTMLElement | null} */ (active);
    state.drawerReturnTarget = activeElement?.dataset?.action ? {
      action: activeElement.dataset.action,
      itemId: activeElement.dataset.itemId || '',
    } : null;
  }

  /** @param {boolean} open */
  function setDrawerOpen(open) {
    if (typeof document !== 'undefined') document.body?.classList.toggle('rag-drawer-open', open);
  }

  function drawerValues() {
    if (!state.drawer) return null;
    return {
      title: getElement('rag-edit-title')?.value ?? state.drawer.title ?? '',
      category: state.drawer.category || '',
      contentType: state.drawer.content_type || '',
      content: getElement('rag-edit-content')?.value ?? state.drawer.content ?? '',
    };
  }

  function captureDrawerFields() {
    if (!state.drawer || state.drawer.kind !== 'item') return;
    state.drawer.title = getElement('rag-edit-title')?.value ?? state.drawer.title;
    state.drawer.content = getElement('rag-edit-content')?.value ?? state.drawer.content;
  }

  function drawerIsDirty() {
    return Boolean(state.drawer && JSON.stringify(drawerValues()) !== JSON.stringify(state.drawer.initialValues));
  }

  function focusDrawerTrigger() {
    const root = getElement('rag-studio-root');
    const target = state.drawerReturnTarget;
    state.drawerReturnTarget = null;
    if (!root || !target) return;
    const selector = `[data-action="${target.action}"]${target.itemId ? `[data-item-id="${target.itemId}"]` : ''}`;
    window.setTimeout(() => {
      const element = root.querySelector?.(selector);
      /** @type {HTMLElement | null} */ (element)?.focus?.();
    }, 0);
  }

  /** @param {{force?: boolean}} [options] */
  function closeDrawer({ force = false } = {}) {
    if (!state.drawer) return true;
    if (!force && drawerIsDirty() && !confirmAction('尚有未儲存的變更，確定要關閉嗎？')) return false;
    state.drawer = null;
    setDrawerOpen(false);
    render();
    focusDrawerTrigger();
    return true;
  }


  function drawer() {
    const drawerState = state.drawer;
    if (!drawerState) return '';
    const item = drawerState.item;
    const contentType = drawerState.content_type;
    const preview = drawerState.preview || [];
    return `<div class="rag-drawer-backdrop"><aside class="rag-drawer" role="dialog" aria-modal="true" aria-labelledby="rag-drawer-title">
      <div class="rag-drawer-head"><div><div class="rag-eyebrow">${item ? `知識項目 · ${escapeHtml(item.item_id)}` : '新增知識項目'}</div><h2 id="rag-drawer-title">${item ? '建立新版本' : '新增知識'}</h2></div><button class="rag-icon-button" data-action="close-drawer" aria-label="關閉">${icon('xmark')}</button></div>
      <label class="rag-label">標題（可留白，將使用內容第一行）<input class="rag-field" id="rag-edit-title" maxlength="160" value="${escapeHtml(drawerState.title || '')}"></label>
      <div class="rag-label" style="margin-top:14px">知識分類<div class="rag-option-grid">${(meta().categories || []).map(row => `<button class="rag-option ${drawerState.category === row.id ? 'selected' : ''}" type="button" data-action="drawer-category" data-category="${row.id}" aria-pressed="${drawerState.category === row.id}"><strong>${icon(row.icon)} ${escapeHtml(row.label)}</strong></button>`).join('')}</div></div>
      <div class="rag-label" style="margin-top:14px">RAG 內容類型<div class="rag-option-grid">${(meta().content_types || []).map(row => `<button class="rag-option ${contentType === row.id ? 'selected' : ''}" type="button" data-action="drawer-type" data-content-type="${row.id}" aria-pressed="${contentType === row.id}"><strong>${escapeHtml(row.label)}</strong><span>${escapeHtml(row.description)}</span></button>`).join('')}</div></div>
      <label class="rag-label" style="margin-top:14px">內容<textarea class="rag-field" id="rag-edit-content" maxlength="200000" placeholder="${escapeHtml((meta().content_types || []).find(row => row.id === contentType)?.template || '')}">${escapeHtml(drawerState.content || '')}</textarea></label>
      <details class="rag-preview" ${preview.length ? 'open' : ''}><summary>自動切塊預覽 · ${preview.length || '儲存後產生'} 個區塊</summary>${preview.map(row => `<article><b class="rag-code">${escapeHtml(row.chunk_id)}</b>\n${escapeHtml(row.content)}</article>`).join('')}</details>
      <div class="rag-drawer-actions">${item ? `<button class="rag-danger" data-action="delete-item">刪除</button>` : ''}<button class="rag-secondary" data-action="close-drawer">取消</button><button class="rag-primary" data-action="save-item">${item ? '儲存並發布' : '建立並發布'}</button></div>
    </aside></div>`;
  }

  function render() {
    const root = getElement('rag-studio-root');
    if (!root || !state.loaded) return;
    root.innerHTML = `<header class="rag-hero"><div><div class="rag-eyebrow">門市專屬檢索管理平台</div><h1>RAG 智慧工作室</h1><p>依序建立知識、完成索引、發布檢索設定，最後以正式結果建立就緒證據。</p></div><button class="rag-primary" data-action="add" ${hasPermission('rag.write') ? '' : 'disabled'}>${icon('plus')} 新增知識</button></header>${statusHeader()}${tabs()}<main role="tabpanel">${state.tab === 'knowledge' ? knowledgeView() : state.tab === 'methods' ? methodsView() : adhocView()}</main>${drawer()}`;
    setDrawerOpen(Boolean(state.drawer));
    bindRoot(root);
  }

  /** @param {HTMLElement} root */
  function bindRoot(root) {
    if (state.boundRoot === root) return;
    state.boundRoot = root;
    root.addEventListener('click', handleClick);
    root.addEventListener('change', handleChange);
    root.addEventListener('input', handleInput);
    root.addEventListener('keydown', handleKeydown);
  }

  async function refresh({ quiet = false } = {}) {
    const root = getElement('rag-studio-root');
    if (root && !quiet) root.innerHTML = '<div class="rag-studio-loading"><span class="rag-spinner"></span>正在同步門市 RAG 狀態…</div>';
    try {
      const [knowledge, configurations] = /** @type {[RagKnowledge, RagConfigurations]} */ (await Promise.all([
        request('/api/v1/rag/knowledge'),
        request('/api/v1/rag/retrieval/configurations'),
      ]));
      state.loaded = true;
      state.knowledge = knowledge;
      state.configurations = configurations;
      const published = /** @type {Partial<RagConfiguration>} */ (configurations.published || {});
      const publishedVersion = Number(published.version || 0) || null;
      if (!state.retrievalCheck.method || state.retrievalCheck.configurationVersion !== publishedVersion) {
        state.retrievalCheck.method = published.method || 'hybrid_rrf';
        state.retrievalCheck.topK = Number(published.top_k || 5);
        state.retrievalCheck.relevancePolicy = published.relevance_policy || 'balanced';
        state.retrievalCheck.configurationVersion = publishedVersion;
      }
      // A quiet poll must not wipe a retrieval query the operator is still editing.
      if (!(quiet && state.tab === 'tests')) render();
    } catch (error) {
      if (root) root.innerHTML = `<div class="rag-empty"><strong>RAG 智慧工作室載入失敗</strong><p>${escapeHtml(errorMessage(error))}</p><button class="rag-primary" data-action="refresh">重試</button></div>`;
      if (root) bindRoot(root);
    }
  }

  /** @param {RagItem | null} [item] */
  function openItem(item = null) {
    rememberDrawerTrigger();
    /** @type {RagItemDrawer} */
    const drawerState = {
      kind: 'item',
      item,
      title: item?.title || '',
      category: item?.category || meta().categories?.[0]?.id || 'store_and_hours',
      content_type: item?.content_type || 'knowledge_article',
      content: item?.content || '',
      preview: item?.chunks || [],
      initialValues: { title: '', category: '', contentType: '', content: '' },
    };
    drawerState.initialValues = {
      title: drawerState.title,
      category: drawerState.category,
      contentType: drawerState.content_type,
      content: drawerState.content,
    };
    state.drawer = drawerState;
    setDrawerOpen(true);
    render();
    window.setTimeout(() => getElement('rag-edit-title')?.focus(), 0);
  }

  async function saveItem(override = false) {
    const drawerState = state.drawer;
    if (!drawerState || drawerState.kind !== 'item') return;
    if (!drawerState.item && !hasPermission('rag.write')) return;
    const content = getElement('rag-edit-content')?.value?.trim() || '';
    if (!content) return notice('請輸入知識內容。', true);
    const item = drawerState.item;
    const payload = {
      title: getElement('rag-edit-title')?.value?.trim() || '',
      category: drawerState.category,
      content_type: drawerState.content_type,
      content,
      expected_row_revision: item?.row_revision || undefined,
      override_near_duplicate: override,
    };
    try {
      await request(item ? `/api/v1/rag/knowledge/${encodeURIComponent(item.item_id)}` : '/api/v1/rag/knowledge', {
        method: item ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      });
      closeDrawer({ force: true });
      notice(item ? '新版本草稿已建立；正式版本仍持續服務。' : '知識草稿已建立。');
      await refresh({ quiet: true });
    } catch (error) {
      const apiError = /** @type {RagApiError} */ (error);
      if (apiError.code === 'near_duplicate' && confirmAction(`找到相近知識「${apiError.details?.title || apiError.details?.item_id}」。仍要建立嗎？`)) {
        return saveItem(true);
      }
      if (apiError.code === 'stale_knowledge_item') {
        notice('此知識已被其他管理者更新。已重新載入最新版本，請比較後再儲存。', true);
        await refresh({ quiet: true });
        const current = state.knowledge.items.find(row => row.item_id === item?.item_id);
        if (current) openItem(current);
        return;
      }
      notice(`儲存失敗：${errorMessage(error)}`, true);
    }
  }

  /**
   * 重新索引單一筆失敗的知識。儲存即發布之後，這是唯一還需要手動排入發布的情境：
   * 索引本身失敗了，內容沒問題，只是要再跑一次。
   * @param {string} itemId
   */
  async function retryItem(itemId) {
    if (!itemId) return;
    try {
      await request('/api/v1/rag/knowledge/publish', {
        method: 'POST',
        body: JSON.stringify({ item_ids: [itemId], retry_failures_only: false }),
      });
      notice('已重新排入索引。');
      await refresh({ quiet: true });
    } catch (error) {
      notice(`重新索引失敗：${errorMessage(error)}`, true);
    }
  }

  /** @param {string | undefined} attemptId */
  async function resumePublication(attemptId) {
    if (!attemptId || !hasPermission('rag.publish')) return;
    try {
      await request(`/api/v1/rag/knowledge/publication-attempts/${encodeURIComponent(attemptId)}/resume`, {
        method: 'POST',
      });
      notice('發布嘗試已重新排入可靠工作佇列；頁面會持續更新進度。');
      await refresh({ quiet: true });
    } catch (error) {
      notice(`無法重新排入索引：${errorMessage(error)}`, true);
    }
  }

  async function deleteItem() {
    const drawerState = state.drawer;
    const item = drawerState?.kind === 'item' ? drawerState.item : null;
    if (!item) return;

    if (!confirmAction('刪除後會從正式檢索下架並徹底移除這筆知識，無法復原。確定要刪除嗎？')) return;

    try {
      await request(
        `/api/v1/rag/knowledge/${encodeURIComponent(item.item_id)}`
        + `?expected_row_revision=${encodeURIComponent(String(item.row_revision))}`,
        { method: 'DELETE' },
      );
      closeDrawer({ force: true });
      notice('知識已刪除。');
      await refresh({ quiet: true });
    } catch (error) {
      notice(`刪除失敗：${errorMessage(error)}`, true);
    }
  }

  /** @param {number | null} [sourceVersion] */
  async function publishConfig(sourceVersion = null) {
    const method = sourceVersion ? 'hybrid_rrf' : (state.selectedMethod || state.configurations.published?.method || 'hybrid_rrf');
    try {
      await request('/api/v1/rag/retrieval/configurations', {
        method: 'POST',
        body: JSON.stringify({
          method,
          top_k: Number(getElement('rag-config-top-k')?.value || 5),
          relevance_policy: getElement('rag-config-policy')?.value || 'balanced',
          source_version: sourceVersion,
        }),
      });
      state.selectedMethod = '';
      notice(sourceVersion ? `已將設定 v${sourceVersion} 重新發布為新版本。` : '檢索設定已發布。');
      await refresh({ quiet: true });
    } catch (error) {
      notice(`設定發布失敗：${errorMessage(error)}`, true);
    }
  }

  /** @param {number} version @param {boolean} [published] */
  async function deleteConfiguration(version, published = false) {
    if (!hasPermission('rag.publish')) return;
    const warning = published
      ? `這是目前使用中的檢索設定。永久刪除 v${version} 後，RAG 將暫停提供檢索，直到重新發布設定。確定繼續？`
      : `確定要永久刪除檢索設定 v${version}？此操作無法復原。`;
    if (!confirmAction(warning)) return;
    try {
      await request(`/api/v1/rag/retrieval/configurations/${encodeURIComponent(version)}`, {
        method: 'DELETE',
      });
      notice(published
        ? `檢索設定 v${version} 已清除；請發布新設定以恢復 RAG 檢索。`
        : `檢索設定 v${version} 已清除。`);
      await refresh({ quiet: true });
    } catch (error) {
      notice(`清除失敗：${errorMessage(error)}`, true);
    }
  }

  async function runTest() {
    const workspace = state.retrievalCheck;
    if (workspace.inFlight) return;
    const query = workspace.draft.trim();
    if (!query) return notice('請先輸入測試問題。', true);
    const snapshot = {
      // 送畫面上實際顯示的方法，不送可能為空的原始值——否則後端沿用正式設定，
      // 執行結果會與下拉選單顯示的方法不符。
      query,
      method: effectiveTestMethod(),
      top_k: Number(workspace.topK),
      relevance_policy: workspace.relevancePolicy,
    };
    workspace.inFlight = true;
    workspace.result = null;
    workspace.error = '';
    render();
    try {
      /** @type {RagRetrievalResult} */
      const result = await request('/api/v1/rag/retrieval/test', {
        method: 'POST',
        body: JSON.stringify(snapshot),
      });
      workspace.result = { ...result, snapshot };
      workspace.inFlight = false;
      render();
    } catch (error) {
      workspace.inFlight = false;
      workspace.error = errorMessage(error);
      render();
    }
  }

  async function confirmTest() {
    const result = state.retrievalCheck.result;
    if (!result?.check_id || !result.confirmation_eligible || !hasPermission('rag.publish')) return;
    try {
      /** @type {RagRetrievalResult} */
      const confirmation = await request(`/api/v1/rag/retrieval/checks/${encodeURIComponent(result.check_id)}/confirm`, {
        method: 'POST',
      });
      state.retrievalCheck.result = { ...result, ...confirmation };
      notice('已確認畫面上的結果快照；RAG 就緒狀態已更新。');
      await refresh({ quiet: true });
      render();
    } catch (error) {
      notice(`確認失敗：${errorMessage(error)}`, true);
    }
  }


  /** @param {File} file */

  /** @param {string} filename @param {string} csvText */
  function downloadCsv(filename, csvText) {
    const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  /** @param {string} path */

  /** @param {File} file */


  /** @param {string | undefined} runId */

  /** @param {MouseEvent} event */
  async function handleClick(event) {
    const eventTarget = /** @type {HTMLElement | null} */ (event.target);
    if (!eventTarget?.classList || typeof eventTarget.closest !== 'function') return;
    if (eventTarget.classList.contains('rag-drawer-backdrop')) {
      closeDrawer();
      return;
    }
    const target = /** @type {HTMLElement | null} */ (eventTarget.closest('[data-action]'));
    if (!target) return;
    const action = target.dataset.action;
    if (action === 'tab') { state.tab = target.dataset.tab || 'knowledge'; history.replaceState(null, '', `#rag/${state.tab}`); render(); }
    if (action === 'go-step') { state.tab = target.dataset.tab || 'knowledge'; history.replaceState(null, '', `#rag/${state.tab}`); render(); }
    if (action === 'category') { state.category = target.dataset.category || ''; render(); }
    if (action === 'refresh') refresh();
    if (action === 'add') openItem();
    if (action === 'edit') openItem(state.knowledge.items.find(row => row.item_id === target.dataset.itemId));
    if (action === 'close-drawer') closeDrawer();
    if (action === 'drawer-category' && state.drawer?.kind === 'item') {
      captureDrawerFields();
      const category = target.dataset.category || '';
      state.drawer.category = category;
      render();
      window.setTimeout(() => {
        const element = getElement('rag-studio-root')?.querySelector?.(`[data-action="drawer-category"][data-category="${category}"]`);
        /** @type {HTMLElement | null} */ (element)?.focus?.();
      }, 0);
    }
    if (action === 'drawer-type' && state.drawer?.kind === 'item') {
      captureDrawerFields();
      const contentType = target.dataset.contentType || '';
      state.drawer.content_type = contentType;
      render();
      window.setTimeout(() => {
        const element = getElement('rag-studio-root')?.querySelector?.(`[data-action="drawer-type"][data-content-type="${contentType}"]`);
        /** @type {HTMLElement | null} */ (element)?.focus?.();
      }, 0);
    }
    if (action === 'save-item') saveItem();
    if (action === 'delete-item') deleteItem();
    if (action === 'retry-item') retryItem(target.dataset.itemId || '');
    if (action === 'resume-publication') resumePublication(target.dataset.attemptId);
    if (action === 'choose-method') { state.selectedMethod = target.dataset.method || ''; render(); }
    if (action === 'publish-config') publishConfig();
    if (action === 'restore-config') publishConfig(Number(target.dataset.version));
    if (action === 'delete-config') deleteConfiguration(Number(target.dataset.version), target.dataset.published === 'true');
    if (action === 'run-test') runTest();
    if (action === 'confirm-test') confirmTest();
  }

  /** @param {Event} event */
  function handleChange(event) {
    const target = /** @type {RagElement} */ (event.target);
    if (target.id === 'rag-status-filter') { state.status = target.value; render(); }
    if (target.id === 'rag-category-filter') { state.category = target.value; render(); }
    if (target.id === 'rag-test-method') state.retrievalCheck.method = target.value;
    if (target.id === 'rag-test-top-k') state.retrievalCheck.topK = Number(target.value);
    if (target.id === 'rag-test-policy') state.retrievalCheck.relevancePolicy = target.value;
  }

  /** @param {KeyboardEvent} event */
  function handleKeydown(event) {
    const target = /** @type {HTMLElement | null} */ (event.target);
    if (target?.id === 'rag-test-query' && event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      runTest();
      return;
    }
    if (!state.drawer) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeDrawer();
      return;
    }
    if (event.key !== 'Tab') return;
    const drawerNode = getElement('rag-studio-root')?.querySelector?.('.rag-drawer');
    const focusable = /** @type {HTMLElement[]} */ ([...(drawerNode?.querySelectorAll?.('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex]:not([tabindex="-1"])') || [])]);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  let searchTimer = 0;
  let previewTimer = 0;
  /** @param {Event} event */
  function handleInput(event) {
    const target = /** @type {RagElement} */ (event.target);
    if (target.id === 'rag-test-query') {
      state.retrievalCheck.draft = target.value;
    }
    if (target.id === 'rag-search') {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => {
        state.search = target.value;
        render();
        getElement('rag-search')?.focus();
      }, 180);
    }
    if (target.id === 'rag-edit-content') {
      const content = target.value;
      if (state.drawer?.kind !== 'item') return;
      state.drawer.content = content;
      window.clearTimeout(previewTimer);
      previewTimer = window.setTimeout(async () => {
        if (!content.trim() || state.drawer?.kind !== 'item') return;
        try {
          /** @type {{chunks: RagChunk[]}} */
          const result = await request('/api/v1/rag/knowledge/chunk-preview', {
            method: 'POST',
            body: JSON.stringify({
              category: state.drawer.category,
              content_type: state.drawer.content_type,
              title: getElement('rag-edit-title')?.value || '',
              content,
            }),
          });
          if (state.drawer?.kind === 'item') {
            state.drawer.preview = result.chunks || [];
            const preview = /** @type {HTMLDetailsElement | null} */ (document.querySelector('.rag-preview'));
            if (preview) {
              preview.open = true;
              preview.innerHTML = `<summary>自動切塊預覽 · ${state.drawer.preview.length} 個區塊</summary>${state.drawer.preview.map(row => `<article><b class="rag-code">${escapeHtml(row.chunk_id)}</b>\n${escapeHtml(row.content)}</article>`).join('')}`;
            }
          }
        } catch {
          // Draft input remains editable when preview is temporarily unavailable.
        }
      }, 350);
    }
    if (target.id === 'rag-edit-title' && state.drawer?.kind === 'item') {
      state.drawer.title = target.value;
    }
  }

  async function loadPage() {
    const route = location.hash.match(/^#rag\/(knowledge|methods|tests)$/)?.[1];
    if (route) state.tab = route;
    await refresh();
    if (!state.pollingStarted) {
      state.pollingStarted = true;
      window.setInterval(() => {
        const page = document.getElementById('page-rag');
        if (page && page.style.display !== 'none' && !state.drawer) refresh({ quiet: true });
      }, 5000);
    }
  }

  return {
    loadPage,
    loadKnowledge: () => refresh({ quiet: true }),
    saveKnowledge: () => saveItem(),
    editKnowledge: openItem,
    cancelEdit: () => closeDrawer(),
    retryKnowledge: retryItem,
    deleteKnowledge: deleteItem,
    testKnowledge: () => runTest(),
    loadHealth: () => refresh({ quiet: true }),
    loadAlerts: async () => {},
    saveSettings: publishConfig,
    updateStrategyHelp: () => {},
    handleAlert: () => refresh({ quiet: true }),
  };
}
