"""被動語音比對路由。"""
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from services import passive_voice_service
from utils.auth_utils import check_rate_limit, read_limited_upload, require_kiosk_token


def create_router(deps: dict | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["passive_voice"])

    @router.post("/passive_check")
    async def passive_check(
        request: Request,
        session_id: str = Form(...),
        media: UploadFile = File(...),
    ):
        """音訊 → Whisper STT → 關鍵詞 + 品項比對 → 回傳結果。"""
        require_kiosk_token(request)
        check_rate_limit(request, "passive_voice", limit=60, key=session_id)
        try:
            audio_bytes = await read_limited_upload(media)
            return await passive_voice_service.check_audio(audio_bytes)
        except HTTPException:
            raise
        except Exception as e:
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    return router
