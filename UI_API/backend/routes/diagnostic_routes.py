import asyncio

from fastapi import APIRouter, Body, Depends, HTTPException

from services import diagnostic_service
from utils.auth_utils import require_permission


def create_router(deps: dict | None = None, *, prefix: str = "") -> APIRouter:
    router = APIRouter(tags=["diagnostics"])

    root = prefix.rstrip("/")

    @router.get(f"{root}/ollama-models" if root else "/api/ollama/models")
    async def get_ollama_models(_=Depends(require_permission("system.debug"))):
        models = await asyncio.to_thread(diagnostic_service.list_ollama_models)
        return {"models": models}

    @router.get(f"{root}/voice-prompt" if root else "/api/diagnostics/voice_prompt")
    async def get_voice_prompt(_=Depends(require_permission("system.debug"))):
        """回傳目前設定的語音 system prompt，供測試頁預填。"""
        return {"prompt": diagnostic_service._get_default_voice_prompt()}

    @router.post(f"{root}/ask" if root else "/api/diagnostics/ask")
    async def diagnostic_ask(body: dict = Body(...), _=Depends(require_permission("system.debug"))):
        # A diagnostic has no sensible default provider — naming the half of the chain to
        # exercise is the entire point of the request, so an absent or unknown provider is a
        # caller error rather than something to quietly resolve into the local runtime.
        provider = str(body.get("provider", ""))
        if provider not in diagnostic_service.SUPPORTED_DIAGNOSTIC_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"不支援的提供者：{provider!r}；"
                    f"可用的提供者為 {sorted(diagnostic_service.SUPPORTED_DIAGNOSTIC_PROVIDERS)}。"
                ),
            )
        model = str(body.get("model", ""))
        system_prompt = str(body.get("system_prompt", "") or "")
        # messages = [{role, content}, ...] 完整對話歷史（含本輪）
        messages: list[dict] = body.get("messages", [])

        # 最後一條是本輪使用者輸入
        user_text = messages[-1].get("content", "") if messages else ""
        # 之前的輪次作為對話歷史
        history = messages[:-1]

        result = await asyncio.to_thread(
            diagnostic_service.ask_voice_style,
            provider,
            model,
            system_prompt,
            user_text,
            history,
        )
        return result

    return router
