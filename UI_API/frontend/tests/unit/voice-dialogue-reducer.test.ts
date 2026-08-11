import { describe, expect, it } from 'vitest';

import {
  createVoiceDialogueState,
  reduceVoiceDialogue,
} from '../../kiosk/voiceDialogueReducer.js';

describe('voice dialogue display order', () => {
  it('creates the customer placeholder before an assistant event and replaces it with final text', () => {
    let state: ReturnType<typeof createVoiceDialogueState> = createVoiceDialogueState('turn-1');

    state = reduceVoiceDialogue(state, {
      type: 'assistant_text',
      voice_turn_id: 'turn-1',
      sequence: 2,
      text: '您好，請問需要什麼？',
    });
    expect(state.rows.map((row) => row.role)).toEqual(['customer', 'assistant']);
    expect(state.rows[0]?.text).toBe('語音辨識中…');

    state = reduceVoiceDialogue(state, {
      type: 'transcript',
      voice_turn_id: 'turn-1',
      sequence: 3,
      text: '我要一杯拿鐵',
      final: false,
    });
    expect(state.rows.map((row) => row.text)).toEqual(['我要一杯拿鐵', '您好，請問需要什麼？']);

    state = reduceVoiceDialogue(state, {
      type: 'transcript',
      voice_turn_id: 'turn-1',
      sequence: 4,
      text: '我要一杯拿鐵，少冰',
      final: true,
    });
    expect(state.rows.map((row) => row.text)).toEqual(['我要一杯拿鐵，少冰', '您好，請問需要什麼？']);
  });

  it('ignores duplicate and late events from another or already-seen turn', () => {
    let state: ReturnType<typeof createVoiceDialogueState> = createVoiceDialogueState('turn-2');

    state = reduceVoiceDialogue(state, {
      type: 'transcript',
      voice_turn_id: 'turn-2',
      sequence: 1,
      text: '我要熱美式',
      final: false,
    });
    state = reduceVoiceDialogue(state, {
      type: 'transcript',
      voice_turn_id: 'turn-2',
      sequence: 1,
      text: '舊內容不應覆寫',
      final: true,
    });
    state = reduceVoiceDialogue(state, {
      type: 'transcript',
      voice_turn_id: 'turn-1',
      sequence: 2,
      text: '另一回合',
      final: true,
    });

    expect(state.rows).toEqual([{ role: 'customer', text: '我要熱美式', final: false }]);
  });
});
