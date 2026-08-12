import asyncio

from fastapi import APIRouter, Body, Form, HTTPException, Query, Request, Response

from capabilities.identity_access import scope_from_admin_principal, scope_from_device_principal
from capabilities.member import member_service
from capabilities.operations_configuration import interface as operations
from utils.auth_utils import authorize_admin_request, check_rate_limit, require_kiosk_token


def create_router(deps: dict | None = None, *, prefix: str = "") -> APIRouter:
    router = APIRouter()
    root = prefix.rstrip("/")

    # 已知安全性限制（原型階段刻意接受，後續改善集中記錄於 docs/FUTURE_MODULES.md）：
    # 會員登入僅以手機號碼識別，無第二因子。任何人在 kiosk 輸入他人號碼即可被綁定為該
    # 會員、讀取其「您的常點」與點餐紀錄（帳號列舉 + 冒用）。資料屬低敏感（暱稱 + 點餐
    # 紀錄，無付款/個資）。正式上線前必須補強：簡訊 OTP 或註冊時設定 PIN（手機 + PIN
    # 登入），並對本端點做 per-IP / per-phone rate limit 與失敗稽核。
    @router.post(f"{root}/api/member/login" if not root else f"{root}/member/login")
    async def member_login(request: Request, session_id: str = Form(...), phone: str = Form(...)):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        check_rate_limit(request, "member_login", limit=10, key=phone)
        result = await asyncio.to_thread(member_service.login, session_id, phone, scope)
        await asyncio.to_thread(
            operations.record_admin_action,
            "member_login",
            target_type="member",
            target_id=member_service.mask_phone(member_service.normalize_phone(phone) or phone),
            request=request,
            metadata={"session_id": session_id, "found": bool(result.get("found"))},
            scope=scope,
        )
        return result

    @router.post(f"{root}/api/member/register" if not root else f"{root}/member/register")
    async def member_register(
        request: Request,
        session_id: str = Form(...),
        phone: str = Form(...),
        nickname: str = Form(default=""),
        order_history_consent: bool = Form(default=False),
        personalization_consent: bool = Form(default=False),
        necessary_terms_accepted: bool = Form(default=False),
    ):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        check_rate_limit(request, "member_register", limit=10, key=phone)
        result = await asyncio.to_thread(
            member_service.register,
            session_id,
            phone,
            nickname,
            order_history_consent,
            personalization_consent,
            "kiosk",
            scope,
            necessary_terms_accepted,
        )
        await asyncio.to_thread(
            operations.record_admin_action,
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
            scope=scope,
        )
        return result

    @router.post(f"{root}/api/member/abandoned_order" if not root else f"{root}/member/abandoned_order")
    async def member_abandoned_order(
        request: Request,
        session_id: str = Form(...),
        cart_ids: str = Form(...),
        cart_total: str = Form(default="0"),
        reason: str = Form(default=""),
    ):
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        check_rate_limit(request, "member_abandoned_order", limit=60, key=session_id)
        from utils.parsing import parse_int_from_decimal, parse_json_list

        member = await asyncio.to_thread(
            member_service.record_abandoned_order,
            session_id,
            parse_json_list(cart_ids, fallback_csv=True),
            parse_int_from_decimal(cart_total),
            reason,
            scope,
        )
        return {"ok": bool(member), "member": member_service.public_member(member) if member else None}

    @router.get(f"{root}/api/members" if not root else f"{root}/members")
    async def list_members(request: Request):
        principal = authorize_admin_request(request, "members.read")
        scope = scope_from_admin_principal(principal)
        return await asyncio.to_thread(member_service.admin_list, scope)

    @router.get(f"{root}/api/members/export" if not root else f"{root}/members/export")
    async def export_members(request: Request):
        principal = authorize_admin_request(request, "members.export")
        scope = scope_from_admin_principal(principal)
        content = await asyncio.to_thread(member_service.export_members_csv, scope)
        audit = await asyncio.to_thread(
            operations.record_admin_action,
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

    @router.get(f"{root}/api/admin/audit_logs" if not root else f"{root}/admin/audit_logs")
    async def list_admin_audits(request: Request, limit: int = Query(default=200, ge=1, le=5000)):
        principal = authorize_admin_request(request, "audit.read")
        scope = scope_from_admin_principal(principal)
        return await asyncio.to_thread(operations.list_admin_audits, limit, scope)

    @router.get(f"{root}/api/members/{{member_ref}}" if not root else f"{root}/members/{{member_ref}}")
    async def member_detail(request: Request, member_ref: str):
        principal = authorize_admin_request(request, "members.read")
        scope = scope_from_admin_principal(principal)
        detail = await asyncio.to_thread(member_service.admin_detail, member_ref, scope)
        if detail is None:
            raise HTTPException(status_code=404, detail="member not found")
        return detail

    @router.put(
        f"{root}/api/members/{{member_ref}}/verified-preferences"
        if not root
        else f"{root}/members/{{member_ref}}/verified-preferences"
    )
    async def update_verified_preferences(request: Request, member_ref: str, body: dict = Body(...)):
        principal = authorize_admin_request(request, "members.write")
        scope = scope_from_admin_principal(principal)
        try:
            verified = await asyncio.to_thread(
                member_service.admin_update_verified_preferences,
                member_ref,
                body,
                actor_id=str(principal.user_id),
                scope=scope,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if verified is None:
            raise HTTPException(status_code=404, detail="member not found")
        audit = await asyncio.to_thread(
            operations.record_admin_action,
            "member_verified_preferences.update",
            target_type="member",
            target_id=member_ref,
            request=request,
            metadata={
                "fields": sorted(
                    key
                    for key in body
                    if key in {"allergies", "dietary_preferences", "favorite_item_ids", "service_notes"}
                )
            },
            scope=scope,
        )
        return {"ok": True, "verified_preferences": verified, "audit_id": audit.get("audit_id", "")}

    @router.delete(
        f"{root}/api/members/{{member_ref}}/records" if not root else f"{root}/members/{{member_ref}}/records"
    )
    async def member_clear_records(request: Request, member_ref: str):
        principal = authorize_admin_request(request, "members.delete")
        scope = scope_from_admin_principal(principal)
        detail = await asyncio.to_thread(member_service.admin_detail, member_ref, scope)
        ok = await asyncio.to_thread(member_service.admin_clear_records, member_ref, scope)
        if not ok:
            raise HTTPException(status_code=404, detail="member not found")
        audit = await asyncio.to_thread(
            operations.record_admin_action,
            "member_clear_records",
            target_type="member",
            target_id=(detail or {}).get("phone_masked", member_ref),
            request=request,
            metadata={"member_ref": member_ref},
        )
        return {"ok": True, "audit_id": audit.get("audit_id", "")}

    @router.delete(f"{root}/api/members/{{member_ref}}" if not root else f"{root}/members/{{member_ref}}")
    async def member_delete(request: Request, member_ref: str):
        principal = authorize_admin_request(request, "members.delete")
        scope = scope_from_admin_principal(principal)
        detail = await asyncio.to_thread(member_service.admin_detail, member_ref, scope)
        ok = await asyncio.to_thread(member_service.admin_delete_member, member_ref, scope)
        if not ok:
            raise HTTPException(status_code=404, detail="member not found")
        audit = await asyncio.to_thread(
            operations.record_admin_action,
            "member_delete",
            target_type="member",
            target_id=(detail or {}).get("phone_masked", member_ref),
            request=request,
            metadata={"member_ref": member_ref},
        )
        return {"ok": True, "audit_id": audit.get("audit_id", "")}

    return router
