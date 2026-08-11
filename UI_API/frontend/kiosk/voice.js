// =========================================================
// 語音助理：錄音 → durable Voice Turn journal → 驗證 draft → 顯示與播放。
// =========================================================
import * as api from '../shared/apiClient.js';
import { ui, escapeHTML } from '../shared/ui.js';
import { state } from './state.js';
import { getRequiredRuntimeDependency } from './runtime.js';
import { createSileroVoiceActivityDetector } from './voiceActivity.js';
import { createVoiceOrderDraftController } from './voiceOrderDraft.js';
import { createVoiceTurnProtocolState, consumeVoiceTurnEvent, assertVoiceTurnStreamEnded } from './voiceTurnProtocol.js';
import { createVoiceDialogueState, reduceVoiceDialogue } from './voiceDialogueReducer.js';
import { kioskText } from './constants/kiosk.js';
import { playVoiceAudioChunk } from './voicePlayback.js';

function isKioskActive() { return getRequiredRuntimeDependency('isKioskActive')(); }
function trackInteractionEvent(event) { return getRequiredRuntimeDependency('trackInteractionEvent')(event); }
function showPushNotice(text) { return getRequiredRuntimeDependency('showPushNotice')(text); }
function sessionId() { return getRequiredRuntimeDependency('sessionId'); }

let voiceEmotionRoundId = '';
let voiceTurnSequence = 0;
let activeVoiceTurn = null;
let activeVoiceDialogue = null;
let voiceDetector = null;
let voiceListening = false;
let voiceSuspended = false;
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
  void voiceDetector?.destroy?.();
  voiceDetector = null;
  voiceListening = false;
  voiceSuspended = false;
  if (voiceMaxTimer) clearTimeout(voiceMaxTimer);
  voiceMaxTimer = null;
  voiceEmotionRoundId = createVoiceFlowId('order');
  voiceTurnSequence = 0;
  activeVoiceTurn = null;
  activeVoiceDialogue = null;
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
  activeVoiceDialogue = createVoiceDialogueState(activeVoiceTurn.turnId);
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
  // 等待文字或播放 TTS 時 overlay 可能先收起；仍須視為同一個 Voice Turn，
  // 避免被動推薦在語音尚未真正完成時重新蓋上畫面。
  return Boolean(
    activeVoiceTurn
    || state.isVoiceProcessing,
  );
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

function renderVoiceDialogue(playbackWarning = '') {
  if (!isKioskActive() || !ui.voiceBubble || !ui.voiceDialogueGrid) return;
  const rows = activeVoiceDialogue?.rows || [];
  ui.voiceDialogueGrid.innerHTML = rows.map((row) => `
    <div class="voice-reply-row ${row.role === 'customer' ? 'voice-reply-question' : 'voice-reply-answer'}">
      <i class="fas ${row.role === 'customer' ? 'fa-microphone' : 'fa-volume-up'}"></i>
      <div>${escapeHTML(row.text || '-')}</div>
    </div>`).join('') + (playbackWarning ? `
    <div class="voice-reply-row voice-reply-playback-warning">
      <i class="fas fa-triangle-exclamation"></i>
      <div>${escapeHTML(playbackWarning)}</div>
    </div>` : '');
  ui.voiceBubble.classList.remove('hidden');
  ui.voiceBubble.setAttribute('aria-hidden', 'false');
}

