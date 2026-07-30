import { afterEach, describe, expect, it, vi } from 'vitest';

import { createRagAdmin, waitForRagRebuildJob } from '../../admin/modules/ragAdmin.js';

afterEach(() => {
  vi.unstubAllGlobals();
});

function actionTarget(action: string, dataset: Record<string, string> = {}) {
  const target = {
    dataset: { action, ...dataset },
    classList: { contains: () => false },
    closest: () => target,
  };
  return target;
}

function setupRagAdmin() {
  const listeners: Record<string, (event: any) => void> = {};
  const root = {
    innerHTML: '',
    addEventListener: vi.fn((type: string, listener: (event: any) => void) => { listeners[type] = listener; }),
    querySelector: vi.fn(() => ({ focus: vi.fn() })),
  };
  const fields: Record<string, any> = {
    'rag-edit-title': { value: '' },
    'rag-edit-content': { value: '' },
  };
  const confirmAction = vi.fn(() => true);
  const bodyClassToggle = vi.fn();
  const appendChild = vi.fn();

  vi.stubGlobal('window', {
    setTimeout: vi.fn(),
    clearTimeout: vi.fn(),
    setInterval: vi.fn(),
  });
  vi.stubGlobal('document', {
    activeElement: { dataset: { action: 'add' } },
    body: { classList: { toggle: bodyClassToggle }, appendChild },
    createElement: vi.fn(() => ({
      className: '',
      textContent: '',
      setAttribute: vi.fn(),
      remove: vi.fn(),
    })),
    getElementById: vi.fn(() => ({ style: { display: 'block' } })),
    querySelector: vi.fn(() => null),
  });
  vi.stubGlobal('history', { replaceState: vi.fn() });
  vi.stubGlobal('location', { hash: '' });

  const payloads: Record<string, any> = {
    '/api/v1/rag/studio': {
      metadata: {
        categories: [
          { id: 'store_and_hours', label: '門市與營業資訊', icon: 'store' },
          { id: 'menu_and_products', label: '菜單與商品', icon: 'utensils' },
        ],
        content_types: [
          { id: 'knowledge_article', label: '知識文章', description: '' },
          { id: 'question_answer', label: '問答', description: '' },
        ],
        methods: [],
        top_k_values: [3, 5, 10],
      },
      dashboard: {},
    },
    '/api/v1/rag/knowledge': { items: [], popular_categories: [], counts: {}, total: 0 },
    '/api/v1/rag/retrieval/configurations': { configurations: [], published: null },
    '/api/v1/rag/test-cases': { test_cases: [], total: 0 },
    '/api/v1/rag/evaluation-runs': { evaluation_runs: [] },
  };
  const fetchImpl = vi.fn(async (url: string, options: RequestInit = {}) => {
    const path = new URL(url).pathname;
    if (path === '/api/v1/rag/retrieval/test' && options.method === 'POST') {
      const request = JSON.parse(String(options.body || '{}'));
      return {
        ok: true,
        json: async () => ({
          data: {
            check_id: 'arc_test',
            method: request.method,
            effective_method: request.method,
            top_k: request.top_k,
            relevance_policy: request.relevance_policy,
            fallback_used: '',
            latency_ms: 4.2,
            total: 1,
            confirmation_eligible: true,
            confirmation_reason: '',
            results: [{ rank: 1, title: '早餐規則', content: '早餐供應到十點。', score: 0.91 }],
          },
        }),
      };
    }
    if (path === '/api/v1/rag/retrieval/checks/arc_test/confirm' && options.method === 'POST') {
      return {
        ok: true,
        json: async () => ({
          data: { check_id: 'arc_test', confirmed_at: '2026-07-28T00:00:00Z', confirmed_by: 'publisher-1' },
        }),
      };
    }
    if (options.method === 'DELETE') {
      const version = Number(path.split('/').pop());
      const configurations = payloads['/api/v1/rag/retrieval/configurations'];
      configurations.configurations = configurations.configurations.filter((row: any) => Number(row.version) !== version);
      if (Number(configurations.published?.version) === version) configurations.published = null;
      return { ok: true, json: async () => ({ data: { deleted_version: version } }) };
    }
    return { ok: true, json: async () => ({ data: payloads[path] }) };
  });
  const admin = createRagAdmin({
    apiBaseUrl: 'https://example.test',
    adminHeaders: () => ({}),
    getElement: (id: string) => id === 'rag-studio-root' ? root : fields[id],
    escapeHtml: value => String(value ?? ''),
    hasPermission: () => true,
    confirmAction,
    fetchImpl: fetchImpl as any,
  });

  return { admin, root, fields, listeners, confirmAction, bodyClassToggle, fetchImpl, payloads };
}

