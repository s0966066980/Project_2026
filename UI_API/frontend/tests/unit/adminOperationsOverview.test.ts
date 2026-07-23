import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const frontendRoot = resolve(__dirname, '../..');
const adminHtml = readFileSync(resolve(frontendRoot, 'admin/admin.html'), 'utf8');
const recommendationModule = readFileSync(
  resolve(frontendRoot, 'admin/modules/recommendationEventsAdmin.js'),
  'utf8',
);
const adminJs = readFileSync(resolve(frontendRoot, 'admin/admin.js'), 'utf8');

describe('營運總覽資訊層級', () => {
  it('只保留一組統計重新整理與清除控制', () => {
    expect(adminHtml.match(/id="refreshBtn"/g)).toHaveLength(1);
    expect(adminHtml.match(/id="clearBtn"/g)).toHaveLength(1);
    expect(adminHtml).not.toContain('recommendationRefreshBtn');
    expect(adminHtml).not.toContain('recommendationClearBtn');
  });

  it('首屏只保留四項推薦成效，明細採漸進揭露', () => {
    expect(recommendationModule).toContain("['有效曝光'");
    expect(recommendationModule).toContain("['完成購買'");
    expect(recommendationModule).toContain("['購買率'");
    expect(recommendationModule).toContain("['推薦營收'");
    expect(adminHtml).toContain('class="recommendation-advanced overview-details"');
  });
});

describe('RAG 策略測試介面', () => {
  it('提供三種策略、正式設定與受限測試輸入', () => {
    expect(adminHtml).toContain('<option value="dense">');
    expect(adminHtml).toContain('<option value="bm25">');
    expect(adminHtml).toContain('<option value="hybrid">');
    expect(adminHtml).toContain('id="rag-test-query"');
    expect(adminHtml).toContain('maxlength="500"');
    expect(adminJs).toContain('RAG_STRATEGY:');
    expect(adminJs).toContain('/api/rag/test');
  });
});

describe('文字情緒分析介面', () => {
  it('提供受限文字輸入、清楚能力說明與結果區', () => {
    const emotionPage = adminHtml.slice(
      adminHtml.indexOf('id="page-emotion"'),
      adminHtml.indexOf('id="page-members"'),
    );
    const testPage = adminHtml.slice(adminHtml.indexOf('id="page-test"'));

    expect(adminHtml).toContain('id="emotion-text-input"');
    expect(adminHtml).toContain('maxlength="500"');
    expect(adminHtml).toContain('不會捏造表情或聲音線索');
    expect(adminHtml).toContain('id="emotion-text-result"');
    expect(emotionPage).not.toContain('id="emotion-text-input"');
    expect(testPage).toContain('id="emotion-text-input"');
    expect(testPage.indexOf('LLM 測試設定')).toBeLessThan(testPage.indexOf('文字模擬說話'));
    expect(testPage).toContain('文字情緒分析回答');
    expect(testPage).toContain('情緒模型分析內容');
    expect(testPage).toContain('id="emotion-text-result-answer"');
    expect(testPage).toContain('id="emotion-video"');
    expect(testPage).toContain('開始即時偵測');
    expect(adminJs).toContain('/api/emotion/analyze_text');
    expect(adminJs).toContain('/api/emotion/analyze_media_test');
    expect(adminJs).toContain('window.analyzeEmotionText');
    expect(adminJs).toContain('window.startEmotionVideoDetection');
  });
});
