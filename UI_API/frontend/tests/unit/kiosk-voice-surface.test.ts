import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const frontendRoot = resolve(import.meta.dirname, '../..');
const read = (path: string) => readFileSync(resolve(frontendRoot, path), 'utf8');

describe('kiosk open-speech voice surface', () => {
  it('removes guest bypasses from member login and registration', () => {
    const html = read('kiosk/index.html');
    const member = read('kiosk/member.js');

    expect(html).toContain('id="memberChoiceGuest"');
    expect(html).not.toContain('id="memberLoginSkip"');
    expect(html).not.toContain('id="memberRegisterSkip"');
    expect(member).not.toContain('memberLoginSkip');
    expect(member).not.toContain('memberRegisterSkip');
  });

  it('pins Silero VAD v5 and has no RMS or manual-submit fallback', () => {
    const voice = read('kiosk/voice.js');
    const activity = read('kiosk/voiceActivity.js');

    expect(activity).toContain('model: \'v5\'');
    expect(activity).toContain('redemptionMs: 1200');
    expect(activity).toContain('minSpeechMs: 250');
    expect(activity).toContain('processorType: \'AudioWorklet\'');
    expect(activity).not.toContain('minimumSpeechRms');
    expect(activity).not.toContain('createAnalyser');
    expect(voice).not.toContain('manual_submit');
    expect(voice).not.toContain('pausePassiveListener');
  });

  it('renders the transcript before the assistant result', () => {
    const voice = read('kiosk/voice.js');
    const transcriptHandler = voice.indexOf('onTranscript(data)');
    const assistantHandler = voice.indexOf('onAssistantText(data)');

    expect(transcriptHandler).toBeGreaterThan(-1);
    expect(assistantHandler).toBeGreaterThan(transcriptHandler);
  });

  it('checks emotion readiness before requesting a periodic-analysis camera', () => {
    const app = read('kiosk/app.js');
    const api = read('shared/apiClient.js');
    const periodicStart = app.indexOf('function startPeriodicEmotionAnalysis');
    const readinessCheck = app.indexOf('await api.getEmotionReadiness()', periodicStart);
    const cameraRequest = app.indexOf('await ensureMediaTracks({ video: true })', periodicStart);

    expect(api).toContain('/api/emotion/readiness');
    expect(readinessCheck).toBeGreaterThan(periodicStart);
    expect(cameraRequest).toBeGreaterThan(readinessCheck);
    expect(app).toContain('ensureMediaTracks({ video: false, audio: needAudio })');
    expect(app).not.toContain('periodicEmotionTimer = setInterval');
  });
});
