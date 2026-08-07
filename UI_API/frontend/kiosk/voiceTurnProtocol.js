// @ts-check

/** @typedef {import('../types.d.ts').VoiceTurnEvent} VoiceTurnEvent */
/** @typedef {import('../types.d.ts').VoiceTurnEventCandidate} VoiceTurnEventCandidate */
/** @typedef {import('../types.d.ts').VoiceTurnEventType} VoiceTurnEventType */
/** @typedef {import('../types.d.ts').VoiceTurnProtocolState} VoiceTurnProtocolState */

/** @type {ReadonlySet<VoiceTurnEventType>} */
const KNOWN_EVENT_TYPES = new Set([
  'accepted',
  'transcribing',
  'transcript',
  'assistant_result',
  'completed',
  'transcription_failed',
  'assistant_failed',
  'playback_failed',
]);

/** @param {VoiceTurnEvent} event */
function signature(event) {
  return JSON.stringify({
    voice_turn_id: event.voice_turn_id,
    sequence: event.sequence,
    type: event.type,
    payload: event.payload,
    terminal: event.terminal,
  });
}

/**
 * @param {{voiceTurnId: string, lastAcknowledgedSequence?: number}} options
 * @returns {VoiceTurnProtocolState}
 */
export function createVoiceTurnProtocolState({ voiceTurnId, lastAcknowledgedSequence = 0 }) {
  return {
    voiceTurnId,
    lastAcknowledgedSequence,
    terminal: false,
    signatures: new Map(),
  };
}

/**
 * @param {VoiceTurnProtocolState} state
 * @param {VoiceTurnEventCandidate} event
 * @returns {{state: VoiceTurnProtocolState, duplicate: boolean, event: VoiceTurnEvent}}
 */
export function consumeVoiceTurnEvent(state, event) {
  if (event.voice_turn_id !== state.voiceTurnId) {
    throw new Error('voice_turn_identity_mismatch');
  }
  if (typeof event.sequence !== 'number' || !Number.isInteger(event.sequence) || event.sequence < 1) {
    throw new Error('invalid_voice_turn_sequence');
  }
  if (typeof event.type !== 'string' || !KNOWN_EVENT_TYPES.has(/** @type {VoiceTurnEventType} */ (event.type))) {
    throw new Error('unknown_voice_turn_event');
  }
  if (!event.payload || typeof event.payload !== 'object' || Array.isArray(event.payload) || typeof event.terminal !== 'boolean') {
    throw new Error('invalid_voice_turn_event');
  }
  const verifiedEvent = /** @type {VoiceTurnEvent} */ (event);
  const currentSignature = signature(verifiedEvent);
  const previousSignature = state.signatures.get(verifiedEvent.sequence);
  if (previousSignature) {
    if (previousSignature !== currentSignature) throw new Error('conflicting_voice_turn_duplicate');
    return { state, duplicate: true, event: verifiedEvent };
  }
  if (state.terminal) throw new Error('voice_turn_event_after_terminal');
  const expected = state.lastAcknowledgedSequence + 1;
  if (verifiedEvent.sequence !== expected) throw new Error('voice_turn_sequence_gap');
  /** @type {VoiceTurnProtocolState} */
  const next = {
    ...state,
    lastAcknowledgedSequence: verifiedEvent.sequence,
    terminal: verifiedEvent.terminal,
    signatures: new Map(state.signatures).set(verifiedEvent.sequence, currentSignature),
  };
  return { state: next, duplicate: false, event: verifiedEvent };
}

/** @param {VoiceTurnProtocolState} state @returns {VoiceTurnProtocolState} */
export function assertVoiceTurnStreamEnded(state) {
  if (!state.terminal) throw new Error('voice_turn_eof_before_terminal');
  return state;
}
