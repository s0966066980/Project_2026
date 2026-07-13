"""Emotion application service — multimodal evidence via gateway only.

事件驅動：analyze_event() 經 Multimodal Evidence Gateway 取得 typed evidence，
再寫 log / 語音快取。Evidence 不得直接下單、付款或發出不可逆命令。
"""
import asyncio
import re
import threading
from datetime import datetime

import config
from models.llm import LLMModelPolicy, LLMRequest
from models.multimodal_evidence import MultimodalEvidence, MultimodalEvidenceRequest
from repositories import emotion_log_repository
from services import llm_gateway_service, multimodal_evidence_gateway

EVENT_TYPE_LABELS = {
    "voice_mode": "語音模式",
    "payment_timeout": "付款逾時協助",
}

PROVIDER_LABELS = {
    "emotion_llama": "Emotion-LLaMA",
    "r1_omni": "R1-Omni",
}


def _provider() -> str:
    return config.get("EMOTION_PROVIDER", "emotion_llama") or "emotion_llama"


_voice_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def is_enabled() -> bool:
    return bool(config.get("EMOTION_LLAMA_ENABLED", False))


def get_voice_emotion_cache(session_id: str) -> dict | None:
    with _cache_lock:
        return _voice_cache.get(session_id)


def clear_voice_emotion_cache(session_id: str) -> None:
    with _cache_lock:
        _voice_cache.pop(session_id, None)


async def analyze_event(session_id: str, media_path: str, event_type: str, speech_text: str = "") -> dict:
    """事件驅動分析主入口。非同步執行，結果寫 log + 更新語音快取。"""
    if not is_enabled():
        return {"status": "disabled"}

    skip_qc = not bool(config.get("EMOTION_LLAMA_QUALITY_CHECK", True))
    prompt_template = config.get("EMOTION_LLAMA_PROMPT", "")
    if speech_text and speech_text.strip():
        question = prompt_template.replace("{speech_text}", speech_text)
    else:
        # 無語音時移除含 {speech_text} 的整行，避免模型看到空白語句
        question = re.sub(r"[^\n]*\{speech_text\}[^\n]*\n?", "", prompt_template).strip()
        if not question:
            question = prompt_template.replace("{speech_text}", "(no speech)")

    try:
        evidence = await asyncio.to_thread(
            multimodal_evidence_gateway.collect_evidence,
            MultimodalEvidenceRequest(
                media_path=media_path,
                question=question,
                session_ref=session_id,
                event_type=event_type,
                speech_text=speech_text or "",
                timeout_seconds=float(config.get("EMOTION_LLAMA_TIMEOUT_SEC", 120) or 120),
                skip_quality_check=skip_qc,
                provider_preference=_provider(),
                prompt_version="emotion_event-v1",
                scope_safe_metadata={"surface": "emotion_analyze_event"},
            ),
            enabled=True,
        )
    except Exception as e:
        print(f"⚠️ {PROVIDER_LABELS.get(_provider(), _provider())} analyze_event 失敗: {e}")
        evidence = MultimodalEvidence(
            provider=_provider(),
            model_version="unknown",
            timestamp=datetime.now().isoformat(),
            confidence=None,
            signals={},
            quality="error",
            latency_ms=0.0,
            safe_error="gateway_failure",
            has_evidence=False,
            status="error",
        )

    quality_skipped = evidence.quality == "skipped" or evidence.status == "skipped"
    error = (not evidence.has_evidence) and evidence.quality in {"error", "unavailable", "timeout"}
    result = {
        "emotion": str((evidence.signals or {}).get("emotion") or ""),
        "intensity": str((evidence.signals or {}).get("intensity") or ""),
        "facial": str((evidence.signals or {}).get("facial") or ""),
        "vocal": str((evidence.signals or {}).get("vocal") or ""),
        "description": str((evidence.signals or {}).get("description") or ""),
    }

    # Emotion-LLaMA 常輸出自然語言而非結構化欄位；經 LLM Gateway 補全
    # （frontend 對 analyze_event 是 fire-and-forget，此處等待不影響 UI）
    if (not quality_skipped and not error
            and not result.get("emotion")
            and result.get("description")):
        try:
            ollama_fields = await _extract_emotion_via_ollama(result["description"])
            if ollama_fields.get("emotion"):
                result["emotion"]   = ollama_fields.get("emotion",   "")
                result["intensity"] = ollama_fields.get("intensity", "") or result.get("intensity", "")
                result["facial"]    = ollama_fields.get("facial",    "") or result.get("facial",    "")
                result["vocal"]     = ollama_fields.get("vocal",     "") or result.get("vocal",     "")
        except Exception as e:
            print(f"⚠️ Emotion Ollama 提取失敗: {e}")

    status = (
        "skipped"
        if quality_skipped
        else ("error" if error else ("ok" if (result.get("emotion") or result.get("description")) else "no_evidence"))
    )
    entry = {
        "timestamp": evidence.timestamp or datetime.now().isoformat(),
        "session_id": session_id,
        "provider": evidence.provider or _provider(),
        "event_type": event_type,
        "event_type_label": EVENT_TYPE_LABELS.get(event_type, event_type),
        "clip_sec": float(config.get("EMOTION_LLAMA_CLIP_SEC", 2.0)),
        "quality_skipped": quality_skipped,
        "emotion": result.get("emotion", ""),
        "intensity": result.get("intensity", ""),
        "facial": result.get("facial", ""),
        "vocal": result.get("vocal", ""),
        "description": result.get("description", ""),
        "status": status,
        "assist_response": "",
        "evidence_quality": evidence.quality,
        "evidence_latency_ms": evidence.latency_ms,
        "model_version": evidence.model_version,
        # Evidence never places orders / payments / irreversible commands.
        "decision_boundary": "evidence_only",
    }

    # payment_timeout：用 Ollama + PAYMENT_ASSIST_PROMPT 生成員工可讀的中文情緒摘要
    if event_type == "payment_timeout" and not quality_skipped and not error:
        try:
            assist = await _generate_payment_assist(entry)
            if assist:
                entry["assist_response"] = assist
        except Exception as e:
            print(f"⚠️ payment assist_response 生成失敗: {e}")

    emotion_log_repository.append_log(entry)
    _print_entry(entry)

    if not quality_skipped and not error and entry.get("emotion"):
        with _cache_lock:
            _voice_cache[session_id] = entry
        if config.get("EMOTION_LLAMA_AFFECT_BARRIER", False):
            try:
                asyncio.create_task(_trigger_barrier_update(session_id, entry))
            except RuntimeError:
                pass

    return entry


