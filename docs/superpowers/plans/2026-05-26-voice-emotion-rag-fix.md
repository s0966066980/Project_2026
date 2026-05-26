# Voice × Emotion × RAG 修復 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復語音模式 AI 回覆失效、整合 emotion 快照到語音流程、推播間隔改 10 秒、emotion 記錄在結帳時寫入 RAG、重建 RAG 知識庫。

**Architecture:** 方案 A 輕量快照整合：語音按鈕按下時非同步觸發 1 秒 emotion 快照 → 結果存入 emotion_cache → voice_service 讀取 → 每次語音對話後累積至 sessionEmotionLog → 結帳時 POST 批次寫入 RAG。

**Tech Stack:** FastAPI (Python 3.x)、Vanilla JS、Ollama (qwen3.5:4b)、ChromaDB、MediaRecorder API

---

## 檔案異動總覽

| 檔案 | 動作 | 說明 |
|---|---|---|
| `UI_API/config.py` | Modify | VOICE_ASSIST_MODEL 改 qwen3.5:4b，RECOMMEND_INTERVAL_SEC 改 10，AUTO_RECOMMEND_MIN_GAP_SEC 改 8 |
| `UI_API/services/voice_assist_service.py` | Modify | model fallback 邏輯 |
| `UI_API/routes/core_routes.py` | Modify | checkout 接收 emotion_session_log，呼叫 RAG 寫入 |
| `UI_API/database.py` | Modify | 新增 save_voice_emotion_to_rag() |
| `UI_API/static/app.js` | Modify | emotion snapshot on voice start、sessionEmotionLog、RECOMMEND_INTERVAL 改 10 |
| `UI_API/seeds/__init__.py` | Create | 空檔 |
| `UI_API/seeds/rag_knowledge.py` | Create | 四類 RAG 知識常數 |
| `UI_API/main.py` | Modify | 啟動時初始化 RAG seeds |

---

## Task 1：修正語音模型名稱與 AI 回覆 Bug

**Files:**
- Modify: `UI_API/config.py:90`
- Modify: `UI_API/services/voice_assist_service.py:43`

### 問題說明
`DEFAULT_SETTINGS["VOICE_ASSIST_MODEL"]` 預設為 `"qwen3.5:9b"`，但系統只裝了 `"qwen3.5:4b"`。Ollama 找不到模型時靜默失敗，`ask_ollama` 回傳 error dict，voice service 走 fallback 路徑，回應沒有 TTS 音訊，前端判定為失敗。

- [ ] **Step 1：修正 config.py 預設模型名稱**

在 `UI_API/config.py` 第 90 行，將：
```python
    "VOICE_ASSIST_MODEL": "qwen3.5:9b",  # 語音協助專用模型
```
改為：
```python
    "VOICE_ASSIST_MODEL": "qwen3.5:4b",  # 語音協助專用模型
```

- [ ] **Step 2：在 voice_assist_service 加入 model fallback**

在 `UI_API/services/voice_assist_service.py` 第 43 行，將：
```python
    model = config.get("VOICE_ASSIST_MODEL", "qwen3.5:9b")
```
改為：
```python
    model = config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b")
    fallback_model = config.get("MODEL_NAME", "qwen3.5:4b")
```

並在第 126 行的 `async with ollama_semaphore:` 區塊中，將：
```python
    async with ollama_semaphore:
        result = await loop.run_in_executor(
            None, ai_services.ask_ollama, system_prompt, user_prompt, "", model
        )
```
改為：
```python
    async with ollama_semaphore:
        result = await loop.run_in_executor(
            None, ai_services.ask_ollama, system_prompt, user_prompt, "", model
        )
        # 若指定模型不存在，以 fallback_model 重試一次
        if isinstance(result, dict) and "error" in result and model != fallback_model:
            result = await loop.run_in_executor(
                None, ai_services.ask_ollama, system_prompt, user_prompt, "", fallback_model
            )
```

- [ ] **Step 3：語法驗證**

