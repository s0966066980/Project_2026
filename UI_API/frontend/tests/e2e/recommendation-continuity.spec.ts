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

// Recommendation events are the second reporting channel. They are not suppressed for
// placeholders — that would leave later add-to-cart and checkout events with no source
// record — so operational reporting excludes them by source instead (ADR-0054), which
// only works if every placeholder event is actually labelled as one.
test('placeholder recommendation events are labelled as locally chosen', async ({ page }) => {
  const sources: string[] = [];
  page.on('request', (request) => {
    if (!request.url().includes('/api/recommendation_events')) return;
    const body = String(request.postData() || '');
    sources.push(String(JSON.parse(body || '{}').source || ''));
  });
  await page.route('**/api/ai_push', (route) => route.fulfill({
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ error: 'recommendation_unavailable' }),
  }));

  await enterMenuAsGuest(page);
  await page.waitForTimeout(6000);

  expect(sources.length, 'the kiosk should still report what it displayed').toBeGreaterThan(0);
  expect(sources.every((source) => ['local_default', 'local_fallback'].includes(source))).toBe(true);
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
