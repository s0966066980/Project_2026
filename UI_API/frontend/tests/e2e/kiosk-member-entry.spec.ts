import { expect, test } from '@playwright/test';

async function disableOptionalKioskFeatures(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    localStorage.setItem('kiosk_feat_version', 'voice-emotion-20260721');
    localStorage.setItem('kiosk_feat', JSON.stringify({
      voiceAssist: false,
      recommend: false,
    }));
  });
}

async function enterPhone(page: import('@playwright/test').Page, phone = '0912345678') {
  for (const digit of phone) {
    await page.locator(`#memberKeypad [data-k="${digit}"]`).click();
  }
}

async function openMemberChoice(page: import('@playwright/test').Page) {
  await disableOptionalKioskFeatures(page);
  await page.route('**/api/public_settings', route => route.fulfill({
    status: 200,
    json: { MEMBER_ENABLED: true, EMOTION_LLAMA_ENABLED: false, DEMO_PUBLIC_MODE: false },
  }));
  await page.goto('/kiosk');
  await page.locator('#startSystemBtn').click();
  await expect(page.locator('#memberChoiceOverlay')).not.toHaveClass(/hidden/);
}

test('開始點餐後保留會員登入與訪客點餐兩段式入口', async ({ page }) => {
  await openMemberChoice(page);

  await expect(page.locator('#memberChoiceMember')).toContainText('會員點餐');
  await expect(page.locator('#memberChoiceGuest')).toContainText('直接點餐');
});

test('公開設定超過三秒未回應時仍顯示點餐方式', async ({ page }) => {
  await disableOptionalKioskFeatures(page);
  await page.route('**/api/public_settings', async route => {
    await new Promise(resolve => setTimeout(resolve, 3_500));
    await route.fulfill({ status: 200, json: { MEMBER_ENABLED: false } });
  });
  await page.goto('/kiosk');
  await page.locator('#startSystemBtn').click();

  await expect(page.locator('#memberChoiceOverlay')).not.toHaveClass(/hidden/, { timeout: 4_500 });
});

test('會員登入服務失敗時停留原頁並可改用訪客點餐', async ({ page }) => {
  await openMemberChoice(page);
  await page.route('**/api/member/login', route => route.fulfill({
    status: 503,
    json: { detail: 'temporarily unavailable' },
  }));

  await page.locator('#memberChoiceMember').click();
  await enterPhone(page);
  await page.locator('#memberLoginNext').click();

  await expect(page.locator('#memberLoginOverlay')).not.toHaveClass(/hidden/);
  await expect(page.locator('#memberLoginHint')).toContainText('登入服務暫時無法使用');
  await expect(page.locator('#memberLoginNext')).toHaveText('重試');
  await expect(page.locator('#memberLoginSkip')).toBeVisible();
});

test('會員註冊失敗時保留輸入內容並提供重試', async ({ page }) => {
  await openMemberChoice(page);
  await page.route('**/api/member/login', route => route.fulfill({
    status: 200,
    json: { found: false, member: null },
  }));
  await page.route('**/api/member/register', route => route.fulfill({
    status: 503,
    json: { detail: 'temporarily unavailable' },
  }));

  await page.locator('#memberChoiceMember').click();
  await enterPhone(page);
  await page.locator('#memberLoginNext').click();
  await expect(page.locator('#memberLoginRegister')).toBeVisible();
  await page.locator('#memberLoginRegister').click();
  await page.locator('#memberNicknameInput').fill('測試會員');
  await page.locator('#memberConsentInput').check();
  await page.locator('#memberRegisterDone').click();

  await expect(page.locator('#memberRegisterOverlay')).not.toHaveClass(/hidden/);
  await expect(page.locator('#memberRegisterHint')).toContainText('會員註冊尚未完成');
  await expect(page.locator('#memberNicknameInput')).toHaveValue('測試會員');
  await expect(page.locator('#memberConsentInput')).toBeChecked();
  await expect(page.locator('#memberRegisterDone')).toHaveText('重試註冊');
});

test('菜單初始化失敗時可原地重試或返回點餐方式', async ({ page }) => {
  let menuRequests = 0;
  await openMemberChoice(page);
  await page.route('**/api/menu', async route => {
    menuRequests += 1;
    if (menuRequests <= 2) {
      await route.abort('failed');
      return;
    }
    await route.fulfill({
      status: 200,
      json: [{ id: 'MCD001', name: '測試套餐', category: '超值全餐', price: 100, image: '' }],
    });
  });

  await page.locator('#memberChoiceGuest').click();
  await expect(page.locator('#menuLoadErrorOverlay')).not.toHaveClass(/hidden/);
  await expect(page.locator('#menuLoadRetry')).toBeVisible();
  await expect(page.locator('#menuLoadBack')).toBeVisible();

  await page.locator('#menuLoadBack').click();
  await expect(page.locator('#memberChoiceOverlay')).not.toHaveClass(/hidden/);
  await page.locator('#memberChoiceGuest').click();
  await expect(page.locator('#menuLoadErrorOverlay')).not.toHaveClass(/hidden/);

  await page.locator('#menuLoadRetry').click();
  await expect(page.locator('#menuLoadErrorOverlay')).toHaveClass(/hidden/);
  await expect(page.getByRole('button', { name: /超值全餐/ }).first()).toBeVisible();
});
