# POS app.js Modularization (P5 continuation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Break the remaining high-coupling feature blocks out of the 2505-line `frontend/pos/app.js` god-module (choice-hesitation popup, payment countdown, voice assistant) into focused ES modules, on top of a new shared mutable-state module.

**Architecture:** Introduce `frontend/pos/state.js` exporting a single mutable object `state` that both `app.js` and the feature modules import, giving them **live shared bindings** (no stale-value problem from passing primitives by value). Feature modules that need app.js helper functions use a controlled circular import that is safe because the imported bindings are only referenced inside function bodies (runtime), never at module-evaluation time. Each extraction is behavior-preserving.

**Tech Stack:** Vanilla ES modules (no framework, no bundler), loaded via `<script type="module">`. There is **no JavaScript test runner** in this repo. The acceptance gate for every task is `node --check <file>` (syntax) plus a concrete in-browser behavior checklist that a human runs at `http://127.0.0.1:8000/pos`.

## Global Constraints

- No behavior changes. Each task is a pure refactor; the POS must behave identically before and after.
- No new dependencies, no bundler, no framework. Keep `<script type="module" src="/static/pos/app.js">` as the single entry; new modules are reached only via `import`.
- Every moved function keeps its exact name and signature unless a step explicitly says otherwise, so unrelated call sites are unaffected.
- Shared mutable state lives in `state.js` as fields on the exported `state` object. Modules never re-declare a migrated `let`; they read/write `state.<field>`.
- `node --check` must pass on every touched `.js` file before each commit.
- Commit after each task (frequent commits). Work on branch `refactor/architecture-cleanup` (already checked out).
- Backend is out of scope. Do not touch `backend/`, `config.py`, or `main.py`.

---

### Task 1: Create the shared state module and migrate the cross-feature fields

**Files:**
- Create: `frontend/pos/state.js`
- Modify: `frontend/pos/app.js` (top-of-file `let` declarations near lines 25–59; all reads/writes of the migrated fields)

**Interfaces:**
- Produces: `export const state` — a mutable object with these fields (initial values copied verbatim from the current `app.js` declarations):
  - `menuData: []`
  - `kioskScreen: 'categories'`
  - `kioskActiveGroup: ''`
  - `kioskActiveFilter: '全部'`
  - `currentChoiceHesitationItem: null`
  - `lastCartAddAt: Date.now()`
  - `_passiveLastTriggerAt: 0`
  - `_paymentCdTimer: null`
  - `_pendingPaymentEmotion: null`
  - `_paymentEmotionPromise: null`
  - `_paymentCdCartIds: []`
  - `_voiceProcessing: false`
  - `askRecordingStartedAt: 0`
  - `voiceBubbleTimer: null`
- These are exactly the fields the later feature tasks share with `app.js`. Fields used only inside `app.js` (e.g. `isSystemRunning`, `posRealtime`, `pageDwellTimer`) stay as plain `let` in `app.js` and are **not** migrated.

> Why only these fields: they are the ones read or written across the module boundary by Tasks 2–4. `kioskLang` (26 refs) is intentionally **not** migrated — it is passed as a function parameter where a feature module needs it (already the pattern after `menu_visuals.js`), avoiding a 26-site churn.

- [ ] **Step 1: Create `state.js`**

```javascript
// =========================================================
// POS 共享可變狀態。app.js 與各功能模組 import 同一個物件，
// 取得 live binding（避免以值傳遞造成的過時讀取）。
// 僅放跨模組共享的欄位；只在 app.js 內使用的狀態仍留在 app.js。
// =========================================================
export const state = {
  // 菜單與 kiosk 視圖
  menuData: [],
  kioskScreen: 'categories',
  kioskActiveGroup: '',
  kioskActiveFilter: '全部',
  // 猶豫彈窗
  currentChoiceHesitationItem: null,
  lastCartAddAt: Date.now(),
  _passiveLastTriggerAt: 0,
  // 付款倒數
  _paymentCdTimer: null,
  _pendingPaymentEmotion: null,
  _paymentEmotionPromise: null,
  _paymentCdCartIds: [],
  // 語音
  _voiceProcessing: false,
  askRecordingStartedAt: 0,
  voiceBubbleTimer: null,
};
```