describe('RAG rebuild job polling', () => {
  it('polls pending and running jobs until success', async () => {
    const jobs = [
      { status: 'pending' },
      { status: 'running', attempts: 1 },
      { status: 'succeeded', result_ref: 'rag-rebuild-status:done' },
    ];
    const loadJob = vi.fn(async () => jobs.shift());
    const onProgress = vi.fn();

    const result = await waitForRagRebuildJob({
      loadJob,
      sleep: async () => {},
      now: (() => {
        let value = 0;
        return () => value++;
      })(),
      onProgress,
    });

    expect(result?.status).toBe('succeeded');
    expect(loadJob).toHaveBeenCalledTimes(3);
    expect(onProgress).toHaveBeenCalledTimes(3);
  });

  it('returns a failed terminal job without polling forever', async () => {
    const result = await waitForRagRebuildJob({
      loadJob: async () => ({ status: 'failed', last_error: 'partial import' }),
      sleep: async () => {},
    });

    expect(result.status).toBe('failed');
    expect(result.last_error).toBe('partial import');
  });
});

describe('RAG guided publication workflow', () => {
  it('shows a missing durable job and lets a publisher requeue the attempt', async () => {
    const { admin, root, listeners, fetchImpl, payloads } = setupRagAdmin();
    payloads['/api/v1/rag/studio'].dashboard = {
      published_items: 0,
      workflow: {
        ready: false,
        completed: 1,
        total: 4,
        next_step: 'publish',
        steps: [
          { id: 'author', title: '建立門市知識草稿', state: 'complete', detail: '已有 1 筆知識項目。', tab: 'knowledge' },
          { id: 'publish', title: '發布並完成索引', state: 'blocked', detail: '可靠工作佇列找不到對應 job。', tab: 'knowledge', action: 'resume-publication', attempt_id: 'pa_1' },
        ],
      },
    };

    await admin.loadPage();

    expect(root.innerHTML).toContain('從門市知識到正式就緒證據');
    expect(root.innerHTML).toContain('重新排入索引');
    listeners.click!({ target: actionTarget('resume-publication', { attemptId: 'pa_1' }) });
    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalledWith(
      'https://example.test/api/v1/rag/knowledge/publication-attempts/pa_1/resume',
      expect.objectContaining({ method: 'POST' }),
    ));
  });
});

describe('RAG knowledge drawer', () => {
  it('selects category and content type while preserving entered fields', async () => {
    const { admin, root, fields, listeners } = setupRagAdmin();
    await admin.loadPage();
    listeners.click!({ target: actionTarget('add') });

    fields['rag-edit-title'].value = '早餐規則';
    fields['rag-edit-content'].value = '早餐供應到上午十點。';
    listeners.input!({ target: { id: 'rag-edit-title', value: fields['rag-edit-title'].value } });
    listeners.input!({ target: { id: 'rag-edit-content', value: fields['rag-edit-content'].value } });
    listeners.click!({ target: actionTarget('drawer-category', { category: 'menu_and_products' }) });
    listeners.click!({ target: actionTarget('drawer-type', { contentType: 'question_answer' }) });

    expect(root.innerHTML).toContain('class="rag-option selected" type="button" data-action="drawer-category" data-category="menu_and_products"');
    expect(root.innerHTML).toContain('class="rag-option selected" type="button" data-action="drawer-type" data-content-type="question_answer"');
    expect(root.innerHTML).toContain('value="早餐規則"');
    expect(root.innerHTML).toContain('早餐供應到上午十點。');
  });

  it('asks before dismissing unsaved changes and closes after confirmation', async () => {
    const { admin, root, fields, listeners, confirmAction, bodyClassToggle } = setupRagAdmin();
    await admin.loadPage();
    listeners.click!({ target: actionTarget('add') });
    fields['rag-edit-title'].value = '尚未儲存';
    listeners.input!({ target: { id: 'rag-edit-title', value: fields['rag-edit-title'].value } });

    confirmAction.mockReturnValueOnce(false);
    listeners.click!({ target: actionTarget('close-drawer') });
    expect(root.innerHTML).toContain('rag-drawer-backdrop');

    confirmAction.mockReturnValueOnce(true);
    listeners.keydown!({ key: 'Escape', preventDefault: vi.fn() });
    expect(root.innerHTML).not.toContain('rag-drawer-backdrop');
    expect(confirmAction).toHaveBeenCalledWith('尚有未儲存的變更，確定要關閉嗎？');
    expect(bodyClassToggle).toHaveBeenLastCalledWith('rag-drawer-open', false);
  });

  it('closes an unchanged drawer by clicking the backdrop without confirmation', async () => {
    const { admin, root, listeners, confirmAction } = setupRagAdmin();
    await admin.loadPage();
    listeners.click!({ target: actionTarget('add') });
    const backdrop = {
      classList: { contains: (name: string) => name === 'rag-drawer-backdrop' },
      closest: () => null,
    };
    listeners.click!({ target: backdrop });

    expect(root.innerHTML).not.toContain('rag-drawer-backdrop');
    expect(confirmAction).not.toHaveBeenCalled();
  });

  it('renders the agreed Traditional Chinese labels', async () => {
    const { admin, root, listeners } = setupRagAdmin();
    await admin.loadPage();
    listeners.click!({ target: actionTarget('add') });

    expect(root.innerHTML).toContain('RAG 智慧工作室');
    expect(root.innerHTML).toContain('門市知識庫');
    expect(root.innerHTML).toContain('知識分類');
    expect(root.innerHTML).toContain('RAG 內容類型');
  });

  it('clears the published retrieval configuration after a stronger confirmation', async () => {
    const { admin, root, listeners, confirmAction, fetchImpl, payloads } = setupRagAdmin();
    payloads['/api/v1/rag/retrieval/configurations'] = {
      published: { version: 2, status: 'published', method: 'dense', top_k: 3, relevance_policy: 'strict' },
      configurations: [
        { version: 2, status: 'published', method: 'dense', top_k: 3, relevance_policy: 'strict', published_at: '2026-07-27T00:00:00Z' },
        { version: 1, status: 'superseded', method: 'hybrid_rrf', top_k: 5, relevance_policy: 'balanced', published_at: '2026-07-26T00:00:00Z' },
      ],
    };
    await admin.loadPage();
    listeners.click!({ target: actionTarget('tab', { tab: 'methods' }) });

    expect(root.innerHTML).toContain('data-action="delete-config" data-version="1"');
    expect(root.innerHTML).toContain('data-action="delete-config" data-version="2" data-published="true"');
    await listeners.click!({ target: actionTarget('delete-config', { version: '2', published: 'true' }) });

    expect(confirmAction).toHaveBeenCalledWith('這是目前使用中的檢索設定。永久刪除 v2 後，RAG 將暫停提供檢索，直到重新發布設定。確定繼續？');
    await vi.waitFor(() => {
      expect(fetchImpl).toHaveBeenCalledWith(
        'https://example.test/api/v1/rag/retrieval/configurations/2',
        expect.objectContaining({ method: 'DELETE' }),
      );
      expect(root.innerHTML).not.toContain('data-version="2"');
    });
  });
});

