import { expect, test } from '@playwright/test';

function observeCriticalBrowserFailures(page: import('@playwright/test').Page) {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  return errors;
}

async function openKioskPaymentScreen(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    localStorage.setItem('kiosk_feat_version', 'voice-emotion-20260721');
    localStorage.setItem('kiosk_feat', JSON.stringify({
      voiceAssist: false,
      recommend: false,
      multiLang: true,
    }));
  });
  await page.route('**/api/public_settings', route => route.fulfill({
    status: 200,
    json: {
      MEMBER_ENABLED: false,
      EMOTION_LLAMA_ENABLED: false,
      DEMO_PUBLIC_MODE: false,
    },
  }));
  await page.route('**/api/menu', route => route.fulfill({
    status: 200,
    json: [{ id: 'MCD001', name: '測試套餐', category: '超值全餐', price: 100, image: '' }],
  }));
  await page.goto('/kiosk');
  await page.locator('#startSystemBtn').click();
  await page.getByRole('button', { name: /超值全餐/ }).first().click();
  await page.locator('#menu-MCD001 .kiosk-add-btn').click();
  await page.locator('#itemConfirmAdd').click();
  await page.locator('#kioskCartBtn').click();
  await page.locator('#checkoutBtn').click();
}

test('Kiosk boots to the start screen without browser failures', async ({ page }) => {
  const errors = observeCriticalBrowserFailures(page);
  await page.route('**/api/public_settings', route => route.fulfill({
    status: 200,
    json: { MEMBER_ENABLED: false, EMOTION_LLAMA_ENABLED: false, DEMO_PUBLIC_MODE: false },
  }));
  await page.route('**/api/menu', route => route.fulfill({ status: 200, json: [] }));

  await page.goto('/kiosk');

  await expect(page.locator('#startSystemBtn')).toBeVisible();
  await expect(page.locator('#startSystemBtn')).toContainText('開始點餐');
  await page.waitForTimeout(100);
  expect(errors).toEqual([]);
});

test('Kiosk preserves start, menu, cart and checkout navigation contracts', async ({ page }) => {
  const errors = observeCriticalBrowserFailures(page);
  await page.addInitScript(() => {
    localStorage.setItem('kiosk_feat_version', 'voice-emotion-20260721');
    localStorage.setItem('kiosk_feat', JSON.stringify({
      voiceAssist: false,
      recommend: false,
      multiLang: true,
    }));
  });
  await page.route('**/api/public_settings', route => route.fulfill({
    status: 200,
    json: { MEMBER_ENABLED: false, EMOTION_LLAMA_ENABLED: false, DEMO_PUBLIC_MODE: false },
  }));
  await page.route('**/api/menu', route => route.fulfill({
    status: 200,
    json: [{ id: 'MCD001', name: '測試套餐', category: '超值全餐', price: 100, image: '' }],
  }));
  await page.route('**/api/checkout/confirm', route => route.fulfill({
    status: 200,
    json: {
      type: 'confirmed',
      order: { order_id: 'order-e2e', pickup_number: 123, session_id: 'e2e-kiosk' },
      replayed: false,
    },
  }));
  await page.goto('/kiosk');
  await expect(page.locator('#startSystemBtn')).toContainText('開始點餐');
  await page.locator('#startSystemBtn').click();
  await page.getByRole('button', { name: /超值全餐/ }).first().click();
  await page.locator('#menu-MCD001 .kiosk-add-btn').click();
  await expect(page.locator('#itemConfirmModal')).not.toHaveClass(/hidden/);
  await page.locator('#itemConfirmAdd').click();
  await expect(page.locator('#checkoutBtn')).toBeEnabled();
  await page.locator('#kioskCartBtn').click();
  await expect(page.locator('#checkoutBtn')).toBeVisible();
  await page.locator('#checkoutBtn').click();
  await expect(page.locator('#kioskPaymentScreen')).not.toHaveClass(/hidden/);
  await page.locator('#kioskCounterPayBtn').click();
  await expect(page.locator('#checkoutOverlay')).not.toHaveClass(/hidden/);
  await expect(page.locator('[data-pick-number]')).toHaveText('123');
  await expect(page.locator('#checkoutBtn')).toBeDisabled();
  expect(errors).toEqual([]);
});

