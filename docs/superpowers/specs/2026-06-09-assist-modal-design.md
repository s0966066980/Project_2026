# 協助選擇 Modal 設計（取代「如何點餐」觸發邏輯）

**日期：** 2026-06-09
**範圍：** `frontend/pos/index.html`、`frontend/pos/app.js`、`frontend/shared/styles.css`、`frontend/shared/api.js`、`backend/routes/ai_push_routes.py`、`backend/services/ai_push_service.py`

---

## 一、移除原有「如何點餐」觸發邏輯

刪除以下內容（`app.js`）：

| 刪除對象 | 說明 |
|---|---|
| `INVALID_CLICK_THRESHOLD` / `INVALID_CLICK_WINDOW_MS` / `INVALID_CLICK_MIN_DWELL_MS` / `INVALID_CLICK_RECENT_ACTION_GRACE_MS` | 常數 |
| `invalidClickTimestamps` | 陣列 |
| `shouldTrackInvalidClick(target)` | 函式 |
| document click handler 中呼叫 `showTutorialPopup()` 的整個 `if (shouldTrackInvalidClick(...))` 區塊 | 邏輯 |

> `showTutorialPopup()` 本身**保留**，因為 intervention `operation_hint` 仍會呼叫它。

---

## 二、全域點擊計數器

```javascript
let totalClickCount = 0;
const ASSIST_CLICK_THRESHOLD = 50;
```

在 document `click` handler 最頂層新增：

```javascript
// 協助 Modal 點擊計數（排除 modal 開啟期間）
const modalOpen = document.getElementById('assistModal')
    && !document.getElementById('assistModal').classList.contains('hidden');
if (!modalOpen) {
  totalClickCount++;
  if (totalClickCount >= ASSIST_CLICK_THRESHOLD) {
    totalClickCount = 0;
    showAssistModal();
  }
}
```

計數器在 `showAssistModal()` 被呼叫時歸零（已含在條件內）。modal 開啟期間點擊不計入。

---

## 三、HTML 結構（`index.html`）

加入 `#choiceHesitationModal` 之後：

```html
<!-- ============ Assist Modal ============ -->
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
        <!-- 載入中 -->
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

---

## 四、餐點卡片範本（由 JS 動態產生）

```html
<div class="assist-item-card">
  <div class="assist-item-photo">
    <img src="..." alt="餐點名稱" onerror="...">
    <span class="assist-item-emoji">🍔</span>  <!-- image 失敗 fallback -->
  </div>
  <div class="assist-item-info">
    <strong class="assist-item-name">大麥克</strong>
    <p class="assist-item-push">...</p>   <!-- push_text 推銷詞 -->
    <span class="assist-item-price">$99</span>
  </div>
  <button class="assist-item-add-btn" type="button" data-id="MCD001">
    加入購物車
  </button>
</div>
```

---

## 五、CSS 設計重點（`styles.css`）

```
.assist-modal       → position:fixed; inset:0; z-index:9250; display:flex; align-items:center; justify-content:center;
.assist-backdrop    → position:absolute; inset:0; background:rgba(0,0,0,0.72); backdrop-filter:blur(5px)
.assist-card        → position:relative; z-index:1; width:min(92vw,480px); border-radius:28px; background:#fff; padding:32px 28px 24px; display:flex; flex-direction:column; gap:20px; animation: assistCardIn 0.22s ease-out
.assist-title       → font-size:22px; font-weight:800; text-align:center; color:#2a2119
.assist-buttons     → display:flex; flex-direction:column; gap:12px
.assist-option-btn  → display:flex; align-items:center; gap:14px; padding:16px 20px; border-radius:16px; background:#f5f1ea; border:2px solid transparent; font-size:16px; font-weight:700; cursor:pointer; transition:background 0.15s, border-color 0.15s
.assist-option-btn:hover → background:#ffecd0; border-color:#ffc72c
.assist-option-btn i → font-size:20px; color:#c8102e; width:28px; text-align:center
.assist-close-link  → text-align:center; color:#8494b0; font-size:13px; background:none; border:none; cursor:pointer; padding:4px
.assist-back-btn    → background:none; border:none; font-size:18px; color:#4a3b30; cursor:pointer; padding:4px 8px
.assist-panel-header → display:flex; align-items:center; gap:10px; margin-bottom:12px
.assist-panel-title → font-size:17px; font-weight:800; color:#2a2119
.assist-recommend-list → display:flex; flex-direction:column; gap:12px; max-height:60vh; overflow-y:auto
.assist-item-card   → display:flex; align-items:center; gap:14px; padding:12px; border-radius:16px; background:#f9f7f3; border:1.5px solid #ede7da
.assist-item-photo  → width:64px; height:64px; border-radius:12px; overflow:hidden; flex-shrink:0; background:#ede7da; position:relative
.assist-item-photo img → width:100%; height:100%; object-fit:cover
.assist-item-emoji  → position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:28px
.assist-item-info   → flex:1; min-width:0
.assist-item-name   → font-size:14px; font-weight:800; display:block; margin-bottom:3px
.assist-item-push   → font-size:12px; color:#8494b0; margin:0 0 4px; line-height:1.4
.assist-item-price  → font-size:13px; font-weight:700; color:#c8102e
.assist-item-add-btn → padding:8px 14px; border-radius:12px; background:#ffc72c; border:none; font-size:13px; font-weight:700; cursor:pointer; flex-shrink:0; white-space:nowrap
@keyframes assistCardIn → from{opacity:0;transform:translateY(16px) scale(0.98)} to{opacity:1;transform:none}
```

---

## 六、JS 函式（`app.js`）

### 6.1 Modal 開關

```javascript
function showAssistModal() {
  document.getElementById('assistModal')?.classList.remove('hidden');
  showAssistPanel('main');
}

