import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from modules.retrieval_check import (
    RetrievalCheckError,
    RetrievalCheckModule,
    RetrievalIdentity,
    SQLiteRetrievalCheckStore,
)

from models.commercial_scope import CommercialScope


class ScriptedEngine:
    def __init__(self):
        self.fallback_used = ""
        self.results = [
            {
                "rank": 1,
                "item_id": "item_1",
                "chunk_id": "chunk_1",
                "content": "早餐供應到十點。",
                "score": 0.91,
            }
        ]

    async def retrieve(self, *, scope, query, method, top_k, relevance_policy):
        selected_method = method or "bm25"
        return {
            "method": selected_method,
            "effective_method": self.fallback_used or selected_method,
            "top_k": top_k or 5,
            "relevance_policy": relevance_policy or "balanced",
            "fallback_used": self.fallback_used,
            "latency_ms": 4.2,
            "results": self.results,
            "total": len(self.results),
        }


class MutableIdentities:
    def __init__(self):
        self.value = RetrievalIdentity(
            index_identity="index-v1",
            configuration_version=1,
            configuration={
                "version": 1,
                "method": "bm25",
                "top_k": 5,
                "relevance_policy": "balanced",
            },
        )

    def current(self, *, scope):
        return self.value


@pytest.fixture
def harness(tmp_path):
    clock = [datetime(2026, 7, 28, tzinfo=timezone.utc)]
    store = SQLiteRetrievalCheckStore(str(tmp_path / "checks.sqlite3"))
    engine = ScriptedEngine()
    identities = MutableIdentities()
    module = RetrievalCheckModule(
        store=store,
        engine=engine,
        identities=identities,
        pending_ttl_seconds=60,
        now=lambda: clock[0],
    )
    scope = CommercialScope(tenant_id=uuid4(), store_id=uuid4())
    return module, store, engine, identities, clock, scope


def test_current_production_snapshot_can_be_confirmed_without_raw_content(harness):
    module, store, _, _, _, scope = harness

    result = asyncio.run(module.execute(scope=scope, query="早餐供應到幾點？"))

    assert result["confirmation_eligible"] is True
    stored = store.get_check(scope=scope, check_id=result["check_id"])
    assert stored is not None
    assert "query" not in stored
    assert "results" not in stored
    assert len(stored["result_fingerprint"]) == 64

    confirmation = module.confirm(
        scope=scope,
        check_id=result["check_id"],
        actor="publisher-1",
    )

    assert confirmation["confirmed_by"] == "publisher-1"
    assert "query" not in confirmation
    assert "results" not in confirmation
    assert module.readiness(scope=scope)["complete"] is True


def test_nonproduction_or_fallback_result_is_visible_but_not_confirmable(harness):
    module, _, engine, _, _, scope = harness

    diagnostic = asyncio.run(
        module.execute(
            scope=scope,
            query="早餐",
            method="dense",
            top_k=3,
        )
    )
    assert diagnostic["total"] == 1
    assert diagnostic["confirmation_eligible"] is False
    assert diagnostic["confirmation_reason"] == "published_configuration_mismatch"

    engine.fallback_used = "hybrid_rrf"
    fallback = asyncio.run(module.execute(scope=scope, query="早餐"))
    assert fallback["total"] == 1
    assert fallback["confirmation_eligible"] is False
    assert fallback["confirmation_reason"] == "fallback_result"

    with pytest.raises(RetrievalCheckError) as exc:
        module.confirm(
            scope=scope,
            check_id=fallback["check_id"],
            actor="publisher-1",
        )
    assert exc.value.code == "retrieval_check_not_confirmable"


def test_confirmation_expires_when_index_or_configuration_changes(harness):
    module, _, _, identities, _, scope = harness
    result = asyncio.run(module.execute(scope=scope, query="早餐"))
    module.confirm(scope=scope, check_id=result["check_id"], actor="publisher-1")

    identities.value = RetrievalIdentity(
        index_identity="index-v2",
        configuration_version=2,
        configuration={
            "version": 2,
            "method": "bm25",
            "top_k": 5,
            "relevance_policy": "balanced",
        },
    )

    assert module.readiness(scope=scope) == {
        "complete": False,
        "confirmation": None,
    }
    with pytest.raises(RetrievalCheckError) as exc:
        module.confirm(
            scope=scope,
            check_id=result["check_id"],
            actor="publisher-1",
        )
    assert exc.value.code == "retrieval_check_stale"


def test_pending_snapshot_expires_and_cannot_be_confirmed(harness):
    module, _, _, _, clock, scope = harness
    result = asyncio.run(module.execute(scope=scope, query="早餐"))
    clock[0] += timedelta(seconds=61)

    with pytest.raises(RetrievalCheckError) as exc:
        module.confirm(
            scope=scope,
            check_id=result["check_id"],
            actor="publisher-1",
        )

    assert exc.value.code == "retrieval_check_expired"
    assert module.cleanup_expired() == 1