test('Kiosk 快速結帳保留 15 秒失敗情境與人員通知，但不啟動情緒分析', async ({ page }) => {
  let paymentRequests = 0;
  let emotionRequests = 0;
  let checkoutRequests = 0;
  let staffRequest: Record<string, any> | null = null;
  await page.route('**/api/v1/payments/quick', async route => {
    paymentRequests += 1;
    await route.fulfill({ status: 200, json: { data: {
      status: 'captured', provider: 'fake_pos', provider_reference: 'pay-unexpected', amount: 100, currency: 'TWD',
    }, meta: { request_id: 'req_e2e', timestamp: new Date().toISOString() } } });
  });
  await page.route('**/api/emotion/analyze_event', async route => {
    emotionRequests += 1;
    await route.fulfill({ status: 500, json: { status: 'unexpected' } });
  });
  await page.route('**/api/interaction_event', async route => {
    const payload = route.request().postDataJSON();
    if (payload.event_type === 'payment_staff_requested') staffRequest = payload;
    await route.fulfill({ status: 200, json: { status: 'success' } });
  });
  await page.route('**/api/checkout', async route => {
    checkoutRequests += 1;
    await route.fulfill({ status: 200, json: { status: 'success', order_number: 999 } });
  });
  await openKioskPaymentScreen(page);

  await page.locator('#kioskFastPayBtn').click();
  await page.waitForTimeout(16_000);

  await expect(page.locator('#paymentCdFailed')).not.toHaveClass(/hidden/);
  await page.locator('#paymentCdAssistBtn').click();
  await expect(page.locator('#paymentCdNotified')).not.toHaveClass(/hidden/);
  await expect(page.locator('#paymentCdNotified')).toContainText('已通知店員');
  await expect.poll(() => staffRequest).not.toBeNull();
  expect(emotionRequests).toBe(0);
  expect((staffRequest as unknown as Record<string, any>).metadata).toEqual({});
  expect(paymentRequests).toBe(0);
  expect(checkoutRequests).toBe(0);
});

test('Admin requires a durable session before dashboard access', async ({ page }) => {
  const errors = observeCriticalBrowserFailures(page);
  let authenticated = false;
  await page.route('**/api/admin/auth/ui-config', route => route.fulfill({
    status: 200,
    json: { manager_login_identity: 'admin', manager_idle_timeout_sec: 1800 },
  }));
  await page.route('**/api/admin/auth/me', route => route.fulfill(
    authenticated
      ? { status: 200, json: { principal: { user_id: 'test', permissions: ['*'] } } }
      : { status: 401, json: { detail: 'authentication required' } },
  ));
  await page.route('**/api/admin/auth/login', async route => {
    authenticated = true;
    await route.fulfill({ status: 200, json: { principal: { user_id: 'test' } } });
  });
  await page.route('**/api/admin/auth/logout', route => route.fulfill({ status: 200, json: { status: 'success' } }));
  await page.route('**/api/menu', route => route.fulfill({ status: 200, json: [] }));
  await page.route('**/api/session_stats', route => route.fulfill({ status: 200, json: { status: 'success' } }));
  await page.goto('/admin');
  await expect(page.locator('#adminAuthBackdrop')).toBeVisible();
  await page.locator('#adminLoginPassword').fill('not-a-real-password');
  await page.locator('#adminAuthForm button[type="submit"]').click();
  await expect(page.locator('#adminAuthBackdrop')).toBeHidden();
  await expect(page.locator('#page-stats')).toBeVisible();
  await page.waitForTimeout(100);
  errors.length = 0; // The expected pre-login /me 401 is Chromium resource noise, not a page failure.
  const logout = await page.request.post('/api/admin/auth/logout');
  expect(logout.status()).toBe(200);
  expect(errors).toEqual([]);
});

