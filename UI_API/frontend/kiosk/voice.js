// =========================================================
// 語音助理：錄音 → durable Voice Turn journal → 驗證 draft → 顯示與播放。
// =========================================================
import * as api from '../shared/apiClient.js';
import { ui, escapeHTML } from '../shared/ui.js';
import { createVoiceRecorder } from './media.js';
import { state } from './state.js';
import { getRequiredRuntimeDependency } from './runtime.js';
import { startVoiceActivityMonitor } from './voiceActivity.js';
import { createVoiceOrderDraftController } from './voiceOrderDraft.js';
import { createVoiceTurnProtocolState, consumeVoiceTurnEvent, assertVoiceTurnStreamEnded } from './voiceTurnProtocol.js';
import { kioskText } from './constants/kiosk.js';

function isAdminMode() { return getRequiredRuntimeDependency('isAdminMode')(); }
function isKioskActive() { return getRequiredRuntimeDependency('isKioskActive')(); }
function getFeatures() { return getRequiredRuntimeDependency('getFeatures')(); }
function getRuntimeSettings() { return getRequiredRuntimeDependency('getRuntimeSettings')(); }
function trackInteractionEvent(event) { return getRequiredRuntimeDependency('trackInteractionEvent')(event); }
function showPushNotice(text) { return getRequiredRuntimeDependency('showPushNotice')(text); }
function clearAllPushCards() { return getRequiredRuntimeDependency('clearAllPushCards')(); }
function pausePassiveListener() { return getRequiredRuntimeDependency('pausePassiveListener')(); }
function resumePassiveListener() { return getRequiredRuntimeDependency('resumePassiveListener')(); }
function sessionId() { return getRequiredRuntimeDependency('sessionId'); }

let voiceEmotionRoundId = '';
let voiceTurnSequence = 0;
let activeVoiceTurn = null;
let voiceActivityMonitor = null;
let voiceStopIntent = 'submit';
let voiceMaxTimer = null;

/** 回傳事件序列未正常收尾的原因，正常收尾則回傳 null。 */
function voiceTurnStreamViolation(protocolState) {
  try {
    assertVoiceTurnStreamEnded(protocolState);
    return null;
  } catch (error) {
    return error;
  }
}

