import { describe, expect, it } from 'vitest';

import { healthServiceView, readinessView } from '../../admin/modules/healthAdmin.js';

describe('維運健康功能說明', () => {
  it('區分必要商業資料庫與不阻擋結帳的 RAG', () => {
    const rows = healthServiceView({
      postgres: { status: 'ok', backend: 'postgres', schema_migration_count: 11 },
      rag: { status: 'ok', doc_count: 2, selected_source_count: 2, collection_name: 'kiosk_rag' },
    });

    expect(rows.find(row => row.key === 'postgres')?.requirement).toContain('必要');
    expect(rows.find(row => row.key === 'rag')?.requirement).toContain('不阻擋結帳');
    expect(rows.find(row => row.key === 'rag')?.evidence).toContain('正式選取 2 筆');
  });

  it('把 readiness 檢查轉成中文用途與可觀察結果', () => {
    const rows = readinessView({ required_checks: { database: { status: 'failed', error_code: 'database_unavailable' } } });

    expect(rows[0]).toMatchObject({ label: '資料庫連線', status: 'failed', detail: 'database_unavailable' });
    expect(rows[0]?.purpose).toContain('不可回退到 JSON');
  });
});
