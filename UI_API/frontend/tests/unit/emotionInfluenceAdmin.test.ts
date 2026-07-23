import { describe, expect, it } from 'vitest';

import {
  buildEmotionInfluenceViewModel,
  createEmotionInfluenceAdmin,
} from '../../admin/modules/emotionInfluenceAdmin.js';

const completeAnalysis = {
  timestamp: '2026-07-21T10:00:02+08:00',
  session_id: 'session-1',
  emotion_round_id: 'round-1',
  voice_turn_id: 'turn-1',
  voice_turn_index: 1,
  analysis_variant: 'media_plus_stt',
  event_type: 'voice_mode_ended',
  status: 'ok',
  emotion: 'anxious',
  intensity: 'medium',
  facial: '眉頭微皺',
  vocal: '語速偏快',
  description: '顧客難以選擇套餐，需要簡短選項。',
};

describe('本輪點餐情緒分析視圖', () => {
  it('依本輪分組，且五個必要欄位都存在才算完整', () => {
    const view = buildEmotionInfluenceViewModel([
      completeAnalysis,
      { ...completeAnalysis, voice_turn_id: 'turn-2', status: 'incomplete', facial: '' },
      { ...completeAnalysis, emotion_round_id: 'round-old', timestamp: '2026-07-20T10:00:00+08:00' },
    ]);

    expect(view.latestRound?.id).toBe('round-1');
    expect(view.latestRound?.analyses).toHaveLength(2);
    expect(view.metrics).toMatchObject({
      roundCount: 2,
      analysisCount: 3,
      structurallyCompleteAnalysisCount: 2,
      incompleteAnalysisCount: 1,
    });
  });

  it('顯示本輪五欄情緒證據與客人分析入口，不顯示 STT 配對結果', () => {
    const elements = {
      'emotion-influence-kpis': { innerHTML: '' },
      'emotion-customer-analysis-context': { innerHTML: '' },
      'emotion-customer-analyze-btn': { disabled: true },
      'emotion-influence-rounds': { innerHTML: '' },
    } as unknown as Record<string, HTMLElement>;
    const admin = createEmotionInfluenceAdmin({
      getElement: id => elements[id] ?? null,
      escapeHtml: value => String(value ?? '').replaceAll('<', '&lt;'),
      emotionLabel: value => String(value || ''),
      intensityLabel: value => String(value || ''),
      providerLabel: value => String(value || ''),
    });

    admin.render([completeAnalysis]);

    expect(elements['emotion-customer-analysis-context']!.innerHTML).toContain('1/1 筆五欄完整');
    expect((elements['emotion-customer-analyze-btn'] as unknown as { disabled: boolean }).disabled).toBe(false);
    const evidence = elements['emotion-influence-rounds']!.innerHTML;
    expect(evidence).toContain('情緒／強度');
    expect(evidence).toContain('表情');
    expect(evidence).toContain('語調');
    expect(evidence).toContain('點餐重點');
    expect(evidence).not.toContain('同片段配對');
    expect(evidence).not.toContain('STT');
  });
});
