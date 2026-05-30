# Emotion-LLaMA 清理與優化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 刪除 Emotion-LLaMA 目錄內訓練/評估用的無關檔案，並加入兩項優化：(A) 結構化 JSON 輸出讓下游解析穩定；(C) 推論前品質快篩節省 GPU。

**Architecture:**
- Task 1 只做 `git rm` 刪檔，不碰程式邏輯。
- Task 2（優化 C）在 `app_EmotionLlamaClient.py` 加入 OpenCV 快篩，不通過直接回傳 `[EMOTION_LLAMA_SKIP] reason`；`ai_services.py` 識別此前綴並提前返回。
- Task 3（優化 A）在 `app_EmotionLlamaClient.py` 加入 `_try_extract_structured()` 後處理層，將模型自由文字轉成固定 JSON；`ai_services.py` 解析此 JSON 並填入 `emotion_structured`；`customer_service.py` 若已有 `emotion_structured` 則跳過 Ollama 二次結構化。

**Tech Stack:** Python, OpenCV (cv2), `json`, `re`, FastAPI, Gradio, `git rm`

---

## File Map

| 狀態 | 路徑 | 說明 |
|------|------|------|
| Delete (many) | `Emotion-LLaMA/train.py`, `train_configs/`, `eval_*.py`, `eval_configs/eval_*.yaml`, `examples/`, `docs/`, `images/`, `audio.wav`, `emotion_*.json`, `Modelfile`, `environment.yml` + `minigpt4` 內部廢棄檔 | Task 1 清理 |
| Modify | `Emotion-LLaMA/app_EmotionLlamaClient.py` | Task 2 + Task 3 |
| Modify | `UI_API/prompts/defaults.py` | Task 3：更新 EMOTION_LLAMA_PROMPT |
| Modify | `UI_API/ai_services.py` | Task 2 + Task 3：處理 SKIP 與解析 JSON |
| Modify | `UI_API/services/customer_service.py` | Task 3：利用 emotion_structured 跳過 Ollama |

---

## Task 1：刪除訓練 / 評估 / 文件相關檔案

**Files:** 僅 `git rm`，不改任何 Python 程式碼。

- [ ] **Step 1：刪除根目錄無關檔案**

```bash
cd /home/oliver/Project_2026

git rm -f \
  "Emotion-LLaMA/train.py" \
  "Emotion-LLaMA/eval_emotion.py" \
  "Emotion-LLaMA/eval_emotion_EMER.py" \
  "Emotion-LLaMA/audio.wav" \
  "Emotion-LLaMA/emotion_history_log.json" \
  "Emotion-LLaMA/emotion_live.json" \
  "Emotion-LLaMA/Modelfile" \
  "Emotion-LLaMA/environment.yml"
```

- [ ] **Step 2：刪除訓練設定目錄**

```bash
git rm -rf \
  "Emotion-LLaMA/train_configs/" \
  "Emotion-LLaMA/eval_configs/eval_emotion.yaml" \
  "Emotion-LLaMA/eval_configs/eval_emotion_EMER.yaml" \
  "Emotion-LLaMA/examples/"
```

- [ ] **Step 3：刪除文件目錄與重複圖片**

```bash
git rm -rf \
  "Emotion-LLaMA/docs/" \
  "Emotion-LLaMA/images/"
```

- [ ] **Step 4：刪除 minigpt4 內訓練/評估/工具檔**

```bash
git rm -f \
  "Emotion-LLaMA/minigpt4/common/gradcam.py" \
  "Emotion-LLaMA/minigpt4/common/optims.py" \
  "Emotion-LLaMA/minigpt4/common/eval_utils.py" \
  "Emotion-LLaMA/minigpt4/common/dist_utils.py" \
  "Emotion-LLaMA/minigpt4/minigpt4.md"

git rm -rf \
  "Emotion-LLaMA/minigpt4/common/vqa_tools/" \
  "Emotion-LLaMA/minigpt4/runners/" \
  "Emotion-LLaMA/minigpt4/configs/models/minigpt4_llama2.yaml" \
  "Emotion-LLaMA/minigpt4/configs/models/minigpt4_vicuna0.yaml" \
  "Emotion-LLaMA/minigpt4/configs/datasets/firstface/mer2024.yaml"
```

- [ ] **Step 5：確認推論必要檔案仍存在**

