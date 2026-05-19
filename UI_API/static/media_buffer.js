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
  const preChunks = rollingChunks.slice();
  const durationMs = Math.max(1, Number(postSec) || 5) * 1000;
  const postChunks = [];
  const mimeType = recorderMimeType();
  let postRecorder = null;

  return new Promise((resolve, reject) => {
    const finish = () => {
      captureInFlight = false;
      const type = mimeType || 'video/webm';
      const chunks = [...preChunks, ...postChunks].filter(Boolean);
      if (!chunks.length) {
        reject(new Error('triggered clip is empty'));
        return;
      }
      resolve(new Blob(chunks, { type }));
    };

    try {
      postRecorder = new MediaRecorder(rollingStream, mimeType ? { mimeType } : undefined);
      postRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) postChunks.push(event.data);
      };
      postRecorder.onerror = (event) => {
        captureInFlight = false;
        reject(event.error || new Error('triggered clip recorder failed'));
      };
      postRecorder.onstop = finish;
      postRecorder.start(1000);
      window.setTimeout(() => safeStopRecorder(postRecorder), durationMs);
    } catch (err) {
      captureInFlight = false;
      reject(err);
    }
  });
}
