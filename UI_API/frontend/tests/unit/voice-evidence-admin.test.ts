import { describe, expect, it } from 'vitest';

import { buildVoiceEvidenceView } from '../../admin/modules/voiceEvidenceAdmin.js';

describe('admin voice evidence browser view', () => {
  it('renders metadata without conversation text and exposes projection state', () => {
    const view = buildVoiceEvidenceView({
      records: [{
        evidence_id: 'vie-1',
        voice_turn_id: 'turn-1',
        observed_at: '2026-08-14T09:30:00+08:00',
        terminal_status: 'completed',
        failure_type: '',
        rag_outcome: 'not_run',
        has_transcript: true,
        has_assistant_text: true,
        projection_status: 'projected',
      }],
      page: { has_more: false },
    });

    expect(view.empty).toBe(false);
    expect(view.rows[0]?.voiceTurnId).toBe('turn-1');
    expect(view.rows[0]?.content).toBe('已保留去識別化內容');
    expect(view.rows[0]?.rag).toBe('尚未執行');
    expect(view.rows[0]?.projection).toBe('已同步');
  });

  it('distinguishes an empty day from a failed query', () => {
    expect(buildVoiceEvidenceView({ records: [] }).emptyLabel).toContain('沒有');
    expect(buildVoiceEvidenceView({ error: '查詢失敗' }).status).toContain('查詢失敗');
    expect(buildVoiceEvidenceView({ error: '查詢失敗' }).statusTone).toBe('attention');
  });

  it('does not turn accepted-but-unprojected turns into a false zero', () => {
    const view = buildVoiceEvidenceView({
      records: [],
      reconciliation: { status: 'awaiting_projection', awaiting_projection: 2 },
    });

    expect(view.empty).toBe(false);
    expect(view.status).toContain('等待同步');
  });
});
