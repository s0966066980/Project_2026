import { expect, test } from '@playwright/test';

function observeCriticalBrowserFailures(page: import('@playwright/test').Page) {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  return errors;
}

test('Kiosk preserves start, menu, cart and checkout navigation contracts', async ({ page }) => {
  const errors = observeCriticalBrowserFailures(page);
  await page.addInitScript(() => {
    localStorage.setItem('kiosk_feat_version', 'event-triggered-20260519');
    localStorage.setItem('kiosk_feat', JSON.stringify({
      emotion: false,
      voiceAssist: false,
      recommend: false,
      eventTriggeredMultimodal: false,
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
  await page.route('**/api/checkout', route => route.fulfill({
    status: 200,
    json: { status: 'success', order_number: 123, session_id: 'e2e-kiosk' },
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

test('Admin preserves login, dashboard and logout request contracts', async ({ page }) => {
  const errors = observeCriticalBrowserFailures(page);
  let authenticated = false;
  await page.route('**/api/admin/auth/me', route => route.fulfill(
    authenticated
      ? { status: 200, json: { principal: { user_id: 'test' } } }
      : { status: 401, json: { detail: 'authentication required' } },
  ));
  await page.route('**/api/admin/auth/login', async route => {
    authenticated = true;
    await route.fulfill({ status: 200, json: { principal: { user_id: 'test' } } });
  });
  await page.route('**/api/menu', route => route.fulfill({ status: 200, json: [] }));
  await page.route('**/api/session_stats', route => route.fulfill({ status: 200, json: { status: 'success' } }));
  await page.goto('/admin');
  await expect(page.locator('#adminAuthBackdrop')).toBeVisible();
  await page.locator('#adminLoginIdentity').fill('e2e-admin');
  await page.locator('#adminLoginPassword').fill('not-a-real-password');
  await page.locator('#adminAuthForm button[type="submit"]').click();
  await expect(page.locator('#adminAuthBackdrop')).toBeHidden();
  await expect(page.locator('#page-stats')).toBeVisible();
  errors.length = 0; // The expected pre-login /me 401 is Chromium resource noise, not a page failure.
  const logout = await page.request.post('/api/admin/auth/logout');
  expect(logout.status()).toBe(200);
  expect(errors).toEqual([]);
});
