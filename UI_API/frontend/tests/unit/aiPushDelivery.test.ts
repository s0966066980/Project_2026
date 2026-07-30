import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchJson, postFormJson } from '../../shared/httpClient.js';

const kioskApp = readFileSync(fileURLToPath(new URL('../../kiosk/app.js', import.meta.url)), 'utf8');

afterEach(() => {
  vi.unstubAllGlobals();
});

/** @param {number} status @param {unknown} body */
function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('httpClient 錯誤處理', () => {
  it('2xx 回傳解析後的 JSON', async () => {
    stubFetch(200, { recommendation_id: 'MCD001', push_text: 'LLM 文案' });
    await expect(fetchJson('/api/ai_push')).resolves.toEqual({
      recommendation_id: 'MCD001',
      push_text: 'LLM 文案',
    });
  });

  it('未授權時丟出例外，不把錯誤內文當成正常結果', async () => {
    stubFetch(401, { detail: 'kiosk token required' });
    await expect(postFormJson('/api/ai_push', new FormData())).rejects.toThrow('kiosk token required');
  });

  it('非 JSON 的錯誤回應退回狀態碼', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 502,
      json: async () => {
        throw new Error('not json');
      },
    }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchJson('/api/ai_push')).rejects.toThrow('HTTP 502');
  });
});

describe('AI 推播採用後端結果', () => {
  const fetchBlock = () => kioskApp.slice(
    kioskApp.indexOf('async function fetchRecommendation('),
    kioskApp.indexOf('function scheduleRecommendationRefresh('),
  );

  it('後端回傳的品項一律採用，不因與目前顯示相同而丟棄推薦詞', () => {
    const block = fetchBlock();

    // 舊行為：品項與目前顯示相同就改用本地隨機備選，導致後端推薦詞被丟棄。
    expect(block).not.toContain('!== currentRecommendationItem?.id');
    expect(block).toContain('renderRecommendation(next.item, next.pushText, next.recommendation)');
    // 沒有可用的品項時，文案也必須換成本地文案，不能沿用別的品項的推薦詞。
    expect(block).toContain("source: 'local_fallback'");
  });

  it('換一個累積排除本次已看過的品項，避免按兩下就轉回第一項', () => {
    expect(kioskApp).toContain('seenRecommendationIds.add(item.id)');
    expect(kioskApp).toContain('return [...seenRecommendationIds]');
  });

  it('已看過清單與預取候選在 stop() 時清空，不會延續到下一位顧客', () => {
    const stopBlock = kioskApp.slice(kioskApp.indexOf('function stop() {'), kioskApp.indexOf('function hide() {'));
    expect(stopBlock).toContain('seenRecommendationIds.clear()');
    expect(stopBlock).toContain('prefetchedRecommendations = []');
  });

  it('已有預取候選時直接換上，不再等待後端', () => {
    const block = fetchBlock();
    expect(block).toContain('prefetchedRecommendations.shift()');
    expect(block).toContain('renderRecommendation(ready.item, ready.pushText, ready.recommendation)');
  });

  it('刷新間隔取自設定而非寫死的 15 秒', () => {
    expect(kioskApp).toContain('Number(runtimeSettings.AI_PUSH_REFRESH_SEC)');
    expect(kioskApp).not.toContain('RECOMMENDATION_REFRESH_DELAY_MS');
  });

  it('推播欄不再有語音模式按鈕（語音入口改由底部常駐按鈕負責）', () => {
    expect(kioskApp).not.toContain('aiPushVoiceBtn');
  });
});
