# Backend Refactor — 語音、Emotion-LLaMA、RAG 清理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 刪除舊語音/Emotion-LLaMA/RAG 實作並以乾淨架構取代，清除所有舊架構殘碼，確保系統仍可啟動。

**Architecture:** 三個方向平行清理：(1) 新語音服務 STT→Ollama→TTS，RAG 留 TODO 插槽；(2) Emotion-LLaMA stub endpoint；(3) 刪除 RAG 實作、清除 recommend_cache / seeds / PDF 殘碼。所有變更在 `UI_API/` 下。每個 task 完成後執行 compile check。

**Tech Stack:** Python 3.x, FastAPI, OpenAI Whisper, Edge TTS, Ollama

---

## 檔案對照表

| 動作 | 檔案 |
|------|------|
| **新增** | `services/voice_service.py` |
| **新增** | `services/emotion_service.py` |
| **重寫** | `routes/voice_routes.py` |
| **重寫** | `routes/emotion_routes.py` |
| **簡化** | `services/barrier_state_service.py` |
| **簡化** | `services/intervention_pipeline_service.py` |
| **局部修改** | `routes/interaction_routes.py` |
| **局部修改** | `routes/demo_routes.py` |
| **局部修改** | `ai_services.py` |
| **重寫** | `database.py` |
| **局部修改** | `routes/menu_routes.py` |
| **局部修改** | `routes/core_routes.py` |
| **局部修改** | `main.py` |
| **刪除** | `services/voice_assist_service.py`, `services/query_router_service.py`, `services/customer_service.py`, `services/emotion_risk_service.py`, `services/multimodal_evidence_service.py`, `routes/multimodal_routes.py`, `rag_service.py`, `routes/rag_routes.py`, `services/rag_review_service.py`, `seeds/`, `gemini_direct_chat.py`, `mcdonalds_tw_extra_value_meals_rag.pdf`, `sample_data/` |

---

## Task 1: 建立新語音服務

**Files:**
- Create: `services/voice_service.py`

- [ ] **Step 1: 建立 `services/voice_service.py`**

```python
"""語音助理服務：STT → Ollama → TTS。"""
import asyncio

import ai_services
import config
import database
from repositories import menu_repository, session_repository
from services.recommendation_service import coerce_cart_actions

_DEFAULT_SYSTEM_PROMPT = (
    "你是麥當勞自助點餐機的語音助理。"
    "根據顧客語音輸入協助點餐或回答菜單問題。"
    "若顧客要點餐，輸出 cart_actions；若是問答，cart_actions 輸出空陣列。"
    "只能使用菜單白名單中的餐點 ID，不得創造不存在的餐點。"
    '只輸出合法 JSON：{"ai_response":"回覆","cart_actions":[{"action":"add","id":"MCDxxx","quantity":1}]}'
)


async def handle_voice(
    session_id: str,
    audio_path: str,
    ollama_semaphore,
    multi_lang: bool = True,
) -> dict:
    loop = asyncio.get_running_loop()

    # 1. Whisper STT
    stt = await ai_services.async_safe_transcribe_with_language(audio_path)
    user_text = (stt.get("text") or "").strip()
    detected_lang = stt.get("language", "zh") if multi_lang else "zh"

    if not user_text:
        return {
            "status": "error",
            "message": "無法辨識語音內容",
            "user_text": "",
            "ai_response": "",
            "audio_base64": "",
            "cart_actions": [],
            "detected_lang": detected_lang,
        }

    menu_items = await asyncio.to_thread(menu_repository.get_menu)
    full_menu_context = await asyncio.to_thread(database.build_full_menu_context)
    system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT") or _DEFAULT_SYSTEM_PROMPT

    # TODO: inject RAG context here
    # rag_context = rag_provider.query(user_text)
    user_prompt = f"【顧客語音輸入】\n{user_text}\n\n{full_menu_context}"

    # 2. Ollama
    model = config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b")
    async with ollama_semaphore:
        result = await loop.run_in_executor(
            None, ai_services.ask_ollama, system_prompt, user_prompt, "", model
        )

    if isinstance(result, list):
        result = next((r for r in result if isinstance(r, dict)), {})
    if not isinstance(result, dict) or "error" in result:
        ai_response = (
            "I can help with menu questions or add items to your cart."
            if detected_lang == "en"
            else "我可以協助您了解菜單或加入餐點。"
        )
        cart_actions = []
    else:
        ai_response = str(result.get("ai_response") or "").strip()
        raw_cart = result.get("cart_actions") or []
        cart_actions = coerce_cart_actions(
            raw_cart if isinstance(raw_cart, list) else [],
            user_text,
            menu_items,
        )
        if not ai_response:
            ai_response = "已為您加入購物車。" if cart_actions else "我可以協助您了解菜單或加入餐點。"

    session_repository.record_session_state(
        session_id=session_id,
        emotion="",
        user_speech=user_text,
        ai_response=ai_response,
        language=detected_lang,
    )

    # 3. TTS
    audio_base64 = await ai_services.generate_tts_audio_base64(ai_response, lang=detected_lang)

    return {
        "status": "success",
        "user_text": user_text,
        "ai_response": ai_response,
        "audio_base64": audio_base64,
        "cart_actions": cart_actions,
        "detected_lang": detected_lang,
    }
```

