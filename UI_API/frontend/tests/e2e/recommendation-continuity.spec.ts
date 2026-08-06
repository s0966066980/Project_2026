import { expect, test } from '@playwright/test';

// The unit tests cover the eligibility and refresh rules as pure functions. What they
// cannot show is whether app.js actually keeps the surface populated when the
// recommendation API is down, or whether the placeholder it falls back to leaks into
// commercial evidence. Both are P0 gate conditions, so they are checked here against
// the running Docker stack.

async function enterMenuAsGuest(page: import('@playwright/test').Page) {
  await page.goto('/kiosk');
  await page.click('#startSystemBtn');
  await page.click('#memberChoiceGuest');
  await expect(page.locator('#aiPushBar')).toBeVisible();
}

test('the recommendation surface stays populated and retryable when the API fails', async ({ page }) => {
  await page.route('**/api/ai_push', (route) => route.fulfill({
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ error: 'recommendation_unavailable' }),
  }));

  await enterMenuAsGuest(page);

  // Long enough for the refresh timer to fire against the failing API more than once.
  await page.waitForTimeout(6000);

  const bar = page.locator('#aiPushBar');
  await expect(bar).toBeVisible();
  await expect(bar).not.toHaveClass(/hidden/);
  await expect(bar).not.toHaveClass(/loading/);
  await expect(page.locator('#aiPushItemName')).not.toBeEmpty();
  await expect(page.locator('#aiPushText')).not.toBeEmpty();
  await expect(page.locator('#aiPushRefreshBtn')).toBeEnabled();
});

test('a placeholder recommendation never becomes commercial evidence', async ({ page }) => {
  const commercialTouches: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/commercial-touches')) {
      commercialTouches.push(String(request.postData() || ''));
    }
  });
  await page.route('**/api/ai_push', (route) => route.fulfill({
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ error: 'recommendation_unavailable' }),
  }));

  await enterMenuAsGuest(page);

  // The impression observer needs the bar visible past its dwell time; this waits well
  // beyond it so an absent touch means suppressed rather than merely not yet sent.
  await page.waitForTimeout(6000);
  await expect(page.locator('#aiPushItemName')).not.toBeEmpty();

  expect(commercialTouches, 'the kiosk chose this item itself; no server decision authored it').toEqual([]);
});

test('a server-authored recommendation still reports its impression', async ({ page }) => {
  const commercialTouches: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/commercial-touches')) {
      commercialTouches.push(String(request.postData() || ''));
    }
  });

  await enterMenuAsGuest(page);
  await page.waitForTimeout(6000);

  expect(commercialTouches.length, 'suppressing placeholders must not suppress real recommendations').toBeGreaterThan(0);
  expect(commercialTouches.some((body) => /"decision_id":\s*"[^"]+"/.test(body))).toBe(true);
});
