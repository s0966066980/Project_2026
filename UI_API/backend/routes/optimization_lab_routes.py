"""Admin-only, reference-only Optimization Lab surface."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from capabilities.identity_access import scope_from_admin_principal
from capabilities.optimization_lab import OptimizationLabError, optimization_runtime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from utils.auth_utils import authorize_admin_request, check_rate_limit


class EvidenceFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: str = ""
    transcript: str = Field(default="", max_length=12_000)
    assistant_text: str = Field(default="", max_length=12_000)
    rag_hit: dict[str, Any] | None = None
    voice_outcome: str = "unknown"
    failure_type: str = ""
    retry_outcome: str = "none"
    synthetic: bool = True


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_date: str = Field(min_length=10, max_length=10)
    timezone: str = Field(min_length=1, max_length=80)
    profile: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=160)
    effort: str = Field(min_length=1, max_length=40)
    data_scope: str = Field(default="synthetic_only", max_length=32)


def _error(error: OptimizationLabError) -> HTTPException:
    status = 404 if error.code in {"report_not_found", "evidence_expired"} else 422
    if error.code in {"local_ollama_analysis_failed", "local_ollama_unavailable"}:
        status = 503
    if error.code in {"customer_evidence_authorization_required", "step_up_required"}:
        status = 403
    return HTTPException(status_code=status, detail={"code": error.code, **error.details})


def create_router(_deps: dict[str, Any] | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/optimization", tags=["optimization-lab"])

    @router.get("/profiles")
    async def profiles(request: Request):
        authorize_admin_request(request, "optimization.summary")
        return {"profiles": optimization_runtime.default_module().profiles()}

    @router.post("/evidence")
    async def ingest_fixture(request: Request, body: EvidenceFixture):
        principal = authorize_admin_request(request, "optimization.summary")
        if not body.synthetic:
            raise HTTPException(status_code=403, detail="sanitized_customer_evidence_ingress_is_not_enabled")
        scope = scope_from_admin_principal(principal)
        check_rate_limit(request, "optimization_evidence", limit=120)
        try:
            record = await asyncio.to_thread(
                optimization_runtime.default_module().ingest_evidence,
                scope=scope,
                payload=body.model_dump(),
                synthetic=True,
            )
        except OptimizationLabError as error:
            raise _error(error) from error
        return {"status": "accepted", "evidence": record}

    @router.post("/simulations")
    async def simulate(request: Request, body: SimulationRequest):
        principal = authorize_admin_request(request, "optimization.summary")
        scope = scope_from_admin_principal(principal)
        check_rate_limit(request, "optimization_simulation", limit=10)
        try:
            report = await asyncio.to_thread(
                optimization_runtime.default_module().simulate,
                scope=scope,
                store_date=body.store_date,
                timezone_name=body.timezone,
                profile_id=body.profile,
                model=body.model,
                effort=body.effort,
                data_scope=body.data_scope,
            )
        except OptimizationLabError as error:
            raise _error(error) from error
        return report

    @router.get("/reports/{report_id}")
    async def report(request: Request, report_id: str):
        principal = authorize_admin_request(request, "optimization.summary")
        scope = scope_from_admin_principal(principal)
        try:
            return await asyncio.to_thread(
                optimization_runtime.default_module().get_report,
                scope=scope,
                report_id=report_id,
            )
        except OptimizationLabError as error:
            raise _error(error) from error

    @router.get("/reports/{report_id}/evidence/{evidence_id}")
    async def expand_evidence(request: Request, report_id: str, evidence_id: str):
        principal = authorize_admin_request(request, "optimization.evidence.read")
        step_up_until = getattr(request.state, "step_up_expires_at", None)
        if isinstance(step_up_until, str):
            try:
                step_up_until = datetime.fromisoformat(step_up_until.replace("Z", "+00:00"))
            except ValueError:
                step_up_until = None
        scope = scope_from_admin_principal(principal)
        try:
            return await asyncio.to_thread(
                optimization_runtime.default_module().expand_evidence,
                scope=scope,
                report_id=report_id,
                evidence_id=evidence_id,
                actor=str(principal.user_id),
                step_up_valid_until=step_up_until,
            )
        except OptimizationLabError as error:
            raise _error(error) from error

    return router
