let rollingRecorder = null;
let rollingChunks = [];
let rollingMaxSec = 5;
let rollingStream = null;
let captureInFlight = false;

function safeStopRecorder(recorder) {
  try {
    if (recorder && recorder.state === 'recording') recorder.stop();
  } catch { }
}

function recorderMimeType() {
  const candidates = [
    'video/webm;codecs=vp8,opus',
    'video/webm;codecs=vp9,opus',
    'video/webm',
  ];
  return candidates.find(type => window.MediaRecorder?.isTypeSupported?.(type)) || '';
}

export function startRollingMediaBuffer(stream, maxSec = 5) {
  if (!stream || !stream.getTracks?.().length) return false;
  if (rollingRecorder?.state === 'recording') return true;

  rollingStream = stream;
  rollingMaxSec = Math.max(1, Number(maxSec) || 5);
  rollingChunks = [];

  try {
    const mimeType = recorderMimeType();
    rollingRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    rollingRecorder.ondataavailable = (event) => {
      if (!event.data || event.data.size <= 0) return;
      rollingChunks.push(event.data);
      rollingChunks = rollingChunks.slice(-rollingMaxSec);
    };
    rollingRecorder.onstop = () => {
      rollingRecorder = null;
    };
    rollingRecorder.start(1000);
    return true;
  } catch (err) {
    console.warn('[rolling media buffer failed]', err);
    rollingRecorder = null;
    return false;
  }
}

export function stopRollingMediaBuffer() {
  safeStopRecorder(rollingRecorder);
  rollingRecorder = null;
  rollingChunks = [];
  rollingStream = null;
  captureInFlight = false;
}

export function hasRollingMediaBuffer() {
  return Boolean(
    rollingStream
    && rollingStream.getVideoTracks?.().some(track => track.readyState === 'live')
    && rollingStream.getAudioTracks?.().some(track => track.readyState === 'live')
    && rollingRecorder?.state === 'recording'
  );
}

export function captureTriggeredClip(postSec = 5) {
  if (captureInFlight) return Promise.reject(new Error('triggered clip capture already running'));
  if (!hasRollingMediaBuffer()) return Promise.reject(new Error('rolling media buffer is not ready'));

  captureInFlight = true;
  const durationMs = Math.max(1, Number(postSec) || 5) * 1000;
  const mimeType = recorderMimeType();

  return new Promise((resolve, reject) => {
    let timer = null;
    let recorder = null;
    const chunks = [];
    const cleanup = () => {
      captureInFlight = false;
      if (timer) window.clearTimeout(timer);
    };
    const fail = (err) => {
      cleanup();
      reject(err);
    };

    try {
      recorder = new MediaRecorder(rollingStream, mimeType ? { mimeType } : undefined);
      recorder.ondataavailable = event => {
        if (event.data && event.data.size > 0) chunks.push(event.data);
      };
      recorder.onerror = event => fail(event.error || new Error('triggered clip recorder error'));
      recorder.onstop = () => {
        cleanup();
        if (!chunks.length) {
          reject(new Error('triggered clip is empty'));
          return;
        }
        resolve(new Blob(chunks, { type: mimeType || 'video/webm' }));
      };
      recorder.start(500);
      timer = window.setTimeout(() => {
        try { recorder.requestData?.(); } catch { }
        try {
          if (recorder.state === 'recording') recorder.stop();
        } catch (err) {
          fail(err);
        }
      }, durationMs);
    } catch (err) {
      fail(err);
    }
  });
}
