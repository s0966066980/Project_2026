import { expect, test } from '@playwright/test';

test('Admin 單次自適應擷取只送一份影音，STT 與分類維持獨立', async ({ page, context }) => {
  await context.grantPermissions(['camera', 'microphone'], { origin: 'http://127.0.0.1:9080' });
  let inFlight = 0;
  let maxInFlight = 0;
  let analysisRequests = 0;

  await page.route('**/api/admin/auth/ui-config', route => route.fulfill({
    status: 200,
    json: { manager_login_identity: 'admin', manager_idle_timeout_sec: 1800 },
  }));
  await page.route('**/api/admin/auth/me', route => route.fulfill({
    status: 200,
    json: { principal: { user_id: 'manager-test', permissions: ['*'] } },
  }));
  await page.route('**/api/menu', route => route.fulfill({ status: 200, json: [] }));
  await page.route('**/api/session_stats', route => route.fulfill({ status: 200, json: { status: 'success' } }));
  await page.route('**/api/emotion/test_capabilities', route => route.fulfill({
    status: 200,
    json: {
      status: 'success', enabled: true,
      capture: { mode: 'single_adaptive', max_seconds: 8, same_capture_stt: true },
      provider: { provider: 'r1_omni', status: 'ready', model_loaded: true, capabilities: ['audio_only', 'video_audio'], latency_ms: 4 },
    },
  }));
  await page.route('**/api/emotion/analyze_media_test', async route => {
    analysisRequests += 1;
    inFlight += 1;
    maxInFlight = Math.max(maxInFlight, inFlight);
    expect(route.request().postData() || '').not.toContain('speech_text');
    expect(route.request().postData() || '').not.toContain('analysis_mode');
    await new Promise(resolve => setTimeout(resolve, 250));
    inFlight -= 1;
    await route.fulfill({
      status: 200,
      json: {
        status: 'ok', provider: 'r1_omni', model_version: 'test', analysis_variant: 'live_same_capture',
        emotion: 'confused', intensity: 'medium', confidence: .9,
        facial: '眉頭微皺', vocal: '語速偏慢', description: '情緒模型分析內容',
        evidence_quality: 'ok', evidence_latency_ms: 180,
        transcript_status: 'available', transcript_character_count: 12,
        emotion_observation_explanation: '可提供簡短步驟協助。',
      },
    });
  });

  await page.goto('/admin');
  await page.locator('[data-page="test"]').click();
  await expect(page.locator('#emotion-test-provider-pill')).toContainText('R1-Omni 已就緒');
  await page.locator('#emotion-video-start-btn').click();

  await expect(page.locator('.emotion-result-card')).toHaveCount(1, { timeout: 12_000 });
  await expect(page.locator('#emotion-video-result')).toContainText('權威情緒模型');
  await expect(page.locator('#emotion-video-result')).toContainText('同片段 STT 完成');
  await expect(page.locator('#emotion-video-result')).toContainText('情緒觀察解說（不改分類）');
  await expect(page.locator('#emotion-video-batch-latency')).not.toHaveText('—');
  await expect(page.locator('#emotion-video-status')).toContainText('單次診斷完成');
  expect(analysisRequests).toBe(1);
  expect(maxInFlight).toBe(1);
  await expect(page.locator('#emotion-video-stop-btn')).toBeDisabled();
});
