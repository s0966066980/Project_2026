# Rename Report

This document lists the naming consistency changes applied to the frontend codebase. The goal was to move the JavaScript modules toward modern TypeScript-style conventions:

- descriptive `camelCase` for variables and functions
- `use*` naming for hook-like utilities
- `PascalCase` for component-like modules
- `*Client` naming for API/realtime service clients
- no leading underscore for exported helpers or shared state
- no abbreviations such as `fd`, `qty`, `Cd`, `btn`, or `tx` in edited source identifiers

Backend Python services were not renamed to TypeScript-style names because Python modules and functions should remain Pythonic `snake_case`.

## File and Module Renames

| Old path | New path | Reason |
| --- | --- | --- |
| `UI_API/frontend/shared/api.js` | `UI_API/frontend/shared/apiClient.js` | Service client module should use descriptive `*Client` naming. |
| `UI_API/frontend/shared/realtime_client.js` | `UI_API/frontend/shared/realtimeClient.js` | Use camelCase module naming for frontend JavaScript. |
| `UI_API/frontend/shared/hooks/dom.js` | `UI_API/frontend/shared/hooks/useDomEvents.js` | Hook-like module now follows `use*` naming. |
| `UI_API/frontend/shared/components/display.js` | `UI_API/frontend/shared/components/VisibilityDisplay.js` | Component-like module now uses PascalCase. |
| `UI_API/frontend/pos/menu_visuals.js` | `UI_API/frontend/pos/menuVisuals.js` | Use camelCase module naming. |
| `UI_API/frontend/pos/payment_countdown.js` | `UI_API/frontend/pos/paymentCountdown.js` | Use camelCase module naming. |
| `UI_API/frontend/pos/choice_hesitation.js` | `UI_API/frontend/pos/choiceHesitation.js` | Use camelCase module naming. |

## Shared Client, Hook, and Component Renames

| Old name | New name | Location | Reason |
| --- | --- | --- | --- |
| `connectRealtime` | `createRealtimeClient` | `frontend/shared/realtimeClient.js` | Factory-style client creation should read as `create*Client`. |
| `on` | `addDomEventListener` | `frontend/shared/hooks/useDomEvents.js` | Avoid vague one-word helper names. |
| `onReady` | `useDomReady` | `frontend/shared/hooks/useDomEvents.js` | Hook-like lifecycle utility should use `use*`. |
| `showAsFlex` | `showFlexElement` | `frontend/shared/components/VisibilityDisplay.js` | Make DOM visibility behavior explicit. |
| `hideFromFlex` | `hideFlexElement` | `frontend/shared/components/VisibilityDisplay.js` | Make DOM visibility behavior explicit. |
| `paymentCdBackdrop` | `paymentCountdownBackdrop` | `frontend/shared/ui.js` | Remove `Cd` abbreviation. |
| `paymentCdModal` | `paymentCountdownModal` | `frontend/shared/ui.js` | Remove `Cd` abbreviation. |
| `paymentCdCounting` | `paymentCountdownCounting` | `frontend/shared/ui.js` | Remove `Cd` abbreviation. |
| `paymentCdFailed` | `paymentCountdownFailed` | `frontend/shared/ui.js` | Remove `Cd` abbreviation. |
| `paymentCdNotified` | `paymentCountdownNotified` | `frontend/shared/ui.js` | Remove `Cd` abbreviation. |
| `paymentCdArc` | `paymentCountdownArc` | `frontend/shared/ui.js` | Remove `Cd` abbreviation. |
| `paymentCdNumber` | `paymentCountdownNumber` | `frontend/shared/ui.js` | Remove `Cd` abbreviation. |
| `paymentCdCancelBtn` | `paymentCountdownCancelButton` | `frontend/shared/ui.js` | Replace `Cd` and `Btn` abbreviations. |
| `paymentCdAssistBtn` | `paymentCountdownAssistButton` | `frontend/shared/ui.js` | Replace `Cd` and `Btn` abbreviations. |
| `paymentCdBackBtn` | `paymentCountdownBackButton` | `frontend/shared/ui.js` | Replace `Cd` and `Btn` abbreviations. |
| `paymentCdNotifyMsg` | `paymentCountdownNotifyMessage` | `frontend/shared/ui.js` | Replace `Cd` and `Msg` abbreviations. |

