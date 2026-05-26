const { test, chromium } = require('playwright/test');
const http = require('http');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const uiDir = path.join(root, 'UI_API');
const outDir = path.join(root, 'reports', 'screenshots', 'pos_manual_verify');
const menu = JSON.parse(fs.readFileSync(path.join(uiDir, 'menu_data', 'menu.json'), 'utf8'));

function send(res, status, body, type = 'application/json') {
  res.writeHead(status, { 'Content-Type': type, 'Access-Control-Allow-Origin': '*' });
  res.end(body);
}

function serveFile(res, filePath) {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    send(res, 404, 'not found', 'text/plain');
    return;
  }
  const ext = path.extname(filePath).toLowerCase();
  const types = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
  };
  send(res, 200, fs.readFileSync(filePath), types[ext] || 'application/octet-stream');
}

function createMockServer() {
  return http.createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1:8765');
    if (req.method === 'OPTIONS') {
      send(res, 204, '');
      return;
    }
    if (url.pathname === '/' || url.pathname === '/pos') {
      serveFile(res, path.join(uiDir, 'index.html'));
      return;
    }
    if (url.pathname.startsWith('/static/')) {
      serveFile(res, path.join(uiDir, url.pathname));
      return;
    }
    if (url.pathname === '/api/public_settings') {
      send(res, 200, JSON.stringify({
        DEMO_PUBLIC_MODE: false,
        EVENT_TRIGGERED_MULTIMODAL_ENABLED: false,
        EMOTION_PERIODIC_ENABLED: false,
        RECOMMEND_INTERVAL_SEC: 999,
        RECOMMEND_AFTER_ASK_DELAY_MS: 1200,
        AUTO_RECOMMEND_MIN_GAP_SEC: 20,
        INTERACTION_TRIGGER_THRESHOLD: 99,
        USE_AI_RECOMMEND: true,
        VOICE_ASSIST_MODEL: 'qwen3.5:9b',
      }));
      return;
    }
    if (url.pathname === '/api/menu') {
      send(res, 200, JSON.stringify(menu));
      return;
    }
    if (url.pathname === '/api/interaction_event') {
      send(res, 200, JSON.stringify({ status: 'success', risk_result: { triggered: false, risk_score: 0 } }));
      return;
    }
    if (url.pathname === '/api/auto_recommend') {
      send(res, 200, JSON.stringify({ status: 'success', recommendation_ids: [], reason: '' }));
      return;
    }
    if (url.pathname === '/api/ask') {
      send(res, 200, JSON.stringify({
        status: 'success',
        detected_lang: 'zh',
        user_text: '我要薯條',
        ai_response: '已為您處理語音需求。',
        dialogue: { zh: { user_text: '我要薯條', ai_response: '已為您處理語音需求。' } },
        cart_actions: [],
        mentioned_ids: [],
      }));
      return;
    }
    send(res, 404, JSON.stringify({ status: 'not_found', path: url.pathname }));
  });
}

test('manual POS screenshot verification', async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const server = createMockServer();
  await new Promise(resolve => server.listen(8765, '127.0.0.1', resolve));
  const browser = await chromium.launch({
    headless: true,
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--no-sandbox'],
  });
  const context = await browser.newContext({
    viewport: { width: 1536, height: 864 },
    permissions: ['microphone', 'camera'],
  });
  const page = await context.newPage();
  const results = [];
  page.on('console', msg => {
    if (msg.type() === 'error') results.push(`console error: ${msg.text()}`);
  });
  page.on('pageerror', err => results.push(`pageerror: ${err.message}`));

  await page.goto('http://127.0.0.1:8765/pos', { waitUntil: 'networkidle' });
  await page.screenshot({ path: path.join(outDir, '01_startup.png'), fullPage: true });

  const startBox = await page.locator('#startSystemBtn').boundingBox();
  await page.mouse.move(startBox.x + startBox.width / 2, startBox.y + startBox.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(180);
  const pressing = await page.locator('#startupOverlay').evaluate(el => el.classList.contains('startup-pressing'));
  await page.screenshot({ path: path.join(outDir, '02_startup_pressed.png'), fullPage: true });
  await page.mouse.up();
  results.push(`startup_pressing_class=${pressing}`);

  await page.waitForFunction(() => document.querySelector('#startupOverlay')?.classList.contains('hidden'), null, { timeout: 10000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(outDir, '03_categories_voice_button.png'), fullPage: true });
  const voiceVisible = await page.locator('#mod-voice-assist').evaluate(el => !el.classList.contains('hidden') && getComputedStyle(el).display !== 'none');
  const voiceBox = await page.locator('#voiceAssistBtn').boundingBox();
  const cartBox = await page.locator('#kioskCartBtn').boundingBox();
  results.push(`voice_visible_on_categories=${voiceVisible}`);
  results.push(`voice_button_x=${Math.round(voiceBox.x)} cart_button_x=${Math.round(cartBox.x)} voice_left_of_cart=${voiceBox.x < cartBox.x}`);

  await page.locator('#kioskCartBtn').click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(outDir, '04_cart_voice_hidden.png'), fullPage: true });
  const voiceHiddenInCart = await page.locator('#mod-voice-assist').evaluate(el => el.classList.contains('hidden') || getComputedStyle(el).display === 'none');
  const operationBoxCount = await page.locator('#interactionInterventionBox').count();
  results.push(`voice_hidden_in_cart=${voiceHiddenInCart}`);
  results.push(`operation_assist_box_count=${operationBoxCount}`);

  await page.locator('#continueOrderBtn').click();
  await page.waitForTimeout(500);
  await page.locator('#voiceAssistBtn').click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(outDir, '05_voice_overlay_listening.png'), fullPage: true });
  const overlayVisible = await page.locator('#voiceAssistOverlay').evaluate(el => !el.classList.contains('hidden') && getComputedStyle(el).display !== 'none');
  const stopText = await page.locator('#voiceAssistStopText').innerText();
  results.push(`voice_overlay_visible=${overlayVisible}`);
  results.push(`voice_stop_text=${stopText}`);

  await page.locator('#voiceAssistStopBtn').dispatchEvent('pointerdown');
  await page.waitForTimeout(1600);
  await page.screenshot({ path: path.join(outDir, '06_voice_overlay_after_stop_processing_or_closed.png'), fullPage: true });
  const overlayHiddenAfterStop = await page.locator('#voiceAssistOverlay').evaluate(el => el.classList.contains('hidden') || getComputedStyle(el).display === 'none');
  results.push(`voice_overlay_hidden_after_stop=${overlayHiddenAfterStop}`);

  fs.writeFileSync(path.join(outDir, 'verification_results.txt'), `${results.join('\n')}\n`);
  await browser.close();
  server.close();
  console.log(results.join('\n'));
  console.log(`screenshots=${outDir}`);
});
