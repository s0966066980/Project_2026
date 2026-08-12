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

    @router.post(
        "/fleet/devices/{device_id}/commands",
        tags=["v1-fleet"],
        operation_id="v1_issue_fleet_command",
        response_model=ApiResponse[FleetCommandDTO],
    )
    async def issue_fleet_command(
        request: Request, device_id: UUID, body: FleetCommandRequest
    ) -> ApiResponse[FleetCommandDTO]:

        scope = _scope(request, "device_identity.manage")

        row = await asyncio.to_thread(
            fleet_management_service.issue_command,
            device_id=device_id,
            tenant_id=scope.tenant_id,
            command=body.command,
            actor="admin",
            expires_at=body.expires_at,
        )

        return ApiResponse(
            data=FleetCommandDTO(
                command_id=str(row.get("command_id") or row.get("id") or ""),
                device_id=device_id,
                command=str(row.get("command") or body.command),
                status=str(row.get("status") or "pending"),
            ),
            meta=_meta(request),
        )

    @router.post(
        "/orders/{order_id}/transition",
        tags=["v1-orders"],
        operation_id="v1_transition_order",
        response_model=ApiResponse[OrderSummaryDTO],
    )
    async def transition_order(
        request: Request, order_id: UUID, body: OrderTransitionRequest
    ) -> ApiResponse[OrderSummaryDTO]:

        scope = _scope(request, "operations.write")

        target = OrderStatus(str(body.target_status).strip().lower())

        row = await asyncio.to_thread(checkout_order_repository.transition_order_scoped, order_id, target, scope)

        return ApiResponse(
            data=OrderSummaryDTO(
                order_id=UUID(str(row.get("order_id") or order_id)),
                status=str(row.get("status") or target.value),
                currency=str(row.get("currency") or "TWD"),
                total=int(row.get("total") or 0),
                created_at=_optional_datetime(row.get("created_at")) or datetime.now(timezone.utc),
                member_id=UUID(str(row["member_id"])) if row.get("member_id") else None,
            ),
            meta=_meta(request),
        )

    return router
