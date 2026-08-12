"""Admin routes for authoring AI push copy.

This is the only place an LLM touches push copy. Kiosk serving is a pure lookup, so anything
saved here is exactly what customers will see until it is edited again — which is why base copy
is rejected outright when it asserts a promotion the store cannot guarantee.
"""

import asyncio

from fastapi import APIRouter, Body, HTTPException, Request

import config
from capabilities import catalog
from capabilities.campaign_promotion import (
    push_copy_authoring_service,
    push_copy_batch_repository,
    push_copy_repository,
    push_copy_service,
    rag_guard_service,
    rag_offer_service,
)
from capabilities.identity_access import scope_from_admin_principal
from capabilities.operations_configuration import interface as operations
from capabilities.operations_configuration import worker_service
from utils.auth_utils import authorize_admin_request, check_rate_limit


def _text(value) -> str:
    return str(value or "").strip()


def create_router(deps: dict | None = None, *, prefix: str = "/api/push-copy") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["push_copy"])

    def _offers_for(scope, menu_items: list[dict]) -> list[dict]:
        try:
            return rag_offer_service.load_active_offers(menu_items, scope=scope)
        except Exception:
            return []

    @router.get("")
    async def list_push_copy(request: Request):
        """Every menu item joined with its authored copy, plus the offers available to bind."""

        principal = authorize_admin_request(request, "settings.read")
        scope = scope_from_admin_principal(principal)
        menu_items = await asyncio.to_thread(catalog.list_items, scope, include_retired=False, ensure_seed=True)
        rows = await asyncio.to_thread(push_copy_repository.list_copy_scoped, scope)
        offers = await asyncio.to_thread(_offers_for, scope, menu_items)
        live_ids = push_copy_service.active_offer_ids(offers, audience="member")

        items = []
        for item in menu_items:
            item_id = _text(item.get("id"))
            if not item_id:
                continue
            entry = rows.get(item_id, {})
            push_text, status = push_copy_service.resolve_copy(item, entry, live_offer_ids=live_ids)
            items.append(
                {
                    "item_id": item_id,
                    "name": _text(item.get("name")),
                    "category": _text(item.get("category")),
                    "description": _text(item.get("description")),
                    **push_copy_repository.normalize_entry(entry),
                    "effective_text": push_text,
                    "effective_status": status,
                    "campaign_live": bool(
                        _text(entry.get("campaign_offer_id")) and _text(entry.get("campaign_offer_id")) in live_ids
                    ),
                }
            )
        return {
            "status": "success",
            "items": items,
            "categories": sorted({row["category"] for row in items if row["category"]}),
            "offers": [
                {"offer_id": _text(o.get("offer_id")), "title": _text(o.get("title"))}
                for o in offers
                if _text(o.get("offer_id"))
            ],
            "text_min": int(config.get("AI_PUSH_TEXT_MIN", 18)),
            "text_max": int(config.get("AI_PUSH_TEXT_MAX", 34)),
        }

    @router.post("/batch")
    async def start_batch(request: Request, payload: dict = Body(default={})):
        """排入一鍵產生。整份菜單逐項呼叫模型要跑上十分鐘，因此交給背景工作而非讓瀏覽器等。"""

        principal = authorize_admin_request(request, "settings.write")
        scope = scope_from_admin_principal(principal)
        check_rate_limit(request, "admin_push_copy_batch", limit=6)

        mode = _text((payload or {}).get("mode")) or "fill_missing"
        if mode not in push_copy_batch_repository.MODES:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_mode", "message": "產生範圍只能是「補齊缺漏」或「重產指定品項」。"},
            )

        running = await asyncio.to_thread(push_copy_batch_repository.latest_batch, scope)
        if running and running["status"] in ("pending", "running"):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "batch_already_running",
                    "message": f"已有一批推薦詞正在產生（{running['processed']}/{running['total']}），請等它完成再開始下一批。",
                },
            )

        menu_items = await asyncio.to_thread(catalog.list_items, scope, include_retired=False, ensure_seed=True)
        rows = await asyncio.to_thread(push_copy_repository.list_copy_scoped, scope)
        if mode == "fill_missing":
            candidates = [
                _text(row.get("id"))
                for row in menu_items
                if _text(row.get("id")) and not _text(rows.get(_text(row.get("id")), {}).get("base_copy"))
            ]
        else:
            # 重產只針對呼叫端明確指定的品項，避免「我以為只會改篩選中的那幾筆」這種誤會。
            requested = {_text(value) for value in (payload or {}).get("item_ids") or []}
            candidates = [_text(row.get("id")) for row in menu_items if _text(row.get("id")) in requested]

        if not candidates:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "nothing_to_generate",
                    "message": "沒有需要產生的品項。" if mode == "fill_missing" else "請先選擇要重產的品項。",
                },
            )

        batch = await asyncio.to_thread(
            push_copy_batch_repository.create_batch,
            scope,
            mode=mode,
            item_ids=candidates,
            actor_id=str(principal.user_id or ""),
        )
        await asyncio.to_thread(
            worker_service.enqueue_job,
            tenant_id=scope.tenant_id,
            store_id=scope.store_id,
            job_type="ai.background",
            payload_ref={"kind": "push_copy_batch", "batch_id": batch["batch_id"]},
            idempotency_key=f"push-copy-batch:{scope.store_id}:{batch['batch_id']}",
            max_attempts=1,
        )
        await asyncio.to_thread(
            operations.record_admin_action,
            "push_copy.batch_start",
            target_type="push_copy_batch",
            target_id=batch["batch_id"],
            request=request,
            metadata={"mode": mode, "total": batch["total"]},
            scope=scope,
        )
        return {"status": "success", "batch": batch}

    @router.get("/batch")
    async def get_batch_progress(request: Request):
        """最近一批的進度。前端輪詢這裡，因此關掉分頁再回來仍看得到進度。"""

        principal = authorize_admin_request(request, "settings.read")
        scope = scope_from_admin_principal(principal)
        batch = await asyncio.to_thread(push_copy_batch_repository.latest_batch, scope)
        return {"status": "success", "batch": batch}

    @router.post("/{item_id}")
    async def save_push_copy(request: Request, item_id: str, payload: dict = Body(...)):
        principal = authorize_admin_request(request, "settings.write")
        scope = scope_from_admin_principal(principal)
        check_rate_limit(request, "admin_push_copy_update", limit=120)

        entry = push_copy_repository.normalize_entry(payload)
        # Base copy must stay true no matter which campaigns are running, so a promotional claim
        # in it is refused rather than silently rewritten.
        offending = rag_guard_service.unverified_promotion_terms(entry["base_copy"])
        if offending:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "unverified_promotion_claim",
                    "message": f"常態推薦詞不可包含促銷用語：{'、'.join(offending)}。優惠請改寫在活動推薦詞並綁定活動。",
                },
            )
        if entry["campaign_copy"] and not entry["campaign_offer_id"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "campaign_binding_required",
                    "message": "活動推薦詞必須綁定一個活動，否則活動結束後無法自動停用。",
                },
            )

        saved = await asyncio.to_thread(
            push_copy_repository.save_copy_scoped,
            item_id,
            entry,
            scope,
            actor_id=str(principal.user_id or ""),
        )
        await asyncio.to_thread(
            operations.record_admin_action,
            "push_copy.update",
            target_type="menu_item",
            target_id=_text(item_id),
            request=request,
            metadata={"has_campaign_copy": bool(saved["campaign_copy"])},
            scope=scope,
        )
        return {"status": "success", "item_id": _text(item_id), **saved}

    @router.post("/{item_id}/generate")
    async def generate_push_copy(request: Request, item_id: str, payload: dict = Body(default={})):
        """Draft copy with the LLM for an operator to review. Never reached by a Kiosk request."""

        principal = authorize_admin_request(request, "settings.write")
        scope = scope_from_admin_principal(principal)
        check_rate_limit(request, "admin_push_copy_generate", limit=60)

        menu_items = await asyncio.to_thread(catalog.list_items, scope, include_retired=False, ensure_seed=True)
        item = next((row for row in menu_items if _text(row.get("id")) == _text(item_id)), None)
        if item is None:
            raise HTTPException(status_code=404, detail={"code": "item_not_found", "message": "找不到這個品項。"})

        slot = _text((payload or {}).get("slot")) or "base"
        offer_id = _text((payload or {}).get("campaign_offer_id"))

        offer = None
        if slot == "campaign":
            offers = await asyncio.to_thread(_offers_for, scope, menu_items)
            offer = next((o for o in offers if _text(o.get("offer_id")) == offer_id), None)
            if offer is None:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "offer_not_active", "message": "請先選擇一個目前有效的活動。"},
                )

        draft, error, terms = await asyncio.to_thread(
            push_copy_authoring_service.draft_copy, item, slot=slot, offer=offer
        )
        if error:
            raise HTTPException(
                status_code=503,
                detail={"code": "generation_unavailable", "message": f"{error}可以先手動輸入。"},
            )
        return {
            "status": "success",
            "item_id": _text(item_id),
            "slot": slot,
            "push_text": draft,
            # Surfaced so the operator sees the same rejection reason the save would give.
            "unverified_terms": terms,
        }

    return router
