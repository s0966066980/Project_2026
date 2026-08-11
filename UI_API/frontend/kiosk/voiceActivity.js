// @ts-check

const VAD_ASSET_PATH = '/static/node_modules/@ricky0123/vad-web/dist/';
const ONNX_WASM_PATH = '/static/node_modules/onnxruntime-web/dist/';

/**
 * Build the only supported kiosk speech detector: self-hosted Silero VAD v5.
 * There is deliberately no amplitude/RMS or manual-submit fallback. If the pinned
 * model or AudioWorklet cannot load, the caller must expose an unavailable state.
 *
 * @param {MediaStream} stream
 * @param {{
 *   onSpeechStart?: () => void,
 *   onSpeechEnd: (audio: Blob) => Promise<void> | void,
 *   onVADMisfire?: () => void,
 * }} callbacks
 */
export async function createSileroVoiceActivityDetector(stream, callbacks) {
  const audioTracks = stream?.getAudioTracks?.() || [];
  if (!audioTracks.length) throw new Error('silero_vad_audio_track_unavailable');
  const vadLibrary = globalThis.vad;
  if (!vadLibrary?.MicVAD || !vadLibrary?.utils?.encodeWAV) {
    throw new Error('silero_vad_v5_assets_unavailable');
  }

  let detector;
  detector = await vadLibrary.MicVAD.new({
    model: 'v5',
    baseAssetPath: VAD_ASSET_PATH,
    onnxWASMBasePath: ONNX_WASM_PATH,
    processorType: 'AudioWorklet',
    startOnLoad: false,
    redemptionMs: 1200,
    minSpeechMs: 250,
    preSpeechPadMs: 300,
    submitUserSpeechOnPause: true,
    getStream: async () => new MediaStream(audioTracks),
    pauseStream: async () => {},
    resumeStream: async () => new MediaStream(audioTracks),
    onSpeechStart: () => callbacks.onSpeechStart?.(),
    onSpeechRealStart: () => callbacks.onSpeechStart?.(),
    onVADMisfire: () => callbacks.onVADMisfire?.(),
    onSpeechEnd: async (audio) => {
      const wav = vadLibrary.utils.encodeWAV(audio, 1, 16000, 1, 16);
      await callbacks.onSpeechEnd(new Blob([wav], { type: 'audio/wav' }));
    },
  });
  return detector;
}
