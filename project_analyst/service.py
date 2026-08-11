"""The Project Analyst Sidecar HTTP surface.

Three endpoints and nothing else. The sidecar cannot read the repository, reach
the database, or write anywhere outside its own temporary directory, so its
whole attack surface is the snapshot it is handed and the one CLI it is allowed
to invoke.

Failures here are deliberately unhelpful to a caller trying to learn about the
host: a refusal carries a stable reason code, never a raw CLI error, a
credential path, or an environment dump.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from . import profiles
from .contract import AnalysisFinding, AnalysisRequest, AnalysisResult, ProfileStatus

# An analysis is an Admin-triggered operation, not a background job, so it is
# bounded rather than allowed to run until something else gives up.
ANALYSIS_TIMEOUT_SECONDS = int(os.getenv("PROJECT_ANALYST_TIMEOUT_SECONDS", "300"))

MAX_FINDINGS = 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prompt(snapshot_json: str) -> str:
    return (
        "You are a read-only project analyst. Analyse the supplied sanitized "
        "project snapshot and return JSON only, matching exactly:\n"
        '{"findings":[{"severity":"healthy|warning|blocked","title":"...",'
        '"detail":"...","evidence_paths":["..."]}]}\n'
        "Report only what the snapshot supports. Never claim to have changed "
        "any file, database or system. Never request or emit secrets.\n\n"
        f"SNAPSHOT:\n{snapshot_json}"
    )


def _findings_from(payload: str, allowed_paths: set[str]) -> list[AnalysisFinding]:
    """Parse a provider response into the common result, or refuse it.

    A provider that answers with prose, with a different schema, or citing files
    that were never in the snapshot has failed the contract probe. Salvaging
    part of such a response would put unattributable text into a report whose
    entire value is that every finding traces to supplied evidence.
    """

    try:
        document = json.loads(payload)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=502, detail="provider_response_not_json") from error
    if not isinstance(document, dict) or not isinstance(document.get("findings"), list):
        raise HTTPException(status_code=502, detail="provider_response_schema_mismatch")

    findings: list[AnalysisFinding] = []
    for raw in document["findings"][:MAX_FINDINGS]:
        if not isinstance(raw, dict):
            raise HTTPException(status_code=502, detail="provider_response_schema_mismatch")
        try:
            finding = AnalysisFinding.model_validate(raw)
        except ValueError as error:
            raise HTTPException(status_code=502, detail="provider_response_schema_mismatch") from error
        unknown = [path for path in finding.evidence_paths if path not in allowed_paths]
        if unknown:
            raise HTTPException(status_code=502, detail="provider_cited_unsupplied_evidence")
        findings.append(finding)
    return findings


def create_app() -> FastAPI:
    app = FastAPI(title="Project Analyst Sidecar", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/profiles")
    def list_profiles() -> dict[str, list[ProfileStatus]]:
        return {"profiles": profiles.discover()}

    @app.post("/analyze")
    def analyze(request: AnalysisRequest) -> AnalysisResult:
        try:
            definition = profiles.profile_by_id(request.profile)
        except KeyError as error:
            raise HTTPException(status_code=422, detail="unknown_profile") from error

        status = profiles.evaluate(definition)
        if not status.ready:
            # No fallback. The caller asked for this provider; another one's
            # answer would be a different claim wearing the same label.
            raise HTTPException(status_code=409, detail=f"profile_not_ready:{status.reason}")

        snapshot_json = request.snapshot.model_dump_json()
        code, output = profiles._run(
            (definition.command, "--print", _prompt(snapshot_json)),
            timeout=ANALYSIS_TIMEOUT_SECONDS,
        )
        if code == 124:
            raise HTTPException(status_code=504, detail="provider_timed_out")
        if code != 0:
            raise HTTPException(status_code=502, detail="provider_invocation_failed")

        allowed_paths = {item.path for item in request.snapshot.evidence}
        return AnalysisResult(
            profile=definition.id,
            observed_at=_now(),
            git_revision=request.snapshot.git_revision,
            findings=_findings_from(output, allowed_paths),
            evidence_references=sorted(allowed_paths),
        )

    return app


app = create_app()