def _print_entry(entry: dict) -> None:
    sid   = entry.get("session_id", "?")[:8]
    evt   = entry.get("event_type_label") or entry.get("event_type", "")
    st    = entry.get("status", "")
    prov  = PROVIDER_LABELS.get(entry.get("provider", ""), entry.get("provider", ""))
    tag   = f"[Emotion:{prov}]" if prov else "[Emotion]"
    if st == "skipped":
        print(f"{tag} {sid} | {evt} | 品質快篩跳過")
        return
    if st == "error":
        print(f"{tag} {sid} | {evt} | ⚠️ 分析失敗")
        return
    emo   = entry.get("emotion", "—")
    intens = entry.get("intensity", "")
    facial = entry.get("facial", "")
    vocal  = entry.get("vocal", "")
    desc   = entry.get("description", "")
    parts = [f"情緒={emo}"]
    if intens:
        parts.append(f"強度={intens}")
    if facial:
        parts.append(f"表情={facial}")
    if vocal:
        parts.append(f"聲音={vocal}")
    if desc:
        desc_display = desc[:120] + ("…" if len(desc) > 120 else "")
        parts.append(f"描述={desc_display}")
    print(f"{tag} {sid} | {evt} | " + " | ".join(parts))



async def _generate_payment_assist(entry: dict) -> str:
    """根據情緒分析結果，用 PAYMENT_ASSIST_PROMPT 生成員工可讀的中文情緒摘要。"""
    prompt_template = config.get("PAYMENT_ASSIST_PROMPT", "")
    if not prompt_template:
        return ""

    emotion     = entry.get("emotion", "")
    intensity   = entry.get("intensity", "")
    facial      = entry.get("facial", "")
    vocal       = entry.get("vocal", "")
    description = entry.get("description", "")

    # 組成情緒資訊供 prompt 使用
    emotion_summary = (
        f"情緒：{emotion or '未知'}\n"
        f"強度：{intensity or '未知'}\n"
        + (f"表情：{facial}\n" if facial else "")
        + (f"聲音：{vocal}\n" if vocal else "")
        + (f"描述：{description}\n" if description else "")
    ).strip()

    system = prompt_template
    user = f"顧客情緒分析結果：\n{emotion_summary}"

    response = await asyncio.to_thread(
        llm_gateway_service.generate,
        LLMRequest(
            task="payment_assist",
            system_prompt=str(system or ""),
            user_prompt=user,
            model_policy=LLMModelPolicy.LOCAL_FIRST,
            timeout_seconds=float(config.get("OLLAMA_TIMEOUT", 30) or 30),
            prompt_version="payment_assist-v1",
            expect_json=True,
            response_tag="PAYMENT_ASSIST",
            model_name=str(config.get("MODEL_NAME", "qwen3.5:4b") or "qwen3.5:4b"),
            max_tokens=80,
            max_retries=0,
        ),
    )
    raw = dict(response.parsed or {}) if response.parsed else {}
    if response.content and not raw:
        return str(response.content).strip()
    if isinstance(raw, dict):
        msg = raw.get("assist_message") or raw.get("message") or raw.get("response") or ""
        return str(msg).strip()
    return ""


