import importlib
import json


def _service(tmp_path, monkeypatch):
    from services import object_storage_service, rag_review_service
    importlib.reload(rag_review_service)
    monkeypatch.setattr(rag_review_service.config, "RAG_DOCUMENTS_DIR", str(tmp_path / "rag_documents"))
    monkeypatch.setattr(rag_review_service.config, "LEARNING_DATA_DIR", str(tmp_path / "learning_data"))
    object_storage_service.reset_for_tests(backend="local", root=tmp_path / "objects")
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
    assert not (tmp_path / "learning_data" / "rag_review_queue.json").exists()


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


def test_rejected_review_requires_a_new_version_before_approval(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    review, errors = service.create_review({
        "source_id": "faq_refund",
        "source_type": "faq",
        "content": "退款請洽門市。",
    })
    assert errors == []
    rejected, errors = service.reject_review(review["review_id"], "缺少期限")
    assert errors == []
    assert rejected["status"] == "rejected"

    approved, errors = service.approve_review(review["review_id"])
    assert approved is None
    assert errors

    revised, errors = service.update_review(review["review_id"], {
        "content": "退款請於七日內洽門市。",
    })
    assert errors == []
    assert revised["version"] == 2
    approved, errors = service.approve_review(review["review_id"])
    assert errors == []
    assert approved["status"] == "approved"


def test_legacy_queue_import_is_idempotent_and_governance_becomes_truth(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    queue_path = tmp_path / "learning_data" / "rag_review_queue.json"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text(json.dumps([{
        "review_id": "legacy_review_faq",
        "source_id": "legacy_faq",
        "source_type": "faq",
        "title": "舊資料",
        "content": "舊 queue 內容",
        "metadata": {},
        "status": "approved",
        "version": 1,
        "created_by": "legacy-admin",
        "updated_by": "legacy-admin",
        "history": [],
    }], ensure_ascii=False), encoding="utf-8")

    first = service.list_reviews()
    second = service.list_reviews()

    assert len(first) == 1
    assert second == first
    assert first[0]["review_id"] == "legacy_review_faq"
    assert first[0]["status"] == "approved"
    assert len(service.rag_governance_service.list_versions("legacy_faq")) == 1
