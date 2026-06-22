import asyncio

from fastapi import APIRouter, Form, HTTPException, Request

from services import member_service
from utils.auth_utils import require_admin_token


def create_router(deps: dict) -> APIRouter:
    router = APIRouter()

    # 已知安全性限制（原型階段刻意接受，見 docs/.../2026-06-21-membership-design.md）：
    # 會員登入僅以手機號碼識別，無第二因子。任何人在 kiosk 輸入他人號碼即可被綁定為該
    # 會員、讀取其「您的常點」與點餐紀錄（帳號列舉 + 冒用）。資料屬低敏感（暱稱 + 點餐
    # 紀錄，無付款/個資）。正式上線前必須補強：簡訊 OTP 或註冊時設定 PIN（手機 + PIN
    # 登入），並對本端點做 per-IP / per-phone rate limit 與失敗稽核。
    @router.post("/api/member/login")
    async def member_login(session_id: str = Form(...), phone: str = Form(...)):
        return await asyncio.to_thread(member_service.login, session_id, phone)

    @router.post("/api/member/register")
    async def member_register(
        session_id: str = Form(...),
        phone: str = Form(...),
        nickname: str = Form(default=""),
    ):
        return await asyncio.to_thread(member_service.register, session_id, phone, nickname)

    @router.get("/api/members")
    async def list_members(request: Request):
        require_admin_token(request)
        return await asyncio.to_thread(member_service.admin_list)

    @router.get("/api/members/{phone}")
    async def member_detail(request: Request, phone: str):
        require_admin_token(request)
        detail = await asyncio.to_thread(member_service.admin_detail, phone)
        if detail is None:
            raise HTTPException(status_code=404, detail="member not found")
        return detail

    @router.delete("/api/members/{phone}/records")
    async def member_clear_records(request: Request, phone: str):
        require_admin_token(request)
        ok = await asyncio.to_thread(member_service.admin_clear_records, phone)
        if not ok:
            raise HTTPException(status_code=404, detail="member not found")
        return {"ok": True}

    @router.delete("/api/members/{phone}")
    async def member_delete(request: Request, phone: str):
        require_admin_token(request)
        ok = await asyncio.to_thread(member_service.admin_delete_member, phone)
        if not ok:
            raise HTTPException(status_code=404, detail="member not found")
        return {"ok": True}

    return router