function hideAssistModal() {
  document.getElementById('assistModal')?.classList.add('hidden');
}

function showAssistPanel(name) {
  // name: 'main' | 'recommend' | 'tutorial'
  ['assistMain','assistRecommend','assistTutorial'].forEach(id => {
    document.getElementById(id)?.classList.toggle('hidden', id !== `assist${name.charAt(0).toUpperCase()+name.slice(1)}`);
  });
}
```

### 6.2 推薦餐點 panel

```javascript
async function loadAssistRecommendations() {
  showAssistPanel('recommend');
  const listEl = document.getElementById('assistRecommendItems');
  const loadingEl = document.getElementById('assistRecommendLoading');
  if (loadingEl) loadingEl.classList.remove('hidden');
  // 清除舊卡片
  [...(listEl?.children || [])].forEach(c => { if (c !== loadingEl) c.remove(); });

  try {
    const items = await api.assistRecommend(sessionId);
    if (loadingEl) loadingEl.classList.add('hidden');
    (items || []).forEach(item => {
      const card = buildAssistItemCard(item);
      listEl?.appendChild(card);
    });
  } catch (e) {
    if (loadingEl) loadingEl.textContent = '推薦載入失敗，請重試';
  }
}

function buildAssistItemCard(item) {
  const visual = getMenuVisual(item);  // 複用現有函式
  const card = document.createElement('div');
  card.className = 'assist-item-card';
  card.innerHTML = `
    <div class="assist-item-photo">
      ${visual.image
        ? `<img src="${visual.image}" alt="${item.name || ''}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`
        : ''}
      <span class="assist-item-emoji" style="${visual.image ? 'display:none' : ''}">${visual.emoji || '🍔'}</span>
    </div>
    <div class="assist-item-info">
      <strong class="assist-item-name">${item.name || '推薦餐點'}</strong>
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
```

### 6.3 事件綁定

```javascript
document.getElementById('assistBackdrop')?.addEventListener('click', hideAssistModal);
document.getElementById('assistClose')?.addEventListener('click', hideAssistModal);
document.getElementById('assistBtnRecommend')?.addEventListener('click', loadAssistRecommendations);
document.getElementById('assistBtnVoice')?.addEventListener('click', () => {
  hideAssistModal();
  startAskRecording(document.getElementById('voiceAssistBtn'));
});
document.getElementById('assistBtnTutorial')?.addEventListener('click', () => showAssistPanel('tutorial'));
document.getElementById('assistRecommendBack')?.addEventListener('click', () => showAssistPanel('main'));
document.getElementById('assistRecommendCancel')?.addEventListener('click', hideAssistModal);
document.getElementById('assistTutorialBack')?.addEventListener('click', () => showAssistPanel('main'));
document.getElementById('assistTutorialClose')?.addEventListener('click', hideAssistModal);
```

---

## 七、後端新 API

### 7.1 新函式（`ai_push_service.py`）

```python
async def generate_three(session_id: str, ollama_semaphore) -> list[dict]:
    """呼叫 generate() 三次，累積 exclude_ids 確保不重複，回傳含 name/price/image 的完整項目清單。"""
    items_map = {i["id"]: i for i in await _get_menu_cached() if i.get("id")}
    results = []
    exclude = []
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

### 7.2 新路由（`ai_push_routes.py`）

```python
@router.get("/assist_recommend")
async def handle_assist_recommend(session_id: str):
    return await ai_push_service.generate_three(
        session_id=session_id,
        ollama_semaphore=deps["ollama_semaphore"],
    )
```

### 7.3 新 API 函式（`api.js`）

```javascript
assistRecommend(sessionId) {
  return fetch(`/api/assist_recommend?session_id=${encodeURIComponent(sessionId)}`)
    .then(r => r.json());
}
```

---

## 八、互動事件追蹤

| 事件 | `event_type` | `button_id` |
|---|---|---|
| 開啟協助 modal | `assist_modal_open` | — |
| 點「推薦餐點」 | `assist_recommend_open` | `assistBtnRecommend` |
| 點「語音模式」 | `assist_voice_open` | `assistBtnVoice` |
| 點「操作教學」 | `assist_tutorial_open` | `assistBtnTutorial` |
| 加入購物車（來源） | source: `assist_recommend` | `assist-item-add-btn` |
| 關閉 modal | `assist_modal_close` | — |

---

## 九、不在本次範圍

- 後台開關（本功能預設開啟，無需 admin toggle）
- Emotion-LLaMA 整合（後續可加）
- `totalClickCount` 持久化（session 內重設即可）
