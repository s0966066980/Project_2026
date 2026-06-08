# Assist Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the invalid-click-based "如何點餐" tutorial trigger with a cumulative 50-click counter that opens a center-screen "需要協助嗎？" modal with three panels: main options, Ollama 3-item recommendation, and tutorial.

**Architecture:** New `#assistModal` HTML mirrors the existing `#choiceHesitationModal` pattern (center + backdrop). A global `pointerdown` counter replaces the old `invalidClickTimestamps` logic. Backend adds `generate_three()` in `ai_push_service.py` and a new `GET /api/assist_recommend` route.

**Tech Stack:** Vanilla JS (ES modules), FastAPI, Ollama (existing `ask_ollama`), existing `getMenuVisual` / `formatItemPrice` / `showItemConfirmModal` helpers.

---

## File Map

| File | Change |
|---|---|
| `UI_API/frontend/pos/index.html` | Add `#assistModal` HTML after `#choiceHesitationModal` (line 118) |
| `UI_API/frontend/shared/styles.css` | Add `.assist-*` CSS after line 3287 |
| `UI_API/frontend/pos/app.js` | Delete invalid-click block (lines 1888–1934); add click counter + all assist JS |
| `UI_API/frontend/shared/api.js` | Add `assistRecommend()` export |
| `UI_API/backend/services/ai_push_service.py` | Add `generate_three()` function |
| `UI_API/backend/routes/ai_push_routes.py` | Add `GET /api/assist_recommend` route |

---

## Task 1: Backend — `generate_three()` + route

**Files:**
- Modify: `UI_API/backend/services/ai_push_service.py` (append after line 137)
- Modify: `UI_API/backend/routes/ai_push_routes.py` (append route inside `create_router`)

- [ ] **Step 1: Add `generate_three` to `ai_push_service.py`**

Append after the last line of `UI_API/backend/services/ai_push_service.py`:

```python
async def generate_three(session_id: str, ollama_semaphore) -> list[dict]:
    """呼叫 generate() 三次，累積 exclude_ids 確保不重複，回傳含 name/price/image 的完整項目清單。"""
    items_map = {i["id"]: i for i in await _get_menu_cached() if i.get("id")}
    results = []
    exclude: list[str] = []
    for _ in range(3):
        rec = await generate(session_id, ollama_semaphore, exclude_ids=exclude)
        rec_id = rec.get("recommendation_id", "")
        if rec_id:
            exclude.append(rec_id)
        menu_item = items_map.get(rec_id, {})
        results.append({
            "id": rec_id,
            "name": menu_item.get("name", ""),
            "price": menu_item.get("price", 0),
            "image": menu_item.get("official_image_url") or menu_item.get("image", ""),
            "push_text": rec.get("push_text", ""),
            "category": menu_item.get("category", ""),
        })
    return results
```

- [ ] **Step 2: Add route to `ai_push_routes.py`**

In `UI_API/backend/routes/ai_push_routes.py`, add inside `create_router` after the existing `@router.post("/ai_push")` block:

```python
    @router.get("/assist_recommend")
    async def handle_assist_recommend(session_id: str):
        return await ai_push_service.generate_three(
            session_id=session_id,
            ollama_semaphore=deps["ollama_semaphore"],
        )
```

- [ ] **Step 3: Syntax check**

```bash
cd UI_API && python3 -m py_compile backend/services/ai_push_service.py && python3 -m py_compile backend/routes/ai_push_routes.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add UI_API/backend/services/ai_push_service.py UI_API/backend/routes/ai_push_routes.py
git commit -m "feat(assist): add generate_three + GET /api/assist_recommend"
```

---

## Task 2: Frontend API — `assistRecommend()`

**Files:**
- Modify: `UI_API/frontend/shared/api.js` (append before last line)

- [ ] **Step 1: Add `assistRecommend` export to `api.js`**

Append at the end of `UI_API/frontend/shared/api.js`:

```javascript
export async function assistRecommend(sessionId) {
  return asJson(await fetch(`${API_BASE}/api/assist_recommend?session_id=${encodeURIComponent(sessionId)}`));
}
```

- [ ] **Step 2: Syntax check**

```bash
node --check UI_API/frontend/shared/api.js && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add UI_API/frontend/shared/api.js
git commit -m "feat(assist): add assistRecommend API function"
```

---

## Task 3: HTML — `#assistModal`

