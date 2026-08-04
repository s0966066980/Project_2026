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
const settingsModule = readFileSync(resolve(frontendRoot, 'admin/modules/settingsAdmin.js'), 'utf8');
const ragAdminModule = readFileSync(resolve(frontendRoot, 'admin/modules/ragAdmin.js'), 'utf8');

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
    expect(adminHtml).toContain('id="operationsTodayMetrics"');
    expect(recommendationModule).toContain('loadTodaySummary');
    expect(adminJs).toContain('recommendationEventsAdmin.loadTodaySummary()');
    expect(adminHtml).toContain('id="inp-recommendation-purchase-target"');
    expect(adminHtml).toContain('id="inp-recommendation-ignore-guardrail"');
    expect(settingsModule).toContain('RECOMMENDATION_PURCHASE_RATE_TARGET');
  });
});

describe('RAG 策略測試介面', () => {
  it('提供九分類、四種檢索方法與 Retrieval-only 測試', () => {
    expect(adminHtml).toContain('id="rag-studio-root"');
    expect(adminHtml).toContain('/static/admin/ragStudio.css');
    expect(ragAdminModule).toContain("store_and_hours");
    expect(ragAdminModule).toContain("nutrition_and_allergens");
    expect(ragAdminModule).toContain("question_answer");
    expect(ragAdminModule).toContain("operating_procedure");
    expect(ragAdminModule).toContain("hybrid_rrf");
    expect(ragAdminModule).toContain("hybrid_reranker");
    expect(ragAdminModule).toContain('id="rag-test-query"');
    expect(ragAdminModule).toContain('maxlength="2000"');
    expect(ragAdminModule).toContain('/api/v1/rag/retrieval/test');
    expect(ragAdminModule).toContain('/api/v1/rag/evaluation-runs');
    expect(ragAdminModule).toContain('/api/v1/rag/knowledge');
    expect(ragAdminModule).not.toContain('/api/rag/faqs');
    expect(ragAdminModule).not.toContain('/api/rag/knowledge-gaps');
    expect(adminJs).toContain('createRagAdmin');
  });
});

describe('情緒測試介面', () => {
  it('只保留即時影音診斷，文字模擬說話已移除', () => {
    // 測試頁已移除，即時影音診斷改掛在情緒分析頁的「即時客人分析」分頁。
    expect(adminHtml).not.toContain('id="page-test"');
    const testPage = adminHtml.slice(adminHtml.indexOf('data-emotion-panel="live"'));

    // 文字模擬說話測試功能已整個移除（UI、腳本與後端路由）。
    expect(adminHtml).not.toContain('id="emotion-text-input"');
    expect(adminHtml).not.toContain('id="emotion-text-result"');
    expect(adminHtml).not.toContain('文字模擬說話');
    expect(adminHtml).not.toContain('data-emotion-sample');
    expect(adminJs).not.toContain('/api/emotion/analyze_text');
    expect(adminJs).not.toContain('analyzeEmotionText');

    expect(testPage).toContain('id="emotion-video"');
    expect(testPage).toContain('開始單次擷取');
    expect(testPage).toContain('同一片段分別送往權威情緒模型與 STT');
    expect(testPage).toContain('不接受手填文字替代');
    expect(testPage).not.toContain('name="emotion-test-scheme"');
    expect(testPage).toContain('每次只做一段自適應擷取');
    expect(testPage).toContain('id="emotion-test-provider-pill"');
    expect(adminJs).toContain('/api/emotion/analyze_media_test');
    expect(adminJs).toContain('/api/emotion/test_capabilities');
    expect(adminJs).not.toContain("formData.append('analysis_mode'");
    expect(adminJs).not.toContain("formData.append('speech_text'");
    expect(adminJs).toContain('captureEmotionVideoClip(emotionVideoStream)');
    expect(adminJs).toContain('window.startEmotionVideoDetection');
  });
});
