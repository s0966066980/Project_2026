// =========================================================
// 語音助理：錄音 → STT/LLM/TTS 串流 → 氣泡/overlay → cart_actions。
// =========================================================
import * as api from '../shared/apiClient.js';
import { ui, escapeHTML } from '../shared/ui.js';
import { createVideoRecorder } from './media.js';
import { state } from './state.js';
import { getRequiredRuntimeDependency } from './runtime.js';

function kt(key) { return getRequiredRuntimeDependency('kt')(key); }
function isAdminMode() { return getRequiredRuntimeDependency('isAdminMode')(); }
function isPosActive() { return getRequiredRuntimeDependency('isPosActive')(); }
function getFeatures() { return getRequiredRuntimeDependency('getFeatures')(); }
function getRuntimeSettings() { return getRequiredRuntimeDependency('getRuntimeSettings')(); }
function getKioskLang() { return getRequiredRuntimeDependency('getKioskLang')(); }
function trackInteractionEvent(event) { return getRequiredRuntimeDependency('trackInteractionEvent')(event); }
function showPushNotice(text) { return getRequiredRuntimeDependency('showPushNotice')(text); }
function clearAllPushCards() { return getRequiredRuntimeDependency('clearAllPushCards')(); }
function triggerEmotionCapture(eventType) { return getRequiredRuntimeDependency('triggerEmotionCapture')(eventType); }
function triggerEmotionCaptureAndWait(eventType) { return getRequiredRuntimeDependency('triggerEmotionCaptureAndWait')(eventType); }
function pausePassiveListener() { return getRequiredRuntimeDependency('pausePassiveListener')(); }
function resumePassiveListener() { return getRequiredRuntimeDependency('resumePassiveListener')(); }
function sessionId() { return getRequiredRuntimeDependency('sessionId'); }

const cartManager = new Proxy({}, {
  get(_target, prop) {
    return getRequiredRuntimeDependency('cartManager')[prop];
  },
});

export function isVoiceAssistantActive() {
  // 語音 overlay 可見（聆聽 or 思考中）時視為語音模式進行中
  return ui.voiceAssistOverlay && !ui.voiceAssistOverlay.classList.contains('hidden');
}

function voiceRecommendationKey(itemId) {
  return `voice:${itemId}`;
}

function createVoiceRecommendationId(itemId) {
  const suffix = Math.random().toString(36).slice(2, 8);
  return `rec_${sessionId()}_voice_${itemId}_${Date.now()}_${suffix}`;
}

function reportVoiceRecommendationEvent(eventType, itemId, quantity = 0) {
  const normalizedId = String(itemId || '').trim();
  if (!normalizedId) return null;
  const item = state.menuData.find(row => row.id === normalizedId) || { id: normalizedId };
  const key = voiceRecommendationKey(normalizedId);
  const existing = state.sessionRecommendationEvents.get(key);
  const record = {
    recommendation_id: existing?.recommendation_id || createVoiceRecommendationId(normalizedId),
    item_id: normalizedId,
    item_name: item.name || '',
    category: item.category || '',
    surface: 'voice',
    source: 'voice_assist',
    rank: existing?.rank || 0,
    score: existing?.score || 0,
    reasons: existing?.reasons || ['voice_llm'],
  };
  state.sessionRecommendationEvents.set(key, record);
  state.sessionRecommendationEvents.set(`item:${normalizedId}`, record);
  api.reportRecommendationEvent({
    session_id: sessionId(),
    event_type: eventType,
    recommendation_id: record.recommendation_id,
    surface: record.surface,
    source: record.source,
    item_id: record.item_id,
    item_name: record.item_name,
    category: record.category,
    rank: record.rank,
    score: record.score,
    reasons: record.reasons,
    quantity,
    audience: state.member ? 'member' : 'guest',
    metadata: { cart_source: eventType === 'recommendation_added_to_cart' ? 'voice_assist' : '' },
  }).catch(err => console.warn('[recommendation_event failed]', err));
  return record;
}