## API Client Service Renames

| Old name | New name | Location | Reason |
| --- | --- | --- | --- |
| `aiPush` | `requestAiPushRecommendation` | `frontend/shared/apiClient.js` | Describe the service action instead of mirroring endpoint shorthand. |
| `askStream` | `streamVoiceAssistantResponse` | `frontend/shared/apiClient.js` | Describe the streaming voice assistant behavior. |
| `checkout` | `submitCheckout` | `frontend/shared/apiClient.js` | Use verb-object naming for service action. |
| `assistRecommend` | `getAssistRecommendations` | `frontend/shared/apiClient.js` | Use descriptive fetch-style naming. |
| `passiveCheck` | `checkPassiveVoice` | `frontend/shared/apiClient.js` | Describe passive voice detection behavior. |
| `fd` | `formData` | `frontend/shared/apiClient.js` | Avoid abbreviation. |

## POS Runtime Renames

| Old name | New name | Location | Reason |
| --- | --- | --- | --- |
| `configurePosRuntime` | `configurePointOfSaleRuntime` | `frontend/pos/runtime.js` | Expand `POS` in shared runtime API. |
| `requireRuntime` | `getRequiredRuntimeDependency` | `frontend/pos/runtime.js` | Make dependency lookup behavior explicit. |

## POS Payment Countdown Renames

| Old name | New name | Location | Reason |
| --- | --- | --- | --- |
| `PAYMENT_CD_TOTAL` | `PAYMENT_COUNTDOWN_TOTAL_SECONDS` | `frontend/pos/paymentCountdown.js` | Remove `Cd` abbreviation and include unit. |
| `PAYMENT_CD_CIRCUMFERENCE` | `PAYMENT_COUNTDOWN_CIRCUMFERENCE` | `frontend/pos/paymentCountdown.js` | Remove `Cd` abbreviation. |
| `_showPaymentCdSection` | `showPaymentCountdownSection` | `frontend/pos/paymentCountdown.js` | Remove leading underscore and abbreviation. |
| `_startPaymentCountdown` | `startPaymentCountdown` | `frontend/pos/paymentCountdown.js` | Remove leading underscore. |
| `_triggerPaymentEmotionCapture` | `capturePaymentEmotion` | `frontend/pos/paymentCountdown.js` | Use direct verb-object naming. |
| `_paymentCdTimer` | `paymentCountdownTimer` | `frontend/pos/state.js` | Remove leading underscore and abbreviation. |
| `_paymentCdCartIds` | `paymentCountdownCartIds` | `frontend/pos/state.js` | Remove leading underscore and abbreviation. |
| `_pendingPaymentEmotion` | `pendingPaymentEmotion` | `frontend/pos/state.js` | Remove leading underscore. |
| `_paymentEmotionPromise` | `paymentEmotionPromise` | `frontend/pos/state.js` | Remove leading underscore. |

## POS Voice and Emotion Renames

| Old name | New name | Location | Reason |
| --- | --- | --- | --- |
| `_isVoiceActive` | `isVoiceAssistantActive` | `frontend/pos/voice.js` | Boolean helper should use `is*` and avoid underscore. |
| `_triggerEmotionCapture` | `triggerEmotionCapture` | `frontend/pos/app.js` | Remove leading underscore from exported helper. |
| `_triggerEmotionCaptureAndWait` | `triggerEmotionCaptureAndWait` | `frontend/pos/app.js` | Remove leading underscore from exported helper. |
| `_pausePassiveListener` | `pausePassiveListener` | `frontend/pos/app.js` | Remove leading underscore from exported helper. |
| `_resumePassiveListener` | `resumePassiveListener` | `frontend/pos/app.js` | Remove leading underscore from exported helper. |
| `_voiceProcessing` | `isVoiceProcessing` | `frontend/pos/state.js` | Boolean state should use `is*`. |
| `_streamQueue` | `audioStreamQueue` | `frontend/pos/voice.js` | Describe queued data. |
| `_streamPlaying` | `isAudioStreamPlaying` | `frontend/pos/voice.js` | Boolean state should use `is*`. |
| `_playStreamQueue` | `playAudioStreamQueue` | `frontend/pos/voice.js` | Remove leading underscore and describe behavior. |
| `_doneText` | `doneButtonText` | `frontend/pos/voice.js` | Avoid vague private-style local name. |
| `_startText` | `startButtonText` | `frontend/pos/voice.js` | Avoid vague private-style local name. |
| `_vaFabBtn` | `voiceAssistantFloatingButton` | `frontend/pos/voice.js` | Expand abbreviation. |

