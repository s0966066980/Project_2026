import { expect, test } from '@playwright/test';

test('health and kiosk entry remain reachable through the browser surface', async ({ page, request }) => {
  const health = await request.get('/live');
  expect(health.ok()).toBeTruthy();

  await page.goto('/kiosk');
  await expect(page.locator('body')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('Emotion-LLaMA');
  await expect(page).toHaveTitle(/點餐|Kiosk|Project/i);
});

