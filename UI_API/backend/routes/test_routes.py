import asyncio

from fastapi import APIRouter, Body, Depends

from services import test_service
from utils.auth_utils import require_admin_token


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(tags=["test"])

    @router.get("/api/ollama/models")
    async def get_ollama_models(_=Depends(require_admin_token)):
        models = await asyncio.to_thread(test_service.list_ollama_models)
        return {"models": models}

    @router.get("/api/test/voice_prompt")
    async def get_voice_prompt(_=Depends(require_admin_token)):
        """回傳目前設定的語音 system prompt，供測試頁預填。"""
        return {"prompt": test_service._get_default_voice_prompt()}

    @router.post("/api/test/ask")
    async def test_ask(body: dict = Body(...), _=Depends(require_admin_token)):
        provider = str(body.get("provider", "ollama"))
        model = str(body.get("model", ""))
        system_prompt = str(body.get("system_prompt", "") or "")
        # messages = [{role, content}, ...] 完整對話歷史（含本輪）
        messages: list[dict] = body.get("messages", [])

        # 最後一條是本輪使用者輸入
        user_text = messages[-1].get("content", "") if messages else ""
        # 之前的輪次作為對話歷史
        history = messages[:-1]

        result = await asyncio.to_thread(
            test_service.ask_voice_style,
            provider, model, system_prompt, user_text, history,
        )
        return result

    return router
