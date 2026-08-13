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

# A local model has to be told when to stop. The common result is a bounded
# list of findings, so a budget that fits it comfortably is also the budget
# that stops a small model looping on its own JSON.
LOCAL_MAX_TOKENS = int(os.getenv("PROJECT_ANALYST_LOCAL_MAX_TOKENS", "1024"))

# Ollama defaults `num_ctx` to 4096 whatever the model can do, and silently
# truncates anything longer — so a prompt that does not fit loses its
# instructions and the model answers with something that is not the contract.
# The window is therefore always stated, and sized from the prompt.
LOCAL_CONTEXT_MAX_TOKENS = int(
    os.getenv("PROJECT_ANALYST_LOCAL_CONTEXT_TOKENS", "65536")
)

# Conservative for a snapshot that mixes source, English and Chinese prose.
# Under-estimating truncates; over-estimating only costs a larger window.
LOCAL_CHARS_PER_TOKEN = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prompt(snapshot_json: str) -> str:
    return (
        "You are a read-only project analyst. Analyse the supplied sanitized "
        "project snapshot and return JSON only, matching exactly:\n"
        '{"findings":[{"severity":"healthy|warning|blocked","title":"...",'
        '"detail":"...","evidence_paths":["..."]}]}\n'
        "Report only what the snapshot supports. Never claim to have changed "
        "any file, database or system. Never request or emit secrets.\n"
        "Cite evidence_paths exactly as they appear in the snapshot: no anchors, "
        "no line numbers, no fragments.\n\n"
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
        raise HTTPException(
            status_code=502, detail="provider_response_not_json"
        ) from error
    if not isinstance(document, dict) or not isinstance(document.get("findings"), list):
        raise HTTPException(status_code=502, detail="provider_response_schema_mismatch")

    findings: list[AnalysisFinding] = []
    for raw in document["findings"][:MAX_FINDINGS]:
        if not isinstance(raw, dict):
            raise HTTPException(
                status_code=502, detail="provider_response_schema_mismatch"
            )
        try:
            finding = AnalysisFinding.model_validate(raw)
        except ValueError as error:
            raise HTTPException(
                status_code=502, detail="provider_response_schema_mismatch"
            ) from error
        # A provider that cites `CONTEXT.md#Some_Section` is pointing at a file
        # it was given, more precisely than asked. Dropping the fragment
        # canonicalises the same path; it does not accept a different claim,
        # and a path still unknown afterwards is still refused.
        cited = [path.split("#", 1)[0] for path in finding.evidence_paths]
        unknown = [path for path in cited if path not in allowed_paths]
        if unknown:
            raise HTTPException(
                status_code=502, detail="provider_cited_unsupplied_evidence"
            )
        findings.append(finding.model_copy(update={"evidence_paths": cited}))
    return findings


def _run_cli(definition: profiles.ProfileDefinition, snapshot_json: str) -> str:
    code, output = profiles._run(
        (definition.command, "--print", _prompt(snapshot_json)),
        timeout=ANALYSIS_TIMEOUT_SECONDS,
    )
    if code == 124:
        raise HTTPException(status_code=504, detail="provider_timed_out")
    if code != 0:
        raise HTTPException(status_code=502, detail="provider_invocation_failed")
    return output


def _generate_local(
    definition: profiles.LocalProfileDefinition, prompt: str, context_tokens: int
) -> str:
    """One call to the local model host.

    `format: json` is not a formality: `_findings_from` refuses anything that
    is not the common result shape, and a small local model asked for free
    text will reliably wrap its JSON in prose. Streaming is off because the
    result is only useful whole.
    """

    import json as _json
    import urllib.error

    payload = {
        "model": profiles.local_model(definition),
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "think": False,
        "options": {
            "temperature": 0,
            "num_predict": LOCAL_MAX_TOKENS,
            "num_ctx": context_tokens,
        },
    }
    try:
        body = profiles.local_request(
            definition, "/api/generate", payload, ANALYSIS_TIMEOUT_SECONDS
        )
    except TimeoutError as error:
        raise HTTPException(status_code=504, detail="provider_timed_out") from error
    except (urllib.error.URLError, OSError, ValueError, _json.JSONDecodeError) as error:
        # A URLError wrapping a socket timeout is still a timeout, and an
        # operator reading "invocation failed" would go looking for the wrong
        # thing.
        if isinstance(getattr(error, "reason", None), TimeoutError):
            raise HTTPException(status_code=504, detail="provider_timed_out") from error
        raise HTTPException(
            status_code=502, detail="provider_invocation_failed"
        ) from error
    return str(body.get("response") or "")


def _local_findings(
    definition: profiles.LocalProfileDefinition, request: AnalysisRequest
) -> list[AnalysisFinding]:
    """Analyse the snapshot one evidence file at a time, then merge.

    A vendor CLI is handed the whole snapshot at once. A 4B model cannot do
    that: the real snapshot is ~186,000 characters, and asked to read it in
    one pass the model returns something that is not the contract at all. The
    same model reading one file at a time answers correctly, so the local
    profile splits the work and the caller still receives one merged result.

    The cost is real and worth stating: each file is judged alone, so findings
    that only exist in the relationship between two files are out of reach
    here. That is a property of the profile, not a bug to be papered over — a
    vendor profile with a large context does see the whole snapshot.
    """

    findings: list[AnalysisFinding] = []
    for evidence in request.snapshot.evidence:
        single = request.snapshot.model_copy(update={"evidence": [evidence]})
        prompt = _prompt(single.model_dump_json())
        needed = len(prompt) // LOCAL_CHARS_PER_TOKEN + LOCAL_MAX_TOKENS
        if needed > LOCAL_CONTEXT_MAX_TOKENS:
            # Silently truncating is what produced an unparseable answer in
            # the first place. A file the profile cannot read is reported as a
            # gap in the report rather than left to look like a clean pass.
            findings.append(
                AnalysisFinding(
                    severity="warning",
                    title="本機設定檔無法分析此檔案：超出可用的上下文長度",
                    detail=(
                        f"{evidence.path} 需要約 {needed} tokens，超過本機設定檔的 "
                        f"{LOCAL_CONTEXT_MAX_TOKENS}。此檔案未被閱讀，本次報告不涵蓋它。"
                    ),
                    evidence_paths=[evidence.path],
                )
            )
            continue

        output = _generate_local(
            definition, prompt, min(LOCAL_CONTEXT_MAX_TOKENS, max(4096, needed))
        )
        try:
            findings.extend(_findings_from(output, {evidence.path}))
        except HTTPException as refused:
            # Only a garbled *shape* is recoverable. A model citing a file it
            # was never given is making a claim about something outside the
            # snapshot, and softening that into a warning would let fabricated
            # attribution into a report whose whole value is that every
            # finding traces to supplied evidence.
            if refused.detail == "provider_cited_unsupplied_evidence":
                raise
            # A small model garbling one file must not discard the ones that
            # passed, and must not vanish either: the report names the file it
            # could not read, so a clean-looking pass is never a file nobody
            # analysed.
            findings.append(
                AnalysisFinding(
                    severity="warning",
                    title="本機設定檔的回覆不符合報告格式，此檔案未納入分析",
                    detail=f"{evidence.path}：{refused.detail}",
                    evidence_paths=[evidence.path],
                )
            )
        if len(findings) >= MAX_FINDINGS:
            break
    return findings[:MAX_FINDINGS]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Project Analyst Sidecar", docs_url=None, redoc_url=None, openapi_url=None
    )

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

        local = isinstance(definition, profiles.LocalProfileDefinition)
        status = (
            profiles.evaluate_local(definition)
            if local
            else profiles.evaluate(definition)
        )
        if not status.ready:
            # No fallback. The caller asked for this provider; another one's
            # answer would be a different claim wearing the same label.
            raise HTTPException(
                status_code=409, detail=f"profile_not_ready:{status.reason}"
            )

        allowed_paths = {item.path for item in request.snapshot.evidence}
        if local:
            findings = _local_findings(definition, request)
        else:
            findings = _findings_from(
                _run_cli(definition, request.snapshot.model_dump_json()), allowed_paths
            )

        return AnalysisResult(
            profile=definition.id,
            observed_at=_now(),
            git_revision=request.snapshot.git_revision,
            findings=findings,
            evidence_references=sorted(allowed_paths),
        )

    return app


app = create_app()