## POS Recommendation Renames

| Old name | New name | Location | Reason |
| --- | --- | --- | --- |
| `aiPush` | `aiRecommendationController` | `frontend/pos/app.js` | Describe the local controller role, not just the backend feature. |
| `REFRESH_MS` | `RECOMMENDATION_REFRESH_DELAY_MS` | `frontend/pos/app.js` | Include domain and unit. |
| `RETRY_MS` | `RECOMMENDATION_RETRY_DELAY_MS` | `frontend/pos/app.js` | Include domain and unit. |
| `_timer` | `recommendationTimer` | `frontend/pos/app.js` | Remove leading underscore and clarify purpose. |
| `_inFlight` | `isRecommendationRequestInFlight` | `frontend/pos/app.js` | Boolean state should use `is*`. |
| `_item` | `currentRecommendationItem` | `frontend/pos/app.js` | Clarify current recommendation state. |
| `_eligible` | `isRecommendationEligible` | `frontend/pos/app.js` | Boolean helper should use `is*`. |
| `_render` | `renderRecommendation` | `frontend/pos/app.js` | Remove leading underscore and clarify render target. |
| `_pickDefault` | `pickDefaultRecommendation` | `frontend/pos/app.js` | Remove leading underscore and clarify domain. |
| `_pickRandom` | `pickRandomRecommendation` | `frontend/pos/app.js` | Remove leading underscore and clarify domain. |
| `_fetch` | `fetchRecommendation` | `frontend/pos/app.js` | Remove leading underscore and clarify service behavior. |
| `_schedule` | `scheduleRecommendationRefresh` | `frontend/pos/app.js` | Clarify scheduled behavior. |
| `_clearTimer` | `clearRecommendationTimer` | `frontend/pos/app.js` | Clarify timer target. |
| `def` | `defaultRecommendation` | `frontend/pos/app.js` | Avoid abbreviation. |
| `nameEl` | `nameElement` | `frontend/pos/app.js` | Avoid DOM abbreviation. |
| `textEl` | `textElement` | `frontend/pos/app.js` | Avoid DOM abbreviation. |
| `imgEl` | `imageElement` | `frontend/pos/app.js` | Avoid DOM abbreviation. |
| `emEl` | `emojiElement` | `frontend/pos/app.js` | Avoid abbreviation. |
| `prEl` | `priceElement` | `frontend/pos/app.js` | Avoid abbreviation. |

## POS Item Confirmation Renames

| Old name | New name | Location | Reason |
| --- | --- | --- | --- |
| `_icItem` | `itemConfirmSelectedItem` | `frontend/pos/app.js` | Expand item confirmation state name. |
| `_icQty` | `itemConfirmQuantity` | `frontend/pos/app.js` | Expand quantity state name. |
| `_icSource` | `itemConfirmSource` | `frontend/pos/app.js` | Expand source state name. |
| `el` | `quantityDisplayElement` | `frontend/pos/app.js` | Avoid DOM abbreviation. |

## POS Assist and Passive Voice Renames

