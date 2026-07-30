import { expect, test, type Route } from '@playwright/test';

function getVoiceTurnId(route: Route): string {
  const multipartBody = route.request().postData() || '';
  return /name="voice_turn_id"\r?\n\r?\n([^\r\n]+)/.exec(multipartBody)?.[1] || '';
}

function voiceEvent(
  voiceTurnId: string,
  sequence: number,
  type: string,
  payload: Record<string, unknown> = {},
  terminal = false,
) {
  return { voice_turn_id: voiceTurnId, sequence, type, payload, terminal };
}

test('語音模式可取消、手動送出，並保留 TTS 降級後的文字結果', async ({ page, context }) => {
  await context.grantPermissions(['microphone'], { origin: 'http://127.0.0.1:9080' });
  await page.addInitScript(() => {
    localStorage.setItem('kiosk_feat_version', 'voice-emotion-20260721');
    localStorage.setItem('kiosk_feat', JSON.stringify({
      voiceAssist: true,
      recommend: false,
      multiLang: true,
    }));
  });

  const interactionEvents: string[] = [];
  await page.route('**/api/public_settings', route => route.fulfill({
    status: 200,
    json: { MEMBER_ENABLED: false, EMOTION_LLAMA_ENABLED: false, DEMO_PUBLIC_MODE: false },
  }));
  await page.route('**/api/menu', route => route.fulfill({ status: 200, json: [] }));
  await page.route('**/api/passive_check', route => route.fulfill({ status: 200, json: { status: 'idle' } }));
  await page.route('**/api/interaction_event', async route => {
    interactionEvents.push(String(route.request().postDataJSON()?.event_type || ''));
    await route.fulfill({ status: 200, json: { status: 'success' } });
  });
  await page.route('**/api/ask/stream', async route => {
    const voiceTurnId = getVoiceTurnId(route);
    expect(voiceTurnId).not.toBe('');
    const userText = '我要一份測試套餐';
    const aiResponse = '好的，文字回覆已保留。';
    await route.fulfill({
      status: 200,
      contentType: 'application/x-ndjson',
      body: [
        voiceEvent(voiceTurnId, 1, 'accepted'),
        voiceEvent(voiceTurnId, 2, 'transcribing'),
        voiceEvent(voiceTurnId, 3, 'transcript', { user_text: userText, detected_lang: 'zh' }),
        voiceEvent(voiceTurnId, 4, 'assistant_result', { ai_response: aiResponse, order_draft: null, mentioned_ids: [] }),
        voiceEvent(voiceTurnId, 5, 'completed', {
          status: 'success',
          user_text: userText,
          ai_response: aiResponse,
          detected_lang: 'zh',
          order_draft: null,
          mentioned_ids: [],
          playback_status: 'degraded',
          playback_message: '文字結果已保留，但語音播放暫時不可用。',
          audio_base64: '',
          audio_format: '',
        }, true),
      ].map(event => JSON.stringify(event)).join('\n') + '\n',
    });
  });

  await page.goto('/kiosk');
  await page.locator('#startSystemBtn').click();

  await page.locator('#voiceAssistBtn').click();
  await expect(page.locator('#voiceAssistOverlay')).not.toHaveClass(/hidden/);
  await expect(page.locator('#voiceAssistSendBtn')).toContainText('立即送出');
  await expect(page.locator('#voiceAssistStopBtn')).toContainText('取消');
  await page.locator('#voiceAssistStopBtn').click();
  await expect(page.locator('#voiceAssistOverlay')).toHaveClass(/hidden/);

  await page.locator('#voiceAssistBtn').click();
  await page.waitForTimeout(1_000);
  await page.locator('#voiceAssistSendBtn').click();

  await expect(page.locator('#voiceReplyBubble')).not.toHaveClass(/hidden/);
  await expect(page.locator('#voiceDialogueGrid')).toContainText('好的，文字回覆已保留。');
  await expect(page.locator('#voiceDialogueGrid')).toContainText('語音播放暫時不可用');
  await expect.poll(() => interactionEvents).toContain('voice_assist_cancelled');
  await expect.poll(() => interactionEvents).toContain('voice_assist_submitted');
  await expect.poll(() => interactionEvents).toContain('voice_assist_playback_degraded');
});

