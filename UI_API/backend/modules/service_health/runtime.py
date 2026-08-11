"""Probe the four watched services over HTTP, with a bounded timeout each.

The probe answers one question — is this reachable, and how long did it take —
so it never asks a service to do work. A model is not loaded, a query is not run,
and nothing here can change state.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

import config

from .module import ServiceHealthModule

_TIMEOUT_SECONDS = 3.0
_MAX_ERROR = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _endpoint(key: str) -> str:
    """Where each service answers a cheap liveness request."""

    if key == "ui_api":
        return "self"
    # These are module-level constants resolved from the environment at import time,
    # not entries in the settings store, so config.get would never find them.
    if key == "ollama":
        base = str(getattr(config, "OLLAMA_BASE_URL", "") or "").strip().rstrip("/")
        return f"{base}/api/tags" if base else ""
    if key == "r1_omni":
        base = str(getattr(config, "R1_OMNI_GRADIO_URL", "") or "").strip().rstrip("/")
        return f"{base}/health" if base else ""
    if key == "rag_retrieval":
        return "local"
    return ""


class HttpServiceProbe:
    def probe(self, key: str) -> dict[str, Any]:
        endpoint = _endpoint(key)
        if not endpoint:
            return {
                "status": "not_configured",
                "latency_ms": None,
                "observed_at": _now(),
                "safe_error": "服務位址未設定",
            }
        if endpoint == "self":
            # The panel is served by this process; reaching it proves the UI API answers.
            return {"status": "ok", "latency_ms": 0, "observed_at": _now(), "safe_error": ""}
        if endpoint == "local":
            return self._probe_local_retrieval()
        return self._probe_http(endpoint)

    @staticmethod
    def _probe_http(endpoint: str) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            request = urllib.request.Request(endpoint, method="GET")
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                reachable = 200 <= int(response.status) < 500
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {
                "status": "ok" if reachable else "down",
                "latency_ms": latency_ms,
                "observed_at": _now(),
                "safe_error": "" if reachable else "服務回應非預期狀態",
            }
        except urllib.error.HTTPError as exc:
            # An HTTP error still proves something answered, so it is reachable but
            # degraded rather than down.
            return {
                "status": "degraded",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "observed_at": _now(),
                "safe_error": f"HTTP {exc.code}"[:_MAX_ERROR],
            }
        except Exception as exc:
            return {
                "status": "down",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "observed_at": _now(),
                "safe_error": type(exc).__name__[:_MAX_ERROR],
            }

    @staticmethod
    def _probe_local_retrieval() -> dict[str, Any]:
        """Retrieval runs in this process against a local index rather than a service."""

        import asyncio

        started = time.perf_counter()
        try:
            from services.rag_provider import get_rag

            asyncio.run(get_rag().count())
            return {
                "status": "ok",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "observed_at": _now(),
                "safe_error": "",
            }
        except Exception as exc:
            return {
                "status": "down",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "observed_at": _now(),
                "safe_error": type(exc).__name__[:_MAX_ERROR],
            }


def default_module() -> ServiceHealthModule:
    return ServiceHealthModule(probe=HttpServiceProbe())
