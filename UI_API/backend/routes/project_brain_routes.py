from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import project_brain_service
from services.project_brain_service import SidecarUnavailable
from utils.auth_utils import authorize_admin_request, check_rate_limit


class AnalyzeRequest(BaseModel):
    # A Project Analyst Profile id, not a model name. The profile is what
    # carries the pinned CLI version and the credential; naming a model here
    # would let a caller ask for something no readiness check ever validated.
    profile: str = Field(min_length=1, max_length=32)


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(prefix="/api/project-brain", tags=["project-brain"])

    @router.get("/status")
    async def status(request: Request):
        authorize_admin_request(request, "system.debug")
        return project_brain_service.status()

    @router.post("/analyze")
    async def analyze(payload: AnalyzeRequest, request: Request):
        authorize_admin_request(request, "system.debug")
        check_rate_limit(request, "project_brain_analyze", limit=10)
        try:
            return await project_brain_service.analyze(payload.profile)
        except SidecarUnavailable as unavailable:
            # 503 rather than 502: the analysis capability is unavailable, and
            # the previous report has already been marked stale rather than
            # replaced or silently reused.
            raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable

    @router.post("/proposals")
    async def proposals(request: Request):
        authorize_admin_request(request, "system.debug")
        # The in-process proposal generator is deleted, not disabled. It ran a
        # provider inside the UI API process, which ADR-0036 forbids, and it
        # produced text described as a proposal without an isolated worktree,
        # a patch, or verification behind it — which ADR-0039 requires.
        #
        # The replacement is a separately authorized workflow with its own
        # permissions and review boundary (ADR-0034). Until it exists this
        # endpoint refuses, because answering with anything else would be the
        # unsafe path wearing a new name.
        raise HTTPException(status_code=503, detail="proposal_workflow_not_provisioned")

    return router
