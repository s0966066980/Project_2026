from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import project_brain_service
from utils.auth_utils import authorize_admin_request, check_rate_limit


class AnalyzeRequest(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    run_tests: bool = False


class ProposalRequest(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=20)
    request: str = Field(min_length=3, max_length=6000)


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api/project-brain", tags=["project-brain"])

    @router.get("/status")
    async def status(request: Request):
        authorize_admin_request(request, "system.debug")
        return {"models": project_brain_service.ready_models(), "latest": project_brain_service.latest_report()}

    @router.post("/analyze")
    async def analyze(payload: AnalyzeRequest, request: Request):
        authorize_admin_request(request, "system.debug")
        check_rate_limit(request, "project_brain_analyze", limit=10)
        try:
            return await project_brain_service.analyze(payload.model, run_tests=payload.run_tests)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/proposals")
    async def proposals(payload: ProposalRequest, request: Request):
        authorize_admin_request(request, "system.debug")
        check_rate_limit(request, "project_brain_proposal", limit=20)
        try:
            return await project_brain_service.propose(payload.model, kind=payload.kind, request=payload.request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return router