function createVoiceFlowId(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function resetVoiceEmotionRound() {
  voiceActivityMonitor?.stop();
  voiceActivityMonitor = null;
  if (voiceMaxTimer) clearTimeout(voiceMaxTimer);
  voiceMaxTimer = null;
  voiceEmotionRoundId = createVoiceFlowId('order');
  voiceTurnSequence = 0;
  activeVoiceTurn = null;
}

function currentVoiceEmotionRoundId() {
  if (!voiceEmotionRoundId) resetVoiceEmotionRound();
  return voiceEmotionRoundId;
}

function beginVoiceTurn() {
  voiceTurnSequence += 1;
  activeVoiceTurn = {
    roundId: currentVoiceEmotionRoundId(),
    turnId: `voice_${voiceTurnSequence}_${Date.now()}`,
    turnIndex: voiceTurnSequence,
  };
  return activeVoiceTurn;
}

const cartManager = new Proxy({}, {
  get(_target, prop) {
    return getRequiredRuntimeDependency('cartManager')[prop];
  },
});

const voiceOrderDraftController = createVoiceOrderDraftController({
  getMenuItems: () => state.menuData,
  cartManager,
  escapeHTML,
  onConfirmed(actions, appliedOrders) {
    actions.forEach(action => {
      for (let i = 0; i < (Number(action.quantity) || 1); i++) {
        state.sessionCartSources.push({ id: action.id, source: 'voice_assist' });
      }
      reportVoiceRecommendationEvent('recommendation_added_to_cart', action.id, Number(action.quantity) || 1);
    });
    if (!appliedOrders.length) return;
    state.lastValidOrderActionAt = Date.now();
    state.lastCartAddAt = Date.now();
    trackInteractionEvent({
      event_type: 'cart_edit', button_id: 'askBtn', cart_edit_count: appliedOrders.length,
      metadata: { source: 'voice_assist_confirmed', items: appliedOrders },
    });
    showPushNotice(kioskText('addedToCart').replace('{items}', appliedOrders.join('、')));
  },
  onCancelled() {
    trackInteractionEvent({
      event_type: 'voice_order_draft_cancelled', button_id: 'voiceOrderDraftModal', metadata: {},
    });
  },
});

function resolveVoiceOrderDraft(data) {
  const draft = data?.order_draft;
  if (!draft || draft.requires_confirmation !== true || !Array.isArray(draft.lines)) return null;
  return {
    items: draft.lines.map(line => ({ id: String(line.item_id || ''), quantity: Number(line.quantity || 1), selected: false })),
    recommendation_ids: [],
    clarification_ids: [],
  };
}

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
  if (!isKioskActive() || !ui.voiceBubble || !ui.voiceDialogueGrid) return;
  hideVoiceAssistOverlay();
  const userText = String(data.user_text || '').trim();
  const answerText = String(data.ai_response || '-').trim();
  const playbackWarning = ['degraded', 'unavailable'].includes(data.playback_status)
    ? (data.playback_message || kioskText('voicePlaybackUnavailable'))
    : '';
  ui.voiceDialogueGrid.innerHTML = `
    ${userText ? `
      <div class="voice-reply-row voice-reply-question">
        <i class="fas fa-microphone"></i>
        <div>${escapeHTML(userText)}</div>
      </div>` : ''}
    <div class="voice-reply-row voice-reply-answer">
      <i class="fas fa-volume-up"></i>
      <div>${escapeHTML(answerText || '-')}</div>
    </div>
    ${playbackWarning ? `
      <div class="voice-reply-row voice-reply-playback-warning">
        <i class="fas fa-triangle-exclamation"></i>
        <div>${escapeHTML(playbackWarning)}</div>
      </div>` : ''}`;
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

function showVoiceAssistMessage(message) {
  showVoiceBubble({
    user_text: '',
    ai_response: message,
  });
}

function showVoiceAssistOverlay(state = 'listening') {
  if (!ui.voiceAssistOverlay) return;
  const listening = state !== 'thinking';
  ui.voiceAssistOverlay.classList.remove('hidden');
  ui.voiceAssistOverlay.classList.toggle('thinking', !listening);
  ui.voiceAssistOverlay.setAttribute('aria-hidden', 'false');
  if (ui.voiceAssistOverlayTitle) ui.voiceAssistOverlayTitle.textContent = '語音模式';
  if (ui.voiceAssistOverlaySubtitle) {
    ui.voiceAssistOverlaySubtitle.textContent = listening
      ? '我正在聽，請說出您的需求'
      : '正在處理您的語音...';
  }
  if (ui.voiceAssistStopText) {
    ui.voiceAssistStopText.textContent = listening
      ? '說完後停頓 1.5 秒會自動送出'
      : '處理中...';
  }
  if (ui.voiceAssistSendBtn) ui.voiceAssistSendBtn.disabled = !listening;
  if (ui.voiceAssistStopBtn) ui.voiceAssistStopBtn.disabled = !listening;
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
  state.askRecorder = createVoiceRecorder(state.stream.clone());
  let chunks = [];
  state.askRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
  state.askRecorder.onstop = async () => {
    if (state.isVoiceProcessing) {
      // 上一次 onstop 還在跑（正常情況不應發生）：放棄本次，但不能把 UI 留在「處理中」。
      hideVoiceAssistOverlay();
      resumePassiveListener();
      return;
    }
    const stopIntent = voiceStopIntent;
    voiceStopIntent = 'submit';
    const mediaType = chunks[0]?.type || state.askRecorder?.mimeType || 'audio/webm';
    const blob = new Blob(chunks, { type: mediaType });
    const durationMs = state.askRecordingStartedAt ? Date.now() - state.askRecordingStartedAt : 0;
    const voiceTurn = activeVoiceTurn;
    state.askRecordingStartedAt = 0;
    chunks = [];

    if (stopIntent === 'cancel' || stopIntent === 'no_speech') {
      hideVoiceAssistOverlay();
      trackInteractionEvent({
        event_type: stopIntent === 'cancel' ? 'voice_assist_cancelled' : 'voice_assist_failed',
        button_id: 'voiceAssistBtn',
        metadata: { reason: stopIntent, duration_ms: durationMs },
      });
      if (stopIntent === 'no_speech') showVoiceAssistMessage(kioskText('voiceNoSpeech'));
      activeVoiceTurn = null;
      resumePassiveListener();
      return;
    }

    state.isVoiceProcessing = true;
    try {
    if (blob.size < 1500 || durationMs < 650) {
      hideVoiceAssistOverlay();
      trackInteractionEvent({
        event_type: 'voice_assist_failed',
        button_id: 'voiceAssistBtn',
        metadata: { reason: 'audio_too_short', duration_ms: durationMs, bytes: blob.size }
      });
      showVoiceAssistMessage(kioskText('voiceTooShort'));
      return;
    }
    trackInteractionEvent({
      event_type: 'voice_assist_submitted',
      button_id: 'voiceAssistBtn',
      metadata: { reason: stopIntent, duration_ms: durationMs, bytes: blob.size, media_type: mediaType },
    });
    const formData = new FormData();
    formData.append('session_id', getRequiredRuntimeDependency('sessionId'));
    formData.append('media', blob, 'voice_ask.webm');
    formData.append('emotion_round_id', voiceTurn?.roundId || currentVoiceEmotionRoundId());
    formData.append('voice_turn_id', voiceTurn?.turnId || '');
    formData.append('voice_turn_index', String(voiceTurn?.turnIndex || 0));

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

    let protocolState = createVoiceTurnProtocolState({ voiceTurnId: voiceTurn?.turnId || '' });
    let protocolViolation = null;
    let streamFailed = false;
    await api.streamVoiceAssistantResponse(formData, {
      onEvent(event) {
        // 協議違規不得從 stream callback 逃逸成 unhandled rejection，
        // 否則語音回合會停在「處理中」而沒有任何終局。
        if (protocolViolation) return;
        try {
          protocolState = consumeVoiceTurnEvent(protocolState, event).state;
        } catch (error) {
          protocolViolation = error;
        }
      },
      onAssistantText(data) {
        hideVoiceAssistOverlay();
        showVoiceBubble(data);
      },
      onAudio(b64, fmt) {
        if (!firstAudioReceived) {
          firstAudioReceived = true;
          hideVoiceAssistOverlay();   // 第一句音訊到就隱藏等待動畫
        }
        audioStreamQueue.push({ b64, fmt });
        if (!isAudioStreamPlaying) playAudioStreamQueue();
      },
      onDone(data) {
        // 顧客已進入付款畫面：這個回合以「已取消」作為唯一可見終局收尾，
        // 不再彈出草稿或氣泡覆蓋付款流程，但也不能無聲消失。
        if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) {
          hideVoiceAssistOverlay();
          trackInteractionEvent({
            event_type: 'voice_assist_cancelled',
            button_id: 'voiceAssistBtn',
            metadata: { reason: 'payment_screen_opened' },
          });
          return;
        }
        if (data.status !== 'success') {
          trackInteractionEvent({
            event_type: 'voice_assist_failed', button_id: 'voiceAssistBtn',
            metadata: { reason: 'assistant_error', message: data.message || '' },
          });
          showVoiceAssistMessage(data.ai_response || data.message || kioskText('voiceOrderFailed'));
          return;
        }
        trackInteractionEvent({
          event_type: data.playback_status === 'degraded'
            ? 'voice_assist_playback_degraded'
            : 'voice_assist_completed',
          button_id: 'voiceAssistBtn',
          metadata: { playback_status: data.playback_status || 'available' },
        });
        const orderDraft = resolveVoiceOrderDraft(data);
        // 有草稿待確認時，助理回覆改為引導顧客到草稿視窗勾選，避免文字與待辦動作不一致。
        const displayData = orderDraft && !String(data.ai_response || '').trim()
          ? {
              ...data,
              ai_response: '已整理您提到的餐點，請在畫面上勾選要加入的品項並確認。',
            }
          : data;
        showVoiceBubble(displayData);
        if (orderDraft) voiceOrderDraftController.show(orderDraft);
        if (data.mentioned_ids) data.mentioned_ids.forEach(id => {
          state.sessionPushedIds.add(id);
          reportVoiceRecommendationEvent('recommendation_shown', id, 0);
        });
      },
      onError() {
        streamFailed = true;
        hideVoiceAssistOverlay();
        trackInteractionEvent({ event_type: 'voice_assist_failed', button_id: 'voiceAssistBtn', metadata: { reason: 'api_error' } });
        showVoiceAssistMessage(kioskText('voiceOrderFailed'));
      },
    }).catch(error => {
      // streamVoiceAssistantResponse 在呼叫 onError 後仍會 rethrow；
      // onError 已經給出可見終局，這裡只負責攔住 rejection。
      streamFailed = true;
      console.warn('[voice] 語音串流中斷。', error);
    });
    // 串流已自行給出終局時不再重複報告；否則檢查事件序列是否完整收尾。
    if (!streamFailed) {
      const violation = protocolViolation || voiceTurnStreamViolation(protocolState);
      if (violation) {
        // 事件序列不完整或違規：以「助理失敗」這個明確終局收尾。
        console.warn('[voice] Voice Turn 協議違規。', violation);
        trackInteractionEvent({
          event_type: 'voice_assist_failed',
          button_id: 'voiceAssistBtn',
          metadata: { reason: 'voice_turn_protocol_violation', detail: String(violation.message || '') },
        });
        showVoiceAssistMessage(kioskText('voiceOrderFailed'));
      }
    }
    const doneButtonText = document.getElementById('voiceAssistBtnText');
    if (doneButtonText) doneButtonText.textContent = kioskText('holdVoiceOrder');
    hideVoiceAssistOverlay();
    } finally {
      activeVoiceTurn = null;
      state.isVoiceProcessing = false;
      resumePassiveListener();
    }
  };
}