test('語音餐點先進入未勾選草稿，確認後才加入購物車', async ({ page, context }) => {
  await context.grantPermissions(['microphone'], { origin: 'http://127.0.0.1:9080' });
  await page.addInitScript(() => {
    localStorage.setItem('kiosk_feat_version', 'voice-emotion-20260721');
    localStorage.setItem('kiosk_feat', JSON.stringify({ voiceAssist: true, recommend: false, multiLang: true }));
  });
  const menu = [
    { id: 'MCD001', name: '大麥克', price: 79, category: '漢堡', description: '雙層牛肉漢堡' },
    { id: 'MCD012', name: '薯條（中）', price: 45, category: '點心' },
  ];
  await page.route('**/api/public_settings', route => route.fulfill({ status: 200, json: { MEMBER_ENABLED: false, EMOTION_LLAMA_ENABLED: false, DEMO_PUBLIC_MODE: false } }));
  await page.route('**/api/menu', route => route.fulfill({ status: 200, json: menu }));
  await page.route('**/api/passive_check', route => route.fulfill({ status: 200, json: { status: 'idle' } }));
  await page.route('**/api/cart/quote', route => route.fulfill({
    status: 200,
    json: { items: [{ item_id: 'MCD001', base_unit_price: 79, effective_unit_price: 79, discount_unit_total: 0 }], total: 158, quote_version: 'test' },
  }));
  await page.route('**/api/ask/stream', async route => {
    const voiceTurnId = getVoiceTurnId(route);
    expect(voiceTurnId).not.toBe('');
    const userText = '我要兩份大麥克';
    const aiResponse = '已整理您提到的餐點，請在畫面上勾選要加入的品項並確認。';
    const orderDraft = {
      requires_confirmation: true,
      lines: [{ item_id: 'MCD001', quantity: 2 }],
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/x-ndjson',
      body: [
        voiceEvent(voiceTurnId, 1, 'accepted'),
        voiceEvent(voiceTurnId, 2, 'transcribing'),
        voiceEvent(voiceTurnId, 3, 'transcript', { user_text: userText, detected_lang: 'zh' }),
        voiceEvent(voiceTurnId, 4, 'assistant_result', { ai_response: aiResponse, order_draft: orderDraft, mentioned_ids: ['MCD001'] }),
        voiceEvent(voiceTurnId, 5, 'completed', {
          status: 'success',
          user_text: userText,
          ai_response: aiResponse,
          detected_lang: 'zh',
          order_draft: orderDraft,
          mentioned_ids: ['MCD001'],
          playback_status: 'degraded',
          playback_message: '文字結果已保留，但語音播放暫時不可用。',
          audio_base64: '',
          audio_format: '',
        }, true),
      ].map(event => JSON.stringify(event)).join('\n') + '\n',
    });
  });

  await page.goto('/kiosk');
  await page.locator('#startSystemBtn').click();
  await page.locator('#voiceAssistBtn').click();
  await page.waitForTimeout(1_000);
  await page.locator('#voiceAssistSendBtn').click();

  await expect(page.locator('#voiceDialogueGrid')).toContainText('請在畫面上勾選要加入的品項並確認');
  await expect(page.locator('#voiceOrderDraftModal')).not.toHaveClass(/hidden/);
  await expect(page.locator('#voiceOrderDraftItems')).toContainText('大麥克');
  await expect(page.locator('#voiceOrderDraftItems input[type="checkbox"]')).not.toBeChecked();
  await expect(page.locator('#cartList')).not.toContainText('大麥克');
  await expect(page.locator('#voiceOrderDraftConfirm')).toBeDisabled();

  await page.locator('#voiceOrderDraftModal [data-voice-draft-cancel]').last().click();
  await expect(page.locator('#voiceOrderDraftModal')).toHaveClass(/hidden/);
  await expect(page.locator('#cartList')).not.toContainText('大麥克');

  await page.locator('#voiceAssistBtn').click();
  await page.waitForTimeout(1_000);
  await page.locator('#voiceAssistSendBtn').click();
  await expect(page.locator('#voiceOrderDraftModal')).not.toHaveClass(/hidden/);

  await page.locator('#voiceOrderDraftItems input[type="checkbox"]').check();
  await expect(page.locator('#voiceOrderDraftConfirm')).toBeEnabled();
  await page.locator('#voiceOrderDraftConfirm').click();

  await expect(page.locator('#voiceOrderDraftModal')).toHaveClass(/hidden/);
  await expect(page.locator('#cartList')).toContainText('大麥克');
  await expect(page.locator('#cartList')).toContainText('2');
});
