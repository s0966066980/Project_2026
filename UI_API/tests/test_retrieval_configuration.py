from modules.retrieval_configuration import RetrievalConfigurationError, RetrievalConfigurationModule
from modules.retrieval_configuration.sqlite_store import SQLiteRetrievalConfigurationStore

from models.commercial_scope import LEGACY_DEFAULT_SCOPE


def _module(tmp_path):
    return RetrievalConfigurationModule(
        store=SQLiteRetrievalConfigurationStore(tmp_path / "retrieval.sqlite3")
    )


def test_only_the_active_configuration_is_stored(tmp_path):
    module = _module(tmp_path)

    first = module.publish(
        scope=LEGACY_DEFAULT_SCOPE,
        method="hybrid_rrf",
        top_k=5,
        relevance_policy="balanced",
        actor="admin-1",
    )
    second = module.publish(
        scope=LEGACY_DEFAULT_SCOPE,
        method="bm25",
        top_k=3,
        relevance_policy="strict",
        actor="admin-1",
    )

    assert first["version"] == 1
    assert second["version"] == 2
    assert module.list(scope=LEGACY_DEFAULT_SCOPE)["configurations"] == [second]


def test_deleting_the_active_configuration_is_explicit_and_scoped(tmp_path):
    module = _module(tmp_path)
    created = module.publish(
        scope=LEGACY_DEFAULT_SCOPE,
        method="hybrid_rrf",
        top_k=5,
        relevance_policy="balanced",
        actor="admin-1",
    )

    deleted = module.delete(
        scope=LEGACY_DEFAULT_SCOPE,
        version=created["version"],
        actor="admin-1",
    )

    assert deleted["deleted_version"] == 1
    assert module.list(scope=LEGACY_DEFAULT_SCOPE)["published"] is None


def test_invalid_configuration_does_not_write(tmp_path):
    module = _module(tmp_path)

    try:
        module.publish(
            scope=LEGACY_DEFAULT_SCOPE,
            method="unknown",
            top_k=5,
            relevance_policy="balanced",
            actor="admin-1",
        )
    except RetrievalConfigurationError as exc:
        assert exc.code == "invalid_retrieval_method"
    else:  # pragma: no cover - assertion documents the contract
        raise AssertionError("invalid method was accepted")

    assert module.list(scope=LEGACY_DEFAULT_SCOPE)["published"] is None
