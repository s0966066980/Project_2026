import { describe, expect, it, vi } from 'vitest';

import { playVoiceAudioChunk } from '../../kiosk/voicePlayback.js';

describe('voice playback completion contract', () => {
  it('completes only after the audio ended event', async () => {
    let audio: any;
    const pending = playVoiceAudioChunk({
      b64: 'd2F2',
      createAudio: vi.fn(() => {
        audio = { play: vi.fn(() => Promise.resolve()), onended: null, onerror: null };
        return audio;
      }),
    });
    let settled = false;
    pending.finally(() => { settled = true; });
    await Promise.resolve();
    expect(settled).toBe(false);
    audio.onended();
    await expect(pending).resolves.toEqual({ played: true, attempts: 1 });
  });

  it('uses a bounded retry and fails when playback never starts', async () => {
    const createAudio = vi.fn(() => ({
      play: vi.fn(() => Promise.reject(new Error('blocked'))),
      onended: null,
      onerror: null,
    } as any));

    await expect(playVoiceAudioChunk({ b64: 'd2F2', attempts: 2, createAudio })).rejects.toThrow('blocked');
    expect(createAudio).toHaveBeenCalledTimes(2);
  });
});