test('Admin 收到付款協助通知時只顯示機台與處理指示', async ({ page }) => {
  await page.addInitScript(() => {
    class FakeWebSocket {
      static OPEN = 1;
      readyState = FakeWebSocket.OPEN;
      onopen: (() => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      onerror: ((error: Error) => void) | null = null;
      onclose: (() => void) | null = null;

      constructor() {
        (window as any).__adminTestSocket = this;
        window.setTimeout(() => this.onopen?.(), 0);
      }

      send() {}
      close() { this.onclose?.(); }
    }
    Object.defineProperty(window, 'WebSocket', { configurable: true, value: FakeWebSocket });
  });
  await page.route('**/api/admin/auth/me', route => route.fulfill({
    status: 200,
    json: { principal: { user_id: 'staff-001', permissions: ['operations.read'] } },
  }));
  await page.route('**/api/menu', route => route.fulfill({ status: 200, json: [] }));
  await page.route('**/api/session_stats', route => route.fulfill({ status: 200, json: { status: 'success' } }));
  await page.goto('/admin');

  await page.evaluate(() => {
    (window as any).__adminTestSocket.onmessage({ data: JSON.stringify({
      type: 'staff_notify',
      payload: {
        kiosk_name: '機台03',
        reason: 'payment_staff_requested',
      },
    }) });
  });

  await expect(page.locator('#staffNotifyBackdrop')).toHaveCSS('display', 'flex');
  await expect(page.locator('#staffNotifyKiosk')).toHaveText('機台03');
  await expect(page.locator('#staffNotifyReason')).toHaveText('人員協助付款');
  await expect(page.locator('#staffNotifyModal')).toContainText('請前往機台查看');
  await expect(page.locator('#staffNotifyModal')).not.toContainText('情緒分析');
});

test('一般員工可用中文精靈建立並發布活動', async ({ page }) => {
  const errors = observeCriticalBrowserFailures(page);
  let campaign: Record<string, any> | null = null;
  await page.setViewportSize({ width: 768, height: 900 });
  await page.route('**/api/admin/auth/me', route => route.fulfill({
    status: 200,
    json: { principal: { user_id: 'staff-001', permissions: ['operations.read', 'campaigns.read', 'campaigns.write', 'campaigns.publish'] } },
  }));
  await page.route('**/api/menu', route => route.fulfill({ status: 200, json: [{ id: 'fries', name: '薯條', category: '點心', price: 50 }] }));
  await page.route('**/api/session_stats', route => route.fulfill({ status: 200, json: { status: 'success' } }));
  await page.route('**/api/v1/campaigns/preview', async route => {
    const request = route.request().postDataJSON();
    await route.fulfill({ status: 200, json: { data: {
      valid: true, field_errors: [], conflicts: [], impact_count: request.placements.length,
      summary: `會影響 ${request.placements.length} 個顧客畫面。`,
      price_previews: [{ item_id: 'fries', item_name: '薯條', base_price: 50, effective_price: 30, savings: 20, conditional: false }],
    }, meta: { request_id: 'req_e2e', timestamp: new Date().toISOString() } } });
  });
  await page.route('**/api/v1/campaigns', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, json: { data: campaign ? [campaign] : [], meta: { request_id: 'req_e2e', timestamp: new Date().toISOString() } } });
      return;
    }
    const payload = route.request().postDataJSON();
    campaign = { campaign_id: 'cmp-e2e', version: 1, status: 'draft', payload: { ...payload, updated_by: 'staff-001' } };
    await route.fulfill({ status: 200, json: { data: campaign, meta: { request_id: 'req_e2e', timestamp: new Date().toISOString() } } });
  });
  await page.route('**/api/v1/campaigns/publish', async route => {
    const payload = route.request().postDataJSON();
    campaign = {
      campaign_id: 'cmp-e2e',
      version: (payload.expected_version || 0) + 3,
      status: 'active',
      payload: { ...payload, status: 'active', updated_by: 'staff-001' },
    };
    await route.fulfill({ status: 200, json: { data: campaign, meta: { request_id: 'req_e2e', timestamp: new Date().toISOString() } } });
  });
  await page.route('**/api/v1/campaigns/cmp-e2e/transition', async route => {
    const payload = route.request().postDataJSON();
    campaign = { ...campaign!, version: payload.expected_version + 1, status: payload.target_status, payload: { ...campaign!.payload, status: payload.target_status } };
    await route.fulfill({ status: 200, json: { data: campaign, meta: { request_id: 'req_e2e', timestamp: new Date().toISOString() } } });
  });

  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto('/admin');
  expect(await page.locator('#page-promotions-legacy').count()).toBe(0);
  expect(await page.evaluate(() => typeof (window as any).savePromotion)).toBe('undefined');
  await page.getByRole('button', { name: /活動管理/ }).click();
  await page.getByRole('button', { name: /建立活動/ }).click();
  const overflowMetrics = await page.locator('#page-promotions').evaluate(element => ({
    page: { clientWidth: element.clientWidth, scrollWidth: element.scrollWidth },
    offenders: [...element.querySelectorAll('*')].map(node => {
      const rect = node.getBoundingClientRect();
      return { tag: node.tagName, id: node.id, className: node.className, left: rect.left, right: rect.right, width: rect.width };
    }).filter(row => row.width > 0 && (row.left < 0 || row.right > window.innerWidth)).slice(0, 20),
  }));
  expect(overflowMetrics.page.scrollWidth).toBeLessThanOrEqual(overflowMetrics.page.clientWidth);
  expect(overflowMetrics.offenders).toEqual([]);
  await page.getByRole('button', { name: /3\. 顯示位置/ }).click();
  const placementOverflow = await page.locator('#page-promotions').evaluate(element => ({
    page: { clientWidth: element.clientWidth, scrollWidth: element.scrollWidth },
    offenders: [...element.querySelectorAll('*')].map(node => {
      const rect = node.getBoundingClientRect();
      return { tag: node.tagName, id: node.id, className: node.className, left: rect.left, right: rect.right, width: rect.width };
    }).filter(row => row.width > 0 && (row.left < 0 || row.right > window.innerWidth)).slice(0, 20),
  }));
  expect(placementOverflow.page.scrollWidth).toBeLessThanOrEqual(placementOverflow.page.clientWidth);
  expect(placementOverflow.offenders).toEqual([]);
  await page.getByRole('button', { name: /1\. 基本資料/ }).click();
  await page.locator('#campaignName').fill('夏日薯條優惠');
  await page.locator('#campaignStart').fill('2026-07-15T08:00');
  await page.getByRole('button', { name: /2\. 優惠內容/ }).click();
  await page.locator('#campaignItem').selectOption('fries');
  await page.locator('#campaignPrice').fill('30');
  await page.locator('#campaignPublishBtn').click();

  await expect(page.locator('#campaignWizard')).toBeHidden();
  await expect(page.locator('.campaign-announcement')).toContainText('「夏日薯條優惠」已發布');
  await expect(page.locator('#campaignList')).toContainText('夏日薯條優惠');
  await expect(page.locator('#campaignList')).toContainText('進行中');
  expect(errors).toEqual([]);
});
