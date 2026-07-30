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
}

function videoRecorderOptions() {
  return MediaRecorder.isTypeSupported('video/webm;codecs=vp8')
    ? { mimeType: 'video/webm;codecs=vp8', videoBitsPerSecond: 180000 }
    : { mimeType: 'video/webm', videoBitsPerSecond: 180000 };
}

function audioRecorderOptions() {
  if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
    return { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 64000 };
  }
  return { mimeType: 'audio/webm', audioBitsPerSecond: 64000 };
}

export function createVideoRecorder(stream) {
  return new MediaRecorder(stream, videoRecorderOptions());
}

export function createVoiceRecorder(stream) {
  if (!stream?.getAudioTracks?.().length) {
    throw new Error('Voice recorder requires an audio track.');
  }
  return stream.getVideoTracks().length
    ? new MediaRecorder(stream, videoRecorderOptions())
    : new MediaRecorder(stream, audioRecorderOptions());
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
let _rollingStream  = null;     // 保存 stream 供自動重啟使用
let _rollingClipSec = 2.0;

export function startRollingBuffer(stream, clipSec = 2.0) {
  if (_rollingRecorder && _rollingRecorder.state !== 'inactive') return;
  if (!stream || !stream.getVideoTracks().length) return;

  _rollingStream  = stream;
  _rollingClipSec = clipSec;
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

  // 意外停止時自動重啟。stopRollingBuffer 先設 _rollingRecorder = null，
  // 所以 onstop 時若 _rollingRecorder 非 null，代表非預期停止。
  // 用 restartStream 快照避免 stopRollingBuffer 在 300ms 視窗內把 _rollingStream 清空（Bug 4）
  _rollingRecorder.onstop = () => {
    if (_rollingRecorder !== null) {
      console.warn('[rolling] 非預期停止，0.3s 後自動重啟');
      const restartStream = _rollingStream; // 快照，避免被 stopRollingBuffer 清空
      const restartSec    = _rollingClipSec;
      _rollingRecorder = null;
      setTimeout(() => {
        if (_rollingRecorder !== null) return; // 已被外部重啟
        if (restartStream && restartStream.getVideoTracks().some(t => t.readyState === 'live')) {
          startRollingBuffer(restartStream, restartSec);
        }
      }, 300);
    }
  };

  _rollingRecorder.onerror = (e) => {
    console.warn('[rolling] MediaRecorder 錯誤，自動重啟:', e.error || e);
    _rollingRecorder = null;
    setTimeout(() => {
      if (_rollingStream && _rollingStream.getVideoTracks().some(t => t.readyState === 'live')) {
        startRollingBuffer(_rollingStream, _rollingClipSec);
      }
    }, 300);
  };

  _rollingRecorder.start(ROLLING_CHUNK_MS);
}

export function stopRollingBuffer() {
  const rec = _rollingRecorder;
  _rollingRecorder = null;   // 先清空，讓 onstop 知道這是預期停止
  _rollingInitChunk = null;
  _rollingChunks = [];
  _rollingStream = null;
  if (rec && rec.state !== 'inactive') rec.stop();
}

export function capturePreEventClip() {
  // 不再使用 requestData()：requestData() 與 500ms 定期 timer 競爭同一個
  // ondataavailable，若 timer 先觸發會消耗掉 onData listener，導致
  // requestData() 的 chunk 進入 ondataavailable 主 handler，可能污染
  // _rollingInitChunk（Bug 1）。改為直接同步快照現有 buffer，損失最多 500ms
  // 的最新片段，但對 pre-event clip 分析影響極小。
  if (!_rollingRecorder || _rollingRecorder.state !== 'recording') return null;
  if (!_rollingInitChunk) return null; // recorder 剛啟動，init segment 尚未就緒

  const allChunks = [_rollingInitChunk, ..._rollingChunks];
  const blob = new Blob(allChunks, { type: 'video/webm' });
  return blob.size > 0 ? blob : null;
}