export function startAskRecording(sourceBtn) {
  if (voiceOrderDraftController.hasPending()) {
    showVoiceAssistMessage('請先確認或取消目前的餐點草稿。');
    return;
  }
  if (!state.askRecorder) setupAskRecorder();
  if (!state.askRecorder || state.askRecorder.state !== 'inactive' || state.isVoiceProcessing) {
    showVoiceAssistMessage(kioskText('voiceMicNotReady'));
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
    const voiceTurn = beginVoiceTurn();
    state.askRecordingStartedAt = Date.now();
    voiceStopIntent = 'submit';
    state.askRecorder.start(250);
    document.getElementById('voiceAssistBtn')?.classList.add('recording');
    showVoiceAssistOverlay('listening');
    const startButtonText = document.getElementById('voiceAssistBtnText');
    if (startButtonText) startButtonText.textContent = kioskText('listeningAsk');
    try {
      voiceActivityMonitor = startVoiceActivityMonitor(state.stream, (decision) => {
        finishAskRecording(decision === 'no_speech' ? 'no_speech' : 'silence_detected');
      });
    } catch (error) {
      console.warn('[voice] 無法啟動停頓偵測，仍可使用立即送出或取消。', error);
    }
    voiceMaxTimer = setTimeout(() => finishAskRecording('max_duration'), 30000);
  }
}

