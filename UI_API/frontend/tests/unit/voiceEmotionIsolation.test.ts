import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const frontendRoot = resolve(import.meta.dirname, '../..');
const appSource = readFileSync(resolve(frontendRoot, 'kiosk/app.js'), 'utf8');
const voiceSource = readFileSync(resolve(frontendRoot, 'kiosk/voice.js'), 'utf8');
const paymentSource = readFileSync(resolve(frontendRoot, 'kiosk/paymentCountdown.js'), 'utf8');
const adminSource = readFileSync(resolve(frontendRoot, 'admin/admin.js'), 'utf8');
const adminHtml = readFileSync(resolve(frontendRoot, 'admin/admin.html'), 'utf8');

describe('語音情緒分析隔離', () => {
  it('Kiosk 只上傳一次語音，STT 配對分析由 voice backend 統一協調', () => {
    expect(voiceSource).not.toContain('analyzeVoiceEmotionInBackground');
    expect(voiceSource).not.toContain('api.analyzeVoiceEmotionEvent');
    expect(appSource).not.toContain('analyzeVoiceEmotionEvent');
    expect(paymentSource).not.toMatch(/emotion/i);
  });

  it('語音請求帶入穩定 turn 識別，完成訂單後重設情緒生命週期', () => {
    expect(voiceSource).toContain("formData.append('emotion_round_id'");
    expect(voiceSource).toContain("formData.append('voice_turn_id'");
    expect(voiceSource).toContain("formData.append('voice_turn_index'");
    const finishOrder = appSource.slice(appSource.indexOf('async function finishOrder'), appSource.indexOf('function openOrderConfirmModal'));
    expect(finishOrder).toContain('resetVoiceEmotionRound()');
  });

  it('Admin 不再提供阻塞模式或付款情緒設定', () => {
    expect(adminSource).not.toContain('EMOTION_LLAMA_VOICE_WAIT_MODE');
    expect(adminSource).not.toContain('EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT');
    expect(adminSource).not.toContain('PAYMENT_ASSIST_PROMPT');
    expect(adminHtml).not.toContain('等待分析完成');
    expect(adminHtml).not.toContain('付款倒數逾時分析');
    expect(adminHtml).not.toContain('inp-payment-assist-prompt');
    expect(adminHtml).toContain('id="inp-emotion-analysis-mode"');
    expect(adminHtml).toContain('<option value="media_only">方案 A｜僅影音');
    expect(adminHtml).toContain('<option value="media_plus_stt" selected>方案 B｜影音＋STT');
    expect(adminHtml).toContain('<option value="paired">方案 A+B｜同片段配對');
    expect(adminSource).toContain('EMOTION_LLAMA_ANALYSIS_MODE');
    expect(adminSource).toContain('EMOTION_LLAMA_INCLUDE_STT');
    expect(adminHtml).toContain('id="inp-emotion-include-stt"');
    expect(adminHtml).toContain('id="inp-emotion-prompt"');
    expect(adminSource).toMatch(/setVal\('inp-emotion-prompt',\s+s\.EMOTION_LLAMA_PROMPT \|\| ''\)/);
  });

  it('Admin 提供本輪客人 LLM 分析，不顯示 STT 同片段配對欄位', () => {
    expect(adminSource).toContain("createEmotionInfluenceAdmin");
    expect(adminHtml).toContain('id="emotion-influence-kpis"');
    expect(adminHtml).toContain('id="emotion-customer-analyze-btn"');
    expect(adminHtml).toContain('id="emotion-customer-analysis-result"');
    expect(adminHtml).toContain('id="emotion-influence-rounds"');
    expect(adminHtml).toContain('本輪客人分析');
    expect(adminHtml).not.toContain('id="emotion-stt-comparison"');
    expect(adminSource).toContain('/api/emotion/analyze_ordering_round');
  });
});