**Files:**
- Modify: `UI_API/frontend/pos/index.html` (insert after line 118, i.e. the closing `</div>` of `#choiceHesitationModal`)

- [ ] **Step 1: Insert `#assistModal` HTML**

In `UI_API/frontend/pos/index.html`, find the closing `</div>` of `#choiceHesitationModal` (the blank line after line 118) and insert immediately after:

```html

<!-- ============ Assist Modal (協助選擇) ============ -->
<div id="assistModal" class="assist-modal hidden" role="dialog"
     aria-modal="true" aria-label="需要協助嗎">
  <div class="assist-backdrop" id="assistBackdrop"></div>
  <div class="assist-card">

    <!-- Panel: main -->
    <div id="assistMain" class="assist-panel">
      <div class="assist-title">需要協助嗎？</div>
      <div class="assist-buttons">
        <button id="assistBtnRecommend" class="assist-option-btn" type="button">
          <i class="fas fa-utensils"></i>
          <span>推薦餐點</span>
        </button>
        <button id="assistBtnVoice" class="assist-option-btn" type="button">
          <i class="fas fa-microphone"></i>
          <span>語音模式</span>
        </button>
        <button id="assistBtnTutorial" class="assist-option-btn" type="button">
          <i class="fas fa-info-circle"></i>
          <span>操作教學</span>
        </button>
      </div>
      <button id="assistClose" class="assist-close-link" type="button">不需要，繼續點餐</button>
    </div>

    <!-- Panel: recommend -->
    <div id="assistRecommend" class="assist-panel hidden">
      <div class="assist-panel-header">
        <button id="assistRecommendBack" class="assist-back-btn" type="button">
          <i class="fas fa-chevron-left"></i>
        </button>
        <span class="assist-panel-title">為您推薦</span>
      </div>
      <div id="assistRecommendItems" class="assist-recommend-list">
        <div id="assistRecommendLoading" class="assist-recommend-loading">
          <i class="fas fa-circle-notch fa-spin"></i> 推薦中...
        </div>
      </div>
      <button id="assistRecommendCancel" class="assist-close-link" type="button">取消</button>
    </div>

    <!-- Panel: tutorial -->
    <div id="assistTutorial" class="assist-panel hidden">
      <div class="assist-panel-header">
        <button id="assistTutorialBack" class="assist-back-btn" type="button">
          <i class="fas fa-chevron-left"></i>
        </button>
        <span class="assist-panel-title">如何點餐</span>
      </div>
      <ol class="assist-tutorial-steps">
        <li><i class="fas fa-th-large"></i> 選擇想吃的餐點分類</li>
        <li><i class="fas fa-plus-circle"></i> 點擊「<b>+</b>」加入購物車</li>
        <li><i class="fas fa-shopping-cart"></i> 點「結帳去」完成付款</li>
      </ol>
      <button id="assistTutorialClose" class="assist-close-link" type="button">關閉</button>
    </div>

  </div>
</div>
```

- [ ] **Step 2: Verify insertion is correct**

```bash
grep -n "assistModal\|assistMain\|assistRecommend\|assistTutorial" UI_API/frontend/pos/index.html
```

Expected: 4+ lines printed showing all four IDs.

- [ ] **Step 3: Commit**

```bash
git add UI_API/frontend/pos/index.html
git commit -m "feat(assist): add assist modal HTML (3 panels)"
```

---

## Task 4: CSS — `.assist-*` styles

**Files:**
- Modify: `UI_API/frontend/shared/styles.css` (append at end of file)

- [ ] **Step 1: Append CSS**

Append at the very end of `UI_API/frontend/shared/styles.css`:

