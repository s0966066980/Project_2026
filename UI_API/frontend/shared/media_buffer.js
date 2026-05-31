let rollingRecorder = null;
let rollingChunks = [];
let rollingMaxSec = 5;
let rollingStream = null;

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
}