- [ ] **Step 2: Verify syntax**

Run: `node --check frontend/pos/state.js`
Expected: no output, exit 0.

- [ ] **Step 3: Import `state` in `app.js`**

Add directly below the existing `menu_visuals.js` import (currently `app.js:18`):

```javascript
import { state } from './state.js';
```

- [ ] **Step 4: Delete the migrated `let` declarations in `app.js`**

Remove exactly these lines from the top-of-file declaration block (currently near 25–59):

```javascript
let menuData = [];
let voiceBubbleTimer = null;
let askRecordingStartedAt = 0;
let _voiceProcessing = false; // onstop async 執行期間鎖定，防止重複啟動
let _paymentCdTimer = null;         // 倒數 setInterval handle
let _pendingPaymentEmotion = null;  // Emotion-LLaMA 分析結果，供 admin 通知使用
let _paymentEmotionPromise = null;  // in-flight emotion API promise
let _paymentCdCartIds = [];         // 本次付款的購物車快照
let lastCartAddAt = Date.now();
let currentChoiceHesitationItem = null;
let _passiveLastTriggerAt = 0;
let kioskScreen = 'categories';
let kioskActiveGroup = '';
let kioskActiveFilter = '全部';
```

Leave every other `let` in that block untouched (`stream`, `askRecorder`, `isSystemRunning`, `orderCompleted`, `sessionPushedIds`, `sessionAiPushCartCount`, `sessionCartSources`, `lastInterventionEventAt`, `interactionModalTimer`, `lastInteractionAt`, `pageDwellTimer`, `posRealtime`, `lastValidOrderActionAt`, `_passiveStream`, `_passiveRecorder`, `_passiveRecTimer`, `_passiveListening`, `_passivePaused`, `_passiveInFlight`, `kioskLang`).

- [ ] **Step 5: Rewrite every read/write of the migrated fields in `app.js` to go through `state`**

Apply these whole-word substitutions across `app.js` (identifier → replacement). Use word-boundary matching so you do not hit substrings (e.g. do not turn `kioskActiveGroup` matches inside other names — there are none, but match whole words):

| identifier | replace with |
|---|---|
| `menuData` | `state.menuData` |
| `kioskScreen` | `state.kioskScreen` |
| `kioskActiveGroup` | `state.kioskActiveGroup` |
| `kioskActiveFilter` | `state.kioskActiveFilter` |
| `currentChoiceHesitationItem` | `state.currentChoiceHesitationItem` |
| `lastCartAddAt` | `state.lastCartAddAt` |
| `_passiveLastTriggerAt` | `state._passiveLastTriggerAt` |
| `_paymentCdTimer` | `state._paymentCdTimer` |
| `_pendingPaymentEmotion` | `state._pendingPaymentEmotion` |
| `_paymentEmotionPromise` | `state._paymentEmotionPromise` |
| `_paymentCdCartIds` | `state._paymentCdCartIds` |
| `_voiceProcessing` | `state._voiceProcessing` |
| `askRecordingStartedAt` | `state.askRecordingStartedAt` |
| `voiceBubbleTimer` | `state.voiceBubbleTimer` |

After substitution there must be zero bare occurrences left. Verify with:

Run: `grep -nE "\b(menuData|kioskScreen|kioskActiveGroup|kioskActiveFilter|currentChoiceHesitationItem|lastCartAddAt|_passiveLastTriggerAt|_paymentCdTimer|_pendingPaymentEmotion|_paymentEmotionPromise|_paymentCdCartIds|_voiceProcessing|askRecordingStartedAt|voiceBubbleTimer)\b" frontend/pos/app.js | grep -v "state\."`
Expected: no output (every occurrence is now `state.<field>`).

- [ ] **Step 6: Verify syntax**

Run: `node --check frontend/pos/app.js`
Expected: no output, exit 0.

- [ ] **Step 7: Browser acceptance check** (human, at `http://127.0.0.1:8000/pos`)

