import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { formatAliasText, mismatchMessage, parseAliasText } from '../../admin/modules/settingsAdmin.js';

const frontendRoot = resolve(__dirname, '../..');
const adminHtml = readFileSync(resolve(frontendRoot, 'admin/admin.html'), 'utf8');
const settingsModule = readFileSync(resolve(frontendRoot, 'admin/modules/settingsAdmin.js'), 'utf8');

describe('設定頁分頁結構', () => {
  it('八個分頁各自有面板，可寫入的分頁另有獨立儲存按鈕與未儲存標記', () => {
    ['ai', 'push', 'copy', 'voice', 'prompt', 'goal', 'diagnostic', 'history'].forEach(tab => {
      expect(adminHtml).toContain(`data-settings-tab="${tab}"`);
      expect(adminHtml).toContain(`data-settings-panel="${tab}"`);
    });
    // 推薦詞管理逐項儲存、模型診斷與變更歷史不寫設定，因此沒有分頁層級的儲存按鈕。
    ['ai', 'push', 'voice', 'prompt', 'goal'].forEach(tab => {
      expect(adminHtml).toContain(`data-settings-save="${tab}"`);
    });
    ['copy', 'diagnostic', 'history'].forEach(tab => {
      expect(adminHtml).not.toContain(`data-settings-save="${tab}"`);
    });
    expect(adminHtml.match(/class="settings-unsaved"/g)).toHaveLength(5);
  });

  it('推播規則與推薦詞管理不共用設定鍵，避免互相覆寫', () => {
    // AI_PUSH_TEXT_MIN/MAX 由「AI 推播規則」擁有，不可再留在「系統指令」的 payload 裡。
    const pushKeys = settingsModule.slice(settingsModule.indexOf('push: ['), settingsModule.indexOf('voice: ['));
    const promptKeys = settingsModule.slice(settingsModule.indexOf('prompt: ['), settingsModule.indexOf('goal: ['));
    expect(pushKeys).toContain('AI_PUSH_TEXT_MIN');
    expect(promptKeys).not.toContain('AI_PUSH_TEXT_MIN');
    expect(pushKeys).toContain('AI_PUSH_SCOPE_MODE');
    expect(pushKeys).toContain('AI_PUSH_REFRESH_SEC');
  });

  it('金鑰欄位已從設定頁移除，改由環境變數提供', () => {
    expect(adminHtml).not.toContain('inp-stt-api-key');
    expect(adminHtml).not.toContain('inp-tts-api-key');
    expect(adminHtml).not.toContain('inp-openai-base-url');
    expect(settingsModule).not.toContain('API_KEY');
    expect(adminHtml).toContain('NVIDIA_API_BASE_URL');
    expect(adminHtml).toContain('NVIDIA_API_KEY');
  });

  it('雲端提供者固定為 NVIDIA NIM，不再是可選分頁', () => {
    expect(adminHtml).toContain('id="inp-llm-policy"');
    expect(adminHtml).toContain('value="local_only"');
    expect(adminHtml).toContain('value="cloud_first"');
    expect(adminHtml).not.toContain('onAiProviderChange');
    expect(adminHtml).not.toContain('id="inp-llm-cloud"');
    expect(adminHtml).not.toContain('data-cloud-fields');
    expect(adminHtml).toContain('id="inp-nim-model"');
    expect(adminHtml).toContain('id="inp-nim-voice-model"');
    expect(adminHtml).not.toMatch(/gemini|Gemini|GEMINI/);
    expect(adminHtml).not.toContain('inp-openai-model');
    expect(adminHtml).not.toContain('inp-openai-voice-model');
    expect(adminHtml).not.toContain('OPENAI_MODEL_NAME');
    expect(adminHtml).not.toContain('data-provider="openai"');
    expect(adminHtml).toContain('data-provider="nvidia_nim"');
  });

  it('保留連線測試、就緒指示與實際生效狀態列', () => {
    expect(adminHtml).toContain('id="llmTestBtn"');
    expect(adminHtml).toContain('id="llmLocalReady"');
    expect(adminHtml).toContain('id="llmCloudReady"');
    expect(adminHtml).toContain('id="llmTrafficStats"');
  });
});

describe('設定與實際流量不一致提示', () => {
  it('偏好雲端但雲端零次時提示檢查連線', () => {
    expect(mismatchMessage('cloud_first', { ollama: 142 })).toContain('測試連線');
  });

  it('僅本機卻有雲端請求時提示立即確認', () => {
    expect(mismatchMessage('local_only', { ollama: 10, nvidia_nim: 3 })).toContain('僅本機');
  });

  it('尚無任何請求時不提示', () => {
    expect(mismatchMessage('cloud_first', {})).toBe('');
  });

  it('設定與實際一致時不提示', () => {
    expect(mismatchMessage('local_first', { ollama: 100 })).toBe('');
  });
});

describe('品項口語別名格式', () => {
  it('可在文字與物件之間往返', () => {
    const parsed = parseAliasText('MCD003 = 魚堡, 魚排堡\nMCD001 = 大麥');
    expect(parsed).toEqual({ MCD003: ['魚堡', '魚排堡'], MCD001: ['大麥'] });
    expect(parseAliasText(formatAliasText(parsed))).toEqual(parsed);
  });

  it('忽略沒有別名或沒有品項 ID 的行', () => {
    expect(parseAliasText('壞掉的行\nMCD003 =\n = 魚堡')).toEqual({});
  });
});
