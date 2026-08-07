// @ts-check

/**
 * Play one TTS chunk and resolve only after the browser reports `ended`.
 * A rejected `play()` or media error is retried with the same provider output;
 * this helper never switches TTS providers.
 *
 * @param {{
 *   b64: string,
 *   format?: string,
 *   attempts?: number,
 *   createAudio?: (url: string) => HTMLAudioElement,
 * }} options
 */
export async function playVoiceAudioChunk({
  b64,
  format = 'wav',
  attempts = 2,
  createAudio = (url) => new Audio(url),
}) {
  if (!String(b64 || '').trim()) throw new Error('voice_audio_missing');
  const boundedAttempts = Math.max(1, Math.min(Number(attempts) || 1, 3));
  let lastError = new Error('voice_playback_failure');

  for (let attempt = 1; attempt <= boundedAttempts; attempt += 1) {
    try {
      await new Promise((resolve, reject) => {
        const audio = createAudio(`data:audio/${format};base64,${b64}`);
        let settled = false;
        const succeed = () => {
          if (settled) return;
          settled = true;
          resolve(undefined);
        };
        /** @param {unknown} error */
        const fail = (error) => {
          if (settled) return;
          settled = true;
          reject(error);
        };
        audio.onended = succeed;
        audio.onerror = () => fail(new Error('voice_audio_media_error'));
        Promise.resolve(audio.play()).catch(fail);
      });
      return { played: true, attempts: attempt };
    } catch (error) {
      lastError = error instanceof Error ? error : new Error('voice_playback_failure');
    }
  }
  throw lastError;
}
