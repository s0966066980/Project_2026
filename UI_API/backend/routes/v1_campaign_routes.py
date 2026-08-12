"""Versioned compatibility endpoints grouped by capability.

These routes keep the published envelope stable while Admin/Kiosk consumers
move to their capability-owned surfaces.
"""

# ruff: noqa: F403, F405

from __future__ import annotations

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
        "/campaigns",
        tags=["v1-campaigns"],
        operation_id="v1_list_campaigns",
        response_model=ApiResponse[list[CampaignSnapshotDTO]],
    )
    async def campaigns(request: Request) -> ApiResponse[list[CampaignSnapshotDTO]]:

        scope = _scope(request, "campaigns.read")

        rows = await asyncio.to_thread(list_campaigns, scope)

        return ApiResponse(data=[_campaign_dto(row) for row in rows], meta=_meta(request))

    @router.get(
        "/campaigns/{campaign_id}",
        tags=["v1-campaigns"],
        operation_id="v1_get_campaign",
        response_model=ApiResponse[CampaignSnapshotDTO],
    )
    async def campaign_detail(request: Request, campaign_id: str) -> ApiResponse[CampaignSnapshotDTO]:

        scope = _scope(request, "campaigns.read")

        row = await asyncio.to_thread(get_campaign, campaign_id, scope)

        if row is None:
            raise HTTPException(status_code=404, detail={"code": "campaign_not_found", "message": "找不到活動。"})

        return ApiResponse(data=_campaign_dto(row), meta=_meta(request))

    @router.post(
        "/campaigns/preview",
        tags=["v1-campaigns"],
        operation_id="v1_preview_campaign",
        response_model=ApiResponse[CampaignPreviewDTO],
    )
    async def campaign_preview(request: Request, body: CampaignPreviewRequest) -> ApiResponse[CampaignPreviewDTO]:

        scope = _scope(request, "campaigns.read")

        payload = body.model_dump(exclude={"campaign_id"})

        catalog_items = await asyncio.to_thread(catalog.list_items, scope, include_retired=False, ensure_seed=True)

        result = await asyncio.to_thread(
            preview_campaign, payload, scope, exclude_campaign_id=body.campaign_id, catalog_items=catalog_items
        )

        return ApiResponse(data=CampaignPreviewDTO(**result.__dict__), meta=_meta(request))

    @router.post(
        "/campaigns",
        tags=["v1-campaigns"],
        operation_id="v1_create_campaign_draft",
        response_model=ApiResponse[CampaignSnapshotDTO],
    )
    async def create_campaign(request: Request, body: CampaignDraftRequest) -> ApiResponse[CampaignSnapshotDTO]:

        scope = _scope(request, "campaigns.write")

        catalog_items = await asyncio.to_thread(catalog.list_items, scope, include_retired=False, ensure_seed=True)

        try:
            row = await asyncio.to_thread(
                create_campaign_draft,
                body.model_dump(),
                scope,
                actor_id=_admin_actor(request),
                catalog_items=catalog_items,
            )

        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "campaign_invalid", "message": "還有欄位需要修正。", "field_errors": list(exc.args[0])},
            ) from exc

        await _publish_campaign_change(row)

        return ApiResponse(data=_campaign_dto(row), meta=_meta(request))

    @router.put(
        "/campaigns/{campaign_id}/draft",
        tags=["v1-campaigns"],
        operation_id="v1_revise_campaign_draft",
        response_model=ApiResponse[CampaignSnapshotDTO],
    )
    async def revise_campaign(
        request: Request, campaign_id: str, body: CampaignDraftUpdateRequest
    ) -> ApiResponse[CampaignSnapshotDTO]:

        scope = _scope(request, "campaigns.write")

        catalog_items = await asyncio.to_thread(catalog.list_items, scope, include_retired=False, ensure_seed=True)

        try:
            row = await asyncio.to_thread(
                revise_campaign_draft,
                campaign_id,
                body.model_dump(exclude={"expected_version"}),
                scope,
                expected_version=body.expected_version,
                actor_id=_admin_actor(request),
                catalog_items=catalog_items,
            )

        except CampaignConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "campaign_version_conflict", "message": "活動已被其他人更新，請重新載入。"},
            ) from exc

        except CampaignStateError as exc:
            raise HTTPException(
                status_code=409, detail={"code": str(exc), "message": "目前活動狀態無法修改。"}
            ) from exc

        except LookupError as exc:
            raise HTTPException(
                status_code=404, detail={"code": "campaign_not_found", "message": "找不到活動。"}
            ) from exc

        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "campaign_invalid", "message": "還有欄位需要修正。", "field_errors": list(exc.args[0])},
            ) from exc

        await _publish_campaign_change(row)

        return ApiResponse(data=_campaign_dto(row), meta=_meta(request))

    @router.post(
        "/campaigns/publish",
        tags=["v1-campaigns"],
        operation_id="v1_publish_campaign",
        response_model=ApiResponse[CampaignSnapshotDTO],
    )
    async def campaign_publish(request: Request, body: CampaignPublishRequest) -> ApiResponse[CampaignSnapshotDTO]:

        _scope(request, "campaigns.write")

        scope = _scope(request, "campaigns.publish")

        catalog_items = await asyncio.to_thread(catalog.list_items, scope, include_retired=False, ensure_seed=True)

        try:
            row = await asyncio.to_thread(
                publish_campaign,
                body.model_dump(exclude={"campaign_id", "expected_version"}),
                scope,
                campaign_id=body.campaign_id,
                expected_version=body.expected_version,
                actor_id=_admin_actor(request),
                catalog_items=catalog_items,
            )

        except CampaignConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "campaign_version_conflict", "message": "活動已被其他人更新，請重新載入。"},
            ) from exc

        except CampaignStateError as exc:
            raise HTTPException(
                status_code=409, detail={"code": str(exc), "message": "此活動已經發布，請從活動列表操作暫停或結束。"}
            ) from exc

        except LookupError as exc:
            raise HTTPException(
                status_code=404, detail={"code": "campaign_not_found", "message": "找不到活動。"}
            ) from exc

        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "campaign_invalid",
                    "message": "還有欄位需要修正，修正後才能發布。",
                    "field_errors": list(exc.args[0]),
                },
            ) from exc

        await _publish_campaign_change(row)

        return ApiResponse(data=_campaign_dto(row), meta=_meta(request))

    @router.post(
        "/campaigns/{campaign_id}/transition",
        tags=["v1-campaigns"],
        operation_id="v1_transition_campaign",
        response_model=ApiResponse[CampaignSnapshotDTO],
    )
    async def campaign_transition(
        request: Request, campaign_id: str, body: CampaignTransitionRequest
    ) -> ApiResponse[CampaignSnapshotDTO]:

        scope = _scope(request, "campaigns.publish")

        try:
            row = await asyncio.to_thread(
                transition_campaign,
                campaign_id,
                body.target_status,
                scope,
                expected_version=body.expected_version,
                actor_id=_admin_actor(request),
            )

        except CampaignConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "campaign_version_conflict", "message": "活動已被其他人更新，請重新載入。"},
            ) from exc

        except CampaignStateError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "campaign_transition_not_allowed", "message": "目前狀態不能執行此操作。"},
            ) from exc

        except LookupError as exc:
            raise HTTPException(
                status_code=404, detail={"code": "campaign_not_found", "message": "找不到活動。"}
            ) from exc

        await _publish_campaign_change(row)

        return ApiResponse(data=_campaign_dto(row), meta=_meta(request))

    return router