async def _extract_emotion_via_ollama(description: str) -> dict:
    """Emotion-LLaMA 自然語言描述 → LLM Gateway → 結構化情緒欄位。"""
    system = (
        "You are an emotion extraction assistant. "
        "Given a video analysis description, extract the structured emotion data. "
        "Reply ONLY with valid JSON, no extra text."
    )
    user = (
        f"Analysis description:\n{description}\n\n"
        "Return ONLY this JSON (fill in values based on the description). "
        "Keep 'emotion' and 'intensity' as the English labels listed below; "
        "write 'facial' and 'vocal' in Traditional Chinese (繁體中文):\n"
        '{"emotion":"<primary emotion label, e.g. neutral/happy/frustrated/anxious/sad>",'
        '"intensity":"low|medium|high",'
        '"facial":"<繁體中文簡述表情線索>",'
        '"vocal":"<繁體中文簡述聲音線索，無聲則填「靜默」>"}'
    )
    response = await asyncio.to_thread(
        llm_gateway_service.generate,
        LLMRequest(
            task="emotion_extract",
            system_prompt=system,
            user_prompt=user,
            model_policy=LLMModelPolicy.LOCAL_FIRST,
            timeout_seconds=float(config.get("OLLAMA_TIMEOUT", 30) or 30),
            prompt_version="emotion_extract-v1",
            expect_json=True,
            response_tag="EMOTION_EXTRACT",
            model_name=str(config.get("MODEL_NAME", "qwen3.5:4b") or "qwen3.5:4b"),
            max_tokens=120,
            max_retries=0,
        ),
    )
    if response.safe_error or not response.parsed:
        return {}
    return dict(response.parsed) if isinstance(response.parsed, dict) else {}


async def _trigger_barrier_update(session_id: str, emotion_entry: dict) -> None:
    """情緒結果非同步觸發 barrier_state 更新。"""
    try:
        from services import intervention_pipeline_service
        emotion_hint = {
            "emotion": emotion_entry.get("emotion", ""),
            "intensity": emotion_entry.get("intensity", ""),
            "event_type": emotion_entry.get("event_type", ""),
        }
        await intervention_pipeline_service.run_intervention_pipeline(
            session_id=session_id,
            ui_context={"emotion_hint": emotion_hint},
            speech_text="",
            source="emotion_llama",
        )
    except Exception as e:
        print(f"⚠️ Emotion barrier update 失敗: {e}")



