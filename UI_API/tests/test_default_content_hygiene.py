from pathlib import Path


def test_default_catalog_does_not_ship_retired_summer_promotions(monkeypatch):
    from models.commercial_scope import LEGACY_DEFAULT_SCOPE
    from repositories import promotion_repository

    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(promotion_repository.config, "RAG_DOCUMENTS_DIR", str(project_root / "rag_documents"))
    monkeypatch.setattr(promotion_repository.postgres_utils, "use_postgres", lambda: False)

    offer_ids = {
        str(row.get("offer_id") or row.get("id") or "")
        for row in promotion_repository.list_promotions_scoped(LEGACY_DEFAULT_SCOPE)
    }

    assert offer_ids.isdisjoint({"summer_drink", "summer_food"})
