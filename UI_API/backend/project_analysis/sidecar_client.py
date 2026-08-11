"""The UI API's only way to reach the Project Analyst Sidecar.

Everything provider-shaped lives on the other side of this boundary. Nothing in
the UI API process invokes a CLI, spawns a shell, or talks to a model provider
for project analysis — that authority moved to the sidecar with ADR-0036, and
this module is what replaced it.

Failures are translated into stable reason codes before they reach a route. A
sidecar that is unreachable, slow, or answering with something unexpected must
produce a bounded, visible failure rather than a stack trace in the Admin page
or a silent empty report.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import config

# The sidecar is reachable only over the compose network and is never published
# to the host, so there is no credential on this hop — the network boundary is
# the authorization.
DEFAULT_BASE_URL = "http://project-analyst:7900"

PROFILES_TIMEOUT_SECONDS = 20
# An analysis runs a provider CLI. The ceiling is generous because the work is
# genuinely slow, and bounded because an Admin request is waiting on it.
ANALYZE_TIMEOUT_SECONDS = 330


class SidecarUnavailable(Exception):
    """The sidecar could not be reached or could not answer.

    Carries a stable reason code. A caller may show it; none may retry against a
    different provider, which is the whole point of ADR-0037's no-fallback rule.
    """


@dataclass(frozen=True)
class SidecarFailure:
    reason: str
    status: int = 0


def _base_url() -> str:
    configured = str(config.get("PROJECT_ANALYST_BASE_URL", "") or "").strip()
    return configured or DEFAULT_BASE_URL


def _request(path: str, *, payload: dict[str, Any] | None, timeout: int) -> Any:
    url = f"{_base_url().rstrip('/')}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed compose-network host
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            body = json.load(error)
            detail = str(body.get("detail", ""))
        except (ValueError, OSError):
            detail = ""
        # The sidecar's reason codes are already bounded and safe to surface;
        # anything else becomes a generic code rather than a leaked body.
        reason = detail if detail and "\n" not in detail and len(detail) <= 120 else "sidecar_rejected_request"
        raise SidecarUnavailable(reason) from error
    except urllib.error.URLError as error:
        raise SidecarUnavailable("sidecar_unreachable") from error
    except TimeoutError as error:
        raise SidecarUnavailable("sidecar_timed_out") from error
    except (ValueError, OSError) as error:
        raise SidecarUnavailable("sidecar_response_unreadable") from error


def profiles() -> list[dict[str, Any]]:
    """Every Project Analyst Profile with its readiness, ready or not."""

    body = _request("/profiles", payload=None, timeout=PROFILES_TIMEOUT_SECONDS)
    if not isinstance(body, dict) or not isinstance(body.get("profiles"), list):
        raise SidecarUnavailable("sidecar_response_unreadable")
    return body["profiles"]


def ready_profile_ids() -> set[str]:
    return {entry.get("id") for entry in profiles() if entry.get("ready")}


def analyze(*, profile: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Run one analysis with one named profile.

    No fallback: if this profile is not ready the sidecar answers 409 and that
    failure is returned as-is. Choosing another provider here would produce a
    report attributed to a model that did not write it.
    """

    body = _request(
        "/analyze",
        payload={"profile": profile, "snapshot": snapshot},
        timeout=ANALYZE_TIMEOUT_SECONDS,
    )
    if not isinstance(body, dict) or "findings" not in body:
        raise SidecarUnavailable("sidecar_response_unreadable")
    return body