// =========================================================
// 語音問答（問題3: 回覆綁定浮動氣泡，問題5: 語言偵測）
// =========================================================
export function closeVoiceBubble(stopAudio = true) {
  if (state.voiceBubbleTimer) clearTimeout(state.voiceBubbleTimer);
  state.voiceBubbleTimer = null;
  if (stopAudio && ui.audio) {
    ui.audio.pause();
    ui.audio.currentTime = 0;
  }
  ui.voiceBubble?.classList.add('hidden');
  ui.voiceBubble?.setAttribute('aria-hidden', 'true');
  const timerBar = document.getElementById('voiceReplyTimerBar');
  if (timerBar) {
    timerBar.style.transition = 'none';
    timerBar.style.width = '100%';
  }
}

function showVoiceBubble(data) {
  if (!isPosActive() || !ui.voiceBubble || !ui.voiceDialogueGrid) return;
  hideVoiceAssistOverlay();
  const lang = data.detected_lang || 'zh';
  const dialogue = data.dialogue || {
    zh: { user_text: lang === 'zh' ? data.user_text : '', ai_response: lang === 'zh' ? data.ai_response : '' },
    en: { user_text: lang === 'en' ? data.user_text : '', ai_response: lang === 'en' ? data.ai_response : '' }
  };
  const d = dialogue[lang] || { user_text: data.user_text || '', ai_response: data.ai_response || '' };
  const userText = String(d.user_text || data.user_text || '').trim();
  const answerText = String(d.ai_response || data.ai_response || '-').trim();
  ui.voiceDialogueGrid.innerHTML = `
    ${userText ? `
      <div class="voice-reply-row voice-reply-question">
        <i class="fas fa-microphone"></i>
        <div>${escapeHTML(userText)}</div>
      </div>` : ''}
    <div class="voice-reply-row voice-reply-answer">
      <i class="fas fa-volume-up"></i>
      <div>${escapeHTML(answerText || '-')}</div>
    </div>`;
  if (ui.voiceLangBadge) ui.voiceLangBadge.textContent = lang === 'en' ? kt('enOutput') : kt('zhOutput');
  ui.voiceBubble.classList.remove('hidden');
  ui.voiceBubble.setAttribute('aria-hidden', 'false');
  const timerBar = document.getElementById('voiceReplyTimerBar');
  if (timerBar) {
    timerBar.style.transition = 'none';
    timerBar.style.width = '100%';
    requestAnimationFrame(() => {
      timerBar.style.transition = 'width 12s linear';
      timerBar.style.width = '0%';
    });
  }
  if (state.voiceBubbleTimer) clearTimeout(state.voiceBubbleTimer);
  state.voiceBubbleTimer = setTimeout(() => closeVoiceBubble(false), 12000);
}

function showVoiceAssistMessage(message, lang = getKioskLang()) {
  const detected = lang === 'en' ? 'en' : 'zh';
  showVoiceBubble({
    detected_lang: detected,
    user_text: '',
    ai_response: message,
    dialogue: {
      zh: { user_text: '', ai_response: detected === 'zh' ? message : '' },
      en: { user_text: '', ai_response: detected === 'en' ? message : '' },
    }
  });
}

function showVoiceAssistOverlay(state = 'listening') {
  if (!ui.voiceAssistOverlay) return;
  const listening = state !== 'thinking';
  ui.voiceAssistOverlay.classList.remove('hidden');
  ui.voiceAssistOverlay.classList.toggle('thinking', !listening);
  ui.voiceAssistOverlay.setAttribute('aria-hidden', 'false');
  if (ui.voiceAssistOverlayTitle) ui.voiceAssistOverlayTitle.textContent = getKioskLang() === 'en' ? 'Voice Mode' : '語音模式';
  if (ui.voiceAssistOverlaySubtitle) {
    ui.voiceAssistOverlaySubtitle.textContent = listening
      ? (getKioskLang() === 'en' ? 'I am listening. Please say what you need.' : '我正在聽，請說出您的需求')
      : (getKioskLang() === 'en' ? 'Processing your voice...' : '正在處理您的語音...');
  }
  if (ui.voiceAssistStopText) {
    ui.voiceAssistStopText.textContent = listening
      ? (getKioskLang() === 'en' ? 'Hold to stop listening' : '按住關閉收音')
      : (getKioskLang() === 'en' ? 'Processing...' : '處理中...');
  }
}