```bash
# 這些檔案必須仍存在，確認後繼續
ls Emotion-LLaMA/app_EmotionLlamaClient.py
ls Emotion-LLaMA/eval_configs/demo.yaml
ls Emotion-LLaMA/minigpt4/conversation/conversation.py
ls Emotion-LLaMA/minigpt4/models/minigpt_v2.py
ls Emotion-LLaMA/minigpt4/configs/models/minigpt_v2.yaml
ls Emotion-LLaMA/minigpt4/configs/datasets/firstface/featureface.yaml
```

預期：6 行都顯示檔案路徑，無 `No such file or directory`。

- [ ] **Step 6：Commit**

```bash
git commit -m "chore: 移除 Emotion-LLaMA 訓練、評估與文件相關檔案

只保留推論（app_EmotionLlamaClient.py + minigpt4 核心套件 + checkpoints）所需檔案。

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2：優化 C — 推論前品質快篩

**Files:**
- Modify: `Emotion-LLaMA/app_EmotionLlamaClient.py`
- Modify: `UI_API/ai_services.py`

### Part A：在 app_EmotionLlamaClient.py 加入快篩

- [ ] **Step 1：在 `is_readable_video()` 後插入 `_quick_quality_check()` 函式**

找到 `is_readable_video()` 函式結尾（約第 67 行），在其後插入：

```python
def _quick_quality_check(path: str) -> tuple[bool, str]:
    """
    OpenCV 快篩：亮度 + 動態檢查。
    通過 → (True, "")；不通過 → (False, reason)。
    reason: "too_dark" | "no_motion" | "quality_check_error"
    """
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            cap.release()
            return False, "quality_check_error"

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        # 均勻取最多 5 幀
        positions = list(range(0, max(frame_count, 1), max(1, frame_count // 5)))[:5]

        brightnesses = []
        grays = []
        for pos in positions:
            if frame_count > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightnesses.append(float(gray.mean()))
            grays.append(cv2.resize(gray, (80, 45)))
        cap.release()

        if not brightnesses:
            return False, "quality_check_error"

        # 亮度門檻：平均亮度 < 15/255 視為太暗
        avg_brightness = sum(brightnesses) / len(brightnesses)
        if avg_brightness < 15.0:
            return False, "too_dark"

        # 動態門檻：幀差分 < 0.003 視為完全靜止（無人）
        if len(grays) >= 2:
            diffs = [
                float(cv2.absdiff(grays[i], grays[i + 1]).mean()) / 255.0
                for i in range(len(grays) - 1)
            ]
            avg_diff = sum(diffs) / len(diffs)
            if avg_diff < 0.003:
                return False, "no_motion"

        return True, ""
    except Exception as e:
        print(f"⚠️ quality_check 失敗（略過，繼續推論）: {e}")
        return True, ""  # 快篩失敗時保守通過，不阻擋推論
```

- [ ] **Step 2：在 `process_video_question()` 加入快篩呼叫**

找到 `process_video_question()` 中 `is_readable_video()` 呼叫後（約第 186–187 行）：

```python
    video_ok, video_error = is_readable_video(video_path)
    if not video_ok:
        return f"[EMOTION_LLAMA_ERROR] {video_error}: {video_path}"

    chat = get_chat()
```

在兩段之間插入快篩：

```python
    video_ok, video_error = is_readable_video(video_path)
    if not video_ok:
        return f"[EMOTION_LLAMA_ERROR] {video_error}: {video_path}"

    quality_ok, quality_reason = _quick_quality_check(video_path)
    if not quality_ok:
        print(f"⚠️ Emotion-LLaMA 品質快篩未通過: {quality_reason}")
        return f"[EMOTION_LLAMA_SKIP] {quality_reason}"

    chat = get_chat()
```

- [ ] **Step 3：語法驗證**

```bash
python3 -m py_compile Emotion-LLaMA/app_EmotionLlamaClient.py && echo "OK"
```

預期：`OK`。

### Part B：在 ai_services.py 識別 SKIP 前綴

- [ ] **Step 4：在 `async_get_emotion_from_llama()` 加入 SKIP 處理**

找到 `async_get_emotion_from_llama()` 中解析 response 的這段（約第 581–589 行）：

```python
        res_data = response.json()
        if "data" not in res_data and "event_id" in res_data:
            return {"emotion_raw": "排隊中(請關閉Gradio Queue)"}
        emotion_text = res_data.get("data", ["無法解析"])[0]
        if isinstance(emotion_text, str):
            for tag in ["<s>", "</s>", "[INST]", "[/INST]"]:
                emotion_text = emotion_text.replace(tag, "")
            emotion_text = emotion_text.strip()
        return {"emotion_raw": emotion_text, "emotion_prompt": prompt, "prepared_video": prepared_path}
```

改為：

```python
        res_data = response.json()
        if "data" not in res_data and "event_id" in res_data:
            return {"emotion_raw": "排隊中(請關閉Gradio Queue)"}
        emotion_text = res_data.get("data", ["無法解析"])[0]
        if isinstance(emotion_text, str):
            for tag in ["<s>", "</s>", "[INST]", "[/INST]"]:
                emotion_text = emotion_text.replace(tag, "")
            emotion_text = emotion_text.strip()

        # 品質快篩未通過：Emotion-LLaMA 回傳 [EMOTION_LLAMA_SKIP] reason
        if emotion_text.startswith("[EMOTION_LLAMA_SKIP]"):
            skip_reason = emotion_text.removeprefix("[EMOTION_LLAMA_SKIP]").strip()
            print(f"⚠️ Emotion-LLaMA 快篩跳過: {skip_reason}")
            return {
                "emotion_raw": "",
                "emotion_available": False,
                "emotion_error": f"quality_skip:{skip_reason}",
            }

        return {"emotion_raw": emotion_text, "emotion_prompt": prompt, "prepared_video": prepared_path}
```

- [ ] **Step 5：語法驗證**

```bash
cd /home/oliver/Project_2026
python3 -m py_compile UI_API/ai_services.py && echo "OK"
```

預期：`OK`。

- [ ] **Step 6：Commit**

```bash
git add -f \
  Emotion-LLaMA/app_EmotionLlamaClient.py \
  UI_API/ai_services.py
git commit -m "feat: Emotion-LLaMA 推論前品質快篩（優化 C）

app_EmotionLlamaClient: 加入 _quick_quality_check()（亮度 + 動態）
  - 太暗 / 完全靜止 → 回傳 [EMOTION_LLAMA_SKIP] reason，跳過 GPU 推論
ai_services: 識別 SKIP 前綴，提前回傳 emotion_available=False

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3：優化 A — 結構化 JSON 輸出

**Files:**
- Modify: `Emotion-LLaMA/app_EmotionLlamaClient.py`
- Modify: `UI_API/prompts/defaults.py`
- Modify: `UI_API/ai_services.py`
- Modify: `UI_API/services/customer_service.py`

### 設計說明
Emotion-LLaMA 是描述型微調模型（非純指令模型），max_new_tokens=120，不能可靠地自行輸出完整 JSON。策略：
1. 更新 prompt 改變描述**格式**（分段標籤），而非強制要求 JSON
2. 在 `app_EmotionLlamaClient.py` 加入 `_try_extract_structured()` 後處理層，將模型輸出解析為固定 dict
3. 將此 dict 序列化為 JSON 字串回傳給 Gradio（string channel 不變）
4. `ai_services.py` 嘗試解析 JSON；成功則填入 `emotion_structured`
5. `customer_service.py` 若收到 `emotion_structured`，略過 Ollama 二次結構化

### Part A：更新 EMOTION_LLAMA_PROMPT

- [ ] **Step 1：修改 `UI_API/prompts/defaults.py` 中的 EMOTION_LLAMA_PROMPT**

將現有的 `EMOTION_LLAMA_PROMPT` 替換為：

```python
EMOTION_LLAMA_PROMPT = (
    "The person in video says: {speech_text}\n"
    "Describe the person's behavior in these labeled sections:\n"
    "FACIAL: [describe facial expression]\n"
    "BODY: [describe posture and gestures]\n"
    "VOCAL: [describe tone and energy from audio]\n"
    "EMOTION: [one word primary emotion]\n"
    "INTENSITY: [low / medium / high]\n"
    "Focus on observable cues. If audio is quiet, rely on visual evidence."
)
```

- [ ] **Step 2：語法驗證**

```bash
python3 -m py_compile UI_API/prompts/defaults.py && echo "OK"
```

### Part B：加入後處理層到 app_EmotionLlamaClient.py

- [ ] **Step 3：在 `_quick_quality_check()` 後插入 `_try_extract_structured()` 函式**

```python
def _try_extract_structured(text: str) -> dict:
    """
    嘗試從 Emotion-LLaMA 的自由文字回應解析結構化資料。
    支援兩種格式：
      1. 標籤格式：「FACIAL: ...\nBODY: ...\nEMOTION: ...」
      2. JSON 格式：{\"facial\": ..., \"emotion\": ...}（若模型剛好輸出）
    永遠回傳包含 description 的 dict；欄位可能為空字串但不為 None。
    """
    import json as _json
    import re as _re

    result = {
        "facial": "",
        "body": "",
        "vocal": "",
        "emotion": "",
        "intensity": "",
        "description": text,
    }

    # 嘗試解析 JSON
    try:
        json_match = _re.search(r'\{[^{}]+\}', text, _re.DOTALL)
        if json_match:
            parsed = _json.loads(json_match.group())
            for key in ("facial", "body", "vocal", "emotion", "intensity"):
                if key in parsed:
                    result[key] = str(parsed[key]).strip()
            return result
    except Exception:
        pass

    # 解析標籤格式（FACIAL: ... / BODY: ... 等）
    label_map = {
        "FACIAL": "facial",
        "BODY": "body",
        "VOCAL": "vocal",
        "EMOTION": "emotion",
        "INTENSITY": "intensity",
    }
    for label, key in label_map.items():
        pattern = _re.compile(
            rf'{label}\s*[:\-]\s*(.+?)(?=\n[A-Z]{{3,}}[:\-]|$)',
            _re.IGNORECASE | _re.DOTALL,
        )
        match = pattern.search(text)
        if match:
            result[key] = match.group(1).strip().strip('[]').strip()

    return result
```

- [ ] **Step 4：修改 `process_video_question()` 回傳 JSON 字串**

找到函式結尾的 `return response`（約第 241 行），改為：

```python
        # 淨化輸出
        for tag in ["<s>", "</s>", "[INST]", "[/INST]", "<video>", "</video>", "<feature>", "</feature>"]:
            response = response.replace(tag, "")
        response = response.strip()

        # 解析結構化資料，回傳 JSON 字串讓下游穩定解析
        import json as _json
        structured = _try_extract_structured(response)
        result_json = _json.dumps(structured, ensure_ascii=False)

        elapsed_ms = int((time.time() - start_ts) * 1000)
        print(f"✅ 推論完成: elapsed_ms={elapsed_ms}, emotion={structured.get('emotion')}, response={response[:80]}")
        return result_json
```

- [ ] **Step 5：語法驗證**

```bash
python3 -m py_compile Emotion-LLaMA/app_EmotionLlamaClient.py && echo "OK"
```

### Part C：ai_services.py 解析 JSON 回傳值

- [ ] **Step 6：在 `async_get_emotion_from_llama()` 解析結構化回傳**

找到 Task 2 中已修改的最後一行：
```python
        return {"emotion_raw": emotion_text, "emotion_prompt": prompt, "prepared_video": prepared_path}
```

替換為：

```python
        # 嘗試解析結構化 JSON（優化 A：app_EmotionLlamaClient 回傳 JSON 字串）
        emotion_structured = None
        try:
            import json as _json
            parsed = _json.loads(emotion_text)
            if isinstance(parsed, dict) and "description" in parsed:
                emotion_structured = parsed
                # 讓 emotion_raw 仍然是可讀文字（description 欄位）
                emotion_text = parsed.get("description") or emotion_text
        except Exception:
            pass  # 非 JSON 格式（舊版相容）

        result = {"emotion_raw": emotion_text, "emotion_prompt": prompt, "prepared_video": prepared_path}
        if emotion_structured:
            result["emotion_structured"] = emotion_structured
        return result
```

- [ ] **Step 7：語法驗證**

```bash
python3 -m py_compile UI_API/ai_services.py && echo "OK"
```

### Part D：customer_service.py 利用 emotion_structured 跳過 Ollama

- [ ] **Step 8：修改 `analyze_customer_emotion()` 中的結構化處理**

找到（約第 405–436 行）：

```python
        emotion_data = await ai_services.async_get_emotion_from_llama(media_path, speech_text, media_signals)
        emotion_text = emotion_data.get("emotion_raw", "") or "無法辨識具體情緒。"
        if emotion_data.get("emotion_available") is False:
            emotion_structured = build_emotion_structured(
                emotion_text,
                "Emotion-LLaMA 未執行：服務未連線或尚未啟動。",
                "無法判斷",
                evidence_hint="Emotion-LLaMA 服務未連線。",
                speech_text=speech_text,
                media_signals=media_signals,
            )
            ...
        if structure_with_llm:
            emotion_structured = await emotion_to_structured_display(
                emotion_text, None, speech_text, media_signals, ollama_semaphore
            )
        else:
            emotion_structured = build_emotion_structured(
                emotion_text,
                emotion_text,
                speech_text=speech_text,
                media_signals=media_signals,
            )
```

將 `if structure_with_llm:` 區塊改為：

```python
        if structure_with_llm:
            # 優化 A：若 Emotion-LLaMA 已回傳結構化資料，跳過 Ollama 二次結構化
            llama_structured = emotion_data.get("emotion_structured")
            if llama_structured and llama_structured.get("emotion"):
                emotion_label = llama_structured.get("emotion", "unknown")
                evidence = (
                    f"FACIAL: {llama_structured.get('facial', '')}, "
                    f"BODY: {llama_structured.get('body', '')}, "
                    f"VOCAL: {llama_structured.get('vocal', '')}, "
                    f"INTENSITY: {llama_structured.get('intensity', '')}"
                ).strip(", ")
                emotion_structured = build_emotion_structured(
                    emotion_label,
                    emotion_text,
                    evidence_hint=evidence,
                    speech_text=speech_text,
                    media_signals=media_signals,
                )
            else:
                emotion_structured = await emotion_to_structured_display(
                    emotion_text, None, speech_text, media_signals, ollama_semaphore
                )
```

- [ ] **Step 9：語法驗證**

```bash
python3 -m py_compile UI_API/services/customer_service.py && echo "OK"
```

- [ ] **Step 10：Commit**

```bash
git add -f \
  Emotion-LLaMA/app_EmotionLlamaClient.py \
  UI_API/prompts/defaults.py \
  UI_API/ai_services.py \
  UI_API/services/customer_service.py
git commit -m "feat: Emotion-LLaMA 結構化 JSON 輸出（優化 A）

app_EmotionLlamaClient: 加入 _try_extract_structured()，將模型自由文字
  轉為 {facial, body, vocal, emotion, intensity, description} JSON
  process_video_question() 改回傳 JSON 字串
prompts/defaults: 更新 EMOTION_LLAMA_PROMPT 使用標籤格式（FACIAL/BODY/...）
ai_services: 解析 JSON 回傳值，填入 emotion_structured
customer_service: emotion_structured 可用時跳過 Ollama 二次結構化

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4：全域驗證

- [ ] **Step 1：語法全檢**

```bash
cd /home/oliver/Project_2026
python3 -m py_compile \
  Emotion-LLaMA/app_EmotionLlamaClient.py \
  UI_API/prompts/defaults.py \
  UI_API/ai_services.py \
  UI_API/services/customer_service.py && \
echo "ALL OK"
```

預期：最後一行 `ALL OK`。

- [ ] **Step 2：確認 SKIP 路徑正確串接**

```bash
grep -n "EMOTION_LLAMA_SKIP\|quality_skip\|emotion_available" \
  Emotion-LLaMA/app_EmotionLlamaClient.py \
  UI_API/ai_services.py
```

預期：
- `app_EmotionLlamaClient.py` 出現 `[EMOTION_LLAMA_SKIP]`（回傳處）
- `ai_services.py` 出現 `EMOTION_LLAMA_SKIP`（識別處）和 `quality_skip`（error 欄位）

- [ ] **Step 3：確認結構化路徑正確串接**

```bash
grep -n "emotion_structured\|_try_extract_structured\|llama_structured" \
  Emotion-LLaMA/app_EmotionLlamaClient.py \
  UI_API/ai_services.py \
  UI_API/services/customer_service.py
```

預期：三個檔案都出現 `emotion_structured`。

---

## Self-Review

**Spec coverage:**
- ✅ 刪除訓練/評估/文件檔案 → Task 1
- ✅ 優化 C：推論前品質快篩 → Task 2（`_quick_quality_check` + SKIP 識別）
- ✅ 優化 A：結構化 JSON 輸出 → Task 3（`_try_extract_structured` + 下游解析）

**Placeholder scan:** 無 TBD/TODO，所有程式碼區塊完整。

**Type consistency:**
- `_quick_quality_check(path: str) -> tuple[bool, str]` — Task 2 定義，Task 2 Step 2 呼叫 ✅
- `_try_extract_structured(text: str) -> dict` — Task 3 Step 3 定義，Task 3 Step 4 呼叫 ✅
- `emotion_structured: dict` — Task 3 Step 6 填入（鍵 `emotion_structured`），Task 3 Step 8 讀取（`.get("emotion_structured")`）✅
- `[EMOTION_LLAMA_SKIP]` 前綴 — Task 2 Step 2 回傳，Task 2 Step 4 用 `.startswith()` 識別 ✅

**⚠️ 注意事項：**
- Task 3 的 `build_emotion_structured()` 調用需要確認其簽名支援 `evidence_hint` 參數。若不支援，改用 `speech_text` 傳入 evidence 字串，或先查閱 `customer_service.py` 中 `build_emotion_structured` 的完整定義再調整。
- `EMOTION_LLAMA_PROMPT` 已更新，`settings.json` 中可能仍有舊版本覆蓋；若後台設定有此欄位，需要管理員手動清空或更新。
