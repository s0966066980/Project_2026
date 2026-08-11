import { describe, expect, it, vi } from 'vitest';

import {
  classifyEmotionMediaError,
  createEmotionSectionLoader,
  describeEmotionApiError,
} from '../../admin/modules/emotionConsoleAdmin.js';

describe('emotion console section isolation', () => {
  it('keeps successful sections ready when another section fails', async () => {
    const states: Array<[string, { status: string; data?: unknown; message?: string }]> = [];
    const loader = createEmotionSectionLoader({
      requests: {
        settings: vi.fn(async () => ({ EMOTION_CAPTURE_MODE: 'voice_only' })),
        model: vi.fn(async () => { throw Object.assign(new Error('unavailable'), { status: 503 }); }),
        records: vi.fn(async () => ({ records: [] })),
      },
      onState: (section, state) => { states.push([section, state]); },
    });

    await loader.refreshAll();

    expect(states).toContainEqual(['settings', expect.objectContaining({ status: 'ready' })]);
    expect(states).toContainEqual(['records', expect.objectContaining({ status: 'ready' })]);
    expect(states).toContainEqual(['model', expect.objectContaining({ status: 'error', message: expect.stringContaining('模型服務') })]);
  });

  it('maps actionable API failures and keeps the request id', () => {
    expect(describeEmotionApiError({ status: 401 })).toContain('裝置');
    expect(describeEmotionApiError({ status: 422 })).toContain('格式');
    expect(describeEmotionApiError({ status: 503 })).toContain('模型服務');
    expect(describeEmotionApiError({ status: 500, requestId: 'req-42' })).toContain('req-42');
  });

  it('distinguishes camera, microphone, browser and empty-media failures', () => {
    expect(classifyEmotionMediaError({ name: 'NotAllowedError' }, 'camera')).toContain('攝影機');
    expect(classifyEmotionMediaError({ name: 'NotFoundError' }, 'microphone')).toContain('麥克風');
    expect(classifyEmotionMediaError({ name: 'NotSupportedError' }, 'recorder')).toContain('瀏覽器');
    expect(classifyEmotionMediaError({ name: 'EmptyMediaError' }, 'media')).toContain('沒有可分析');
  });
});
