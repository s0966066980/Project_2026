from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from capabilities.identity_access import scope_from_admin_principal
from capabilities.voice_evidence import voice_evidence_runtime
from utils.auth_utils import authorize_admin_request


def create_router(_deps: dict[str, Any] | None = None, *, prefix: str = "/api/v1/voice-evidence") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["voice-evidence"])

    @router.get("")
    async def list_voice_evidence(
        request: Request,
        observed_from: str = Query(min_length=1, max_length=40),
        observed_to: str = Query(min_length=1, max_length=40),
        terminal_status: str | None = Query(default=None, max_length=40),
        failure_type: str | None = Query(default=None, max_length=80),
        rag_outcome: str | None = Query(default=None, max_length=20),
        limit: int = Query(default=50, ge=1, le=100),
        after_observed_at: str | None = Query(default=None, max_length=40),
        after_evidence_id: str | None = Query(default=None, max_length=160),
    ):
        principal = authorize_admin_request(request, "voice.evidence.summary")
        scope = scope_from_admin_principal(principal)
        try:
            window_end = datetime.fromisoformat(observed_to.replace("Z", "+00:00"))
            if window_end.tzinfo is None:
                window_end = window_end.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_evidence_window"}) from exc
        if window_end <= datetime.now(timezone.utc) - timedelta(days=30):
            raise HTTPException(status_code=410, detail={"code": "evidence_expired"})
        if bool(after_observed_at) != bool(after_evidence_id):
            raise HTTPException(status_code=422, detail={"code": "invalid_cursor"})
        try:
            module = voice_evidence_runtime.default_module()
            records = await asyncio.to_thread(
                module.list_metadata,
                scope=scope,
                observed_from=observed_from,
                observed_to=observed_to,
                terminal_status=terminal_status,
                failure_type=failure_type,
                rag_outcome=rag_outcome,
                limit=limit,
                after=(after_observed_at, after_evidence_id) if after_observed_at and after_evidence_id else None,
            )
            reconciliation = await asyncio.to_thread(
                module.reconciliation,
                scope=scope,
                observed_from=observed_from,
                observed_to=observed_to,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "invalid_evidence_window"}) from exc
        next_cursor = None
        if len(records) == limit:
            last = records[-1]
            next_cursor = {
                "observed_at": last["observed_at"],
                "evidence_id": last["evidence_id"],
            }
        return {
            "records": records,
            "page": {"limit": limit, "has_more": next_cursor is not None, "next_cursor": next_cursor},
            "reconciliation": reconciliation,
            "observed_from": observed_from,
            "observed_to": observed_to,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    return router