/**
 * 進入付款流程等情境時，主動把進行中的語音回合以「已取消」終局收掉，
 * 而不是讓它在背景跑完後無處可去。
 */
export function cancelActiveVoiceTurn() {
  if (state.askRecorder?.state === 'recording') {
    finishAskRecording('cancel');
    return;
  }
  if (voiceOrderDraftController.hasPending()) voiceOrderDraftController.close('cancelled');
  hideVoiceAssistOverlay();
}

function finishAskRecording(intent = 'manual_submit') {
  if (state.askRecorder && state.askRecorder.state === 'recording') {
    voiceStopIntent = intent;
    voiceActivityMonitor?.stop();
    voiceActivityMonitor = null;
    if (voiceMaxTimer) clearTimeout(voiceMaxTimer);
    voiceMaxTimer = null;
    state.askRecorder.stop();
    document.getElementById('voiceAssistBtn')?.classList.remove('recording');
    const buttonText = document.getElementById('voiceAssistBtnText');
    if (buttonText) buttonText.textContent = kioskText('holdVoiceOrder');
    if (intent === 'cancel' || intent === 'no_speech') hideVoiceAssistOverlay();
    else showVoiceAssistOverlay('thinking');
  }
}
const voiceAssistantFloatingButton = document.getElementById('voiceAssistBtn');
if (voiceAssistantFloatingButton) {
  voiceAssistantFloatingButton.addEventListener('click', (e) => {
    e.preventDefault();
    if (state.askRecorder?.state === 'recording') finishAskRecording('manual_submit');
    else startAskRecording(voiceAssistantFloatingButton);
  });
}
function stopOrHideVoiceAssistOverlay(event) {
  event?.preventDefault?.();
  if (state.askRecorder?.state === 'recording') {
    finishAskRecording('cancel');
  } else {
    hideVoiceAssistOverlay();
  }
}

ui.voiceAssistSendBtn?.addEventListener('click', (event) => {
  event.preventDefault();
  finishAskRecording('manual_submit');
});
ui.voiceAssistStopBtn?.addEventListener('click', stopOrHideVoiceAssistOverlay);
