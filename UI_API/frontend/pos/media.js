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

export function attachStream(stream, elements = {}) {
  if (!stream) return;
  if (stream.getVideoTracks().length && elements.webcam) elements.webcam.srcObject = stream;
  if (stream.getVideoTracks().length && elements.emotionCameraVideo) elements.emotionCameraVideo.srcObject = stream;
}

export function videoRecorderOptions() {
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

export function stopRecorder(recorder) {
  if (recorder && recorder.state === 'recording') recorder.stop();
}
