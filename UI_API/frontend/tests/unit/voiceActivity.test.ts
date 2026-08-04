import { describe, expect, it } from 'vitest';

import { VoiceActivityState } from '../../kiosk/voiceActivity.js';

describe('VoiceActivityState', () => {
  it('submits after speech followed by 1.5 seconds of silence', () => {
    const state = new VoiceActivityState();
    expect(state.update(0.001, 0)).toBeNull();
    expect(state.update(0.08, 500)).toBeNull();
    expect(state.update(0.08, 650)).toBeNull();
    expect(state.update(0.001, 1000)).toBeNull();
    expect(state.update(0.001, 2149)).toBeNull();
    expect(state.update(0.001, 2150)).toBe('submit');
  });

  it('ends with no speech after eight seconds', () => {
    const state = new VoiceActivityState();
    expect(state.update(0.001, 0)).toBeNull();
    expect(state.update(0.001, 7999)).toBeNull();
    expect(state.update(0.001, 8000)).toBe('no_speech');
  });

  it('submits heard speech at the thirty second limit', () => {
    const state = new VoiceActivityState();
    state.update(0.001, 0);
    state.update(0.08, 100);
    state.update(0.08, 250);
    expect(state.update(0.08, 29999)).toBeNull();
    expect(state.update(0.08, 30000)).toBe('submit');
  });

  it('returns each terminal decision only once', () => {
    const state = new VoiceActivityState({ initialSpeechTimeoutMs: 10 });
    state.update(0, 0);
    expect(state.update(0, 10)).toBe('no_speech');
    expect(state.update(0, 20)).toBeNull();
  });
});