- Start order → menu renders, categories switch, sub-filters work (exercises `state.menuData`, `state.kioskScreen`, `state.kioskActiveGroup`, `state.kioskActiveFilter`).
- Add an item, then with an empty cart wait ~60s on the menu → the hesitation popup appears (exercises `state.currentChoiceHesitationItem`, `state.lastCartAddAt`).
- Run the payment countdown to timeout, and run a voice turn → both work (exercises the payment/voice `state.*` fields).

- [ ] **Step 8: Commit**

```bash
git add frontend/pos/state.js frontend/pos/app.js
git commit -m "refactor(pos): introduce shared state.js for cross-module fields (P5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Extract the choice-hesitation popup into `choice_hesitation.js`

**Files:**
- Create: `frontend/pos/choice_hesitation.js`
- Modify: `frontend/pos/app.js` (remove the 9 functions; add import; the modal button wiring near 2200–2215 and the re-show block near 2472–2482 stay in app.js but call imported functions)

**Interfaces:**
- Consumes from `state.js`: `state.menuData`, `state.kioskScreen`, `state.kioskActiveGroup`, `state.kioskActiveFilter`, `state.currentChoiceHesitationItem`, `state.lastCartAddAt`, `state._passiveLastTriggerAt`.
- Consumes from `app.js` (controlled circular import, used only inside function bodies): `getFeatures`, `isPosActive`, `_isVoiceActive`, `isCartScreenOpen`, `itemMatchesSubFilter`, `KIOSK_GROUPS`, `kioskLang` (passed where needed).
- Consumes from existing modules: `getMenuVisual`, `formatItemPrice` (from `./menu_visuals.js`); `ui` (from `../shared/ui.js`); `cartManager` (see Step 3 note).
- Produces (named exports, exact signatures): `getChoiceHesitationModal()`, `isChoiceHesitationVisible()`, `hideChoiceHesitationModal(resetIdle = false)`, `isChoiceHesitationEligible()`, `getChoiceHesitationCandidates()`, `pickChoiceHesitationItem()`, `renderChoiceHesitationItem(item)`, `showChoiceHesitationModal()`, `stopChoiceHesitationTimer()`.

> Circular-import note: `app.js` will `import { showChoiceHesitationModal, hideChoiceHesitationModal, stopChoiceHesitationTimer, isChoiceHesitationVisible, pickChoiceHesitationItem, renderChoiceHesitationItem } from './choice_hesitation.js'`, and `choice_hesitation.js` will `import { getFeatures, isPosActive, _isVoiceActive, isCartScreenOpen, itemMatchesSubFilter, KIOSK_GROUPS, cartManager } from './app.js'`. This is safe in ES modules because neither side dereferences the other's bindings during module evaluation — only inside functions invoked at runtime. To make app.js's helpers importable, they must be `export`ed (Step 2).

- [ ] **Step 1: Confirm the exact source block to move**

Run: `grep -n "function getChoiceHesitationModal\|function stopChoiceHesitationTimer" frontend/pos/app.js`
Expected: two line numbers bounding the contiguous block (currently ~731 and ~828). The 9 functions listed in Interfaces are contiguous between them.

- [ ] **Step 2: Add `export` to the app.js helpers the module needs**

In `app.js`, add the `export` keyword in front of these existing declarations (names unchanged):
`function isPosActive`, `function _isVoiceActive`, `function isCartScreenOpen`, `function getFeatures`, `function itemMatchesSubFilter`, and `const KIOSK_GROUPS`. Also `export` the `cartManager` binding (it is constructed via `createCartManager(...)`; change its `const cartManager = ...` to `export const cartManager = ...`).

Run: `node --check frontend/pos/app.js`
Expected: exit 0.

- [ ] **Step 3: Create `choice_hesitation.js` by moving the 9 functions verbatim**

Move the 9 functions out of `app.js` into the new file **unchanged in body**, then apply only these adjustments at the top of the new file and to the moved code:

Header + imports:

```javascript
// =========================================================
// 猶豫彈窗：購物車空且閒置時推薦單品。
// =========================================================
import { ui } from '../shared/ui.js';
import { getMenuVisual, formatItemPrice } from './menu_visuals.js';
import { state } from './state.js';
import {
  getFeatures, isPosActive, _isVoiceActive, isCartScreenOpen,
  itemMatchesSubFilter, KIOSK_GROUPS, cartManager,
} from './app.js';
```

Then prefix the 9 function declarations with `export`. The bodies already reference `state.*`, `getMenuVisual`, `formatItemPrice(item, kioskLang)` — **change** the lone `kioskLang` read inside `renderChoiceHesitationItem` (the `formatItemPrice(item, kioskLang)` call) to take an explicit argument: give `renderChoiceHesitationItem(item, lang = 'zh')` a `lang` param and call `formatItemPrice(item, lang)`; update the two in-module callers (`showChoiceHesitationModal` and the re-show flow) — but since those callers are split between this module and app.js, instead keep it simplest: import nothing for lang and read it via a passed argument. Concretely:
  - `renderChoiceHesitationItem(item)` stays single-arg, and replace its `formatItemPrice(item, kioskLang)` with `formatItemPrice(item, ui.kioskLang ?? 'zh')` **only if** `ui` exposes the language; otherwise add `kioskLang` to the app.js exports (Step 2) and import it here. Pick the export-and-import route for correctness: add `kioskLang` is a `let` reassigned at runtime, so export a getter instead — add `export function getKioskLang() { return kioskLang; }` in app.js and call `formatItemPrice(item, getKioskLang())` here.

- [ ] **Step 4: Wire imports back in `app.js`**

Add near the other `./` imports:

```javascript
import {
  showChoiceHesitationModal, hideChoiceHesitationModal, stopChoiceHesitationTimer,
  isChoiceHesitationVisible, pickChoiceHesitationItem, renderChoiceHesitationItem,
} from './choice_hesitation.js';
```

The existing call sites in `app.js` (the `clearPOSFloatingUI` / `trackedAddToCart` calls to `hideChoiceHesitationModal`; the `stopChoiceHesitationTimer` calls; the modal button listeners near 2200–2215; the re-show block near 2472–2482) keep their exact text — they now resolve to the imported functions. The direct `state.currentChoiceHesitationItem` reads/writes in those app.js blocks remain valid (same `state` object).

- [ ] **Step 5: Verify syntax (both files)**

Run: `node --check frontend/pos/choice_hesitation.js && node --check frontend/pos/app.js`
Expected: exit 0.

Run: `grep -n "function getChoiceHesitationModal\|function showChoiceHesitationModal" frontend/pos/app.js`
Expected: no output (defs moved out).

- [ ] **Step 6: Browser acceptance check** (human)

- Empty cart on the menu, idle ~60s → hesitation popup appears with a priced item, correct image/emoji/price.
- Click "再看看" / refresh control → a different item renders (`pickChoiceHesitationItem` excludes current).
- Click the pick CTA → item-confirm modal opens with source `choice_hesitation`; adding it increments AI-push cart count.
- Close the popup → it hides; add an item → popup does not immediately re-trigger (passive cooldown reset via `state._passiveLastTriggerAt`).
- Open cart screen / payment / start a voice turn → popup is suppressed (eligibility gates).

- [ ] **Step 7: Commit**

```bash
git add frontend/pos/choice_hesitation.js frontend/pos/app.js
git commit -m "refactor(pos): extract choice-hesitation popup into choice_hesitation.js (P5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Extract the payment countdown into `payment_countdown.js`