function showVoiceBubble(data = {}) {
  if (!isKioskActive() || !ui.voiceBubble || !ui.voiceDialogueGrid) return;
  if (!activeVoiceDialogue && (data.user_text || data.ai_response)) {
    activeVoiceDialogue = createVoiceDialogueState(String(data.voice_turn_id || 'message'));
    const turnId = activeVoiceDialogue.voiceTurnId;
    if (data.user_text) reduceVoiceDialogue(activeVoiceDialogue, {
      type: 'transcript', voice_turn_id: turnId, sequence: 1, text: data.user_text, final: true,
    });
    if (data.ai_response) reduceVoiceDialogue(activeVoiceDialogue, {
      type: 'assistant_text', voice_turn_id: turnId, sequence: 2, text: data.ai_response,
    });
  }
  if (activeVoiceDialogue && data.ai_response
    && !activeVoiceDialogue.rows.some((row) => row.role === 'assistant')) {
    reduceVoiceDialogue(activeVoiceDialogue, {
      type: 'assistant_text',
      voice_turn_id: activeVoiceDialogue.voiceTurnId,
      sequence: Number.MAX_SAFE_INTEGER,
      text: data.ai_response,
    });
  }
  hideVoiceAssistOverlay();
  const playbackWarning = ['degraded', 'unavailable', 'failed'].includes(data.playback_status)
    ? (data.playback_message || kioskText('voicePlaybackUnavailable'))
    : '';
  renderVoiceDialogue(playbackWarning);
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

function showVoiceTranscript(data) {
  if (!activeVoiceDialogue) return;
  reduceVoiceDialogue(activeVoiceDialogue, {
    type: 'transcript',
    voice_turn_id: activeVoiceDialogue.voiceTurnId,
    sequence: Number(data?.sequence || 0),
    text: data?.user_text || data?.transcript || data?.text || '',
    final: Boolean(data?.final),
  });
  renderVoiceDialogue();
}

function applyVoiceDialogueEvent(event) {
  if (!activeVoiceDialogue || !event?.payload) return;
  if (event.type === 'transcript') {
    showVoiceTranscript({ ...event.payload, sequence: event.sequence });
  }
  if (event.type === 'assistant_result') {
    reduceVoiceDialogue(activeVoiceDialogue, {
      type: 'assistant_text',
      voice_turn_id: activeVoiceDialogue.voiceTurnId,
      sequence: event.sequence,
      text: event.payload.ai_response || event.payload.text || event.payload.response || '',
    });
    renderVoiceDialogue();
  }
}

function setVoiceStatus(status, text) {
  const surface = document.getElementById('voiceAssistBtn');
  const label = document.getElementById('voiceAssistBtnText');
  if (surface) {
    surface.dataset.voiceStatus = status;
    surface.classList.toggle('recording', status === 'listening' || status === 'speaking');
  }
  if (label) label.textContent = text;
}

export function hideVoiceAssistOverlay() {
  globalThis.dispatchEvent?.(new Event('kiosk:recommendation-eligibility-changed'));
}


export async function setupAskRecorder() {
  if (voiceDetector) return;
  if (!state.stream?.getAudioTracks?.().length) {
    setVoiceStatus('unavailable', '語音不可用');
    return;
  }
  setVoiceStatus('loading', '語音模型載入中');
  try {
    voiceDetector = await createSileroVoiceActivityDetector(state.stream, {
      onSpeechStart() {
        if (state.isVoiceProcessing || activeVoiceTurn) return;
        activeVoiceTurn = beginVoiceTurn();
        state.askRecordingStartedAt = Date.now();
        setVoiceStatus('speaking', '偵測到語音');
        clearTimeout(voiceMaxTimer);
        voiceMaxTimer = setTimeout(() => { void voiceDetector?.pause(); }, 30000);
        trackInteractionEvent({ event_type: 'voice_assist_started', button_id: 'silero_vad_v5', metadata: {} });
      },
      onVADMisfire() {
        activeVoiceTurn = null;
        state.askRecordingStartedAt = 0;
        setVoiceStatus('listening', '自動聆聽中');
      },
      onSpeechEnd(blob) { return submitVoiceSegment(blob); },
    });
    await voiceDetector.start();
    voiceListening = true;
    setVoiceStatus('listening', '自動聆聽中');
  } catch (error) {
    console.error('[voice] Silero VAD v5 無法啟動。', error);
    voiceDetector = null;
    voiceListening = false;
    setVoiceStatus('unavailable', '語音不可用');
    showVoiceAssistMessage('語音模型暫時無法使用，仍可觸控點餐。');
  }
}

async function submitVoiceSegment(blob) {
    clearTimeout(voiceMaxTimer);
    voiceMaxTimer = null;
    if (state.isVoiceProcessing || !activeVoiceTurn) return;
    await voiceDetector?.pause();
    voiceListening = false;
    const mediaType = blob.type || 'audio/wav';
    const durationMs = state.askRecordingStartedAt ? Date.now() - state.askRecordingStartedAt : 0;
    const voiceTurn = activeVoiceTurn;
    state.askRecordingStartedAt = 0;
    state.isVoiceProcessing = true;
    setVoiceStatus('processing', '語音處理中');
    try {
    if (blob.size < 1000 || durationMs < 250) {
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
      metadata: { reason: 'silero_vad_speech_end', duration_ms: durationMs, bytes: blob.size, media_type: mediaType },
    });
    const formData = new FormData();
    formData.append('session_id', getRequiredRuntimeDependency('sessionId'));
    formData.append('media', blob, 'voice_ask.wav');
    formData.append('emotion_round_id', voiceTurn?.roundId || currentVoiceEmotionRoundId());
    formData.append('voice_turn_id', voiceTurn?.turnId || '');
    formData.append('voice_turn_index', String(voiceTurn?.turnIndex || 0));

    // ── 串流版：邊生成邊播音 ─────────────────────────────────────────
    let audioPlayback = Promise.resolve();
    let playbackAttempted = false;
    let playbackFailed = false;

    let firstAudioReceived = false;

    let protocolState = createVoiceTurnProtocolState({ voiceTurnId: voiceTurn?.turnId || '' });
    let protocolViolation = null;
    let streamFailed = false;
    let terminalData = null;
    await api.streamVoiceAssistantResponse(formData, {
      onEvent(event) {
        // 協議違規不得從 stream callback 逃逸成 unhandled rejection，
        // 否則語音回合會停在「處理中」而沒有任何終局。
        if (protocolViolation) return;
        try {
          const consumed = consumeVoiceTurnEvent(protocolState, event);
          protocolState = consumed.state;
          if (!consumed.duplicate) applyVoiceDialogueEvent(consumed.event);
        } catch (error) {
          protocolViolation = error;
        }
      },
      onAudio(b64, fmt) {
        if (!firstAudioReceived) {
          firstAudioReceived = true;
          hideVoiceAssistOverlay();   // 第一句音訊到就隱藏等待動畫
        }
        playbackAttempted = true;
        audioPlayback = audioPlayback
          .then(() => playVoiceAudioChunk({ b64, format: fmt, attempts: 2 }))
          .catch((error) => {
            playbackFailed = true;
            console.warn('[voice] TTS 音訊播放失敗。', error);
          });
      },
      onDone(data) {
        terminalData = data;
      },
      onError(_message, refusal) {
        streamFailed = true;
        hideVoiceAssistOverlay();
        // A capability that is still loading is not a failed turn and not
        // Voice Listening Unavailable either: that state disables voice for
        // the whole ordering session, and this one clears in seconds.
        // Listening resumes in the `finally` below, so the customer only has
        // to say it again.
        const warming = refusal?.code === 'voice_capability_warming';
        trackInteractionEvent({
          event_type: 'voice_assist_failed',
          button_id: 'voiceAssistBtn',
          metadata: { reason: warming ? 'voice_capability_warming' : 'api_error' },
        });
        showVoiceAssistMessage(
          warming ? '語音服務正在啟動，請稍候再說一次；期間仍可觸控點餐。' : kioskText('voiceOrderFailed'),
        );
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
      } else if (terminalData) {
        await audioPlayback;
        if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) {
          closeVoiceBubble();
          trackInteractionEvent({
            event_type: 'voice_assist_cancelled',
            button_id: 'voiceAssistBtn',
            metadata: { reason: 'payment_screen_opened' },
          });
        } else if (
          terminalData.status !== 'success'
          || terminalData.playback_status !== 'available'
          || !playbackAttempted
          || playbackFailed
        ) {
          const failureData = {
            ...terminalData,
            playback_status: 'failed',
            playback_message: terminalData.playback_message || kioskText('voicePlaybackUnavailable'),
          };
          trackInteractionEvent({
            event_type: 'voice_assist_failed',
            button_id: 'voiceAssistBtn',
            metadata: { reason: 'voice_playback_failure', playback_status: 'failed' },
          });
          showVoiceBubble(failureData);
        } else {
          trackInteractionEvent({
            event_type: 'voice_assist_completed',
            button_id: 'voiceAssistBtn',
            metadata: { playback_status: 'played' },
          });
          const orderDraft = resolveVoiceOrderDraft(terminalData);
          const displayData = orderDraft && !String(terminalData.ai_response || '').trim()
            ? {
                ...terminalData,
                ai_response: '已整理您提到的餐點，請在畫面上勾選要加入的品項並確認。',
              }
            : terminalData;
          showVoiceBubble(displayData);
          if (orderDraft) voiceOrderDraftController.show(orderDraft);
          if (terminalData.mentioned_ids) terminalData.mentioned_ids.forEach(id => {
            state.sessionPushedIds.add(id);
            reportVoiceRecommendationEvent('recommendation_shown', id, 0);
          });
        }
      }
    }
    hideVoiceAssistOverlay();
    } finally {
      activeVoiceTurn = null;
      state.isVoiceProcessing = false;
      if (!voiceSuspended && isKioskActive()) {
        await new Promise(resolve => setTimeout(resolve, 400));
        try {
          await voiceDetector?.start();
          voiceListening = Boolean(voiceDetector);
          setVoiceStatus(voiceListening ? 'listening' : 'unavailable', voiceListening ? '自動聆聽中' : '語音不可用');
        } catch (error) {
          console.error('[voice] Silero VAD v5 無法恢復監聽。', error);
          setVoiceStatus('unavailable', '語音不可用');
        }
      }
      globalThis.dispatchEvent?.(new Event('kiosk:recommendation-eligibility-changed'));
    }
}

export async function startAskRecording() {
  if (voiceOrderDraftController.hasPending()) {
    showVoiceAssistMessage('請先確認或取消目前的餐點草稿。');
    return;
  }
  voiceSuspended = false;
  if (!voiceDetector) await setupAskRecorder();
  else if (!voiceListening && !state.isVoiceProcessing) {
    await voiceDetector.start();
    voiceListening = true;
    setVoiceStatus('listening', '自動聆聽中');
  }
}

/**
 * 進入付款流程等情境時，主動把進行中的語音回合以「已取消」終局收掉，
 * 而不是讓它在背景跑完後無處可去。
 */
export function cancelActiveVoiceTurn() {
  voiceSuspended = true;
  clearTimeout(voiceMaxTimer);
  voiceMaxTimer = null;
  void voiceDetector?.pause();
  voiceListening = false;
  activeVoiceTurn = null;
  activeVoiceDialogue = null;
  if (voiceOrderDraftController.hasPending()) voiceOrderDraftController.close('cancelled');
  hideVoiceAssistOverlay();
  setVoiceStatus('paused', '語音已暫停');
}
