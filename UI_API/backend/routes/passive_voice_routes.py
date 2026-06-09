"""被動語音比對路由。"""
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from services import passive_voice_service


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["passive_voice"])

    @router.post("/passive_check")
    async def passive_check(
        session_id: str = Form(...),
        media: UploadFile = File(...),
    ):
        """音訊 → Whisper STT → 關鍵詞 + 品項比對 → 回傳結果。"""
        try:
            audio_bytes = await media.read()
            return await passive_voice_service.check_audio(audio_bytes)
        except Exception as e:
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    return router