```bash
cd /home/oliver/Project_2026/UI_API
python3 -m py_compile config.py services/voice_assist_service.py
echo "OK"
```
預期輸出：`OK`

- [ ] **Step 4：Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/config.py UI_API/services/voice_assist_service.py
git commit -m "fix: voice model fallback to qwen3.5:4b, add retry on model-not-found"
```

---

## Task 2：AI 推播間隔改為 10 秒

**Files:**
- Modify: `UI_API/config.py:128-129`
- Modify: `UI_API/static/app.js:246-248`

- [ ] **Step 1：修正 config.py 預設推播間隔**

在 `UI_API/config.py` 找到以下兩行：
```python
    "RECOMMEND_INTERVAL_SEC": 30,
    "RECOMMEND_AFTER_ASK_DELAY_MS": 1200,
    "AUTO_RECOMMEND_MIN_GAP_SEC": 20,
```
改為：
```python
    "RECOMMEND_INTERVAL_SEC": 10,
    "RECOMMEND_AFTER_ASK_DELAY_MS": 1200,
    "AUTO_RECOMMEND_MIN_GAP_SEC": 8,
```

- [ ] **Step 2：修正 app.js 前端初始值**

在 `UI_API/static/app.js` 找到 `runtimeSettings` 物件（第 241 行附近）：
```javascript
let runtimeSettings = {
  PERFORMANCE_MODE: 'balanced',
  EMOTION_PING_INTERVAL_SEC: 15,
  EMOTION_RECORD_MS: 900,
  YOLO_FRAME_INTERVAL_MS: 650,
  RECOMMEND_INTERVAL_SEC: 30,
  RECOMMEND_AFTER_ASK_DELAY_MS: 1200,
  AUTO_RECOMMEND_MIN_GAP_SEC: 20,
```
改為：
```javascript
let runtimeSettings = {
  PERFORMANCE_MODE: 'balanced',
  EMOTION_PING_INTERVAL_SEC: 15,
  EMOTION_RECORD_MS: 900,
  YOLO_FRAME_INTERVAL_MS: 650,
  RECOMMEND_INTERVAL_SEC: 10,
  RECOMMEND_AFTER_ASK_DELAY_MS: 1200,
  AUTO_RECOMMEND_MIN_GAP_SEC: 8,
```

- [ ] **Step 3：JS 語法驗證**

```bash
node --check /home/oliver/Project_2026/UI_API/static/app.js && echo "OK"
```
預期輸出：`OK`

- [ ] **Step 4：Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/config.py UI_API/static/app.js
git commit -m "feat: reduce recommend interval to 10s, min-gap to 8s"
```

---

## Task 3：語音按下時觸發 Emotion 快照

**Files:**
- Modify: `UI_API/static/app.js` — 新增 `captureEmotionSnapshotForVoice()`、在 `startAskRecording` 呼叫

### 設計說明
語音按鈕 `pointerdown` 時，非同步（不 await）執行 1 秒短片段擷取並送至 `/api/ping_state`。
結果存入後端 `emotion_cache`，下次語音呼叫 `/api/ask` 時 `voice_routes.py` 會自動讀取並傳入 `handle_voice_assist`。

需要攝影機串流（`stream` 含 video track）才能執行。若無 video track 則靜默跳過（不影響語音錄音）。

- [ ] **Step 1：在 app.js 新增 emotion snapshot 函式**

在 `UI_API/static/app.js` 中，找到 `function startAskRecording(sourceBtn) {` 這行（第 1721 行附近），在其**上方**插入以下函式：

```javascript
// 語音模式開始時非同步捕捉 emotion 快照（不阻塞錄音）
function captureEmotionSnapshotForVoice() {
  if (!stream || !stream.getVideoTracks().length) return;
  if (!getFeatures().emotion) return;
  if (!isPosActive()) return;
  const rec = createVideoRecorder(stream);
  const chunks = [];
  rec.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
  rec.onstop = async () => {
    const blob = new Blob(chunks, { type: 'video/webm' });
    if (blob.size < 2000) return;
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('video', blob, 'voice_emotion_snapshot.webm');
    fd.append('detect_only', 'false');
    try {
      const d = await api.pingState(fd);
      if (d.person_check) updateEmotionDetectionOverlay(d.person_check);
    } catch { /* 非關鍵路徑，靜默忽略 */ }
  };
  try {
    rec.start();
    setTimeout(() => { if (rec.state === 'recording') rec.stop(); }, 1000);
  } catch { /* 無攝影機時靜默跳過 */ }
}
```

- [ ] **Step 2：在 startAskRecording 中呼叫**

找到 `function startAskRecording(sourceBtn) {` 內部，找到：
```javascript
  if (askRecorder && askRecorder.state === 'inactive') {
    voiceAssistRecommendFallbackUntil = Date.now() + 45000;
    trackInteractionEvent({
```
在 `voiceAssistRecommendFallbackUntil` 那行**上方**插入：
```javascript
    captureEmotionSnapshotForVoice();
```

完整區塊應變成：
```javascript
  if (askRecorder && askRecorder.state === 'inactive') {
    captureEmotionSnapshotForVoice();
    voiceAssistRecommendFallbackUntil = Date.now() + 45000;
    trackInteractionEvent({
```

- [ ] **Step 3：JS 語法驗證**

```bash
node --check /home/oliver/Project_2026/UI_API/static/app.js && echo "OK"
```
預期輸出：`OK`

- [ ] **Step 4：Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/static/app.js
git commit -m "feat: capture emotion snapshot when voice mode starts"
```

---

## Task 4：Session Emotion Log 累積與結帳時寫入 RAG

**Files:**
- Modify: `UI_API/static/app.js` — sessionEmotionLog、推送邏輯、checkout FormData
- Modify: `UI_API/routes/core_routes.py` — checkout 接收 emotion_session_log
- Modify: `UI_API/database.py` — 新增 save_voice_emotion_to_rag()

### 4a：前端累積 sessionEmotionLog

- [ ] **Step 1：宣告 sessionEmotionLog 陣列**

在 `UI_API/static/app.js` 頂部狀態宣告區（`let stream, askRecorder;` 附近，約第 50 行），找到：
```javascript
let stream, askRecorder;
```
在其**下一行**加入：
```javascript
let sessionEmotionLog = [];
```

- [ ] **Step 2：語音回應完成後 push 到 sessionEmotionLog**

在 `askRecorder.onstop` 的成功處理區，找到：
```javascript
      if (data.status === 'success') {
        lastVoiceText = data.user_text || lastVoiceText;
        if (data.audio_base64) playVoice(data.audio_base64);
        showVoiceBubble(data);
```
在 `showVoiceBubble(data);` **後面**插入：
```javascript
        // 累積 session 情緒記錄，結帳時批次寫 RAG
        if (lastEmotionStructured) {
          sessionEmotionLog.push({
            ts: new Date().toISOString(),
            emotion_label: lastEmotionStructured.emotion_label || lastEmotionStructured.emotion_display || '',
            emotion_evidence: lastEmotionStructured.emotion_evidence || '',
            user_text: data.user_text || '',
            ai_response: data.ai_response || '',
          });
        }
```

- [ ] **Step 3：結帳時附上 emotion_session_log**

在 `writeCheckoutLog` 函式（約第 2914 行）中，找到：
```javascript
async function writeCheckoutLog(cartIds = []) {
  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('pushed_ids', JSON.stringify(Array.from(sessionPushedIds)));
  fd.append('cart_ids', JSON.stringify(cartIds));
```
在 `cart_ids` append **後面**插入：
```javascript
  if (sessionEmotionLog.length > 0) {
    fd.append('emotion_session_log', JSON.stringify(sessionEmotionLog));
  }
```

- [ ] **Step 4：JS 語法驗證**

```bash
node --check /home/oliver/Project_2026/UI_API/static/app.js && echo "OK"
```
預期輸出：`OK`

### 4b：後端接收與 RAG 寫入

- [ ] **Step 5：database.py 新增 save_voice_emotion_to_rag()**

在 `UI_API/database.py` 末尾加入以下函式：

```python
def save_voice_emotion_to_rag(session_id: str, emotion_log: list[dict]) -> int:
    """將 session 情緒對話記錄批次寫入 RAG（source_type=session_emotion）。"""
    if not emotion_log:
        return 0
    now = _now_iso()
    lines = [f"Session: {session_id}  記錄時間: {now}"]
    for entry in emotion_log:
        ts = entry.get("ts", "")
        label = entry.get("emotion_label", "")
        evidence = entry.get("emotion_evidence", "")
        user_text = entry.get("user_text", "")
        ai_response = entry.get("ai_response", "")
        lines.append(
            f"[{ts}] 情緒={label} | 依據={evidence} | "
            f"顧客={user_text} | AI={ai_response}"
        )
    text = "\n".join(lines)
    source_id = f"session_emotion_{session_id}_{int(time.time())}"
    review_result = {
        "status": "approved",
        "reviewed_text": text,
        "notes": "voice session emotion auto-saved at checkout",
    }
    upsert_reviewed_rag_doc("session_emotion", source_id, text, review_result)
    return 1
```

- [ ] **Step 6：core_routes.py checkout 接收 emotion_session_log**

在 `UI_API/routes/core_routes.py` 的 `process_checkout` endpoint，找到：
```python
    @router.post("/api/checkout")
    async def process_checkout(
        session_id: str = Form(...),
        pushed_ids: str = Form(...),
        cart_ids: str = Form(...),
    ):
```
改為：
```python
    @router.post("/api/checkout")
    async def process_checkout(
        session_id: str = Form(...),
        pushed_ids: str = Form(...),
        cart_ids: str = Form(...),
        emotion_session_log: str = Form(default=""),
    ):
```

然後在函式最末、`return {"status": "success", ...}` **之前**，找到：
```python
        session_repository.archive_session(session_id)
        deps["emotion_cache"].pop(session_id, None)
```
在其**上方**插入：
```python
        # 批次寫入 session 情緒記錄到 RAG
        if emotion_session_log:
            try:
                emotion_log_list = json.loads(emotion_session_log)
                if isinstance(emotion_log_list, list) and emotion_log_list:
                    saved = await asyncio.to_thread(
                        database.save_voice_emotion_to_rag, session_id, emotion_log_list
                    )
                    if saved:
                        deps["schedule_rag_rebuild"]("voice emotion session log")
            except Exception as _e:
                print(f"⚠️ emotion session log RAG 寫入失敗: {_e}")
```

- [ ] **Step 7：語法驗證**

```bash
cd /home/oliver/Project_2026/UI_API
python3 -m py_compile database.py routes/core_routes.py
echo "OK"
```
預期輸出：`OK`

- [ ] **Step 8：Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/static/app.js UI_API/database.py UI_API/routes/core_routes.py
git commit -m "feat: accumulate voice emotion log and save to RAG on checkout"
```

---

## Task 5：RAG 清理與知識種子

**Files:**
- Create: `UI_API/seeds/__init__.py`
- Create: `UI_API/seeds/rag_knowledge.py`
- Modify: `UI_API/main.py` — 啟動時初始化 RAG seeds

### 5a：建立 seeds 模組

- [ ] **Step 1：建立 `UI_API/seeds/__init__.py`（空檔）**

```bash
touch /home/oliver/Project_2026/UI_API/seeds/__init__.py
```

- [ ] **Step 2：建立 `UI_API/seeds/rag_knowledge.py`**

建立 `/home/oliver/Project_2026/UI_API/seeds/rag_knowledge.py`，內容如下（每個 `RAG_SEEDS` 項目是一筆知識文件）：

```python
"""
RAG 知識種子 — 啟動時寫入，已存在則跳過。
source_id 以 seed_ 開頭作為識別，不覆蓋 PDF chunks 或手動 RAG。
"""

RAG_SEEDS = [
    # ============================================================
    # 1. 麥當勞台灣點餐 Q&A
    # ============================================================
    {
        "source_id": "seed_mcd_tw_ordering_qa_v1",
        "source_type": "manual",
        "text": """麥當勞台灣自助點餐常見問題與解答

Q: 套餐可以換餐嗎？
A: 超值全餐的主食、飲料通常可以在同分類中替換，例如將可樂換成雪碧或礦泉水，或將薯條換成沙拉。請在點餐畫面選擇替換選項。

Q: 外帶和內用價格一樣嗎？
A: 台灣麥當勞外帶與內用價格相同，無額外加收費用。

Q: 等餐時間大概多久？
A: 一般餐點約 3–5 分鐘，高峰期或特殊餐點可能需要 8–10 分鐘。部分餐點（如麥辣雞腿堡）製作時間較長。

Q: 可以指定不加某種配料嗎？
A: 自助點餐機目前不支援個別配料調整，如需特殊需求請至櫃檯由服務人員協助。

Q: 兒童餐（Happy Meal）包含什麼？
A: Happy Meal 包含主餐（漢堡或麥克雞塊）、配餐（薯條或蘋果片）、飲料（牛奶或蘋果汁），以及一份玩具。

Q: 分享盒適合幾個人吃？
A: 麥當勞分享盒通常適合 2–4 人分享，內含多件炸雞、薯條與醬料，適合聚餐或家庭用餐。

Q: 可以使用信用卡付款嗎？
A: 自助點餐機支援信用卡、悠遊卡、一卡通、Apple Pay、Google Pay 等行動支付。現金付款請至櫃檯。

Q: 可以修改已加入購物車的餐點嗎？
A: 可以。在購物車畫面，點擊餐點旁的加減號即可調整數量，或點擊刪除圖示移除該項目。""",
    },

    # ============================================================
    # 2. 麥當勞台灣優惠活動規則
    # ============================================================
    {
        "source_id": "seed_mcd_tw_promotions_v1",
        "source_type": "manual",
        "text": """麥當勞台灣優惠活動規則說明

麥當勞 App 優惠券使用方式：
1. 下載麥當勞 App 並登入帳號
2. 於 App 內領取優惠券
3. 在自助點餐機點餐完成後，前往櫃檯結帳時出示 App 優惠券 QR Code
4. 部分優惠券可直接在自助點餐機輸入優惠碼使用

麥克雞塊買一送一活動：
- 活動期間每日限特定時段（通常為午餐或晚餐時段）
- 每筆訂單限用一次
- 須透過 App 優惠券兌換，不接受口頭要求

麥當勞點點卡（集點）規則：
- 每消費 NT$1 積 1 點
- 使用 App 或實體點點卡均可集點
- 積點可兌換免費餐點或折扣（兌換品項依當期活動為準）
- 點數不可轉讓，有效期限通常為一年

1+1 星級點活動：
- 從 1+1 星級點分類選擇任兩件組合
- 組合享有特定優惠價格
- 品項每日可能不同，請以當日菜單為準

注意事項：
- 優惠活動有期限，詳細規則請以麥當勞官方 App 或官網公告為準
- 部分優惠不可與其他折扣併用""",
    },

    # ============================================================
    # 3. 自助點餐機操作使用教學
    # ============================================================
    {
        "source_id": "seed_kiosk_operation_guide_v1",
        "source_type": "manual",
        "text": """麥當勞自助點餐機操作教學

【開始點餐】
1. 觸碰螢幕上的「開始點餐」按鈕
2. 選擇語言（繁體中文 / English）
3. 從畫面左側選擇餐點類別（推薦套餐、超值全餐、飲料甜點等）

【加入購物車】
- 點擊餐點圖片或右側的「+」號即可加入購物車
- 購物車圖示在畫面右下角，顯示目前品項數量與金額

【修改訂單】
- 點擊右下角購物車圖示進入購物車
- 使用「+/-」調整數量，或點擊垃圾桶圖示刪除品項
- 點「繼續點餐」可回到菜單繼續選擇

【結帳付款】
- 確認購物車內容後，點擊「結帳去」
- 選擇用餐方式（內用 / 外帶）
- 選擇付款方式（信用卡快速結帳 / 至櫃檯付款）
- 信用卡：跟隨畫面指示完成感應付款
- 至櫃檯：列印取餐號碼，持號碼至櫃檯付款後取餐

【語音協助】
- 點擊畫面下方麥克風按鈕啟動語音模式
- 說出想點的餐點（例如：「我要一個大麥克套餐」）
- 也可詢問菜單、價格或推薦餐點
- 點擊 X 結束語音模式

【切換語言】
- 點擊畫面左上角地球圖示可切換中文/英文介面

【取消訂單】
- 點擊「取消整單訂單」可清空購物車並重新開始""",
    },

    # ============================================================
    # 4. 餐飲通用知識（過敏原、熱量概念）
    # ============================================================
    {
        "source_id": "seed_food_general_knowledge_v1",
        "source_type": "manual",
        "text": """餐飲通用知識 — 過敏原與熱量說明

【常見過敏原說明】
麥當勞餐點可能含有以下常見過敏原，有食物過敏疑慮的顧客請特別注意：

- 小麥（麩質）：麵包、漢堡皮、炸粉等幾乎所有炸物與堡類均含有
- 乳製品（奶）：起司堡、奶昔、McCafé 咖啡系列、鬆餅等含有牛奶成分
- 雞蛋：部分醬料（如美乃滋）、某些早餐品項含蛋
- 大豆：部分炸油與醬料含大豆成分
- 芝麻：部分麵包含芝麻

嚴重過敏者請向服務人員確認最新過敏原資訊，因廚房共用設備，可能有交叉污染風險。

【熱量概念】
- 一般成年人每日建議熱量攝取約 2000 大卡（依個人體重與活動量而異）
- 麥當勞超值全餐套餐（含主食、薯條、飲料）熱量約 800–1200 大卡
- 大麥克漢堡約 540 大卡、麥香魚約 380 大卡、麥辣雞腿堡約 500 大卡
- 大薯約 490 大卡、中薯約 340 大卡
- 可樂（中杯）約 210 大卡；零卡可樂熱量幾乎為零
- McCafé 拿鐵（中杯，全脂）約 190 大卡

選擇低熱量組合建議：用沙拉替換薯條、選擇飲料改為無糖飲品或礦泉水。

【套餐組成說明】
- 超值全餐 = 主食（漢堡類）+ 配餐（薯條）+ 飲料
- 極選系列 = 精選主食（通常為安格斯牛肉或特色雞肉）+ 配餐 + 飲料，價格較超值全餐高
- 超值配餐 = 僅配餐類（薯條、沙拉、玉米湯等），不含主食
- Happy Meal = 兒童餐，含小份主食、小份配餐、兒童飲料與玩具

【素食者注意事項】
麥當勞目前在台灣無認證素食品項，所有餐點在共用設備上製作，不適合嚴格素食者。""",
    },
]
```

- [ ] **Step 3：語法驗證**

```bash
cd /home/oliver/Project_2026/UI_API
python3 -m py_compile seeds/rag_knowledge.py
echo "OK"
```
預期輸出：`OK`

### 5b：main.py 啟動時初始化 RAG seeds 與 PDF

- [ ] **Step 4：database.py 新增 seed_rag_docs()**

在 `UI_API/database.py` 末尾（`save_voice_emotion_to_rag` 之後）加入：

```python
def seed_rag_docs(seeds: list[dict]) -> int:
    """將知識種子寫入 RAG，已存在（source_id 相同）則跳過。回傳新增筆數。"""
    existing_ids = {doc.get("source_id") for doc in get_rag_docs() if not doc.get("deleted")}
    added = 0
    for seed in seeds:
        source_id = seed.get("source_id", "")
        if not source_id or source_id in existing_ids:
            continue
        text = seed.get("text", "").strip()
        if not text:
            continue
        review_result = {
            "status": "approved",
            "reviewed_text": text,
            "notes": "auto-seeded knowledge base entry",
        }
        upsert_reviewed_rag_doc(
            seed.get("source_type", "manual"),
            source_id,
            text,
            review_result,
        )
        added += 1
    return added
```

- [ ] **Step 5：查看現有 RAG docs 與 PDF 路徑確認**

```bash
ls /home/oliver/Project_2026/UI_API/mcdonalds_tw_extra_value_meals_rag.pdf
cat /home/oliver/Project_2026/UI_API/learning_data/rag_docs.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'目前 RAG 筆數: {len(d)}')"
```
預期：PDF 存在、RAG 筆數為 0（空的）。

- [ ] **Step 6：main.py 加入 RAG 初始化函式**

在 `UI_API/main.py` 的 import 區，找到：
```python
import config
import ai_services
import database
```
在其**下方**加入：
```python
from seeds.rag_knowledge import RAG_SEEDS
```

然後找到 `async def _background_init_once():` 函式中的 `_init_rag` 內部函式：
```python
    async def _init_rag():
        try:
            await loop.run_in_executor(None, database.init_rag_system)
            print("✅ RAG 系統背景初始化完成")
        except Exception as e:
            print(f"❌ RAG 背景初始化失敗: {e}")
```
改為：
```python
    async def _init_rag():
        try:
            await loop.run_in_executor(None, database.init_rag_system)
            print("✅ RAG 系統背景初始化完成")
        except Exception as e:
            print(f"❌ RAG 背景初始化失敗: {e}")
            return

        # 種子知識注入（首次啟動或 RAG 為空時）
        try:
            added = await loop.run_in_executor(None, database.seed_rag_docs, RAG_SEEDS)
            if added > 0:
                print(f"✅ RAG 知識種子注入：新增 {added} 筆")
                await loop.run_in_executor(None, database.init_rag_system, True)
                print("✅ RAG 重建完成（含種子知識）")
            else:
                print("✅ RAG 種子已存在，跳過注入")
        except Exception as e:
            print(f"⚠️ RAG 種子注入失敗（不影響系統運作）: {e}")
```

- [ ] **Step 7：語法驗證**

```bash
cd /home/oliver/Project_2026/UI_API
python3 -m py_compile main.py database.py
echo "OK"
```
預期輸出：`OK`

- [ ] **Step 8：Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/seeds/__init__.py UI_API/seeds/rag_knowledge.py UI_API/main.py UI_API/database.py
git commit -m "feat: add RAG knowledge seeds and auto-inject on startup"
```

---

## Task 6：整合驗證

- [ ] **Step 1：全部 Python 語法驗證**

```bash
cd /home/oliver/Project_2026/UI_API
python3 -m py_compile main.py config.py database.py ai_services.py \
  routes/core_routes.py routes/voice_routes.py \
  services/voice_assist_service.py \
  seeds/rag_knowledge.py
echo "ALL OK"
```
預期輸出：`ALL OK`

- [ ] **Step 2：全部 JS 語法驗證**

```bash
node --check /home/oliver/Project_2026/UI_API/static/app.js
node --check /home/oliver/Project_2026/UI_API/static/api.js
node --check /home/oliver/Project_2026/UI_API/static/recommendation.js
echo "ALL OK"
```
預期輸出：`ALL OK`

- [ ] **Step 3：確認 RAG 種子筆數符合預期**

```bash
cd /home/oliver/Project_2026/UI_API
python3 -c "
from seeds.rag_knowledge import RAG_SEEDS
print(f'種子筆數: {len(RAG_SEEDS)}')
for s in RAG_SEEDS:
    print(f'  - {s[\"source_id\"]} ({len(s[\"text\"])} chars)')
"
```
預期輸出：種子筆數 4，每筆均有合理字元數（>200）。

- [ ] **Step 4：Final Commit**

```bash
cd /home/oliver/Project_2026
git add -A
git commit -m "chore: final integration and validation pass"
```