- [ ] **Step 2: Compile check**

```bash
python3 -m py_compile services/voice_service.py && echo "OK"
```
期望：`OK`

- [ ] **Step 3: Commit**

```bash
git add services/voice_service.py
git commit -m "feat: add clean voice_service (STT→Ollama→TTS, RAG TODO slot)"
```

---

## Task 2: 建立 Emotion-LLaMA Stub 服務

**Files:**
- Create: `services/emotion_service.py`

- [ ] **Step 1: 建立 `services/emotion_service.py`**

```python
"""Emotion-LLaMA 情緒分析 stub — 預留對接介面。"""


async def analyze(session_id: str, media_path: str) -> dict:
    # TODO: Connect to Emotion-LLaMA at config.EMOTION_LLAMA_GRADIO_URL
    # Replace this stub when Emotion-LLaMA service is ready.
    return {
        "session_id": session_id,
        "emotion_label": "未偵測",
        "emotion_score": 0,
        "emotion_available": False,
        "status": "stub",
    }
```

- [ ] **Step 2: Compile check**

```bash
python3 -m py_compile services/emotion_service.py && echo "OK"
```
期望：`OK`

- [ ] **Step 3: Commit**

```bash
git add services/emotion_service.py
git commit -m "feat: add emotion_service stub (Emotion-LLaMA placeholder)"
```

---

## Task 3: 重寫 voice_routes.py

**Files:**
- Modify: `routes/voice_routes.py`

- [ ] **Step 1: 覆寫 `routes/voice_routes.py`**

```python
"""語音助理路由。"""
import asyncio
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile

from services import voice_service
from utils.file_utils import write_binary_file


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["voice"])

    @router.post("/ask")
    async def process_voice_assist(
        session_id: str = Form(...),
        media: UploadFile = File(...),
        multi_lang: str = Form(default="true"),
    ):
        temp_path = None
        try:
            suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_path = tmp.name
            media_bytes = await media.read()
            await asyncio.to_thread(write_binary_file, temp_path, media_bytes)
            return await voice_service.handle_voice(
                session_id=session_id,
                audio_path=temp_path,
                ollama_semaphore=deps["ollama_semaphore"],
                multi_lang=multi_lang.lower() == "true",
            )
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    return router
```

- [ ] **Step 2: Compile check**

```bash
python3 -m py_compile routes/voice_routes.py && echo "OK"
```
期望：`OK`

- [ ] **Step 3: Commit**

```bash
git add routes/voice_routes.py
git commit -m "refactor: rewrite voice_routes to use new voice_service"
```

---

## Task 4: 重寫 emotion_routes.py 為 Stub

**Files:**
- Modify: `routes/emotion_routes.py`

- [ ] **Step 1: 覆寫 `routes/emotion_routes.py`**

```python
"""Emotion-LLaMA 路由 — stub，預留對接介面。"""
import asyncio
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile

from services import emotion_service
from utils.file_utils import write_binary_file


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api/emotion", tags=["emotion"])

    @router.post("/analyze")
    async def analyze_emotion(
        session_id: str = Form(...),
        media: UploadFile = File(...),
    ):
        temp_path = None
        try:
            suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                temp_path = tmp.name
            media_bytes = await media.read()
            await asyncio.to_thread(write_binary_file, temp_path, media_bytes)
            return await emotion_service.analyze(
                session_id=session_id,
                media_path=temp_path,
            )
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    return router
```

- [ ] **Step 2: Compile check**

```bash
python3 -m py_compile routes/emotion_routes.py && echo "OK"
```
期望：`OK`

- [ ] **Step 3: Commit**

```bash
git add routes/emotion_routes.py
git commit -m "refactor: rewrite emotion_routes as Emotion-LLaMA stub"
```

---

## Task 5: 簡化 barrier_state_service.py（移除 emotion 依賴）

**Files:**
- Modify: `services/barrier_state_service.py`

- [ ] **Step 1: 覆寫 `services/barrier_state_service.py`**