```css
/* ============ Assist Modal (協助選擇) ============ */
.assist-modal {
  position: fixed;
  inset: 0;
  z-index: 9250;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.assist-modal.hidden { display: none; }
.assist-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,0.72);
  backdrop-filter: blur(5px);
}
.assist-card {
  position: relative;
  z-index: 1;
  width: min(92vw, 480px);
  border-radius: 28px;
  background: #fff;
  padding: 32px 28px 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  box-shadow: 0 24px 80px rgba(0,0,0,0.42);
  animation: assistCardIn 0.22s ease-out;
}
@keyframes assistCardIn {
  from { opacity: 0; transform: translateY(16px) scale(0.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
.assist-panel { display: flex; flex-direction: column; gap: 16px; }
.assist-panel.hidden { display: none; }
.assist-title {
  font-size: 22px;
  font-weight: 800;
  text-align: center;
  color: #2a2119;
}
.assist-buttons { display: flex; flex-direction: column; gap: 12px; }
.assist-option-btn {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
  border-radius: 16px;
  background: #f5f1ea;
  border: 2px solid transparent;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  color: #2a2119;
  transition: background 0.15s, border-color 0.15s;
}
.assist-option-btn:hover { background: #ffecd0; border-color: #ffc72c; }
.assist-option-btn i { font-size: 20px; color: #c8102e; width: 28px; text-align: center; flex-shrink: 0; }
.assist-close-link {
  text-align: center;
  color: #8494b0;
  font-size: 13px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
}
.assist-close-link:hover { color: #4a3b30; }
.assist-panel-header { display: flex; align-items: center; gap: 10px; }
.assist-back-btn {
  background: none;
  border: none;
  font-size: 18px;
  color: #4a3b30;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 8px;
  line-height: 1;
}
.assist-back-btn:hover { background: #f0ece4; }
.assist-panel-title { font-size: 17px; font-weight: 800; color: #2a2119; }
.assist-recommend-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 58vh;
  overflow-y: auto;
}
.assist-recommend-loading {
  text-align: center;
  color: #8494b0;
  padding: 24px 0;
  font-size: 14px;
}
.assist-item-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px;
  border-radius: 16px;
  background: #f9f7f3;
  border: 1.5px solid #ede7da;
}
.assist-item-photo {
  width: 64px;
  height: 64px;
  border-radius: 12px;
  overflow: hidden;
  flex-shrink: 0;
  background: #ede7da;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}
.assist-item-photo img { width: 100%; height: 100%; object-fit: cover; display: block; }
.assist-item-emoji { font-size: 28px; line-height: 1; }
.assist-item-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.assist-item-name { font-size: 14px; font-weight: 800; color: #2a2119; }
.assist-item-push { font-size: 12px; color: #8494b0; margin: 0; line-height: 1.4; }
.assist-item-price { font-size: 13px; font-weight: 700; color: #c8102e; }
.assist-item-add-btn {
  padding: 8px 14px;
  border-radius: 12px;
  background: #ffc72c;
  border: none;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  flex-shrink: 0;
  white-space: nowrap;
  color: #1a1a1a;
}
.assist-item-add-btn:hover { background: #ffb300; }
.assist-tutorial-steps {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.assist-tutorial-steps li {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 15px;
  font-weight: 600;
  color: #2a2119;
}
.assist-tutorial-steps li i {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f5f1ea;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
  color: #c8102e;
}
```

- [ ] **Step 2: Syntax check (node parses CSS indirectly via grep)**

```bash
grep -c "assist-" UI_API/frontend/shared/styles.css
```

Expected: number >= 20 (confirms all classes were appended)

- [ ] **Step 3: Commit**

```bash
git add UI_API/frontend/shared/styles.css
git commit -m "feat(assist): add assist modal CSS styles"
```

---

## Task 5: JS — Remove old invalid-click logic, add click counter + assist modal

**Files:**
- Modify: `UI_API/frontend/pos/app.js`

This task has three sub-steps: delete old block, add click counter to existing `pointerdown` handler, add all assist JS functions and event bindings.

- [ ] **Step 1: Delete the invalid-click section (lines 1888–1934)**

In `UI_API/frontend/pos/app.js`, delete the entire block from the comment `// =========================================================` before line 1888 through the closing `});` at line 1934. The block starts with:

```javascript
// =========================================================
// 無效點擊偵測（需連續 N 次才觸發教學提示）
// =========================================================
const INVALID_CLICK_THRESHOLD = 3;
```

and ends with:

```javascript
    if (invalidClickTimestamps.length >= INVALID_CLICK_THRESHOLD) {
      invalidClickTimestamps = [];
      showTutorialPopup();
    }
  }
});
```

After deletion, verify nothing between these lines remains:

```bash
grep -n "INVALID_CLICK\|invalidClickTimestamps\|shouldTrackInvalidClick" UI_API/frontend/pos/app.js
```

Expected: no output.

- [ ] **Step 2: Add click counter + `showAssistModal` call**

In `UI_API/frontend/pos/app.js`, find the `document.addEventListener('pointerdown'` line that now exists (after deletion it should be the original `document.addEventListener` for cancel logic or another one). Add a NEW `pointerdown` listener for the click counter. Insert just before the `// =========================================================` comment for **Cancel order popup** section (grep for `// 2-3: Cancel order popup`):