describe('Ad Hoc Retrieval Check workspace', () => {
  it('preserves its draft across tab changes and quiet polling', async () => {
    const { admin, root, listeners } = setupRagAdmin();
    await admin.loadPage();
    listeners.click!({ target: actionTarget('tab', { tab: 'tests' }) });
    listeners.input!({ target: { id: 'rag-test-query', value: '早餐供應到幾點？' } });

    listeners.click!({ target: actionTarget('test-tab', { tab: 'cases' }) });
    listeners.click!({ target: actionTarget('test-tab', { tab: 'adhoc' }) });
    expect(root.innerHTML).toContain('早餐供應到幾點？');

    const htmlBeforePoll = root.innerHTML;
    const intervalCallback = (window.setInterval as any).mock.calls[0][0];
    await intervalCallback();
    await vi.waitFor(() => expect(root.innerHTML).toBe(htmlBeforePoll));
  });

  it('runs an immutable snapshot and confirms without rerunning retrieval', async () => {
    const { admin, root, listeners, fetchImpl } = setupRagAdmin();
    await admin.loadPage();
    listeners.click!({ target: actionTarget('tab', { tab: 'tests' }) });
    listeners.input!({ target: { id: 'rag-test-query', value: '早餐供應到幾點？' } });
    listeners.change!({ target: { id: 'rag-test-method', value: 'bm25', classList: { contains: () => false } } });
    listeners.change!({ target: { id: 'rag-test-top-k', value: '5', classList: { contains: () => false } } });
    listeners.change!({ target: { id: 'rag-test-policy', value: 'balanced', classList: { contains: () => false } } });

    listeners.click!({ target: actionTarget('run-test') });
    await vi.waitFor(() => expect(root.innerHTML).toContain('arc_test'));

    const retrievalCalls = fetchImpl.mock.calls.filter(([url]) => new URL(String(url)).pathname === '/api/v1/rag/retrieval/test');
    expect(retrievalCalls).toHaveLength(1);
    expect(JSON.parse(String(retrievalCalls[0]![1]?.body))).toEqual({
      query: '早餐供應到幾點？',
      method: 'bm25',
      top_k: 5,
      relevance_policy: 'balanced',
    });

    listeners.click!({ target: actionTarget('confirm-test') });
    await vi.waitFor(() => expect(root.innerHTML).toContain('已確認為 RAG 就緒證據'));
    expect(fetchImpl.mock.calls.filter(([url]) => new URL(String(url)).pathname === '/api/v1/rag/retrieval/test')).toHaveLength(1);
    expect(fetchImpl).toHaveBeenCalledWith(
      'https://example.test/api/v1/rag/retrieval/checks/arc_test/confirm',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
