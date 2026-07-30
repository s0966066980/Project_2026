import { describe, expect, it } from 'vitest';

import {
  assertVoiceTurnStreamEnded,
  consumeVoiceTurnEvent,
  createVoiceTurnProtocolState,
} from '../../kiosk/voiceTurnProtocol.js';

const event = (sequence: number, type: string, terminal = false, payload = {}) => ({
  voice_turn_id: 'turn-1', sequence, type, terminal, payload,
});

describe('voice turn streaming protocol', () => {
  it('accepts monotonic events and ignores an identical transport duplicate', () => {
    let state = createVoiceTurnProtocolState({ voiceTurnId: 'turn-1' });
    state = consumeVoiceTurnEvent(state, event(1, 'accepted')).state;
    const duplicate = consumeVoiceTurnEvent(state, event(1, 'accepted'));
    expect(duplicate.duplicate).toBe(true);
    state = consumeVoiceTurnEvent(state, event(2, 'completed', true)).state;
    expect(assertVoiceTurnStreamEnded(state).terminal).toBe(true);
  });

  it.each([
    ['gap', [event(2, 'transcribing')], 'voice_turn_sequence_gap'],
    ['unknown', [event(1, 'mystery')], 'unknown_voice_turn_event'],
  ])('rejects %s', (_name, events, code) => {
    let state = createVoiceTurnProtocolState({ voiceTurnId: 'turn-1' });
    expect(() => {
      for (const row of events) state = consumeVoiceTurnEvent(state, row).state;
    }).toThrow(code);
  });

  it('rejects conflicting duplicates, post-terminal events, and EOF without terminal', () => {
    let state = createVoiceTurnProtocolState({ voiceTurnId: 'turn-1' });
    state = consumeVoiceTurnEvent(state, event(1, 'accepted')).state;
    expect(() => consumeVoiceTurnEvent(state, event(1, 'accepted', false, { changed: true })))
      .toThrow('conflicting_voice_turn_duplicate');
    expect(() => assertVoiceTurnStreamEnded(state)).toThrow('voice_turn_eof_before_terminal');
    state = consumeVoiceTurnEvent(state, event(2, 'assistant_failed', true)).state;
    expect(() => consumeVoiceTurnEvent(state, event(3, 'completed', true)))
      .toThrow('voice_turn_event_after_terminal');
  });
});
