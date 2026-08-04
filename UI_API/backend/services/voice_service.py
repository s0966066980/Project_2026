"""語音服務：STT → Ollama → TTS。

STT 和 TTS 實作透過 Provider 抽象層決定，不在此層關心。
"""
import asyncio
import base64
from difflib import SequenceMatcher
import json as _json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from typing import AsyncGenerator

import database

import config
from modules.assistance_policy import decide as decide_assistance
from models.commercial_scope import CommercialScope
from models.llm import LLMRequest
from repositories import menu_repository, session_repository
from services import (
    emotion_service,
    llm_gateway_service,
    llm_routing_service,
    rag_guard_service,
    rag_offer_service,
    recommendation_context_service,
    recommendation_engine_service,
)
from services.recommendation_service import (
    coerce_cart_actions,
    looks_like_order_request,
    menu_aliases,
    normalize_order_text,
)
from services.stt_service import get_stt
from services.tts_service import get_tts

_menu_cache: dict = {"items": None, "context": None, "ts": 0.0}
_menu_cache_lock = asyncio.Lock()
_EMOTION_REFERENCE_UNSET = object()
_background_emotion_tasks: set[asyncio.Task] = set()


def _media_has_video_track(media_path: str) -> bool:
    """Return whether a media file contains a decodable video stream."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not media_path or not os.path.exists(media_path):
        return False
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=index",
                "-of", "csv=p=0",
                media_path,
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return completed.returncode == 0 and bool(completed.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


async def _load_menu_cached() -> tuple:
    now = time.monotonic()
    ttl = float(config.get("VOICE_MENU_CACHE_TTL_SEC", 60.0))
    if _menu_cache["items"] is not None and now - _menu_cache["ts"] <= ttl:
        return _menu_cache["items"], _menu_cache["context"]
    async with _menu_cache_lock:
        now = time.monotonic()
        if _menu_cache["items"] is not None and now - _menu_cache["ts"] <= ttl:
            return _menu_cache["items"], _menu_cache["context"]
        items, context = await asyncio.gather(
            asyncio.to_thread(menu_repository.get_menu),
            asyncio.to_thread(database.build_compact_menu_context),
        )
        _menu_cache["items"] = items
        _menu_cache["context"] = context
        _menu_cache["ts"] = now
    return _menu_cache["items"], _menu_cache["context"]


def _format_history(history: list) -> str:
    if not history:
        return ""
    max_turns = int(config.get("VOICE_HISTORY_MAX_TURNS", 4))
    recent = history[-max_turns:]
    lines = []
    for turn in recent:
        if turn.get("user_speech"):
            lines.append(f"顧客：{turn['user_speech']}")
        if turn.get("ai_response"):
            ai_line = f"系統：{turn['ai_response']}"
            # 補上推薦 ID，讓下一輪 Ollama 可直接引用而不需在文字中重新解析
            ids = [i for i in (turn.get("mentioned_ids") or []) if i]
            if ids:
                ai_line += f"（推薦品項 ID：{', '.join(ids)}）"
            lines.append(ai_line)
    if not lines:
        return ""
    return "【對話歷史（最近幾輪）】\n" + "\n".join(lines)



async def _analyze_current_voice_emotion_pair(
    *,
    session_id: str,
    media_path: str,
    speech_text: str,
    emotion_round_id: str,
    voice_turn_id: str,
    voice_turn_index: int,
) -> dict | None:
    """Analyze one completed turn for later-turn assistance and observability."""
    if (
        not emotion_service.is_enabled()
        or config.get("EMOTION_LLAMA_EVENT_VOICE", True) is False
    ):
        return None

    pair_id = f"{emotion_round_id}:{voice_turn_id or voice_turn_index}"[:160]
    common = {
        "session_id": session_id,
        "media_path": media_path,
        "event_type": "voice_mode_ended",
        "update_voice_session": True,
        "emotion_round_id": emotion_round_id,
        "voice_turn_id": voice_turn_id,
        "voice_turn_index": voice_turn_index,
        "observed_at_ms": int(time.time() * 1000),
        "comparison_pair_id": pair_id,
        "cache_voice_observation": True,
    }
    try:
        mode = str(config.get("EMOTION_LLAMA_ANALYSIS_MODE", "media_plus_stt") or "")
        if mode not in {"media_only", "media_plus_stt", "paired"}:
            mode = "media_plus_stt"
        if not speech_text or config.get("EMOTION_LLAMA_INCLUDE_STT", True) is False:
            mode = "media_only"

        if mode == "media_only":
            result = await emotion_service.analyze_event(
                speech_text="",
                analysis_variant="media_only",
                **common,
            )
        elif mode == "media_plus_stt":
            result = await emotion_service.analyze_event(
                speech_text=speech_text,
                analysis_variant="media_plus_stt",
                **common,
            )
        else:
            result, _baseline = await asyncio.gather(
                emotion_service.analyze_event(
                    speech_text=speech_text,
                    analysis_variant="media_plus_stt",
                    **common,
                ),
                emotion_service.analyze_event(
                    speech_text="",
                    analysis_variant="media_only",
                    **common,
                ),
            )
    except Exception as exc:
        print(f"⚠️ 本次語音情緒分析失敗，將不影響語音回覆: {exc}")
        return None
    return result if result.get("status") == "ok" and result.get("emotion") else None


def _schedule_voice_emotion_observation(
    *,
    session_id: str,
    media_path: str,
    speech_text: str,
    emotion_round_id: str,
    voice_turn_id: str,
    voice_turn_index: int,
) -> asyncio.Task | None:
    """Run slow emotion inference outside the current Voice Turn critical path.

    Durable Voice Turns execute their effects in a worker thread, while the
    legacy async path calls this function from an event loop. Support both
    callers without constructing an orphaned coroutine when no loop is running.
    """
    if (
        not emotion_service.is_enabled()
        or config.get("EMOTION_LLAMA_EVENT_VOICE", True) is False
    ):
        return None

    suffix = os.path.splitext(media_path)[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        background_path = tmp.name
    try:
        shutil.copyfile(media_path, background_path)
    except Exception:
        try:
            os.remove(background_path)
        except OSError:
            pass
        raise

    async def _run() -> None:
        try:
            if not await asyncio.to_thread(_media_has_video_track, background_path):
                return
            await _analyze_current_voice_emotion_pair(
                session_id=session_id,
                media_path=background_path,
                speech_text=speech_text,
                emotion_round_id=emotion_round_id,
                voice_turn_id=voice_turn_id,
                voice_turn_index=voice_turn_index,
            )
        except Exception as exc:
            print(f"⚠️ 背景語音情緒分析失敗: {exc}")
        finally:
            try:
                os.remove(background_path)
            except OSError:
                pass

    task_name = f"voice-emotion-{voice_turn_id or voice_turn_index}"
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        def _thread_runner() -> None:
            asyncio.run(_run())

        thread = threading.Thread(target=_thread_runner, name=task_name, daemon=True)
        try:
            thread.start()
        except Exception:
            try:
                os.remove(background_path)
            except OSError:
                pass
            raise
        return None

    task = loop.create_task(_run(), name=task_name)
    _background_emotion_tasks.add(task)
    task.add_done_callback(_background_emotion_tasks.discard)
    return task


async def _record_voice_emotion_influence(**payload) -> None:
    """Observability must never turn a successful voice reply into an error."""
    try:
        await asyncio.to_thread(emotion_service.record_voice_llm_influence, **payload)
    except Exception as exc:
        print(f"⚠️ 語音 LLM 情緒參考紀錄失敗: {exc}")


def _build_emotion_context(
    session_id: str,
    emotion_round_id: str = "",
    emotion_reference: dict | None | object = _EMOTION_REFERENCE_UNSET,
) -> str:
    """Only expose policy-approved assistance instructions to the voice LLM."""
    cached = (
        emotion_service.get_voice_emotion_cache(session_id, emotion_round_id)
        if emotion_reference is _EMOTION_REFERENCE_UNSET
        else emotion_reference
    )
    decision = _emotion_assistance_decision(session_id, cached)
    if not decision.get("applied"):
        return ""
    return (
        "【本輪回覆輔助政策】\n"
        "使用較短句子；一次只問一個確認問題；任何購物車變更前再次確認。"
        "不得診斷或提及顧客情緒，不得改價、自行選品或自行下單。"
    )


def _emotion_assistance_decision(session_id: str, evidence: dict | None) -> dict:
    mode = str(config.get("EMOTION_ASSISTANCE_MODE", "shadow") or "shadow")
    # Legacy switch remains a compatibility kill switch for active prompt changes.
    if mode == "active" and not config.get("EMOTION_LLAMA_AFFECT_VOICE", False):
        mode = "shadow"
    return decide_assistance(
        evidence,
        mode=mode,
        confidence_threshold=float(
            config.get("EMOTION_ASSISTANCE_CONFIDENCE_THRESHOLD", 0.7) or 0.7
        ),
        session_id=session_id,
        rollout_percent=int(
            config.get("EMOTION_ASSISTANCE_ROLLOUT_PERCENT", 0) or 0
        ),
    )


def _history_menu_ids(history: list[dict]) -> set[str]:
    ids: set[str] = set()
    for turn in history[-4:]:
        ids.update(str(item_id or "").strip() for item_id in turn.get("mentioned_ids") or [])
        ids.update(
            str(action.get("id") or "").strip()
            for action in turn.get("cart_actions") or []
            if isinstance(action, dict)
        )
    return {item_id for item_id in ids if item_id}


def _select_voice_menu_candidates(
    user_text: str,
    menu_items: list[dict],
    recommendation: dict,
    history: list[dict],
    *,
    limit: int | None = None,
) -> tuple[list[dict], bool]:
    """Return a bounded menu set and whether an order request needs clarification."""
    candidate_limit = max(3, min(20, int(limit or config.get("VOICE_MENU_CANDIDATE_LIMIT", 12))))
    normalized_text = normalize_order_text(user_text)
    history_ids = _history_menu_ids(history)
    recommended = recommendation.get("items") or []
    recommended_ids = [str(row.get("id") or "") for row in recommended if isinstance(row, dict)]
    ranked_recommendations = sorted(
        (row for row in recommendation.get("candidates") or [] if isinstance(row, dict)),
        key=lambda row: (-int(row.get("score") or 0), str(row.get("id") or "")),
    )
    recommendation_rank = {
        str(row.get("id") or ""): index
        for index, row in enumerate(ranked_recommendations)
        if isinstance(row, dict) and row.get("id")
    }

    scored: list[tuple[float, str, dict]] = []
    lexical_matches: set[str] = set()
    for item in menu_items:
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        aliases = [alias for alias in menu_aliases(item) if len(alias) >= 2]
        exact = max((len(alias) for alias in aliases if alias in normalized_text), default=0)
        if exact:
            lexical_matches.add(item_id)
        fuzzy = max(
            (SequenceMatcher(None, normalized_text, alias).ratio() for alias in aliases),
            default=0.0,
        )
        category = normalize_order_text(str(item.get("category") or ""))
        score = float(exact * 20)
        if category and category in normalized_text:
            score = max(score, 75.0)
        if item_id in history_ids:
            score = max(score, 70.0)
        if item_id in recommended_ids:
            score = max(score, 60.0 - recommended_ids.index(item_id))
        if item_id in recommendation_rank:
            score = max(score, 35.0 - min(20, recommendation_rank[item_id]))
        score = max(score, fuzzy * 45.0)
        scored.append((score, item_id, item))

    scored.sort(key=lambda row: (-row[0], row[1]))
    candidates = [row[2] for row in scored[:candidate_limit]]
    needs_clarification = looks_like_order_request(user_text) and not lexical_matches and not history_ids
    return candidates, needs_clarification


def _format_voice_menu_candidates(candidates: list[dict], needs_clarification: bool) -> str:
    rows = ["【語音菜單候選集】ID｜名稱｜分類｜價格"]
    for item in candidates:
        rows.append(
            f"{item.get('id', '')}｜{item.get('name', '')}｜"
            f"{item.get('category', '')}｜${item.get('price', '')}"
        )
    if needs_clarification:
        rows.append("候選信心不足：不得輸出 cart_actions；請用上述少量相近品項詢問顧客澄清。")
    else:
        rows.append("只能引用上述候選 ID；最終品項、價格與購物車動作仍由伺服器驗證。")
    return "\n".join(rows)


def _build_voice_order_draft(
    user_text: str,
    proposed_actions: list[dict],
    candidate_items: list[dict],
) -> dict:
    """Build a non-transactional, server-validated draft for explicit kiosk confirmation."""
    if not looks_like_order_request(user_text):
        return {"items": [], "recommendation_ids": [], "clarification_ids": []}

    by_id = {
        str(item.get("id") or ""): item
        for item in candidate_items
        if isinstance(item, dict) and item.get("id")
    }
    items = [
        {
            "id": action["id"],
            "quantity": max(1, min(10, int(action.get("quantity") or 1))),
            "selected": False,
        }
        for action in proposed_actions
        if action.get("id") in by_id
    ]
    proposed_ids = {item["id"] for item in items}
    remaining_ids = [item_id for item_id in by_id if item_id not in proposed_ids]
    return {
        "items": items,
        "recommendation_ids": remaining_ids[:3] if items else [],
        "clarification_ids": remaining_ids[:3] if not items else [],
    }


async def _build_voice_context(
    session_id: str,
    user_text: str,
    scope: CommercialScope | None = None,
    emotion_round_id: str = "",
    emotion_reference: dict | None | object = _EMOTION_REFERENCE_UNSET,
) -> tuple[str, str, list]:
    """組合語音 LLM 的 system_prompt 與 user_prompt。

    handle_voice 與 handle_voice_stream 共用此邏輯：
    載入菜單與對話歷史、使用繁體中文 system prompt、注入情緒／RAG／熱門 context。
    回傳 (system_prompt, user_prompt, menu_items)。
    """
    (menu_items, _full_menu_context), history = await asyncio.gather(
        _load_menu_cached(),
        asyncio.to_thread(session_repository.get_session_history, session_id),
    )
    history_context = _format_history(history)

    system_prompt = config.get("VOICE_ASSIST_SYSTEM_PROMPT")
    system_prompt += (
        "\n購物車安全規則：cart_actions 只代表要呈現在確認視窗的候選草稿，"
        "不得宣稱已加入購物車或已完成下單；請告知顧客必須在畫面上勾選並確認。"
    )

    # 注入這次語音 request 的 STT 版本快照；不依賴跨 request 快取。
    emotion_context = _build_emotion_context(session_id, emotion_round_id, emotion_reference)
    if emotion_context:
        system_prompt += (
            "\n顧客情緒參考是非同步模型的輔助線索，不一定代表顧客真實感受。"
            "只能用來調整回覆語氣與措辭，不得改變價格、資格、品項或購物車規則，"
            "也不得向顧客宣稱、暗示或透露系統辨識了其情緒。"
        )

    recommendation_context = await recommendation_context_service.build_context(
        session_id,
        rag_query=user_text,
        surface="voice",
        menu_items=menu_items,
        scope=scope,
    )
    rag_context = recommendation_context.get("rag", {}).get("context", "")
    offer_section = rag_offer_service.format_offer_prompt_section(
        recommendation_context.get("rag", {}).get("offers") or [],
        audience=recommendation_context.get("audience", "guest"),
    )
    rag_guard_section = rag_guard_service.build_voice_guard_section(
        user_text,
        offers=recommendation_context.get("rag", {}).get("offers") or [],
        audience=recommendation_context.get("audience", "guest"),
        rag_context=rag_context,
    )
    member_section = recommendation_context_service.member_prompt_section(recommendation_context)
    recommendation = await asyncio.to_thread(
        recommendation_engine_service.recommend,
        recommendation_context,
        3,
        False,
    )
    recommendation_section = recommendation_engine_service.format_voice_recommendation_context(recommendation)
    candidate_items, needs_clarification = _select_voice_menu_candidates(
        user_text,
        menu_items,
        recommendation,
        history,
    )
    candidate_menu_context = _format_voice_menu_candidates(candidate_items, needs_clarification)

    input_label = "【本輪語音輸入】" if history_context else "【顧客語音輸入】"
    user_prompt = (
        (f"{history_context}\n\n" if history_context else "")
        + f"{input_label}\n{user_text}\n\n"
        + (f"{member_section}\n\n" if member_section else "")
        + (f"{emotion_context}\n\n" if emotion_context else "")
        + (f"{rag_guard_section}\n\n" if rag_guard_section else "")
        + (f"{offer_section}\n\n" if offer_section else "")
        + (f"{recommendation_section}\n\n" if recommendation_section else "")
        + (f"{rag_context}\n\n" if rag_context else "")
        + candidate_menu_context
    )
    return system_prompt, user_prompt, candidate_items


async def handle_voice(
    session_id: str,
    audio_path: str,
    ollama_semaphore,
    scope: CommercialScope | None = None,
    emotion_round_id: str = "",
    voice_turn_id: str = "",
    voice_turn_index: int = 0,
) -> dict:
    # ── 1. STT ────────────────────────────────────────────────────
    stt = get_stt()
    try:
        stt_result = await stt.transcribe(audio_path)
    except Exception as e:
        return {
            "status": "error",
            "message": f"STT 失敗: {e}",
            "user_text": "", "ai_response": "", "audio_base64": "",
            "audio_format": "", "cart_actions": [], "order_draft": None,
        }

    user_text = (stt_result.get("text") or "").strip()
    if not user_text:
        return {
            "status": "error",
            "message": "無法辨識語音內容",
            "user_text": "", "ai_response": "", "audio_base64": "",
            "audio_format": "", "cart_actions": [], "order_draft": None,
        }

    # ── 2. Ollama LLM ─────────────────────────────────────────────
    emotion_reference = emotion_service.get_voice_emotion_cache(session_id, emotion_round_id)
    _schedule_voice_emotion_observation(
        session_id=session_id,
        media_path=audio_path,
        speech_text=user_text,
        emotion_round_id=emotion_round_id,
        voice_turn_id=voice_turn_id,
        voice_turn_index=voice_turn_index,
    )
    system_prompt, user_prompt, menu_items = await _build_voice_context(
        session_id, user_text, scope, emotion_round_id, emotion_reference
    )

    model = config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b")
    async with ollama_semaphore:
        llm_response = await asyncio.to_thread(
            llm_gateway_service.generate,
            LLMRequest(
                task="voice_assist",
                system_prompt=str(system_prompt or ""),
                user_prompt=str(user_prompt or ""),
                model_policy=llm_routing_service.configured_policy(),
                timeout_seconds=float(config.get("OLLAMA_TIMEOUT", 30) or 30),
                prompt_version="voice_assist-v1",
                expect_json=True,
                response_tag="",
                model_name=str(model or "qwen3.5:4b"),
                max_retries=0,
            ),
        )
    result = dict(llm_response.parsed or {}) if llm_response.parsed else {}
    if llm_response.safe_error or llm_response.finish_reason in {"error", "timeout", "schema_failure"}:
        result = {}

    if not isinstance(result, dict) or not result.get("ai_response"):
        ai_response = "我可以協助您了解菜單或加入餐點。"
        proposed_actions = []
    else:
        ai_response = str(result.get("ai_response") or "").strip()
        raw_cart = result.get("cart_actions") or []
        proposed_actions = coerce_cart_actions(
            raw_cart if isinstance(raw_cart, list) else [],
            user_text, menu_items,
        )
        if proposed_actions:
            ai_response = "已整理您提到的餐點，請在畫面上勾選要加入的品項並確認。"
        if not ai_response:
            ai_response = "已整理您提到的餐點，請在畫面上勾選確認。" if proposed_actions else "我可以協助您了解菜單或選擇餐點。"

    order_draft = _build_voice_order_draft(user_text, proposed_actions, menu_items)

    _mentioned = result.get("mentioned_ids") or [] if isinstance(result, dict) else []
    await asyncio.to_thread(
        session_repository.record_session_state,
        session_id=session_id,
        user_speech=user_text,
        ai_response=ai_response,
        language="zh",
        mentioned_ids=_mentioned,
        cart_actions=proposed_actions,
    )

    # ── 3. TTS ────────────────────────────────────────────────────
    tts = get_tts()
    try:
        audio_base64 = await tts.synthesize_base64(ai_response)
    except Exception as e:
        print(f"⚠️ TTS 失敗: {e}")
        audio_base64 = ""
    playback_status = "available" if audio_base64 else "degraded"

    await _record_voice_emotion_influence(
        session_id=session_id,
        emotion_round_id=emotion_round_id,
        voice_turn_id=voice_turn_id,
        voice_turn_index=voice_turn_index,
        user_speech=user_text,
        ai_response=ai_response,
        emotion_reference=emotion_reference,
        affect_voice_enabled=bool(config.get("EMOTION_LLAMA_AFFECT_VOICE", False)),
        assistance_decision=_emotion_assistance_decision(session_id, emotion_reference),
    )

    return {
        "status": "success",
        "user_text": user_text,
        "ai_response": ai_response,
        "audio_base64": audio_base64,
        "audio_format": tts.audio_format,
        "playback_status": playback_status,
        "playback_message": "" if playback_status == "available" else "文字結果已保留，但語音播放暫時不可用。",
        # Compatibility field is intentionally non-executable. Voice ordering is
        # committed only through explicit confirmation of order_draft in the kiosk.
        "cart_actions": [],
        "order_draft": order_draft,
    }


# ── 串流版語音處理 ─────────────────────────────────────────────────
_AI_RESP_RE = re.compile(r'"ai_response"\s*:\s*"((?:[^"\\]|\\.)*)')
_HARD_ENDS  = frozenset("。！？")
_SOFT_ENDS  = frozenset("，；\n")
_SOFT_MIN   = 15          # 軟斷點最小字數


def _safe_progressive_voice_text(text: str) -> str:
    """Prevent streamed model prose from claiming a draft already changed the cart."""
    normalized = str(text or "").strip()
    unsafe_claim = re.search(r"(?:加入|放入|下單|\b(?:add|added|order(?:ed)?|placed)\b)", normalized, re.IGNORECASE)
    if unsafe_claim:
        return "已整理您提到的餐點，請在畫面上勾選並確認。"
    return normalized


async def handle_voice_stream(
    session_id: str,
    audio_path: str,
    ollama_semaphore,
    scope: CommercialScope | None = None,
    emotion_round_id: str = "",
    voice_turn_id: str = "",
    voice_turn_index: int = 0,
) -> AsyncGenerator[bytes, None]:
    """
    串流版：STT → LLM 串流 → 逐句 TTS。
    每個 chunk 為 NDJSON 行（後接 \\n）：
      {"type":"transcript","user_text":...}
      {"type":"assistant_text","ai_response":...}
      {"type":"audio","data":"<base64>","format":"<wav|mp3>"}
      {"type":"done","status":"success","user_text":...,"ai_response":...,"cart_actions":...}
    """
    tts = get_tts()
    stt = get_stt()

    # ── STT ──────────────────────────────────────────────────────────
    try:
        stt_result = await stt.transcribe(audio_path)
    except Exception as e:
        err = _json.dumps({"type": "done", "status": "error", "message": f"STT 失敗: {e}"})
        yield (err + "\n").encode()
        return

    user_text    = (stt_result.get("text") or "").strip()
    if not user_text:
        err = _json.dumps({"type": "done", "status": "error", "message": "無法辨識語音內容"})
        yield (err + "\n").encode()
        return

    transcript = _json.dumps({
        "type": "transcript",
        "user_text": user_text,
    }, ensure_ascii=False)
    yield (transcript + "\n").encode()

    # ── Context + System prompt（與 handle_voice 共用組裝邏輯） ──────────
    emotion_reference = emotion_service.get_voice_emotion_cache(session_id, emotion_round_id)
    _schedule_voice_emotion_observation(
        session_id=session_id,
        media_path=audio_path,
        speech_text=user_text,
        emotion_round_id=emotion_round_id,
        voice_turn_id=voice_turn_id,
        voice_turn_index=voice_turn_index,
    )
    system_prompt, user_prompt, menu_items = await _build_voice_context(
        session_id, user_text, scope, emotion_round_id, emotion_reference
    )

    model = config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b")
    voice_num_predict = int(config.get("VOICE_NUM_PREDICT",
                            config.get("OLLAMA_NUM_PREDICT", 220)))

    # ── LLM 串流 → 逐句 TTS ─────────────────────────────────────────
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _run_stream():
        try:
            stream_request = LLMRequest(
                task="voice_assist",
                system_prompt=str(system_prompt or ""),
                user_prompt=str(user_prompt or ""),
                # Carries the store policy so a cloud-only store is served by the gateway's
                # non-streaming fallback instead of silently reaching Ollama anyway.
                model_policy=llm_routing_service.configured_policy(),
                timeout_seconds=float(config.get("OLLAMA_TIMEOUT", 120) or 120),
                prompt_version="voice_assist-stream-v1",
                expect_json=True,
                model_name=str(model or "qwen3.5:4b"),
                max_tokens=voice_num_predict,
            )
            for token in llm_gateway_service.stream_tokens(stream_request, num_predict=voice_num_predict):
                loop.call_soon_threadsafe(queue.put_nowait, token)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    full_buf   = ""   # 累積完整 token 串，最後解析 JSON
    matched_len = 0   # 已處理 ai_response 長度
    sent_buf   = ""   # 待 TTS 的句子 buffer
    ai_response_final = ""
    tts_failed = False
    audio_emitted = False

    async with ollama_semaphore:
        threading.Thread(target=_run_stream, daemon=True).start()

        while True:
            token = await queue.get()
            if token is None:
                break
            full_buf += token

            m = _AI_RESP_RE.search(full_buf)
            if not m:
                continue

            new_text = m.group(1)[matched_len:]
            matched_len = len(m.group(1))
            sent_buf += new_text

            # 找斷點
            flush_at = -1
            for i, ch in enumerate(sent_buf):
                if ch in _HARD_ENDS:
                    flush_at = i
                    break
                if ch in _SOFT_ENDS and i >= _SOFT_MIN:
                    flush_at = i
                    break

            if flush_at >= 0:
                sentence = _safe_progressive_voice_text(
                    sent_buf[:flush_at + 1]
                )
                sent_buf = sent_buf[flush_at + 1:]
                if sentence:
                    text_chunk = _json.dumps({
                        "type": "assistant_text",
                        "ai_response": (ai_response_final + sentence).strip(),
                        "user_text": user_text,
                    }, ensure_ascii=False)
                    ai_response_final = (ai_response_final + sentence).strip()
                    yield (text_chunk + "\n").encode()
                    try:
                        audio_bytes = await tts.synthesize(sentence)
                        if not audio_bytes:
                            raise RuntimeError("TTS returned empty audio")
                        b64 = base64.b64encode(audio_bytes).decode()
                        chunk = _json.dumps({
                            "type": "audio",
                            "data": b64,
                            "format": tts.audio_format,
                        }, ensure_ascii=False)
                        yield (chunk + "\n").encode()
                        audio_emitted = True
                    except Exception as e:
                        tts_failed = True
                        print(f"⚠️ 串流 TTS 失敗: {e}")

    # 剩餘 buffer flush
    remainder = _safe_progressive_voice_text(sent_buf)
    if remainder:
        ai_response_final = (ai_response_final + remainder).strip()
        text_chunk = _json.dumps({
            "type": "assistant_text",
            "ai_response": ai_response_final,
            "user_text": user_text,
        }, ensure_ascii=False)
        yield (text_chunk + "\n").encode()
        try:
            audio_bytes = await tts.synthesize(remainder)
            if not audio_bytes:
                raise RuntimeError("TTS returned empty audio")
            b64 = base64.b64encode(audio_bytes).decode()
            chunk = _json.dumps({
                "type": "audio",
                "data": b64,
                "format": tts.audio_format,
            }, ensure_ascii=False)
            yield (chunk + "\n").encode()
            audio_emitted = True
        except Exception as e:
            tts_failed = True
            print(f"⚠️ 串流 TTS 失敗: {e}")

    # 解析完整 JSON → server-validated, non-transactional order draft
    result = llm_gateway_service.parse_structured_content(full_buf, "VOICE_STREAM")
    ai_response_final = str(result.get("ai_response") or "").strip() or ai_response_final
    raw_cart    = result.get("cart_actions") or []
    proposed_actions = coerce_cart_actions(
        raw_cart if isinstance(raw_cart, list) else [],
        user_text, menu_items,
    )
    if proposed_actions:
        ai_response_final = "已整理您提到的餐點，請在畫面上勾選要加入的品項並確認。"
    mentioned_ids = result.get("mentioned_ids") or []
    order_draft = _build_voice_order_draft(user_text, proposed_actions, menu_items)

    # 某些模型會在串流期間輸出不完整的 JSON escape，直到完整解析後才拿得到
    # ai_response。若先前尚未產生音訊，最後再嘗試一次完整答案。
    if ai_response_final and not audio_emitted and not tts_failed:
        try:
            audio_bytes = await tts.synthesize(ai_response_final)
            if not audio_bytes:
                raise RuntimeError("TTS returned empty audio")
            b64 = base64.b64encode(audio_bytes).decode()
            chunk = _json.dumps({
                "type": "audio",
                "data": b64,
                "format": tts.audio_format,
            }, ensure_ascii=False)
            yield (chunk + "\n").encode()
            audio_emitted = True
        except Exception as e:
            tts_failed = True
            print(f"⚠️ 串流 TTS 失敗: {e}")

    # 寫回 session history（含推薦 ID，供下一輪多輪記憶使用）
    await asyncio.to_thread(
        session_repository.record_session_state,
        session_id=session_id,
        user_speech=user_text,
        ai_response=ai_response_final,
        language="zh",
        mentioned_ids=mentioned_ids,
        cart_actions=proposed_actions,
    )
    await _record_voice_emotion_influence(
        session_id=session_id,
        emotion_round_id=emotion_round_id,
        voice_turn_id=voice_turn_id,
        voice_turn_index=voice_turn_index,
        user_speech=user_text,
        ai_response=ai_response_final,
        emotion_reference=emotion_reference,
        affect_voice_enabled=bool(config.get("EMOTION_LLAMA_AFFECT_VOICE", False)),
        assistance_decision=_emotion_assistance_decision(session_id, emotion_reference),
    )

    done = _json.dumps({
        "type": "done",
        "status": "success",
        "user_text": user_text,
        "ai_response": ai_response_final,
        "cart_actions": [],
        "order_draft": order_draft,
        "mentioned_ids": mentioned_ids,
        "playback_status": "available" if audio_emitted else "degraded",
        "playback_message": "" if audio_emitted else "文字結果已保留，但語音播放暫時不可用。",
    }, ensure_ascii=False)
    yield (done + "\n").encode()
