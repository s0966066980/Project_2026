import importlib


class FakeRag:
    def __init__(self):
        self.deleted = False
        self.documents = []

    async def clear_all(self):
        self.deleted = True
        self.documents.clear()
        return 3

    async def add_document(self, content, source_id=None, source_type="manual", metadata=None):
        self.documents.append({
            "content": content,
            "source_id": source_id,
            "source_type": source_type,
            "metadata": metadata or {},
        })
        return source_id

    async def count(self):
        return len(self.documents)


def _service(tmp_path, monkeypatch):
    from services import rag_document_service
    importlib.reload(rag_document_service)
    monkeypatch.setattr(rag_document_service.config, "RAG_DOCUMENTS_DIR", str(tmp_path / "rag_documents"))
    monkeypatch.setattr(rag_document_service.config, "LEARNING_DATA_DIR", str(tmp_path / "learning_data"))
    monkeypatch.setattr(rag_document_service.config, "get", lambda key, default=None: {
        "RAG_ALERT_MAX_RECORDS": 1000,
        "RAG_ALERT_WEBHOOK_ENABLED": False,
    }.get(key, default))
    return rag_document_service


def test_validate_source_documents_reports_duplicate_source_id(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    root = tmp_path / "rag_documents"
    (root / "faq").mkdir(parents=True)
    (root / "faq" / "a.json").write_text('[{"source_id":"same","source_type":"faq","content":"A"}]', encoding="utf-8")
    (root / "faq" / "b.json").write_text('[{"source_id":"same","source_type":"faq","content":"B"}]', encoding="utf-8")

    result = service.validate_source_documents(include_documents=True)

    assert result["ok"] is False
    assert any("source_id 重複" in error["message"] for error in result["errors"])


def test_rebuild_stops_before_clear_when_validation_fails(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    fake_rag = FakeRag()
    root = tmp_path / "rag_documents"
    (root / "faq").mkdir(parents=True)
    (root / "faq" / "broken.json").write_text('{"content": ', encoding="utf-8")
    monkeypatch.setattr(service, "get_rag", lambda: fake_rag)

    import asyncio
    result = asyncio.run(service.rebuild_from_source_documents())

    assert result["status"] == "error"
    assert fake_rag.deleted is False
    assert result["deleted"] == 0
    assert result["imported"] == 0
    assert result["alert"]["created"] is True
    assert result["alert"]["alert"]["alert_type"] == "rag_rebuild_validation_failed"


def test_rebuild_imports_valid_documents_after_validation(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    fake_rag = FakeRag()
    root = tmp_path / "rag_documents"
    (root / "faq").mkdir(parents=True)
    (root / "faq" / "payment.md").write_text("# 付款 FAQ\n可使用現金或信用卡。", encoding="utf-8")
    monkeypatch.setattr(service, "get_rag", lambda: fake_rag)

    import asyncio
    result = asyncio.run(service.rebuild_from_source_documents())

    assert result["status"] == "ok"
    assert fake_rag.deleted is True
    assert result["imported"] == 1
    assert fake_rag.documents[0]["source_type"] == "faq"


def test_successful_rebuild_resolves_previous_rebuild_alert(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    from services import rag_alert_service
    importlib.reload(rag_alert_service)
    monkeypatch.setattr(rag_alert_service.config, "LEARNING_DATA_DIR", str(tmp_path / "learning_data"))
    monkeypatch.setattr(rag_alert_service.config, "get", lambda key, default=None: {
        "RAG_ALERT_MAX_RECORDS": 1000,
        "RAG_ALERT_WEBHOOK_ENABLED": False,
    }.get(key, default))
    fake_rag = FakeRag()
    root = tmp_path / "rag_documents"
    (root / "faq").mkdir(parents=True)
    (root / "faq" / "broken.json").write_text('{"content": ', encoding="utf-8")
    monkeypatch.setattr(service, "get_rag", lambda: fake_rag)

    import asyncio
    failed = asyncio.run(service.rebuild_from_source_documents())
    assert failed["status"] == "error"

    (root / "faq" / "broken.json").unlink()
    (root / "faq" / "payment.md").write_text("# 付款 FAQ\n可使用現金或信用卡。", encoding="utf-8")
    ok = asyncio.run(service.rebuild_from_source_documents())

    assert ok["status"] == "ok"
    alerts = rag_alert_service.list_alerts()
    assert alerts[0]["status"] == "resolved"


def test_validate_source_documents_rejects_invalid_promotion_timezone(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    from services import promotion_service
    importlib.reload(promotion_service)
    monkeypatch.setattr(promotion_service.config, "RAG_DOCUMENTS_DIR", str(tmp_path / "rag_documents"))
    monkeypatch.setattr(
        promotion_service.menu_repository,
        "get_menu",
        lambda: [{"id": "MCD001", "name": "大麥克套餐", "category": "超值全餐", "price": 155}],
    )
    root = tmp_path / "rag_documents"
    (root / "promotions").mkdir(parents=True)
    (root / "promotions" / "bad_timezone.json").write_text(
        '{"type":"promotion","offer_id":"bad_timezone","title":"錯誤時區","status":"active","timezone":"Mars/Olympus","item_ids":["MCD001"]}',
        encoding="utf-8",
    )

    result = service.validate_source_documents(include_documents=True)

    assert result["ok"] is False
    assert any("timezone 不存在" in error["message"] for error in result["errors"])