```javascript
// =========================================================
// 協助 Modal 點擊計數（任意點擊累積 50 次觸發）
// =========================================================
let totalClickCount = 0;
const ASSIST_CLICK_THRESHOLD = 50;

document.addEventListener('pointerdown', () => {
  if (document.getElementById('assistModal')?.classList.contains('hidden') === false) return;
  totalClickCount++;
  if (totalClickCount >= ASSIST_CLICK_THRESHOLD) {
    totalClickCount = 0;
    showAssistModal();
  }
});
```

- [ ] **Step 3: Add assist modal JS functions and event bindings**

Find the line `document.getElementById('tutorialPopupClose')?.addEventListener('click', hideTutorialPopup);` (currently around line 2403). Insert the following block immediately **after** that line:

```javascript
// =========================================================
// 協助 Modal (需要協助嗎？)
// =========================================================
function showAssistModal() {
  document.getElementById('assistModal')?.classList.remove('hidden');
  _showAssistPanel('main');
  trackInteractionEvent({ event_type: 'assist_modal_open', button_id: '' });
}

function hideAssistModal() {
  document.getElementById('assistModal')?.classList.add('hidden');
  trackInteractionEvent({ event_type: 'assist_modal_close', button_id: '' });
}

function _showAssistPanel(name) {
  const panels = { main: 'assistMain', recommend: 'assistRecommend', tutorial: 'assistTutorial' };
  Object.entries(panels).forEach(([key, id]) => {
    document.getElementById(id)?.classList.toggle('hidden', key !== name);
  });
}

async function _loadAssistRecommendations() {
  _showAssistPanel('recommend');
  trackInteractionEvent({ event_type: 'assist_recommend_open', button_id: 'assistBtnRecommend' });
  const listEl = document.getElementById('assistRecommendItems');
  const loadingEl = document.getElementById('assistRecommendLoading');
  if (loadingEl) loadingEl.classList.remove('hidden');
  [...(listEl?.children || [])].forEach(c => { if (c !== loadingEl) c.remove(); });

  try {
    const items = await api.assistRecommend(sessionId);
    if (loadingEl) loadingEl.classList.add('hidden');
    (Array.isArray(items) ? items : []).forEach(item => {
      listEl?.appendChild(_buildAssistItemCard(item));
    });
  } catch (e) {
    if (loadingEl) loadingEl.textContent = '推薦載入失敗，請重試';
  }
}

function _buildAssistItemCard(item) {
  const visual = getMenuVisual(item);
  const card = document.createElement('div');
  card.className = 'assist-item-card';
  const hasImg = Boolean(visual.image);
  card.innerHTML = `
    <div class="assist-item-photo">
      ${hasImg ? `<img src="${visual.image}" alt="${item.name || ''}"
        onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">` : ''}
      <span class="assist-item-emoji"${hasImg ? ' style="display:none"' : ''}>${visual.emoji || '🍔'}</span>
    </div>
    <div class="assist-item-info">
      <span class="assist-item-name">${item.name || '推薦餐點'}</span>
      <p class="assist-item-push">${item.push_text || ''}</p>
      <span class="assist-item-price">${formatItemPrice(item)}</span>
    </div>
    <button class="assist-item-add-btn" type="button">加入購物車</button>
  `;
  card.querySelector('.assist-item-add-btn').addEventListener('click', () => {
    hideAssistModal();
    showItemConfirmModal(item, 'assist_recommend');
  });
  return card;
}

document.getElementById('assistBackdrop')?.addEventListener('click', hideAssistModal);
document.getElementById('assistClose')?.addEventListener('click', hideAssistModal);
document.getElementById('assistBtnRecommend')?.addEventListener('click', _loadAssistRecommendations);
document.getElementById('assistBtnVoice')?.addEventListener('click', () => {
  hideAssistModal();
  trackInteractionEvent({ event_type: 'assist_voice_open', button_id: 'assistBtnVoice' });
  startAskRecording(document.getElementById('voiceAssistBtn'));
});
document.getElementById('assistBtnTutorial')?.addEventListener('click', () => {
  _showAssistPanel('tutorial');
  trackInteractionEvent({ event_type: 'assist_tutorial_open', button_id: 'assistBtnTutorial' });
});
document.getElementById('assistRecommendBack')?.addEventListener('click', () => _showAssistPanel('main'));
document.getElementById('assistRecommendCancel')?.addEventListener('click', hideAssistModal);
document.getElementById('assistTutorialBack')?.addEventListener('click', () => _showAssistPanel('main'));
document.getElementById('assistTutorialClose')?.addEventListener('click', hideAssistModal);
```

