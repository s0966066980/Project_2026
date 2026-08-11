"""Read-only project analysis with isolated, non-applying proposals."""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone

import config
from models.llm import LLMModelPolicy, LLMRequest
from services import diagnostic_service, health_service, llm_gateway_service
from services.multimodal_evidence_gateway import configured_provider_status

_REPORT_PATH = os.path.join(config.LEARNING_DATA_DIR, "project_brain_latest.json")


def ready_models() -> list[dict]:
    return [{"id": name, "provider": "ollama", "ready": True} for name in diagnostic_service.list_ollama_models()]


def latest_report() -> dict | None:
    try:
        with open(_REPORT_PATH, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _save_report(report: dict) -> None:
    os.makedirs(os.path.dirname(_REPORT_PATH), exist_ok=True)
    temp_path = f"{_REPORT_PATH}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, _REPORT_PATH)


async def _snapshot(run_tests: bool) -> dict:
    health = await health_service.build_admin_health()
    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": config.APP_ENV,
        "health": {
            "status": health.get("status"),
            "readiness": health.get("readiness"),
            "checks": health.get("checks"),
        },
        "features": {
            "rag_enabled": bool(config.get("RAG_ENABLED", False)),
            "emotion_enabled": bool(config.get("EMOTION_ENABLED", False)),
            "emotion_mode": config.get("EMOTION_CAPTURE_MODE", "voice"),
            "voice_model": config.get("VOICE_ASSIST_MODEL", ""),
            "database_backend": config.get("DATABASE_BACKEND", ""),
        },
        "models": {
            "ollama": ready_models(),
            "r1_omni": configured_provider_status(),
        },
    }
    if run_tests:
        snapshot["allowlisted_tests"] = {
            "application_readiness": bool(health.get("readiness", {}).get("ready")),
            "ollama_model_catalog": bool(snapshot["models"]["ollama"]),
            "r1_omni_cuda_ready": (
                snapshot["models"]["r1_omni"].get("status") == "ready"
                and snapshot["models"]["r1_omni"].get("device") == "cuda"
            ),
        }
    return snapshot


def _generate(*, model: str, system_prompt: str, user_prompt: str, max_tokens: int = 1600) -> str:
    response = llm_gateway_service.generate(LLMRequest(
        task="project_brain",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_policy=LLMModelPolicy.LOCAL_ONLY,
        model_name=model,
        timeout_seconds=120,
        prompt_version="project-brain-v1",
        expect_json=False,
        max_tokens=max_tokens,
        max_retries=0,
    ))
    if response.safe_error or response.finish_reason in {"error", "timeout"}:
        raise RuntimeError(response.safe_error or "selected_model_failed")
    return response.content.strip()


async def analyze(model: str, *, run_tests: bool = False) -> dict:
    if model not in {item["id"] for item in ready_models()}:
        raise ValueError("selected_model_not_ready")
    snapshot = await _snapshot(run_tests)
    analysis = await asyncio.to_thread(
        _generate,
        model=model,
        system_prompt=(
            "你是專案核心大腦。只根據提供的唯讀快照分析目前狀態、風險與下一步。"
            "不得宣稱已修改檔案、資料或系統；不得要求或輸出秘密。用繁體中文 Markdown。"
        ),
        user_prompt=json.dumps(snapshot, ensure_ascii=False),
    )
    report = {"generated_at": snapshot["generated_at"], "model": model, "snapshot": snapshot, "analysis": analysis}
    await asyncio.to_thread(_save_report, report)
    return report


async def propose(model: str, *, kind: str, request: str) -> dict:
    if model not in {item["id"] for item in ready_models()}:
        raise ValueError("selected_model_not_ready")
    if kind not in {"document", "extension"}:
        raise ValueError("proposal_kind_not_allowed")
    slug = re.sub(r"[^a-z0-9-]+", "-", request.lower())[:48].strip("-") or "proposal"
    proposed_path = f"docs/proposals/{slug}.md" if kind == "document" else f"extensions/proposals/{slug}/README.md"
    content = await asyncio.to_thread(
        _generate,
        model=model,
        system_prompt=(
            "產生一份隔離提案，不得修改或取代現有核心業務、API、資料表或設定。"
            "只允許新非核心文件或獨立 extension。回覆繁體中文 Markdown，清楚列出邊界、介面、驗證與不會做的事。"
        ),
        user_prompt=f"提案類型：{kind}\n建議路徑：{proposed_path}\n需求：{request[:6000]}",
    )
    return {"status": "proposal_only", "kind": kind, "proposed_path": proposed_path, "content": content, "applied": False}