export function hideVoiceAssistOverlay() {
  ui.voiceAssistOverlay?.classList.add('hidden');
  ui.voiceAssistOverlay?.setAttribute('aria-hidden', 'true');
}


export function setupAskRecorder() {
  if (isAdminMode()) return;
  if (state.askRecorder) return; // 避免重複設定
  if (!state.stream || !state.stream.getAudioTracks().length) return;

  // clone stream：讓 askRecorder 有獨立的 encoded track pipeline，
  // 避免與 _rollingRecorder 共用 encoder 導致 rolling buffer 被餓死（Bug 2）
  state.askRecorder = createVideoRecorder(state.stream.clone());
  let chunks = [];
  state.askRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
  state.askRecorder.onstop = async () => {
    if (state.isVoiceProcessing) return; // 上一次 onstop 還在跑，放棄本次（正常情況不應發生）
    state.isVoiceProcessing = true;
    try {
    const blob = new Blob(chunks, { type: 'video/webm' });
    const durationMs = state.askRecordingStartedAt ? Date.now() - state.askRecordingStartedAt : 0;
    state.askRecordingStartedAt = 0;
    chunks = [];
    if (getRuntimeSettings().EMOTION_LLAMA_EVENT_VOICE) {
      if (getRuntimeSettings().EMOTION_LLAMA_VOICE_WAIT_MODE === 'analysis') {
        await triggerEmotionCaptureAndWait('voice_mode'); // 等分析完才繼續
      } else {
        triggerEmotionCapture('voice_mode');              // 背景執行
      }
    }
    if (blob.size < 1500 || durationMs < 650) {
      hideVoiceAssistOverlay();
      trackInteractionEvent({
        event_type: 'voice_assist_failed',
        button_id: 'voiceAssistBtn',
        metadata: { reason: 'audio_too_short', duration_ms: durationMs, bytes: blob.size }
      });
      showVoiceAssistMessage(kt('voiceTooShort'));
      return;
    }
    const formData = new FormData();
    formData.append('session_id', getRequiredRuntimeDependency('sessionId'));
    formData.append('media', blob, 'voice_ask.webm');
    formData.append('multi_lang', String(getFeatures().multiLang));

    // ── 串流版：邊生成邊播音 ─────────────────────────────────────────
    const audioStreamQueue = [];
    let   isAudioStreamPlaying = false;

    async function playAudioStreamQueue() {
      isAudioStreamPlaying = true;
      while (audioStreamQueue.length) {
        const { b64, fmt } = audioStreamQueue.shift();
        await new Promise(resolve => {
          const a = new Audio(`data:audio/${fmt};base64,${b64}`);
          a.onended = resolve;
          a.onerror = resolve;
          a.play().catch(resolve);
        });
      }
      isAudioStreamPlaying = false;
    }

    let firstAudioReceived = false;

    await api.streamVoiceAssistantResponse(formData, {
      onAudio(b64, fmt) {
        if (!firstAudioReceived) {
          firstAudioReceived = true;
          hideVoiceAssistOverlay();   // 第一句音訊到就隱藏等待動畫
        }
        audioStreamQueue.push({ b64, fmt });
        if (!isAudioStreamPlaying) playAudioStreamQueue();
      },
      onDone(data) {
        if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) return;
        if (data.status !== 'success') {
          showVoiceAssistMessage(data.ai_response || data.message || kt('voiceOrderFailed'), data.detected_lang || getKioskLang());
          return;
        }
        showVoiceBubble(data);
        const appliedOrders = cartManager.applyCartActions(data.cart_actions || []);
        (data.cart_actions || []).forEach(action => {
          if (action.action === 'add' && action.id) {
            for (let i = 0; i < (Number(action.quantity) || 1); i++) {
              state.sessionCartSources.push({ id: action.id, source: 'voice_assist' });
            }
            reportVoiceRecommendationEvent('recommendation_added_to_cart', action.id, Number(action.quantity) || 1);
          }
        });
        if (appliedOrders.length) {
          state.lastValidOrderActionAt = Date.now();
          state.lastCartAddAt = Date.now();
          trackInteractionEvent({
            event_type: 'cart_edit', button_id: 'askBtn',
            cart_edit_count: appliedOrders.length,
            metadata: { source: 'voice_assist', items: appliedOrders }
          });
          showPushNotice(kt('addedToCart').replace('{items}', appliedOrders.join('、')));
        }
        if (data.mentioned_ids) data.mentioned_ids.forEach(id => {
          state.sessionPushedIds.add(id);
          reportVoiceRecommendationEvent('recommendation_shown', id, 0);
        });
      },
      onError() {
        hideVoiceAssistOverlay();
        trackInteractionEvent({ event_type: 'voice_assist_failed', button_id: 'voiceAssistBtn', metadata: { reason: 'api_error' } });
        showVoiceAssistMessage(kt('voiceOrderFailed'));
      },
    });
    const doneButtonText = document.getElementById('voiceAssistBtnText');
    if (doneButtonText) doneButtonText.textContent = kt('holdVoiceOrder');
    hideVoiceAssistOverlay();
    } finally {
      state.isVoiceProcessing = false;
      resumePassiveListener();
    }
  };
}