```python
from services import interaction_event_service
from services import scenario_service


BARRIER_STATES = {
    "normal_operation", "menu_hesitation", "operation_confusion",
    "payment_confusion", "coupon_confusion", "impatience_detected",
    "service_needed", "potential_complaint", "low_confidence",
}

INTERVENTION_CATEGORY_MAP = {
    "menu_hesitation": "menu_confusion",
    "payment_confusion": "operation_difficulty",
    "coupon_confusion": "operation_difficulty",
    "operation_confusion": "operation_difficulty",
    "impatience_detected": "service_needed",
    "service_needed": "service_needed",
    "potential_complaint": "service_needed",
    "low_confidence": "menu_confusion",
    "normal_operation": "none",
}

INTERVENTION_CATEGORY_LABELS = {
    "menu_confusion": "困惑不知道吃什麼",
    "operation_difficulty": "不會操作機台",
    "service_needed": "需要客服協助",
    "none": "操作正常",
}

PATENT_CATEGORY_MAP = {
    "menu_hesitation": "decision_hesitation",
    "payment_confusion": "operation_failure",
    "coupon_confusion": "operation_failure",
    "operation_confusion": "operation_failure",
    "impatience_detected": "service_or_question",
    "service_needed": "service_or_question",
    "potential_complaint": "service_or_question",
    "low_confidence": "service_or_question",
    "normal_operation": "none",
}

PATENT_CATEGORY_LABELS = {
    "decision_hesitation": "困惑、無法決定餐點",
    "operation_failure": "操作失敗、不會點餐",
    "service_or_question": "詢問餐點、客服情況",
    "none": "正常操作",
}


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _latest_page(pos_events: list | None, ui_context: dict | None) -> str:
    context_page = str((ui_context or {}).get("page_id") or "")
    if context_page:
        return context_page
    for event in reversed(pos_events or []):
        if isinstance(event, dict) and event.get("page_id"):
            return str(event.get("page_id"))
    return "unknown"


def _max_field(pos_events: list | None, field: str) -> int:
    values = []
    for event in pos_events or []:
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        try:
            values.append(int(float(event.get(field, metadata.get(field)) or 0)))
        except Exception:
            continue
    return max(values) if values else 0


def _latest_event_type(pos_events: list | None) -> str:
    for event in reversed(pos_events or []):
        if isinstance(event, dict) and event.get("event_type"):
            return str(event.get("event_type"))
    return ""


def _confidence_from(score: int, evidence_count: int) -> float:
    return round(min(0.95, 0.45 + score * 0.04 + evidence_count * 0.06), 2)


def _severity_from(score: int, evidence_count: int) -> float:
    return round(min(1.0, 0.25 + score * 0.07 + evidence_count * 0.05), 2)


def map_barrier_to_default_action(barrier_state: str, severity: float) -> str:
    mapping = {
        "payment_confusion": "show_payment_tutorial",
        "coupon_confusion": "show_coupon_guide",
        "operation_confusion": "show_operation_hint",
        "menu_hesitation": "recommend_popular_combo",
        "impatience_detected": "call_staff_or_fast_mode",
        "service_needed": "call_staff",
        "potential_complaint": "call_staff",
        "low_confidence": "ask_clarifying_question",
        "normal_operation": "none",
    }
    return mapping.get(barrier_state, "ask_clarifying_question")


def map_barrier_to_category(barrier_state: str) -> dict:
    key = INTERVENTION_CATEGORY_MAP.get(barrier_state, "menu_confusion")
    return {
        "intervention_category": key,
        "intervention_category_label": INTERVENTION_CATEGORY_LABELS.get(key, ""),
    }


def map_barrier_to_patent_category(barrier_state: str) -> dict:
    key = PATENT_CATEGORY_MAP.get(barrier_state, "service_or_question")
    return {
        "patent_category": key,
        "patent_category_label": PATENT_CATEGORY_LABELS.get(key, ""),
    }


def infer_barrier_state(
    speech_text: str = "",
    pos_events: list | None = None,
    ui_context: dict | None = None,
    risk_result: dict | None = None,
) -> dict:
    events = pos_events or []
    risk = risk_result or interaction_event_service.calculate_interaction_risk(events, ui_context)
    risk_score = int(risk.get("risk_score") or 0)
    page_id = _latest_page(events, ui_context)
    speech = speech_text or ""
    evidence = []

    payment_fail_count = _max_field(events, "payment_fail_count")
    coupon_error_count = _max_field(events, "coupon_error_count")
    category_switch_count = _max_field(events, "category_switch_count")
    cart_remove_count = _max_field(events, "cart_remove_count")
    recommend_ignore_count = _max_field(events, "recommend_ignore_count")
    max_dwell_time_sec = _max_field(events, "dwell_time_sec")
    latest_event_type = _latest_event_type(events)

    barrier_state = "normal_operation"
    if _contains_any(speech, ["客訴", "投訴", "不爽", "太誇張", "我要找人", "經理", "爛"]):
        barrier_state = "potential_complaint"
        evidence.append("speech contains complaint intent")
    elif page_id == "payment_page" and (risk_score >= 5 or payment_fail_count >= 1):
        barrier_state = "payment_confusion"
        evidence.extend(["page_id=payment_page", "payment risk triggered"])
    elif _contains_any(speech, ["不能刷", "付款", "刷卡", "line pay", "LINE Pay", "悠遊卡"]) and risk_score >= 1:
        barrier_state = "payment_confusion"
        evidence.append("speech contains payment issue")
    elif _contains_any(speech, ["優惠券", "折扣碼", "掃碼", "qr", "QR"]) and coupon_error_count >= 1:
        barrier_state = "coupon_confusion"
        evidence.extend(["coupon_error_count >= 1", "speech contains coupon issue"])
    elif page_id == "menu_page" and (
        category_switch_count >= 4
        or cart_remove_count >= 2
        or recommend_ignore_count >= 1
        or latest_event_type in ("menu_page_dwell_timeout", "category_switch_repeat", "recommendation_ignored")
        or _contains_any(speech, ["不知道吃什麼", "推薦", "吃什麼", "選不出來", "猶豫"])
        or (risk_score >= 5 and max_dwell_time_sec > 40)
    ):
        barrier_state = "menu_hesitation"
        evidence.append("page_id=menu_page")
        if category_switch_count >= 4:
            evidence.append("category_switch_count >= 4")
        if cart_remove_count >= 2:
            evidence.append("cart_remove_count >= 2")
        if recommend_ignore_count >= 1:
            evidence.append("recommend_ignore_count >= 1")
        if latest_event_type in ("menu_page_dwell_timeout", "category_switch_repeat", "recommendation_ignored"):
            evidence.append(f"event_type={latest_event_type}")
        if _contains_any(speech, ["不知道吃什麼", "推薦", "吃什麼", "選不出來", "猶豫"]):
            evidence.append("speech contains menu hesitation")
        if risk_score >= 5 and max_dwell_time_sec > 40:
            evidence.append("risk_score >= 5 and dwell_time_sec > 40")
    elif _contains_any(speech, ["不會", "不懂", "怎麼用", "看不懂", "怎麼點"]):
        barrier_state = "operation_confusion"
        evidence.append("speech contains operation confusion")
    elif _contains_any(speech, ["太慢", "等很久", "快一點", "趕時間"]):
        barrier_state = "impatience_detected"
        evidence.append("speech contains impatience")
    elif risk_score >= 5 and page_id == "coupon_page":
        barrier_state = "coupon_confusion"
        evidence.extend(["risk_score >= threshold", "page_id=coupon_page"])
    elif risk_score >= 5:
        barrier_state = "operation_confusion"
        evidence.append("risk_score >= threshold")
    elif not events and not speech.strip():
        barrier_state = "low_confidence"
        evidence.append("insufficient context")

    if payment_fail_count >= 1 and "payment_fail_count >= 1" not in evidence:
        evidence.append("payment_fail_count >= 1")
    if page_id and f"page_id={page_id}" not in evidence:
        evidence.append(f"page_id={page_id}")
    for reason in risk.get("trigger_reasons") or []:
        if reason not in evidence:
            evidence.append(reason)

    confidence = _confidence_from(risk_score, len(evidence))
    severity = _severity_from(risk_score, len(evidence))
    if barrier_state == "normal_operation":
        confidence = max(0.55, min(confidence, 0.75))
        severity = min(severity, 0.25)
    if barrier_state == "low_confidence":
        confidence = 0.35
        severity = 0.2

    category_info = map_barrier_to_category(barrier_state)
    patent_category_info = map_barrier_to_patent_category(barrier_state)
    scenario_info = {}
    scenario_id = scenario_service.infer_scenario_from_barrier_state(barrier_state)
    if scenario_id:
        scenario_info = scenario_service.attach_scenario_metadata({}, scenario_id)

    return {
        "barrier_state": barrier_state,
        "severity": severity,
        "confidence": confidence,
        "evidence": evidence,
        "risk_score": risk_score,
        "risk_score_scale": int(risk.get("risk_score_scale") or 10),
        "risk_level": risk.get("risk_level") or "none",
        "recommended_action": map_barrier_to_default_action(barrier_state, severity),
        "payment_fail_count": payment_fail_count,
        "coupon_error_count": coupon_error_count,
        "category_switch_count": category_switch_count,
        "cart_remove_count": cart_remove_count,
        "recommend_ignore_count": recommend_ignore_count,
        **category_info,
        **patent_category_info,
        **scenario_info,
    }
```

