import { describe, expect, it } from 'vitest';

import { healthServiceView, operationalHealthView, readinessView } from '../../admin/modules/healthAdmin.js';

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

    expect(rows[0]).toMatchObject({ label: 'Runtime Persistence Profile', status: 'failed', detail: 'database_unavailable' });
    expect(rows[0]?.purpose).toContain('不可回退到其他儲存');
  });

  it('優先呈現能否營運、受影響能力與事件', () => {
    const view = operationalHealthView({
      state: 'operate_with_degraded_features',
      headline: '可以營運，但部分功能降級',
      business_impact: '結帳可繼續。',
      capabilities: [{ key: 'rag_answers', label: 'RAG 知識回答', status: 'degraded' }],
      incidents: [{ incident_id: 'health_rag_1', title: '知識回答降級' }],
    });

    expect(view.tone).toBe('degraded');
    expect(view.businessImpact).toContain('結帳可繼續');
    expect(view.capabilities[0]?.statusLabel).toBe('降級');
    expect(view.incidents[0]?.incident_id).toBe('health_rag_1');
  });
});
