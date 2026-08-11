const CUSTOMER_PLACEHOLDER = '語音辨識中…';

/**
 * @typedef {{ role: 'customer'|'assistant', text: string, final?: boolean }} VoiceDialogueRow
 * @typedef {{ voiceTurnId: string, rows: VoiceDialogueRow[], seenSequences: Set<number> }} VoiceDialogueState
 */

/** @param {string} voiceTurnId @returns {VoiceDialogueState} */
export function createVoiceDialogueState(voiceTurnId) {
  return {
    voiceTurnId,
    rows: [],
    seenSequences: new Set(),
  };
}

/** @param {VoiceDialogueState} state @param {{ type: string, voice_turn_id?: string, sequence?: number, text?: string, final?: boolean }} event */
export function reduceVoiceDialogue(state, event) {
  if (!event || event.voice_turn_id !== state.voiceTurnId) return state;
  const sequence = event.sequence;
  if (typeof sequence === 'number' && Number.isInteger(sequence)) {
    if (state.seenSequences.has(sequence)) return state;
    state.seenSequences.add(sequence);
  }

  if (event.type === 'transcript') {
    const customer = state.rows.find((row) => row.role === 'customer');
    const text = String(event.text || '').trim() || CUSTOMER_PLACEHOLDER;
    if (customer) {
      customer.text = text;
      customer.final = Boolean(event.final);
    } else {
      state.rows.push({ role: 'customer', text, final: Boolean(event.final) });
    }
  }

  if (event.type === 'assistant_text') {
    if (!state.rows.some((row) => row.role === 'customer')) {
      state.rows.push({ role: 'customer', text: CUSTOMER_PLACEHOLDER, final: false });
    }
    const assistant = state.rows.find((row) => row.role === 'assistant');
    const text = String(event.text || '').trim();
    if (assistant) assistant.text = text;
    else state.rows.push({ role: 'assistant', text });
  }

  return state;
}