- [ ] **Step 2: Compile check**

```bash
python3 -m py_compile services/barrier_state_service.py && echo "OK"
```
期望：`OK`

- [ ] **Step 3: Commit**

```bash
git add services/barrier_state_service.py
git commit -m "refactor: simplify barrier_state_service, remove emotion dependencies"
```

---

## Task 6: 簡化 intervention_pipeline_service.py

**Files:**
- Modify: `services/intervention_pipeline_service.py`

- [ ] **Step 1: 覆寫 `services/intervention_pipeline_service.py`**

```python
import asyncio

from repositories import interaction_event_repository
from realtime import event_bus
from services import barrier_state_service
from services import interaction_event_service
from services import intervention_service
from services import scenario_service


async def run_intervention_pipeline(
    session_id: str,
    ui_context: dict,
    risk_result: dict | None = None,
    recent_events: list | None = None,
    speech_text: str = "",
    scenario_id: str | None = None,
    source: str = "unknown",
    publish: bool = True,
) -> dict:
    safe_session_id = str(session_id or "anonymous")
    safe_ui_context = ui_context if isinstance(ui_context, dict) else {}
    events = recent_events if isinstance(recent_events, list) else await asyncio.to_thread(
        interaction_event_repository.get_recent_session_events,
        safe_session_id,
    )
    risk = risk_result if isinstance(risk_result, dict) and risk_result else (
        interaction_event_service.calculate_interaction_risk(events, safe_ui_context)
    )
    speech = str(speech_text or "")
    normalized_scenario = scenario_service.normalize_scenario_id(scenario_id or "")
    if normalized_scenario not in scenario_service.MAIN_SCENARIO_IDS and events:
        normalized_scenario = scenario_service.infer_scenario_from_event(events[-1], risk)

    barrier_result = barrier_state_service.infer_barrier_state(
        speech_text=speech,
        pos_events=events,
        ui_context=safe_ui_context,
        risk_result=risk,
    )
    barrier_scenario = scenario_service.infer_scenario_from_barrier_state(
        barrier_result.get("barrier_state", "")
    )
    if barrier_scenario in scenario_service.MAIN_SCENARIO_IDS:
        normalized_scenario = barrier_scenario
    if normalized_scenario in scenario_service.MAIN_SCENARIO_IDS:
        scenario_service.attach_scenario_metadata(barrier_result, normalized_scenario)
    intervention = intervention_service.decide_intervention(barrier_result, safe_ui_context)
    if normalized_scenario in scenario_service.MAIN_SCENARIO_IDS:
        scenario_service.attach_scenario_metadata(intervention, normalized_scenario)

    intervention_log = None
    if (
        intervention.get("action") != "none"
        and barrier_result.get("barrier_state") != "normal_operation"
    ):
        log_payload = intervention_service.build_intervention_log(
            safe_session_id, barrier_result, intervention, safe_ui_context,
        )
        log_payload["source"] = source
        if normalized_scenario in scenario_service.MAIN_SCENARIO_IDS:
            scenario_service.attach_scenario_metadata(log_payload, normalized_scenario)
        log_payload["patent_category"] = barrier_result.get("patent_category")
        log_payload["patent_intervention_type"] = intervention.get("patent_intervention_type")
        intervention_log = await asyncio.to_thread(
            interaction_event_repository.append_intervention_log,
            log_payload,
        )

    result = {
        "risk_result": risk,
        "barrier_result": barrier_result,
        "intervention": intervention,
        "intervention_log": intervention_log,
        "source": source,
    }
    if normalized_scenario in scenario_service.MAIN_SCENARIO_IDS:
        scenario_service.attach_scenario_metadata(result, normalized_scenario)

    if publish and intervention.get("action") != "none":
        await event_bus.publish_intervention(safe_session_id, result)
    if publish and intervention.get("staff_notify"):
        await event_bus.publish_to_admin("staff_notify", {
            "session_id": safe_session_id,
            "reason": intervention.get("reason", ""),
            "barrier_state": barrier_result.get("barrier_state"),
            "patent_category": barrier_result.get("patent_category"),
            "action": intervention.get("action"),
            "patent_intervention_type": intervention.get("patent_intervention_type"),
            "source": source,
        })

    return result
```

