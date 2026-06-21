import asyncio

from fastapi import APIRouter, Form, HTTPException, Request

from services import member_service
from utils.auth_utils import require_admin_token


def create_router(deps: dict) -> APIRouter:
    router = APIRouter()

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

    return router
