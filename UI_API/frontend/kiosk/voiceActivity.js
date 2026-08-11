// @ts-check

/** @typedef {'submit' | 'no_speech'} VoiceActivityDecision */
/**
 * @typedef {object} VoiceActivityOptions
 * @property {number} silenceMs
 * @property {number} initialSpeechTimeoutMs
 * @property {number} maxDurationMs
 * @property {number} speechStartMs
 * @property {number} minimumSpeechRms
 * @property {number} noiseMultiplier
 */

const DEFAULTS = Object.freeze({
  silenceMs: 1500,
  initialSpeechTimeoutMs: 8000,
  maxDurationMs: 30000,
  speechStartMs: 120,
  minimumSpeechRms: 0.018,
  noiseMultiplier: 2.8,
});

export class VoiceActivityState {
  /** @param {Partial<VoiceActivityOptions>} [options] */
  constructor(options = {}) {
    this.options = { ...DEFAULTS, ...options };
    this.startedAt = null;
    this.speechCandidateAt = null;
    this.lastSpeechAt = null;
    this.heardSpeech = false;
    this.noiseFloor = 0.006;
    this.finished = false;
  }

  /** @param {number} rms @param {number} now @returns {VoiceActivityDecision | null} */
  update(rms, now) {
    if (this.finished) return null;
    if (this.startedAt === null) this.startedAt = now;

    const elapsed = now - this.startedAt;
    if (elapsed >= this.options.maxDurationMs) {
      this.finished = true;
      return this.heardSpeech ? 'submit' : 'no_speech';
    }

    const level = Number.isFinite(rms) ? Math.max(0, rms) : 0;
    const threshold = Math.max(
      this.options.minimumSpeechRms,
      this.noiseFloor * this.options.noiseMultiplier,
    );
    const active = level >= threshold;

    if (!this.heardSpeech) {
      if (!active) {
        this.noiseFloor = (this.noiseFloor * 0.92) + (level * 0.08);
        this.speechCandidateAt = null;
      } else if (this.speechCandidateAt === null) {
        this.speechCandidateAt = now;
      } else if (now - this.speechCandidateAt >= this.options.speechStartMs) {
        this.heardSpeech = true;
        this.lastSpeechAt = now;
      }

      if (!this.heardSpeech && elapsed >= this.options.initialSpeechTimeoutMs) {
        this.finished = true;
        return 'no_speech';
      }
      return null;
    }

    if (active) {
      this.lastSpeechAt = now;
      return null;
    }
    if (this.lastSpeechAt !== null && now - this.lastSpeechAt >= this.options.silenceMs) {
      this.finished = true;
      return 'submit';
    }
    return null;
  }
}

/** @param {Uint8Array<ArrayBuffer>} samples */
function calculateRms(samples) {
  let sum = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const normalized = ((samples[index] ?? 128) - 128) / 128;
    sum += normalized * normalized;
  }
  return Math.sqrt(sum / samples.length);
}

/**
 * @param {MediaStream} stream
 * @param {(decision: VoiceActivityDecision) => void} onDecision
 * @param {Partial<VoiceActivityOptions>} [options]
 */
export function startVoiceActivityMonitor(stream, onDecision, options = {}) {
  const audioTracks = stream?.getAudioTracks?.() || [];
  if (!audioTracks.length) throw new Error('No audio track available for voice activity detection.');

  const AudioContextConstructor = window.AudioContext;
  if (!AudioContextConstructor) throw new Error('Web Audio API is unavailable.');

  const context = new AudioContextConstructor();
  const audioStream = new MediaStream(audioTracks);
  const source = context.createMediaStreamSource(audioStream);
  const analyser = context.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0.2;
  source.connect(analyser);
  const samples = new Uint8Array(analyser.fftSize);
  const state = new VoiceActivityState(options);
  let frameId = 0;
  let stopped = false;

  const stop = () => {
    if (stopped) return;
    stopped = true;
    if (frameId) cancelAnimationFrame(frameId);
    source.disconnect();
    analyser.disconnect();
    void context.close();
  };

  /** @param {number} now */
  const sample = (now) => {
    if (stopped) return;
    analyser.getByteTimeDomainData(samples);
    const decision = state.update(calculateRms(samples), now);
    if (decision) {
      stop();
      onDecision(decision);
      return;
    }
    frameId = requestAnimationFrame(sample);
  };

  void context.resume();
  frameId = requestAnimationFrame(sample);
  return { stop, state };
}