- [ ] **Step 2: Compile check**

```bash
python3 -m py_compile services/intervention_pipeline_service.py && echo "OK"
```
期望：`OK`

- [ ] **Step 3: Commit**

```bash
git add services/intervention_pipeline_service.py
git commit -m "refactor: remove emotion/multimodal params from intervention_pipeline"
```

---

## Task 7: 更新 interaction_routes.py 與 demo_routes.py

**Files:**
- Modify: `routes/interaction_routes.py` (barrier_state endpoint 移除 emotion params)
- Modify: `routes/demo_routes.py` (run_intervention_pipeline 呼叫移除 emotion params)

- [ ] **Step 1: 修改 `routes/interaction_routes.py` 的 `post_barrier_state`**

找到 `post_barrier_state` handler（約第 160–191 行），將整個函式替換為：

```python
    @router.post("/barrier_state")
    async def post_barrier_state(payload: dict = Body(...)):
        session_id = str(payload.get("session_id") or "")
        ui_context = payload.get("ui_context") if isinstance(payload.get("ui_context"), dict) else {}
        speech_text = str(payload.get("speech_text") or "")
        events = await asyncio.to_thread(
            interaction_event_repository.get_recent_session_events, session_id
        )
        pipeline_result = await intervention_pipeline_service.run_intervention_pipeline(
            session_id=session_id,
            ui_context=ui_context,
            recent_events=events,
            speech_text=speech_text,
            source="barrier_state",
        )
        return {
            "status": "success",
            "session_id": session_id,
            **pipeline_result,
        }
```

- [ ] **Step 2: 修改 `routes/demo_routes.py` 的 `trigger_scenario`**

找到 `run_intervention_pipeline` 呼叫（約第 181–192 行），將參數替換為：

