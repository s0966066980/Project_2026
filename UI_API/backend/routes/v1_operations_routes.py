"""Versioned compatibility endpoints grouped by capability.

These routes keep the published envelope stable while Admin/Kiosk consumers
move to their capability-owned surfaces.
"""

# ruff: noqa: F403, F405

from __future__ import annotations

from fastapi import Body, Response

from routes.v1_support import *  # noqa: F401,F403


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Security(_document_admin_security)],
        responses={
            401: {"model": ApiErrorResponse, "description": "Authentication required"},
            403: {"model": ApiErrorResponse, "description": "Permission denied"},
            422: {"model": ApiErrorResponse, "description": "Request validation failed"},
            500: {"model": ApiErrorResponse, "description": "Safe internal error"},
        },
    )

    @router.get(
        "/operations/service-health",
        tags=["v1-analytics"],
        operation_id="v1_get_service_health",
        response_model=ApiResponse[dict],
    )
    async def service_health(request: Request) -> ApiResponse[dict]:
        """Connection status, latency, observation time and a safe error, per service.



        Nothing about the inside of the system: an operator reads this to answer

        whether a customer can order right now.

        """

        _scope(request, "operations.read")

        statuses = await asyncio.to_thread(service_health_runtime().default_module().snapshot)

        return ApiResponse(data={"services": [status.as_dict() for status in statuses]}, meta=_meta(request))

    @router.get(
        "/operations/overview",
        tags=["v1-analytics"],
        operation_id="v1_get_operations_overview",
        response_model=ApiResponse[dict],
    )
    async def operations_overview(request: Request, days: Annotated[int, Query(ge=1, le=31)] = 1) -> ApiResponse[dict]:
        """The four counts a store manager reads, each carrying what it means.



        The definitions travel with the values because every one of them excludes

        something a reader would otherwise assume was included.

        """

        scope = _scope(request, "analytics.read")

        overview = await asyncio.to_thread(
            operations_overview_runtime().default_module().build,
            scope=scope,
            since=operations_overview_runtime().since_days_ago(days),
        )

        return ApiResponse(data={**overview.as_dict(), "window_days": days}, meta=_meta(request))

    @router.get(
        "/recommendation-effectiveness",
        tags=["v1-analytics"],
        operation_id="v1_get_recommendation_effectiveness",
        response_model=ApiResponse[RecommendationEffectivenessDTO],
    )
    async def recommendation_effectiveness(
        request: Request,
        since: Annotated[str, Query(max_length=60)] = "",
        until: Annotated[str, Query(max_length=60)] = "",
        placement: Annotated[str, Query(max_length=80)] = "",
        campaign_id: Annotated[str, Query(max_length=120)] = "",
        strategy_version: Annotated[str, Query(max_length=100)] = "",
        variant_id: Annotated[str, Query(max_length=100)] = "",
        audience: Annotated[str, Query(max_length=40)] = "",
    ) -> ApiResponse[RecommendationEffectivenessDTO]:

        scope = _scope(request, "recommendations.effectiveness.read")

        events, attributions = await asyncio.gather(
            asyncio.to_thread(
                analytics_pipeline_service.list_events,
                tenant_id=scope.tenant_id,
                store_id=scope.store_id,
                since=since,
                until=until,
            ),
            asyncio.to_thread(
                checkout_order_repository.list_order_touch_attributions_scoped, scope, since=since, until=until
            ),
        )

        report = build_effectiveness_report(
            events,
            attributions,
            filters={
                "placement": placement,
                "campaign_id": campaign_id,
                "strategy_version": strategy_version,
                "variant_id": variant_id,
                "audience": audience,
            },
        )

        return ApiResponse(data=RecommendationEffectivenessDTO(**report.__dict__), meta=_meta(request))

    @router.get(
        "/members",
        tags=["v1-members"],
        operation_id="v1_list_members",
        response_model=PaginatedResponse[MemberSummaryDTO],
    )
    async def members(
        request: Request,
        page: Page = 1,
        page_size: PageSize = 25,
        q: Annotated[str, Query(max_length=120)] = "",
        sort_by: Annotated[Literal["created_at", "nickname", "visit_count", "total_spend"], Query()] = "created_at",
        sort_order: SortOrder = "desc",
    ) -> PaginatedResponse[MemberSummaryDTO]:

        scope = _scope(request, "members.read")

        records, total = await asyncio.to_thread(
            member_service.admin_search,
            q,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            scope=scope,
        )

        mapped = [
            MemberSummaryDTO(
                member_id=_member_uuid(row.get("member_id") or row.get("id"), scope),
                member_ref=str(row.get("member_ref") or ""),
                phone_masked=str(row.get("phone_masked") or ""),
                nickname=str(row.get("nickname") or ""),
                visit_count=int(row.get("visit_count") or 0),
                total_spend=int(row.get("total_spend") or 0),
                created_at=_optional_datetime(row.get("created_at")),
            )
            for row in records
        ]

        data = mapped

        pagination = PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

        return PaginatedResponse(data=data, pagination=pagination, meta=_meta(request))

    @router.get(
        "/members/export",
        tags=["v1-members"],
        operation_id="v1_export_members",
        response_class=Response,
        responses={200: {"content": {"text/csv": {}}}},
    )
    async def export_members(request: Request) -> Response:
        scope = _scope(request, "members.export")
        content = await asyncio.to_thread(member_service.export_members_csv, scope)
        audit = await asyncio.to_thread(
            operations.record_admin_action,
            "member_export",
            target_type="member",
            target_id="members",
            request=request,
            metadata={"format": "csv", "masked": True},
            scope=scope,
        )
        return Response(
            content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="members_export.csv"',
                "X-Admin-Audit-Id": str(audit.get("audit_id", "")),
            },
        )

    @router.get(
        "/members/{member_ref}",
        tags=["v1-members"],
        operation_id="v1_get_member",
        response_model=ApiResponse[dict],
    )
    async def member_detail(request: Request, member_ref: str) -> ApiResponse[dict]:
        scope = _scope(request, "members.read")
        detail = await asyncio.to_thread(member_service.admin_detail, member_ref, scope)
        if detail is None:
            raise HTTPException(status_code=404, detail={"code": "member_not_found", "message": "找不到會員。"})
        return ApiResponse(data=detail, meta=_meta(request))

    @router.put(
        "/members/{member_ref}/verified-preferences",
        tags=["v1-members"],
        operation_id="v1_update_member_verified_preferences",
        response_model=ApiResponse[dict],
    )
    async def update_member_verified_preferences(
        request: Request, member_ref: str, body: dict = Body(...)
    ) -> ApiResponse[dict]:
        scope = _scope(request, "members.write")
        try:
            verified = await asyncio.to_thread(
                member_service.admin_update_verified_preferences,
                member_ref,
                body,
                actor_id=_admin_actor(request),
                scope=scope,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"code": "member_preferences_invalid", "message": str(exc)}
            ) from exc
        if verified is None:
            raise HTTPException(status_code=404, detail={"code": "member_not_found", "message": "找不到會員。"})
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
        return ApiResponse(
            data={"ok": True, "verified_preferences": verified, "audit_id": audit.get("audit_id", "")},
            meta=_meta(request),
        )

    @router.delete(
        "/members/{member_ref}/records",
        tags=["v1-members"],
        operation_id="v1_clear_member_records",
        response_model=ApiResponse[dict],
    )
    async def clear_member_records(request: Request, member_ref: str) -> ApiResponse[dict]:
        scope = _scope(request, "members.delete")
        detail = await asyncio.to_thread(member_service.admin_detail, member_ref, scope)
        ok = await asyncio.to_thread(member_service.admin_clear_records, member_ref, scope)
        if not ok:
            raise HTTPException(status_code=404, detail={"code": "member_not_found", "message": "找不到會員。"})
        audit = await asyncio.to_thread(
            operations.record_admin_action,
            "member_clear_records",
            target_type="member",
            target_id=(detail or {}).get("phone_masked", member_ref),
            request=request,
            metadata={"member_ref": member_ref},
            scope=scope,
        )
        return ApiResponse(data={"ok": True, "audit_id": audit.get("audit_id", "")}, meta=_meta(request))

    @router.delete(
        "/members/{member_ref}",
        tags=["v1-members"],
        operation_id="v1_delete_member",
        response_model=ApiResponse[dict],
    )
    async def delete_member(request: Request, member_ref: str) -> ApiResponse[dict]:
        scope = _scope(request, "members.delete")
        detail = await asyncio.to_thread(member_service.admin_detail, member_ref, scope)
        ok = await asyncio.to_thread(member_service.admin_delete_member, member_ref, scope)
        if not ok:
            raise HTTPException(status_code=404, detail={"code": "member_not_found", "message": "找不到會員。"})
        audit = await asyncio.to_thread(
            operations.record_admin_action,
            "member_delete",
            target_type="member",
            target_id=(detail or {}).get("phone_masked", member_ref),
            request=request,
            metadata={"member_ref": member_ref},
            scope=scope,
        )
        return ApiResponse(data={"ok": True, "audit_id": audit.get("audit_id", "")}, meta=_meta(request))

    @router.get(
        "/orders", tags=["v1-orders"], operation_id="v1_list_orders", response_model=PaginatedResponse[OrderSummaryDTO]
    )
    async def orders(
        request: Request,
        page: Page = 1,
        page_size: PageSize = 25,
        status: Annotated[str, Query(max_length=40)] = "",
        sort_order: SortOrder = "desc",
    ) -> PaginatedResponse[OrderSummaryDTO]:

        scope = _scope(request, "members.read")

        records, total = await asyncio.to_thread(
            checkout_order_repository.list_orders_scoped,
            scope,
            status=status,
            offset=(page - 1) * page_size,
            limit=page_size,
            sort_order=sort_order,
        )

        data = [OrderSummaryDTO(**row) for row in records]

        pagination = PaginationMeta(
            page=page, page_size=page_size, total=total, total_pages=math.ceil(total / page_size) if total else 0
        )

        return PaginatedResponse(data=data, pagination=pagination, meta=_meta(request))

    @router.get(
        "/promotions",
        tags=["v1-promotions"],
        operation_id="v1_list_promotions",
        response_model=PaginatedResponse[PromotionSummaryDTO],
    )
    async def promotions(
        request: Request, page: Page = 1, page_size: PageSize = 25
    ) -> PaginatedResponse[PromotionSummaryDTO]:

        scope = _scope(request, "rag.read")

        records = await asyncio.to_thread(promotion_service.list_promotions, scope)

        mapped = [
            PromotionSummaryDTO(
                offer_id=str(row.get("offer_id") or ""),
                title=str(row.get("title") or ""),
                status=str(row.get("status") or (row.get("metadata") or {}).get("status") or "draft"),
                enabled=bool(row.get("enabled", True)),
            )
            for row in records
        ]

        data, pagination = _page(mapped, page, page_size)

        return PaginatedResponse(data=data, pagination=pagination, meta=_meta(request))

    @router.get(
        "/recommendations",
        tags=["v1-recommendations"],
        operation_id="v1_list_recommendations",
        response_model=PaginatedResponse[RecommendationEventDTO],
    )
    async def recommendations(
        request: Request, page: Page = 1, page_size: PageSize = 25
    ) -> PaginatedResponse[RecommendationEventDTO]:

        scope = _scope(request, "recommendations.read")

        records = await asyncio.to_thread(list_recommendation_events, scope, limit=5000)

        mapped = [
            RecommendationEventDTO(
                event_id=str(row.get("event_id") or row.get("id") or ""),
                event_type=str(row.get("event_type") or ""),
                session_id=str(row.get("session_id") or ""),
                item_id=str(row.get("item_id") or ""),
                item_name=str(row.get("item_name") or ""),
                surface=str(row.get("surface") or ""),
                source=str(row.get("source") or ""),
                audience=str(row.get("audience") or ("member" if row.get("is_member") else "guest")),
                offer_ids=[str(value) for value in row.get("offer_ids") or []],
                reasons=[str(value) for value in row.get("reasons") or []],
                experiment_id=str(row.get("experiment_id") or (row.get("metadata") or {}).get("experiment_id") or ""),
                variant_id=str(row.get("variant_id") or (row.get("metadata") or {}).get("variant_id") or ""),
                strategy=str(row.get("strategy") or (row.get("metadata") or {}).get("strategy") or ""),
                timestamp=_optional_datetime(row.get("timestamp")),
            )
            for row in records
        ]

        data, pagination = _page(mapped, page, page_size)

        return PaginatedResponse(data=data, pagination=pagination, meta=_meta(request))

    @router.get(
        "/audits", tags=["v1-audits"], operation_id="v1_list_audits", response_model=PaginatedResponse[AuditRecordDTO]
    )
    async def audits(request: Request, page: Page = 1, page_size: PageSize = 25) -> PaginatedResponse[AuditRecordDTO]:

        scope = _scope(request, "audit.read")

        records = await asyncio.to_thread(operations.list_admin_audits, 5000, scope)

        mapped = [
            AuditRecordDTO(
                audit_id=str(row.get("audit_id") or ""),
                actor=str(row.get("actor") or ""),
                action=str(row.get("action") or ""),
                target_type=str(row.get("target_type") or ""),
                target_id=str(row.get("target_id") or ""),
                created_at=_optional_datetime(row.get("created_at")),
            )
            for row in records
        ]

        data, pagination = _page(mapped, page, page_size)

        return PaginatedResponse(data=data, pagination=pagination, meta=_meta(request))

    @router.get(
        "/settings", tags=["v1-settings"], operation_id="v1_get_settings", response_model=ApiResponse[SettingsDTO]
    )
    async def settings(request: Request) -> ApiResponse[SettingsDTO]:

        scope = _scope(request, "settings.read")

        values = await asyncio.to_thread(operations.get_public_settings, scope)

        return ApiResponse(data=SettingsDTO(values=values), meta=_meta(request))

    @router.patch(
        "/settings", tags=["v1-settings"], operation_id="v1_patch_settings", response_model=ApiResponse[SettingsDTO]
    )
    async def patch_settings(request: Request, body: SettingsPatchRequest) -> ApiResponse[SettingsDTO]:

        scope = _scope(request, "settings.write")

        principal = authorize_admin_request(request, "settings.write")

        values = await asyncio.to_thread(
            operations.save_settings, dict(body.values), scope, actor_id=getattr(principal, "user_id", None)
        )

        await asyncio.to_thread(
            operations.record_admin_action,
            "settings.patch",
            target_type="settings",
            target_id=str(scope.store_id),
            request=request,
            metadata={"actor_id": str(getattr(principal, "user_id", ""))},
            scope=scope,
        )

        return ApiResponse(data=SettingsDTO(values=values), meta=_meta(request))

    @router.put(
        "/availability/{item_id}",
        tags=["v1-availability"],
        operation_id="v1_put_availability",
        response_model=ApiResponse[AvailabilityDTO],
    )
    async def put_availability(
        request: Request, item_id: str, body: AvailabilityPutRequest
    ) -> ApiResponse[AvailabilityDTO]:

        scope = _scope(request, "catalog.availability.write")

        current = await asyncio.to_thread(catalog.get_availability, scope)

        sold_out = set((str(x) for x in current.get("sold_out_ids") or []))

        if body.available:
            sold_out.discard(item_id)

        else:
            sold_out.add(item_id)

        current["sold_out_ids"] = sorted(sold_out)

        if body.reason:
            reasons = dict(current.get("reasons") or {})

            reasons[item_id] = body.reason

            current["reasons"] = reasons

        await asyncio.to_thread(catalog.save_availability, scope, current)

        return ApiResponse(
            data=AvailabilityDTO(item_id=item_id, available=body.available, reason=body.reason), meta=_meta(request)
        )

    @router.post(
        "/promotions",
        tags=["v1-promotions"],
        operation_id="v1_create_promotion",
        response_model=ApiResponse[PromotionSummaryDTO],
    )
    async def create_promotion(request: Request, body: PromotionCreateRequest) -> ApiResponse[PromotionSummaryDTO]:

        scope = _scope(request, "rag.write")

        row, errors = await asyncio.to_thread(
            promotion_service.save_promotion,
            {
                "offer_id": body.offer_id,
                "title": body.title,
                "enabled": body.enabled,
                "metadata": dict(body.metadata or {}),
            },
            scope=scope,
        )

        if errors or not row:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail={"code": "validation_error", "errors": errors})

        return ApiResponse(
            data=PromotionSummaryDTO(
                offer_id=str(row.get("offer_id") or body.offer_id),
                title=str(row.get("title") or body.title),
                status=str(row.get("status") or (row.get("metadata") or {}).get("status") or "draft"),
                enabled=bool(row.get("enabled", body.enabled)),
            ),
            meta=_meta(request),
        )

    return router