- [ ] **Step 4: Also add `#assistModal` to the existing excluded-targets string in `shouldTrackInvalidClick`**

Wait — we deleted `shouldTrackInvalidClick` in Step 1. So this is N/A. ✓

Instead, verify the one remaining place that references `#tutorialPopup,#choiceHesitationModal` for target exclusion (line 1905 in the original):

```bash
grep -n "startupOverlay.*tutorialPopup\|tutorialPopup.*choiceHesitation" UI_API/frontend/pos/app.js
```

If that line still exists (it's inside a different handler), add `#assistModal` to its exclusion list:

Find:
```javascript
  if (target.closest('#startupOverlay,#tutorialPopup,#choiceHesitationModal,#cancelGuidePopup,#voiceAssistOverlay,#voiceReplyBubble,#aiOverlayStack')) {
```

Replace with:
```javascript
  if (target.closest('#startupOverlay,#tutorialPopup,#choiceHesitationModal,#assistModal,#cancelGuidePopup,#voiceAssistOverlay,#voiceReplyBubble,#aiOverlayStack')) {
```

- [ ] **Step 5: Syntax check**

```bash
node --check UI_API/frontend/pos/app.js && echo "OK"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add UI_API/frontend/pos/app.js
git commit -m "feat(assist): replace invalid-click logic with 50-click counter + assist modal JS"
```

---

## Task 6: Verification

- [ ] **Step 1: Full syntax check all modified files**

```bash
cd UI_API
python3 -m py_compile backend/services/ai_push_service.py
python3 -m py_compile backend/routes/ai_push_routes.py
node --check frontend/shared/api.js
node --check frontend/pos/app.js
echo "All OK"
```

Expected: `All OK`

- [ ] **Step 2: Smoke-test backend endpoint (server must be running)**

```bash
curl -s "http://127.0.0.1:8000/api/assist_recommend?session_id=test" | python3 -m json.tool | head -20
```

Expected: JSON array with 3 objects, each having `id`, `name`, `price`, `push_text`.

- [ ] **Step 3: Manual UI test checklist**

Start the server (`cd UI_API && python main.py`) and open `http://127.0.0.1:8000`:

1. Click anywhere on the POS page 50 times → `#assistModal` appears with "需要協助嗎？" and 3 buttons
2. Click backdrop → modal closes
3. Reopen (click 50 more times) → click "推薦餐點" → loading spinner shows → 3 item cards appear with name, push text, price, "加入購物車" button
4. Click "加入購物車" on an item → modal closes → item confirm modal opens (source: `assist_recommend`)
5. Reopen → click "語音模式" → modal closes → voice overlay opens
6. Reopen → click "操作教學" → tutorial panel slides in with 3 steps, "返回" button works
7. Reopen → click "不需要，繼續點餐" → modal closes
8. Verify `#tutorialPopup` (original top-slide) still works via DevTools: `showTutorialPopup()` in console → top-slide popup appears

- [ ] **Step 4: Final commit (if any last-minute fixes)**

```bash
git add -p
git commit -m "fix(assist): final corrections after manual test"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✓ §1 Delete old logic → Task 5 Step 1
- ✓ §2 Click counter (50, reset on show) → Task 5 Step 2
- ✓ §3 HTML structure (3 panels) → Task 3
- ✓ §4 Item card template (JS-generated) → Task 5 Step 3 `_buildAssistItemCard`
- ✓ §5 CSS → Task 4
- ✓ §6 JS functions (show/hide/panels/load) → Task 5 Step 3
- ✓ §7 Backend generate_three + route → Task 1
- ✓ §7.3 api.js assistRecommend → Task 2
- ✓ §8 Interaction event tracking → embedded in JS functions (Task 5 Step 3)
- ✓ Note: `#assistModal` added to excluded-targets string → Task 5 Step 4

**No placeholders found.**

**Type consistency:** `_showAssistPanel('main'|'recommend'|'tutorial')` used consistently. `generate_three` signature matches call in route. `assistRecommend(sessionId)` matches usage in `_loadAssistRecommendations`.