**Files:**
- Create: `frontend/pos/payment_countdown.js`
- Modify: `frontend/pos/app.js` (remove `_showPaymentCdSection`, `openPaymentCountdown`, `closePaymentCountdown`, `_startPaymentCountdown`, `_triggerPaymentEmotionCapture`; add import; the payment-page button handlers near 2056–2096 stay in app.js and call the imports)

**Interfaces:**
- Consumes from `state.js`: `state._paymentCdTimer`, `state._pendingPaymentEmotion`, `state._paymentEmotionPromise`, `state._paymentCdCartIds`.
- Consumes from `app.js` (export + circular import, runtime-only use): `sessionId`, `reportInteractionEvent` (or whatever the countdown's timeout-event reporter is — confirm in Step 1), and any DOM helpers it calls (`ui`, `setVisible`). Confirm the exact set in Step 1 before moving.
- Consumes from media/api modules already imported at top of app.js: `api.analyzeEmotionEvent`, the rolling-buffer/`captureVideoFrameBlob` helpers (from `./media.js`) and `runtimeSettings` — these must be passed in or imported; determine in Step 1.
- Produces (exact signatures): `openPaymentCountdown(cartIds)`, `closePaymentCountdown()`. (`_showPaymentCdSection`, `_startPaymentCountdown`, `_triggerPaymentEmotionCapture` move too but stay module-private — not exported.)

- [ ] **Step 1: Enumerate the exact dependencies**

Run: `sed -n '1110,1205p' frontend/pos/app.js`
Read every identifier the 5 functions reference that is NOT one of the 5 functions themselves or a `state._payment*` field. Write the list down. Expected references include: `sessionId`, `api` (`api.analyzeEmotionEvent`), a video-frame/clip capture helper from `./media.js`, `runtimeSettings`, `ui` DOM nodes, the interaction-event reporter, and `EMOTION_LLAMA_CLIP_SEC`/timeout constants. This list defines the imports for the new module.

- [ ] **Step 2: Export the needed app.js bindings**

For each plain-`app.js` identifier from Step 1 that the module will use (e.g. `sessionId`, `runtimeSettings`, `reportInteractionEvent`, `setVisible`), add `export` to its declaration in `app.js`. For runtime-reassigned `let`s (`runtimeSettings`), export a getter (`export function getRuntimeSettings() { return runtimeSettings; }`) instead of the binding, and use the getter in the module. `sessionId` is a `const` — export it directly.

Run: `node --check frontend/pos/app.js`
Expected: exit 0.

- [ ] **Step 3: Create `payment_countdown.js` by moving the 5 functions verbatim**

Header + imports (fill the import list from Step 1):

```javascript
// =========================================================
// 付款倒數 Modal：15 秒倒數 → Emotion-LLaMA 擷取 → 失敗畫面/人員協助。
// =========================================================
import * as api from '../shared/api.js';
import { ui } from '../shared/ui.js';
import { state } from './state.js';
import { captureVideoFrameBlob /* + the exact media helpers from Step 1 */ } from './media.js';
import { sessionId, getRuntimeSettings, reportInteractionEvent, setVisible /* + others from Step 1 */ } from './app.js';
```

Move the 5 functions unchanged except: prefix `openPaymentCountdown` and `closePaymentCountdown` with `export`; replace any `runtimeSettings` read with `getRuntimeSettings()`. Bodies already use `state._payment*`.

- [ ] **Step 4: Wire imports in `app.js`**

```javascript
import { openPaymentCountdown, closePaymentCountdown } from './payment_countdown.js';
```

The payment-page handlers near 2056–2096 keep their exact text (they call `openPaymentCountdown`, `closePaymentCountdown`, `_showPaymentCdSection`). **Note:** `_showPaymentCdSection` and `_pendingPaymentEmotion`/`_paymentEmotionPromise` are referenced by the "人員協助付款" handler around 2084–2096. Because `_showPaymentCdSection` becomes module-private, either (a) also export it, or (b) move that handler block into a small exported function `showPaymentNotified()` in the module. Choose (a) for the smallest diff: add `export` to `_showPaymentCdSection` and import it in app.js.

- [ ] **Step 5: Verify syntax (both files)**

Run: `node --check frontend/pos/payment_countdown.js && node --check frontend/pos/app.js`
Expected: exit 0.

- [ ] **Step 6: Browser acceptance check** (human)

- "在此快速結帳" → 15s countdown UI shows and ticks.
- Let it reach `15 - PAYMENT_EMOTION_CLIP_SEC` → emotion capture fires (with Emotion-LLaMA enabled), no console error.
- Let it hit zero → payment-failed screen ("需要協助嗎？").
- "人員協助付款" → shows Ollama assist text ~3s, then closes back to payment page; admin receives the staff notify with emotion payload.
- Cancel mid-countdown → `closePaymentCountdown` clears the timer (no lingering interval; verify cart/return path normal).

- [ ] **Step 7: Commit**

```bash
git add frontend/pos/payment_countdown.js frontend/pos/app.js
git commit -m "refactor(pos): extract payment countdown into payment_countdown.js (P5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Extract the voice assistant into `voice.js`

**Files:**
- Create: `frontend/pos/voice.js`
- Modify: `frontend/pos/app.js` (remove the ~13 voice functions; add import; assist-modal/voice-button wiring stays in app.js and calls the imports)

**Interfaces:**
- Consumes from `state.js`: `state._voiceProcessing`, `state.askRecordingStartedAt`, `state.voiceBubbleTimer`.
- Consumes from `app.js` (export + circular import): `sessionId`, `stream`/`askRecorder` access, `ensureMediaTracks`, `isPosActive`, `updateVoiceAssistVisibility` (decide direction in Step 1), interaction reporters, and the cart mutators (`trackedAddToCart`) used when applying `cart_actions`.
- Consumes from existing modules: `api` (`../shared/api.js`), media recorder helpers (`./media.js`), `ui`.
- Produces (exact signatures, confirm names in Step 1): `_isVoiceActive()`, `closeVoiceBubble(stopAudio = true)`, `playVoice(b64, format = 'wav')`, `showVoiceBubble(data)`, `showVoiceAssistMessage(message, lang)`, `showVoiceAssistOverlay(state = 'listening')`, `hideVoiceAssistOverlay()`, `setupAskRecorder()`, `startAskRecording(sourceBtn)`, `stopAskRecording()`, `stopOrHideVoiceAssistOverlay(event)`.

> `_isVoiceActive` is consumed by `choice_hesitation.js` (Task 2) and `app.js`. After this task it lives in `voice.js`; update Task 2's import source for `_isVoiceActive` from `./app.js` to `./voice.js`, and have `app.js` import it from `./voice.js` too. Keep the name identical so no call site text changes.

- [ ] **Step 1: Enumerate dependencies and the exact function span**

Run: `grep -nE "function (_isVoiceActive|closeVoiceBubble|playVoice|showVoiceBubble|showVoiceAssistMessage|showVoiceAssistOverlay|hideVoiceAssistOverlay|setupAskRecorder|startAskRecording|stopAskRecording|stopOrHideVoiceAssistOverlay)" frontend/pos/app.js`
Run: `sed -n '<first>,<last>p' frontend/pos/app.js` over that span and list every external identifier (as in Task 3 Step 1). Expected: `sessionId`, `stream`, `askRecorder`, `ensureMediaTracks`, recorder factories from `./media.js`, `api.ask`/streaming endpoints, `trackedAddToCart`, `ui`, language helper `getKioskLang()`.

- [ ] **Step 2: Export the needed app.js bindings**

Add `export` to the app.js identifiers from Step 1 not already exported (`trackedAddToCart`, `ensureMediaTracks`, etc.). For `stream`/`askRecorder` (reassigned `let`s shared with media setup): move them into `state.js` as `state.stream` / `state.askRecorder` in this task (add the two fields, delete the `let`s, substitute references in both `app.js` and `voice.js`) so both modules share the live handles. Verify zero bare `stream`/`askRecorder` remain:

Run: `grep -nE "\b(stream|askRecorder)\b" frontend/pos/app.js | grep -v "state\.\|Stream\|Recorder\b"`
Expected: only intentional non-state matches (inspect each).

- [ ] **Step 3: Create `voice.js` by moving the ~13 functions verbatim**

Header + imports (fill from Step 1):

```javascript
// =========================================================
// 語音助理：錄音 → STT/LLM/TTS → 氣泡與 overlay → cart_actions。
// =========================================================
import * as api from '../shared/api.js';
import { ui } from '../shared/ui.js';
import { state } from './state.js';
import { createAudioRecorder /* + media helpers from Step 1 */ } from './media.js';
import { sessionId, ensureMediaTracks, trackedAddToCart, isPosActive, getKioskLang /* + others */ } from './app.js';
```

Move the functions unchanged except: prefix the public ones (Interfaces list) with `export`; replace `kioskLang` reads with `getKioskLang()`. Bodies already use `state._voiceProcessing`, `state.askRecordingStartedAt`, `state.voiceBubbleTimer`, `state.stream`, `state.askRecorder`.

- [ ] **Step 4: Re-point `_isVoiceActive` and wire imports**

In `app.js`, import the voice API:

```javascript
import {
  _isVoiceActive, closeVoiceBubble, playVoice, showVoiceBubble,
  showVoiceAssistMessage, showVoiceAssistOverlay, hideVoiceAssistOverlay,
  setupAskRecorder, startAskRecording, stopAskRecording, stopOrHideVoiceAssistOverlay,
} from './voice.js';
```

In `choice_hesitation.js`, change the `_isVoiceActive` import source from `./app.js` to `./voice.js`. Existing call sites keep their text.

- [ ] **Step 5: Verify syntax (all three touched files)**

Run: `node --check frontend/pos/voice.js && node --check frontend/pos/app.js && node --check frontend/pos/choice_hesitation.js`
Expected: exit 0.

Run: `grep -nE "function (startAskRecording|setupAskRecorder|_isVoiceActive)" frontend/pos/app.js`
Expected: no output (moved out).

- [ ] **Step 6: Browser acceptance check** (human)

- Open the assist modal (50 clicks) → voice panel; press-to-talk records, releases, transcribes, replies with TTS audio, and bubble shows.
- Say an order ("我要一個大麥克") → item added to cart via `trackedAddToCart`.
- A recommendation question returns spoken answer with no cart change.
- Overlay states (listening / processing) show and hide correctly; closing mid-record stops cleanly with no stuck `state._voiceProcessing` lock (try a second turn immediately after).
- With Emotion-LLaMA voice event enabled, ending a voice turn still triggers analysis without error.

- [ ] **Step 7: Commit**

```bash
git add frontend/pos/voice.js frontend/pos/choice_hesitation.js frontend/pos/app.js frontend/pos/state.js
git commit -m "refactor(pos): extract voice assistant into voice.js (P5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:** The three remaining P5 cuts (choice-hesitation, payment countdown, voice) each have a task (2, 3, 4), preceded by the enabling `state.js` foundation (Task 1). The two already-done cuts (mood removal, `menu_visuals.js`) are out of scope here.

**Placeholder scan:** Tasks 3 and 4 contain two deliberate "confirm in Step 1" dependency-enumeration steps. These are **not** placeholders for code — they are required discovery steps because the exact import set for payment/voice depends on identifiers (media-helper names, the interaction-event reporter name) that must be read from the live file at execution time rather than guessed; each is paired with the exact `grep`/`sed` command to produce the list and the rule for what to do with it. Task 1 and Task 2 contain complete, literal code.

**Type/name consistency:** Function names are preserved verbatim across move (no rename), so call sites are unaffected. `_isVoiceActive` ownership transfers from `app.js` (Task 2 imports it from app.js) to `voice.js` (Task 4 re-points Task 2's import) — flagged explicitly in Task 4 Interfaces and Step 4. `getKioskLang()` is introduced in Task 2 Step 3 and reused in Tasks 3–4. The `state` field list in Task 1 is the union of fields consumed by Tasks 2–4; `state.stream`/`state.askRecorder` are added later in Task 4 Step 2 (noted there, not in Task 1, because only voice needs them).

**Risk note for the executor:** There is no JS test runner, so `node --check` only catches syntax, not runtime wiring (undefined refs, circular-import evaluation order, stale handles). The browser acceptance checklist in each task is the real gate — do not mark a task done on `node --check` alone. If a circular import misbehaves at evaluation time, move the offending top-level usage inside a function or convert a shared binding to a getter.
