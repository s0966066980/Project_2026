from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import config
from capabilities import catalog
from models.llm import LLMRequest
from modules.runtime_persistence.runtime import sqlite_database_path
from repositories import postgres_utils, session_repository
from services import llm_gateway_service, llm_routing_service
from services.recommendation_service import coerce_cart_actions
from services.stt_service import get_stt
from services.tts_service import get_tts

from .module import TransientVoiceTurnError, VoiceTurnModule
from .postgres_store import PostgresVoiceTurnStore
from .sqlite_store import SQLiteVoiceTurnStore


class ProductionSTT:
    def transcribe(self, *, audio_ref: str, operation_key: str) -> dict[str, Any]:
        try:
            return asyncio.run(get_stt().transcribe(audio_ref))
        except (TimeoutError, ConnectionError) as exc:
            raise TransientVoiceTurnError(str(exc)) from exc


class ProductionMenu:
    def candidates(self, *, scope, session_id: str, operation_key: str) -> list[dict[str, Any]]:
        rows = catalog.list_active_items()
        return [
            {
                **row,
                "item_id": str(row.get("id") or row.get("item_id") or ""),
                "available": row.get("available", True) is not False,
            }
            for row in rows
            if row.get("id") or row.get("item_id")
        ]


class ProductionAssistant:
    def assist(self, *, transcript: str, candidates: list[dict[str, Any]], operation_key: str) -> dict[str, Any]:
        compact = [
            {
                "id": row["item_id"],
                "name": row.get("name", ""),
                "price": row.get("price", 0),
                "available": row.get("available", True),
            }
            for row in candidates
        ]
        prompt = (
            "Return JSON with ai_response, cart_actions, mentioned_ids. "
            "ai_response must be concise (at most 60 Chinese characters or 35 English words). "
            "mentioned_ids must contain at most five available menu ids explicitly named by the customer or ai_response. "
            "cart_actions may only contain available menu ids and never means the cart was changed.\n"
            f"customer={transcript}\nmenu={json.dumps(compact, ensure_ascii=False)}"
        )
        try:
            response = llm_gateway_service.generate(
                LLMRequest(
                    task="voice_assist",
                    system_prompt="You are a kiosk menu assistant. Never claim an order was placed; ask for on-screen confirmation.",
                    user_prompt=prompt,
                    model_policy=llm_routing_service.configured_policy(),
                    timeout_seconds=float(config.get("OLLAMA_TIMEOUT", 30) or 30),
                    prompt_version="voice-turn-v2",
                    expect_json=True,
                    model_name=str(config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b")),
                    max_tokens=96,
                    max_retries=0,
                )
            )
        except (TimeoutError, ConnectionError) as exc:
            raise TransientVoiceTurnError(str(exc)) from exc
        parsed = dict(response.parsed or {})
        actions = coerce_cart_actions(
            parsed.get("cart_actions") if isinstance(parsed.get("cart_actions"), list) else [],
            transcript,
            candidates,
        )
        lines = [
            {"item_id": str(action["id"]), "quantity": int(action.get("quantity") or 1)}
            for action in actions
            if action.get("action") == "add" and action.get("id")
        ]
        text = str(parsed.get("ai_response") or "").strip()
        if lines:
            text = "已整理您提到的餐點，請在畫面上確認。"
        if not text:
            text = "我可以協助您了解菜單。"
        candidate_by_id = {str(row["item_id"]): row for row in candidates}
        mentioned_ids = []
        searchable_text = f"{transcript}\n{text}".casefold()
        for value in parsed.get("mentioned_ids") or []:
            item_id = str(value)
            row = candidate_by_id.get(item_id)
            name = str((row or {}).get("name") or "").strip().casefold()
            if row is None or not name or name not in searchable_text or item_id in mentioned_ids:
                continue
            mentioned_ids.append(item_id)
            if len(mentioned_ids) == 5:
                break
        return {
            "text": text,
            "mentioned_ids": mentioned_ids,
            "order_draft": (
                {"draft_id": operation_key, "lines": lines, "requires_confirmation": True} if lines else None
            ),
        }


class ProductionTTS:
    def synthesize(self, *, text: str, operation_key: str) -> dict[str, Any]:
        provider = get_tts()
        try:
            audio = asyncio.run(provider.synthesize(text))
        except (TimeoutError, ConnectionError) as exc:
            raise TransientVoiceTurnError(str(exc)) from exc
        return {
            "audio_ref": base64.b64encode(audio).decode("ascii") if audio else "",
            "format": provider.audio_format,
        }


class ProductionEffects:
    def schedule_observation(self, **values: Any) -> None:
        # Observation remains an independent, non-blocking module. Import lazily to
        # avoid making Voice Turn initialization depend on the emotion stack.
        try:
            from services.voice_service import _schedule_voice_emotion_observation

            _schedule_voice_emotion_observation(
                session_id=values["session_id"],
                media_path=values["audio_ref"],
                speech_text=values["transcript"],
                emotion_round_id="",
                voice_turn_id=values["voice_turn_id"],
                voice_turn_index=0,
            )
        except Exception as exc:
            # The module already guarantees the turn survives this; the adapter's job
            # is to leave operators a trace instead of failing silently.
            print(f"⚠️ 語音情緒觀測未排程：{exc}")

    def record_history(self, **values: Any) -> None:
        session_repository.record_session_state(
            session_id=values["session_id"],
            user_speech=values["user_text"],
            ai_response=values["assistant_text"],
            mentioned_ids=values.get("mentioned_ids") or [],
            cart_actions=[],
        )


_DEFAULT: VoiceTurnModule | None = None
_KEY: tuple[bool, str] | None = None
_LOCK = Lock()


def default_module() -> VoiceTurnModule:
    global _DEFAULT, _KEY
    use_postgres = postgres_utils.use_postgres()
    path = sqlite_database_path()
    key = (use_postgres, path)
    with _LOCK:
        if _DEFAULT is None or _KEY != key:
            store = PostgresVoiceTurnStore() if use_postgres else SQLiteVoiceTurnStore(path)
            _DEFAULT = VoiceTurnModule(
                store=store,
                stt=ProductionSTT(),
                assistant=ProductionAssistant(),
                menu=ProductionMenu(),
                tts=ProductionTTS(),
                effects=ProductionEffects(),
            )
            _KEY = key
        return _DEFAULT


def reset_default_for_tests() -> None:
    global _DEFAULT, _KEY
    with _LOCK:
        _DEFAULT = None
        _KEY = None


def cleanup_expired(*, hours: int | None = None) -> int:
    retention_hours = int(hours if hours is not None else config.get("VOICE_TURN_RETENTION_HOURS", 24))
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, retention_hours))).isoformat()
    return default_module().cleanup_expired(cutoff=cutoff)
