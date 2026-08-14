import { describe, expect, it } from 'vitest';

import { buildDiagnosticWorkbenchView } from '../../admin/modules/diagnosticWorkbench.js';

describe('daily diagnostic workbench browser view', () => {
  it('renders the saved question snapshot as dialogue and exposes the RAG handoff', () => {
    const view = buildDiagnosticWorkbenchView({
      questions: [{ question_id: 'q1', display_name: '今日語音診斷', prompt: '診斷今日語音對話' }],
      report: {
        recorded_at: '2026-08-13T08:00:00+00:00',
        diagnostic_question: { question_id: 'q1', display_name: '今日語音診斷', prompt: '診斷今日語音對話' },
        dialogue: { question: '診斷今日語音對話', answer: '需要我幫你將分析結果加入 RAG 嗎？' },
        findings: [{ classification: 'RAG Knowledge Gap', occurrences: 3 }],
        evidence_summary: { count: 3, level: 'Reference Guidance' },
        knowledge_candidate: { candidate_id: 'candidate-1', status: 'pending', action: 'create' },
      },
      candidate: { candidate_id: 'candidate-1', status: 'pending', action: 'create', offline_acceptance: 'passed' },
    });

    expect(view.questionLabel).toBe('今日語音診斷');
    expect(view.dialogue.question).toBe('診斷今日語音對話');
    expect(view.dialogue.answer).toContain('加入 RAG');
    expect(view.findings[0]?.label).toBe('RAG Knowledge Gap');
    expect(view.candidate.actionLabel).toBe('建議新增 RAG 知識');
    expect(view.candidate.canConfirm).toBe(true);
  });

  it('keeps a safe previous-result state when a later run fails', () => {
    const view = buildDiagnosticWorkbenchView({
      report: { report_id: 'report-1', dialogue: { question: '舊問題', answer: '舊結果' } },
      error: '分析失敗（503）',
    });

    expect(view.dialogue.answer).toBe('舊結果');
    expect(view.status).toContain('503');
    expect(view.statusTone).toBe('attention');
  });

  it('distinguishes no evidence from an insufficient evidence signal', () => {
    const empty = buildDiagnosticWorkbenchView({ report: { evidence_summary: { count: 0 } } });
    const insufficient = buildDiagnosticWorkbenchView({
      report: { evidence_summary: { count: 2, level: 'Observation Signal' } },
    });

    expect(empty.evidence.label).toContain('沒有可分析');
    expect(insufficient.evidence.label).toContain('證據不足');
    expect(insufficient.candidate.visible).toBe(false);
  });
});
