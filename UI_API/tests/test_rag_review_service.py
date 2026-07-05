import importlib
import json


def _service(tmp_path, monkeypatch):
    from services import rag_review_service
    importlib.reload(rag_review_service)
    monkeypatch.setattr(rag_review_service.config, "RAG_DOCUMENTS_DIR", str(tmp_path / "rag_documents"))
    monkeypatch.setattr(rag_review_service.config, "LEARNING_DATA_DIR", str(tmp_path / "learning_data"))
    return rag_review_service


def test_review_publish_writes_source_document(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    review, errors = service.create_review({
        "source_id": "store_policy_breakfast_time",
        "source_type": "policy",
        "title": "早餐供應時間",
        "content": "早餐供應時間為每日 05:00 至 10:30。",
    })
    assert errors == []
    assert review["status"] == "draft"

    approved, errors = service.approve_review(review["review_id"])
    assert errors == []
    assert approved["status"] == "approved"

    published, errors = service.publish_review(review["review_id"])
    assert errors == []
    assert published["status"] == "published"
    assert published["published_path"] == "store_policy/store_policy_breakfast_time.json"

    source_path = tmp_path / "rag_documents" / "store_policy" / "store_policy_breakfast_time.json"
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == "store_policy_breakfast_time"
    assert payload["source_type"] == "policy"
    assert payload["metadata"]["status"] == "published"
    assert payload["metadata"]["review_id"] == review["review_id"]


def test_review_reject_and_archive_status(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    review, errors = service.create_review({
        "source_id": "faq_payment_method",
        "source_type": "faq",
        "content": "可使用現金或信用卡。",
    })
    assert errors == []

    rejected, errors = service.reject_review(review["review_id"], "內容需補充限制")
    assert errors == []
    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "內容需補充限制"

    archived, errors = service.archive_review(review["review_id"])
    assert errors == []
    assert archived["status"] == "archived"


def test_update_published_review_returns_to_draft_with_new_version(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    review, errors = service.create_review({
        "source_id": "menu_alias_big_mac",
        "source_type": "menu_supplement",
        "content": "大麥克也可稱為 Big Mac。",
    })
    assert errors == []
    service.approve_review(review["review_id"])
    service.publish_review(review["review_id"])

    updated, errors = service.update_review(review["review_id"], {
        "source_id": "menu_alias_big_mac",
        "source_type": "menu_supplement",
        "content": "大麥克也可稱為 Big Mac，套餐包含主餐與配餐。",
    })

    assert errors == []
    assert updated["status"] == "draft"
    assert updated["version"] == 2
    assert updated["history"]
