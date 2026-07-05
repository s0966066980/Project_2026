import asyncio

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response

from services import admin_audit_service, member_service
from utils.auth_utils import check_rate_limit, require_admin_token, require_kiosk_token


def create_router(deps: dict) -> APIRouter:
    router = APIRouter()

    # 已知安全性限制（原型階段刻意接受，後續改善集中記錄於 docs/FUTURE_MODULES.md）：
    # 會員登入僅以手機號碼識別，無第二因子。任何人在 kiosk 輸入他人號碼即可被綁定為該
    # 會員、讀取其「您的常點」與點餐紀錄（帳號列舉 + 冒用）。資料屬低敏感（暱稱 + 點餐
    # 紀錄，無付款/個資）。正式上線前必須補強：簡訊 OTP 或註冊時設定 PIN（手機 + PIN
    # 登入），並對本端點做 per-IP / per-phone rate limit 與失敗稽核。
    @router.post("/api/member/login")
    async def member_login(request: Request, session_id: str = Form(...), phone: str = Form(...)):
        require_kiosk_token(request)
        check_rate_limit(request, "member_login", limit=10, key=phone)
        result = await asyncio.to_thread(member_service.login, session_id, phone)
        await asyncio.to_thread(
            admin_audit_service.record_admin_action,
            "member_login",
            target_type="member",
            target_id=member_service.mask_phone(member_service.normalize_phone(phone) or phone),
            request=request,
            metadata={"session_id": session_id, "found": bool(result.get("found"))},
        )
        return result

    @router.post("/api/member/register")
    async def member_register(
        request: Request,
        session_id: str = Form(...),
        phone: str = Form(...),
        nickname: str = Form(default=""),
        order_history_consent: bool = Form(default=True),
        personalization_consent: bool = Form(default=True),
    ):
        require_kiosk_token(request)
        check_rate_limit(request, "member_register", limit=10, key=phone)
        result = await asyncio.to_thread(
            member_service.register,
            session_id,
            phone,
            nickname,
            order_history_consent,
            personalization_consent,
            "kiosk",
        )
        await asyncio.to_thread(
            admin_audit_service.record_admin_action,
            "member_register",
            target_type="member",
            target_id=member_service.mask_phone(member_service.normalize_phone(phone) or phone),
            request=request,
            metadata={
                "session_id": session_id,
                "ok": bool(result.get("ok")),
                "error": result.get("error", ""),
                "order_history_consent": bool(order_history_consent),
                "personalization_consent": bool(personalization_consent),
            },
        )
        return result

    @router.post("/api/member/abandoned_order")
    async def member_abandoned_order(
        request: Request,
        session_id: str = Form(...),
        cart_ids: str = Form(...),
        cart_total: str = Form(default="0"),
        reason: str = Form(default=""),
    ):
        require_kiosk_token(request)
        check_rate_limit(request, "member_abandoned_order", limit=60, key=session_id)
        from utils.parsing import parse_int_from_decimal, parse_json_list

        member = await asyncio.to_thread(
            member_service.record_abandoned_order,
            session_id,
            parse_json_list(cart_ids, fallback_csv=True),
            parse_int_from_decimal(cart_total),
            reason,
        )
        return {"ok": bool(member), "member": member_service._public_member(member) if member else None}

    @router.get("/api/members")
    async def list_members(request: Request):
        require_admin_token(request)
        return await asyncio.to_thread(member_service.admin_list)

    @router.get("/api/members/export")
    async def export_members(request: Request):
        require_admin_token(request)
        content = await asyncio.to_thread(member_service.export_members_csv)
        audit = await asyncio.to_thread(
            admin_audit_service.record_admin_action,
            "member_export",
            target_type="member",
            target_id="members",
            request=request,
            metadata={"format": "csv", "masked": True},
        )
        return Response(
            content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="members_export.csv"',
                "X-Admin-Audit-Id": str(audit.get("audit_id", "")),
            },
        )

    @router.get("/api/admin/audit_logs")
    async def list_admin_audits(request: Request, limit: int = Query(default=200, ge=1, le=5000)):
        require_admin_token(request)
        return await asyncio.to_thread(admin_audit_service.list_admin_audits, limit)

    @router.get("/api/members/{member_ref}")
    async def member_detail(request: Request, member_ref: str):
        require_admin_token(request)
        detail = await asyncio.to_thread(member_service.admin_detail, member_ref)
        if detail is None:
            raise HTTPException(status_code=404, detail="member not found")
        return detail

    @router.delete("/api/members/{member_ref}/records")
    async def member_clear_records(request: Request, member_ref: str):
        require_admin_token(request)
        detail = await asyncio.to_thread(member_service.admin_detail, member_ref)
        ok = await asyncio.to_thread(member_service.admin_clear_records, member_ref)
        if not ok:
            raise HTTPException(status_code=404, detail="member not found")
        audit = await asyncio.to_thread(
            admin_audit_service.record_admin_action,
            "member_clear_records",
            target_type="member",
            target_id=(detail or {}).get("phone_masked", member_ref),
            request=request,
            metadata={"member_ref": member_ref},
        )
        return {"ok": True, "audit_id": audit.get("audit_id", "")}

    @router.delete("/api/members/{member_ref}")
    async def member_delete(request: Request, member_ref: str):
        require_admin_token(request)
        detail = await asyncio.to_thread(member_service.admin_detail, member_ref)
        ok = await asyncio.to_thread(member_service.admin_delete_member, member_ref)
        if not ok:
            raise HTTPException(status_code=404, detail="member not found")
        audit = await asyncio.to_thread(
            admin_audit_service.record_admin_action,
            "member_delete",
            target_type="member",
            target_id=(detail or {}).get("phone_masked", member_ref),
            request=request,
            metadata={"member_ref": member_ref},
        )
        return {"ok": True, "audit_id": audit.get("audit_id", "")}

    return router
