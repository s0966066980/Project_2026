from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import uuid4

from models.commercial_scope import CommercialScope


class RetrievalCheckError(ValueError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class RetrievalIdentity:
    index_identity: str
    configuration_version: int | None
    configuration: dict[str, Any] | None


class RetrievalEngine(Protocol):
    async def retrieve(
        self,
        *,
        scope: CommercialScope,
        query: str,
        method: str | None,
        top_k: int | None,
        relevance_policy: str | None,
    ) -> dict[str, Any]: ...


class RetrievalIdentityProvider(Protocol):
    def current(self, *, scope: CommercialScope) -> RetrievalIdentity: ...


class RetrievalCheckStore(Protocol):
    def create_check(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]: ...

    def get_check(self, *, scope: CommercialScope, check_id: str) -> dict[str, Any] | None: ...

    def mark_confirmed(
        self,
        *,
        scope: CommercialScope,
        check_id: str,
        actor: str,
        confirmed_at: str,
    ) -> dict[str, Any]: ...

    def latest_confirmation(
        self,
        *,
        scope: CommercialScope,
        index_identity: str,
        configuration_version: int,
    ) -> dict[str, Any] | None: ...

    def cleanup_expired(self, *, before: str) -> int: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _public_confirmation(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: record.get(key)
        for key in (
            "check_id",
            "index_identity",
            "configuration_version",
            "method",
            "top_k",
            "relevance_policy",
            "effective_method",
            "fallback_used",
            "result_fingerprint",
            "result_count",
            "created_at",
            "confirmed_at",
            "confirmed_by",
        )
    }


class RetrievalCheckModule:
    def __init__(
        self,
        *,
        store: RetrievalCheckStore,
        engine: RetrievalEngine,
        identities: RetrievalIdentityProvider,
        pending_ttl_seconds: int = 900,
        now=_utc_now,
    ):
        self._store = store
        self._engine = engine
        self._identities = identities
        self._pending_ttl_seconds = max(60, int(pending_ttl_seconds))
        self._now = now

    async def execute(
        self,
        *,
        scope: CommercialScope,
        query: str,
        method: str | None = None,
        top_k: int | None = None,
        relevance_policy: str | None = None,
    ) -> dict[str, Any]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            raise RetrievalCheckError("query_required")

        self.cleanup_expired()
        before = self._identities.current(scope=scope)
        result = await self._engine.retrieve(
            scope=scope,
            query=normalized_query,
            method=method,
            top_k=top_k,
            relevance_policy=relevance_policy,
        )
        after = self._identities.current(scope=scope)
        configuration = after.configuration
        configuration_matches = bool(
            configuration
            and result.get("method") == configuration.get("method")
            and int(result.get("top_k") or 0) == int(configuration.get("top_k") or 0)
            and result.get("relevance_policy") == configuration.get("relevance_policy")
        )
        identity_stable = before == after
        fallback_used = str(result.get("fallback_used") or "")
        result_count = int(result.get("total") or 0)

        if not identity_stable:
            eligibility_reason = "retrieval_identity_changed"
        elif configuration is None:
            eligibility_reason = "published_configuration_required"
        elif not configuration_matches:
            eligibility_reason = "published_configuration_mismatch"
        elif fallback_used:
            eligibility_reason = "fallback_result"
        elif result_count <= 0:
            eligibility_reason = "result_required"
        else:
            eligibility_reason = ""

        fingerprint = _canonical_fingerprint(
            {
                "query": normalized_query,
                "index_identity": after.index_identity,
                "configuration_version": after.configuration_version,
                "method": result.get("method"),
                "effective_method": result.get("effective_method"),
                "top_k": result.get("top_k"),
                "relevance_policy": result.get("relevance_policy"),
                "fallback_used": fallback_used,
                "results": result.get("results") or [],
            }
        )
        now = self._now()
        record = self._store.create_check(
            scope=scope,
            record={
                "check_id": f"arc_{uuid4().hex}",
                "index_identity": after.index_identity,
                "configuration_version": after.configuration_version,
                "method": str(result.get("method") or ""),
                "top_k": int(result.get("top_k") or 0),
                "relevance_policy": str(result.get("relevance_policy") or ""),
                "effective_method": str(result.get("effective_method") or ""),
                "fallback_used": fallback_used,
                "result_fingerprint": fingerprint,
                "result_count": result_count,
                "eligible": not eligibility_reason,
                "eligibility_reason": eligibility_reason,
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(seconds=self._pending_ttl_seconds)).isoformat(),
            },
        )
        return {
            **result,
            "check_id": record["check_id"],
            "index_identity": record["index_identity"],
            "configuration_version": record["configuration_version"],
            "result_fingerprint": record["result_fingerprint"],
            "confirmation_eligible": bool(record["eligible"]),
            "confirmation_reason": record["eligibility_reason"],
        }

    def confirm(
        self,
        *,
        scope: CommercialScope,
        check_id: str,
        actor: str,
    ) -> dict[str, Any]:
        record = self._store.get_check(scope=scope, check_id=check_id)
        if record is None:
            raise RetrievalCheckError("retrieval_check_not_found")

        current = self._identities.current(scope=scope)
        if (
            current.configuration_version is None
            or record.get("index_identity") != current.index_identity
            or int(record.get("configuration_version") or 0) != current.configuration_version
        ):
            raise RetrievalCheckError("retrieval_check_stale")
        if record.get("confirmed_at"):
            return _public_confirmation(record)
        if self._now() > datetime.fromisoformat(str(record["expires_at"])):
            raise RetrievalCheckError("retrieval_check_expired")
        if not record.get("eligible"):
            raise RetrievalCheckError(
                "retrieval_check_not_confirmable",
                details={"reason": record.get("eligibility_reason")},
            )

        confirmed = self._store.mark_confirmed(
            scope=scope,
            check_id=check_id,
            actor=str(actor or "admin"),
            confirmed_at=self._now().isoformat(),
        )
        return _public_confirmation(confirmed)

    def readiness(self, *, scope: CommercialScope) -> dict[str, Any]:
        identity = self._identities.current(scope=scope)
        if identity.configuration_version is None:
            return {"complete": False, "confirmation": None}
        record = self._store.latest_confirmation(
            scope=scope,
            index_identity=identity.index_identity,
            configuration_version=identity.configuration_version,
        )
        return {
            "complete": record is not None,
            "confirmation": _public_confirmation(record) if record else None,
        }

    def cleanup_expired(self) -> int:
        return self._store.cleanup_expired(before=self._now().isoformat())