```python
        pipeline_result = await intervention_pipeline_service.run_intervention_pipeline(
            session_id=session_id,
            ui_context=ui_context,
            risk_result=risk_result,
            recent_events=recent_events,
            speech_text=speech_text,
            scenario_id=scenario if scenario != "low_risk" else None,
            source="demo_trigger_scenario",
        )
```

- [ ] **Step 3: Compile check**

```bash
python3 -m py_compile routes/interaction_routes.py routes/demo_routes.py && echo "OK"
```
期望：`OK`

- [ ] **Step 4: Commit**

```bash
git add routes/interaction_routes.py routes/demo_routes.py
git commit -m "refactor: remove emotion params from interaction_routes and demo_routes"
```

---

## Task 8: 移除 ai_services.py 中的 Emotion-LLaMA 函式

**Files:**
- Modify: `ai_services.py`

刪除以下 5 個函式（約第 378–630 行）：
- `_build_emotion_llama_prompt()` (line ~378)
- `async_prepare_emotion_video()` (line ~423)
- `_measure_motion_signals()` (line ~463)
- `async_analyze_emotion_media_signals()` (line ~503)
- `async_get_emotion_from_llama()` (line ~538)

- [ ] **Step 1: 刪除 `_build_emotion_llama_prompt` 函式**

找到並刪除從 `def _build_emotion_llama_prompt(` 到下一個 `async def` 前的整段函式。

- [ ] **Step 2: 刪除 `async_prepare_emotion_video` 函式**

找到並刪除 `async def async_prepare_emotion_video(` 整段。

- [ ] **Step 3: 刪除 `_measure_motion_signals` 函式**

找到並刪除 `def _measure_motion_signals(` 整段。

- [ ] **Step 4: 刪除 `async_analyze_emotion_media_signals` 函式**

找到並刪除 `async def async_analyze_emotion_media_signals(` 整段。

- [ ] **Step 5: 刪除 `async_get_emotion_from_llama` 函式**

找到並刪除 `async def async_get_emotion_from_llama(` 整段（到下一個函式前）。

- [ ] **Step 6: Compile check**

```bash
python3 -m py_compile ai_services.py && echo "OK"
```
期望：`OK`

- [ ] **Step 7: Commit**

```bash
git add ai_services.py
git commit -m "refactor: remove Emotion-LLaMA functions from ai_services"
```

---

## Task 9: 重寫 database.py（移除 RAG 與舊推薦系統函式）

**Files:**
- Modify: `database.py`

- [ ] **Step 1: 覆寫 `database.py`**

```python
import config
from repositories import log_repository, menu_repository
from services import recommendation_service


def build_menu_item_text(item: dict) -> str:
    prep_minutes = item.get("prep_time_minutes", item.get("prep_minutes", ""))
    return (
        f"ID: {item.get('id')}\n"
        f"名稱: {item.get('name')}\n"
        f"描述: {item.get('description')}\n"
        f"營養: {item.get('nutrition', '')}\n"
        f"製作時間: {prep_minutes}分鐘\n"
        f"價格: {item.get('price')}元"
    )


def build_full_menu_context() -> str:
    menu_items = menu_repository.get_menu()
    if not menu_items:
        return "【完整菜單白名單】目前沒有菜單資料。"
    lines = ["【完整菜單白名單】", "只能使用以下餐點 ID 與名稱，不得創造其他餐點。"]
    for item in menu_items:
        lines.append(build_menu_item_text(item))
    return "\n\n".join(lines)


def update_menu(new_menu_data: list) -> None:
    menu_repository.save_menu(new_menu_data)
    # TODO: trigger RAG rebuild when RAG is implemented


def record_final_checkout(
    session_id: str,
    pushed_ids: list,
    cart_ids: list,
    session_history: list,
) -> dict:
    log_entry = recommendation_service.build_checkout_log_entry(
        session_id=session_id,
        pushed_ids=pushed_ids,
        cart_ids=cart_ids,
        session_history=session_history,
    )
    return log_repository.append_session_log(log_entry)
```

- [ ] **Step 2: Compile check**

```bash
python3 -m py_compile database.py && echo "OK"
```
期望：`OK`

- [ ] **Step 3: Commit**

```bash
git add database.py
git commit -m "refactor: remove all RAG and legacy recommendation functions from database"
```

---

## Task 10: 修改 menu_routes.py 與 core_routes.py

**Files:**
- Modify: `routes/menu_routes.py`
- Modify: `routes/core_routes.py`

- [ ] **Step 1: 覆寫 `routes/menu_routes.py`**

```python
import asyncio

from fastapi import APIRouter, Body, Request

import database
from repositories import menu_repository
from utils.auth_utils import require_admin_token


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["menu"])

    @router.get("/menu")
    async def get_menu():
        return await asyncio.to_thread(menu_repository.get_menu)

    @router.post("/menu")
    async def update_menu(request: Request, new_menu: list = Body(...)):
        require_admin_token(request)
        if not isinstance(new_menu, list):
            return {"status": "error", "message": "menu payload must be a list"}
        await asyncio.to_thread(database.update_menu, new_menu)
        return {"status": "success", "count": len(new_menu)}

    return router
```

