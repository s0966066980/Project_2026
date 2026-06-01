export async function ensureMediaTracks(currentStream, elements, { video = false, audio = false } = {}) {
  if (!video && !audio) return currentStream || new MediaStream();
  const stream = currentStream || new MediaStream();

  const needVideo = video && !stream.getVideoTracks().length;
  const needAudio = audio && !stream.getAudioTracks().length;
  if (!needVideo && !needAudio) return stream;

  const videoConstraint = needVideo
    ? { width: { ideal: 320, max: 480 }, height: { ideal: 240, max: 360 }, frameRate: { ideal: 8, max: 10 } }
    : false;
  const audioConstraint = needAudio
    ? { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    : false;

  const added = await navigator.mediaDevices.getUserMedia({ video: videoConstraint, audio: audioConstraint });
  added.getTracks().forEach(track => stream.addTrack(track));
  attachStream(stream, elements);
  return stream;
}

function attachStream(stream, elements = {}) {
  if (!stream) return;
  if (stream.getVideoTracks().length && elements.webcam) elements.webcam.srcObject = stream;
  if (stream.getVideoTracks().length && elements.emotionCameraVideo) elements.emotionCameraVideo.srcObject = stream;
}

function videoRecorderOptions() {
  return MediaRecorder.isTypeSupported('video/webm;codecs=vp8')
    ? { mimeType: 'video/webm;codecs=vp8', videoBitsPerSecond: 180000 }
    : { mimeType: 'video/webm', videoBitsPerSecond: 180000 };
}

export function audioRecorderOptions() {
  return { mimeType: 'audio/webm' };
}

export function createVideoRecorder(stream) {
  return new MediaRecorder(stream, videoRecorderOptions());
}

export function createAudioRecorder(stream) {
  return new MediaRecorder(new MediaStream(stream.getAudioTracks()), audioRecorderOptions());
}

export function captureVideoFrameBlob(video, { maxWidth = 320, type = 'image/jpeg', quality = 0.62 } = {}) {
  return new Promise(resolve => {
    if (!video || video.readyState < 2 || !video.videoWidth || !video.videoHeight) {
      resolve(null);
      return;
    }
    const canvas = captureVideoFrameBlob.canvas || (captureVideoFrameBlob.canvas = document.createElement('canvas'));
    const scale = Math.min(1, maxWidth / video.videoWidth);
    canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    const ctx = canvas.getContext('2d', { willReadFrequently: false });
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob => resolve(blob), type, quality);
  });
}

// ── Rolling Buffer（Emotion-LLaMA 事件截片用）────────────────────────
// WebM 格式說明：MediaRecorder 第一個 chunk 是含 EBML 標頭的 init segment，
// 後續 chunks 是無法獨立解碼的 continuation fragments。
// 截片時必須永遠在最前面補上 init segment，否則 ffmpeg 會報 EBML header parsing failed。
const ROLLING_CHUNK_MS = 500;

let _rollingRecorder = null;
let _rollingInitChunk = null;   // 保存含 EBML 標頭的第一個 chunk
let _rollingChunks = [];
let _rollingMaxChunks = 6;

export function startRollingBuffer(stream, clipSec = 2.0) {
  if (_rollingRecorder && _rollingRecorder.state !== 'inactive') return;
  if (!stream || !stream.getVideoTracks().length) return;

  _rollingMaxChunks = Math.ceil((clipSec * 1000) / ROLLING_CHUNK_MS) + 2;
  _rollingInitChunk = null;
  _rollingChunks = [];

  _rollingRecorder = new MediaRecorder(stream, videoRecorderOptions());
  _rollingRecorder.ondataavailable = (e) => {
    if (!e.data || e.data.size === 0) return;
    if (_rollingInitChunk === null) {
      _rollingInitChunk = e.data;   // 第一個 chunk = init segment，單獨保存
      return;
    }
    _rollingChunks.push(e.data);
    if (_rollingChunks.length > _rollingMaxChunks) _rollingChunks.shift();
  };
  _rollingRecorder.start(ROLLING_CHUNK_MS);
}

export function stopRollingBuffer() {
  if (_rollingRecorder && _rollingRecorder.state !== 'inactive') {
    _rollingRecorder.stop();
  }
  _rollingRecorder = null;
  _rollingInitChunk = null;
  _rollingChunks = [];
}

export async function capturePreEventClip() {
  if (!_rollingRecorder || _rollingRecorder.state !== 'recording') return null;

  return new Promise((resolve) => {
    const snapChunks = [..._rollingChunks];
    let resolved = false;

    const finish = (flushedChunk) => {
      if (resolved) return;
      resolved = true;
      if (flushedChunk && flushedChunk.size > 0) snapChunks.push(flushedChunk);
      // init segment 必須排在最前面，確保 EBML 標頭完整
      const allChunks = _rollingInitChunk ? [_rollingInitChunk, ...snapChunks] : snapChunks;
      const blob = new Blob(allChunks, { type: 'video/webm' });
      resolve(blob.size > 0 ? blob : null);
    };

    const onData = (e) => {
      _rollingRecorder.removeEventListener('dataavailable', onData);
      finish(e.data);
    };

    _rollingRecorder.addEventListener('dataavailable', onData);
    _rollingRecorder.requestData();

    setTimeout(() => {
      _rollingRecorder?.removeEventListener('dataavailable', onData);
      finish(null);
    }, 100);
  });
}