| Old name | New name | Location | Reason |
| --- | --- | --- | --- |
| `_showAssistPanel` | `showAssistPanel` | `frontend/pos/app.js` | Remove leading underscore. |
| `_loadAssistRecommendations` | `loadAssistRecommendations` | `frontend/pos/app.js` | Remove leading underscore. |
| `_buildAssistItemCard` | `buildAssistItemCard` | `frontend/pos/app.js` | Remove leading underscore. |
| `_assistRecommendLoading` | `isAssistRecommendationLoading` | `frontend/pos/app.js` | Boolean state should use `is*`. |
| `_passiveStream` | `passiveAudioStream` | `frontend/pos/app.js` | Clarify media stream purpose. |
| `_passiveRecorder` | `passiveAudioRecorder` | `frontend/pos/app.js` | Clarify recorder purpose. |
| `_passiveRecTimer` | `passiveRecordingTimer` | `frontend/pos/app.js` | Expand abbreviation. |
| `_passiveListening` | `isPassiveListening` | `frontend/pos/app.js` | Boolean state should use `is*`. |
| `_passivePaused` | `isPassivePaused` | `frontend/pos/app.js` | Boolean state should use `is*`. |
| `_passiveInFlight` | `isPassiveRequestInFlight` | `frontend/pos/app.js` | Boolean state should use `is*`. |
| `_schedulePassiveChunk` | `schedulePassiveAudioChunk` | `frontend/pos/app.js` | Describe scheduled work. |
| `_handlePassiveHit` | `handlePassiveVoiceHit` | `frontend/pos/app.js` | Describe event handling. |
| `_showHesitationForItem` | `showHesitationForItem` | `frontend/pos/app.js` | Remove leading underscore. |
| `_passiveLastTriggerAt` | `passiveLastTriggerAt` | `frontend/pos/state.js` | Remove leading underscore. |
| `btn` | `addButton` | `frontend/pos/app.js` | Avoid abbreviation in assist item card. |

## POS Member Flow Renames

| Old name | New name | Location | Reason |
| --- | --- | --- | --- |
| `_phone` | `memberPhoneNumber` | `frontend/pos/member.js` | Describe state value. |
| `_onResolved` | `onMemberResolved` | `frontend/pos/member.js` | Remove leading underscore and clarify callback purpose. |
| `cb` | `resolveCallback` | `frontend/pos/member.js` | Avoid abbreviation. |
| `el` | `element` | `frontend/pos/member.js` | Avoid DOM abbreviation. |
| `el` | `imageElement` | `frontend/pos/member.js` | Avoid DOM abbreviation for image node. |

## POS Cart Renames

| Old name | New name | Location | Reason |
| --- | --- | --- | --- |
| `tx` | `translateCartText` | `frontend/pos/cart.js` | Avoid abbreviation and clarify translation role. |
| `qty` | `quantity` | `frontend/pos/cart.js` | Avoid abbreviation. |
| `quantity` parameter | `requestedQuantity` | `frontend/pos/cart.js` | Avoid shadowing normalized value. |
| normalized `qty` | `normalizedQuantity` | `frontend/pos/cart.js` | Clarify bounded quantity. |

## Checkout Display Renames

| Old name | New name | Location | Reason |
| --- | --- | --- | --- |
| destructured `qty` | `quantity` | `frontend/pos/app.js` | Use full local name for completion screen data. |
| reducer `s` | `sum` | `frontend/pos/app.js` | Avoid one-letter accumulator in edited checkout total calculation. |
| reducer `i` | `item` | `frontend/pos/app.js` | Avoid one-letter item variable in edited checkout total calculation. |

## Intentionally Not Renamed

The following names were intentionally left unchanged because they are external contracts, DOM/CSS contracts, or backend/Python conventions:

| Name pattern | Reason |
| --- | --- |
| API route paths such as `/api/ai_push`, `/api/checkout`, `/api/passive_check` | Backend route contracts used by FastAPI and frontend fetch calls. |
| Payload keys such as `session_id`, `cart_ids`, `event_type`, `button_id`, `ai_push_cart_count` | Backend request/response schema contracts. |
| Event names such as `payment_countdown_start`, `choice_hesitation`, `enter_payment_page` | Analytics/intervention event contracts. |
| DOM IDs such as `paymentCdCancelBtn` and CSS classes such as `co-item-qty` | Existing HTML/CSS contracts. |
| Backend Python files and functions such as `ai_push_service.py` and `interaction_event_service.py` | Python service naming should stay `snake_case`, not TypeScript `camelCase`. |
| Admin dashboard local variables still using `btn`/`el` in untouched sections | The admin file is large and behavior-sensitive; only shared client imports were renamed in this pass. |