- [ ] **Step 2: 修改 `routes/core_routes.py` — 移除 3 處 `recommend_cache` 與 `schedule_rag_rebuild` 殘碼**

**2a. 修改 `clear_logs` handler（約第 169–174 行）**

原：
```python
    @router.delete("/api/logs")
    async def clear_logs(request: Request):
        require_admin_token(request)
        await asyncio.to_thread(log_repository.clear_session_logs)
        deps["recommend_cache"].clear()
        return {"status": "success"}
```

改為：
```python
    @router.delete("/api/logs")
    async def clear_logs(request: Request):
        require_admin_token(request)
        await asyncio.to_thread(log_repository.clear_session_logs)
        return {"status": "success"}
```

**2b. 修改 `delete_log` handler（約第 176–181 行）**

原：
```python
    @router.delete("/api/logs/{log_index}")
    async def delete_log(request: Request, log_index: int):
        require_admin_token(request)
        deleted = await asyncio.to_thread(log_repository.delete_session_log, log_index)
        deps["recommend_cache"].clear()
        return {"status": "success" if deleted else "not_found"}
```

改為：
```python
    @router.delete("/api/logs/{log_index}")
    async def delete_log(request: Request, log_index: int):
        require_admin_token(request)
        deleted = await asyncio.to_thread(log_repository.delete_session_log, log_index)
        return {"status": "success" if deleted else "not_found"}
```

**2c. 修改 `update_settings` handler — 移除 `schedule_rag_rebuild` 呼叫（約第 134–147 行）**

原：
```python
    @router.post("/api/settings")
    async def update_settings(request: Request, new_settings: dict = Body(...)):
        require_admin_token(request)
        old_rag_settings = config.get("rag", {})
        config.save_settings(new_settings)
        saved_settings = config.load_settings()
        await event_bus.publish_event({...})
        if new_settings.get("rag") != old_rag_settings:
            deps["schedule_rag_rebuild"]("RAG settings changed")
        return {"status": "success"}
```

改為：
```python
    @router.post("/api/settings")
    async def update_settings(request: Request, new_settings: dict = Body(...)):
        require_admin_token(request)
        config.save_settings(new_settings)
        saved_settings = config.load_settings()
        await event_bus.publish_event({
            "type": "settings_changed",
            "session_id": "",
            "payload": {"settings": saved_settings},
        })
        return {"status": "success"}
```

**2d. 修改 `process_checkout` handler — 移除 `save_voice_emotion_to_rag`、`schedule_rag_rebuild`、`recommend_cache` 相關程式碼（約第 229–262 行）**

找到以下段落並刪除：
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

以及刪除 checkout handler 末尾的 `recommend_cache` 清除段落：
```python
        recommend_cache = deps.get("recommend_cache") or {}
        for key in list(recommend_cache.keys()):
            if key.startswith(f"{session_id}:"):
                recommend_cache.pop(key, None)
```

同時，`process_checkout` 的 Form 參數中移除 `emotion_session_log`：

原：
```python
    async def process_checkout(
        session_id: str = Form(...),
        pushed_ids: str = Form(...),
        cart_ids: str = Form(...),
        emotion_session_log: str = Form(default=""),
        ai_push_cart_count: str = Form(default="0"),
    ):
```

改為：
```python
    async def process_checkout(
        session_id: str = Form(...),
        pushed_ids: str = Form(...),
        cart_ids: str = Form(...),
        ai_push_cart_count: str = Form(default="0"),
    ):
```

- [ ] **Step 3: Compile check**

```bash
python3 -m py_compile routes/menu_routes.py routes/core_routes.py && echo "OK"
```
期望：`OK`

- [ ] **Step 4: Commit**

```bash
git add routes/menu_routes.py routes/core_routes.py
git commit -m "refactor: remove recommend_cache, schedule_rag_rebuild, emotion_session_log from routes"
```

---

## Task 11: 更新 main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 移除 seeds import（第 13 行）**

刪除：
```python
from seeds.rag_knowledge import RAG_SEEDS
```

- [ ] **Step 2: 更新 routes import（第 14–25 行）**

原：
```python
from routes import (
    core_routes,
    emotion_routes,
    debug_routes,
    menu_routes,
    rag_routes,
    ai_push_routes,
    voice_routes,
    multimodal_routes,
    interaction_routes,
    realtime_routes,
)
```

改為：
```python
from routes import (
    core_routes,
    emotion_routes,
    debug_routes,
    menu_routes,
    ai_push_routes,
    voice_routes,
    interaction_routes,
    realtime_routes,
)
```

- [ ] **Step 3: 移除 `_emotion_semaphore`、`_emotion_cache`（約第 78–82 行）**

刪除：
```python
_emotion_semaphore = LoopBoundSemaphore(1)
```
以及：
```python
_emotion_cache = {}
```