export function startAskRecording(sourceBtn) {
  if (!state.askRecorder) setupAskRecorder();
  if (!state.askRecorder || state.askRecorder.state !== 'inactive' || state.isVoiceProcessing) {
    showVoiceAssistMessage(kt('voiceMicNotReady'));
    return;
  }
  if (state.askRecorder && state.askRecorder.state === 'inactive') {
    // 開始錄音前先清除推播卡與殘留計時器，避免語音模式與推播卡重疊
    if (state.interactionModalTimer) { clearTimeout(state.interactionModalTimer); state.interactionModalTimer = null; }
    clearAllPushCards();
    trackInteractionEvent({
      event_type: 'voice_assist_started',
      button_id: sourceBtn?.id || 'voiceAssistBtn',
      metadata: {}
    });
    pausePassiveListener();
    state.askRecordingStartedAt = Date.now();
    state.askRecorder.start();
    document.getElementById('voiceAssistBtn')?.classList.add('recording');
    showVoiceAssistOverlay('listening');
    const startButtonText = document.getElementById('voiceAssistBtnText');
    if (startButtonText) startButtonText.textContent = kt('listeningAsk');
  }
}
function stopAskRecording() {
  if (state.askRecorder && state.askRecorder.state === 'recording') {
    state.askRecorder.stop();
    document.getElementById('voiceAssistBtn')?.classList.remove('recording');
    hideVoiceAssistOverlay(); // 立刻關閉；語音背景處理後以 voice bubble 顯示結果
  }
}
const voiceAssistantFloatingButton = document.getElementById('voiceAssistBtn');
if (voiceAssistantFloatingButton) {
  voiceAssistantFloatingButton.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    startAskRecording(voiceAssistantFloatingButton);
  });
}
function stopOrHideVoiceAssistOverlay(event) {
  event?.preventDefault?.();
  if (state.askRecorder?.state === 'recording') {
    stopAskRecording();
  } else {
    hideVoiceAssistOverlay();
  }
}

// X 按鈕：pointerdown 覆蓋 desktop mouse + touch，不再重複監聽 click
// （click 在 touch 設備上會在 pointerdown 之後再觸發，導致 hideVoiceAssistOverlay
//   在 onstop 尚未執行前就把 thinking overlay 收起，造成「開→關→開→關」閃爍）
ui.voiceAssistStopBtn?.addEventListener('pointerdown', stopOrHideVoiceAssistOverlay);