- [ ] **Step 4: 簡化 `_background_init_once`（約第 110–155 行）**

覆寫整個函式為：
```python
async def _background_init_once():
    if not config.get("ENABLE_GEMINI_OPTIONS", False):
        return
    loop = asyncio.get_running_loop()
    try:
        ok = await loop.run_in_executor(None, ai_services.init_gemini_client)
        if ok:
            print("✅ Gemini client 背景初始化完成")
    except Exception as e:
        print(f"❌ Gemini client 背景初始化失敗: {e}")
```

- [ ] **Step 5: 移除 `_safe_rebuild_rag`、`_schedule_rag_rebuild`、`_rag_rebuild_task`（約第 158–172 行）**

刪除這三個函式與全域變數。

- [ ] **Step 6: 更新 `_route_dependencies`**

原：
```python
def _route_dependencies() -> dict:
    return {
        "emotion_cache": _emotion_cache,
        "emotion_semaphore": _emotion_semaphore,
        "ollama_semaphore": _ollama_semaphore,
        "safe_rebuild_rag": _safe_rebuild_rag,
        "schedule_rag_rebuild": _schedule_rag_rebuild,
    }
```

改為：
```python
def _route_dependencies() -> dict:
    return {
        "ollama_semaphore": _ollama_semaphore,
    }
```

- [ ] **Step 7: 移除 `rag_routes`、`multimodal_routes` 的 include_router 呼叫**

刪除：
```python
app.include_router(rag_routes.create_router(_deps))
app.include_router(multimodal_routes.create_router(_deps))
```

- [ ] **Step 8: 移除 `_background_init_once` 中 PDF 路徑參照**

刪除 `main.py` 中所有對 `mcdonalds_tw_extra_value_meals_rag.pdf` 的參照（此時 `_background_init_once` 已被簡化，應已無殘留）。

- [ ] **Step 9: Compile check**

```bash
python3 -m py_compile main.py && echo "OK"
```
期望：`OK`

- [ ] **Step 10: Commit**

```bash
git add main.py
git commit -m "refactor: remove seeds/RAG/emotion deps from main.py, simplify startup"
```

---

## Task 12: 刪除舊檔案

**Files:**
- Delete: 13 個檔案 / 目錄

- [ ] **Step 1: 刪除舊 service 檔案**

```bash
rm services/voice_assist_service.py \
   services/query_router_service.py \
   services/customer_service.py \
   services/emotion_risk_service.py \
   services/multimodal_evidence_service.py
```

- [ ] **Step 2: 刪除舊 route 與 RAG 相關檔案**

```bash
rm routes/multimodal_routes.py \
   routes/rag_routes.py \
   rag_service.py \
   services/rag_review_service.py \
   gemini_direct_chat.py \
   "mcdonalds_tw_extra_value_meals_rag.pdf"
```

- [ ] **Step 3: 刪除 seeds 與 sample_data 目錄**

```bash
rm -rf seeds/ sample_data/
```

- [ ] **Step 4: Compile check — 所有剩餘 .py**

```bash
python3 -m py_compile main.py database.py ai_services.py \
  services/voice_service.py services/emotion_service.py \
  services/barrier_state_service.py services/intervention_pipeline_service.py \
  services/intervention_service.py services/interaction_event_service.py \
  services/scenario_service.py services/recommendation_service.py \
  services/ai_push_service.py \
  routes/voice_routes.py routes/emotion_routes.py \
  routes/core_routes.py routes/menu_routes.py \
  routes/interaction_routes.py routes/demo_routes.py \
  routes/ai_push_routes.py routes/realtime_routes.py \
  routes/debug_routes.py && echo "ALL OK"
```
期望：`ALL OK`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: delete legacy voice/emotion/RAG/seeds/sample_data files"
```

---

## Task 13: 最終驗收

- [ ] **Step 1: 確認沒有殘留的舊 import**

```bash
grep -rn "voice_assist_service\|query_router_service\|customer_service\|emotion_risk_service\|multimodal_evidence_service\|rag_service\|rag_routes\|multimodal_routes\|recommend_cache\|schedule_rag_rebuild\|RAG_SEEDS\|seed_pdf_to_rag\|save_voice_emotion_to_rag" . --include="*.py" | grep -v __pycache__
```
期望：無任何輸出

- [ ] **Step 2: 啟動服務確認**

```bash
curl http://127.0.0.1:8000/api/settings
```
期望：回傳 JSON settings 物件，HTTP 200

- [ ] **Step 3: 測試 emotion stub endpoint**

```bash
curl -s -X POST http://127.0.0.1:8000/api/emotion/analyze \
  -F "session_id=test_001" \
  -F "media=@/dev/null;type=video/webm" | python3 -m json.tool
```
期望：`{"status": "stub", "emotion_available": false, ...}`

- [ ] **Step 4: 最終 commit**

```bash
git add .
git commit -m "chore: final compile verification — backend refactor complete"
```
