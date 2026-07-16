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


def test_rebuild_imports_only_selected_sources_and_reuses_saved_selection(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    fake_rag = FakeRag()
    root = tmp_path / "rag_documents" / "faq"
    root.mkdir(parents=True)
    (root / "keep.md").write_text("# 保留\n有效內容", encoding="utf-8")
    (root / "legacy.md").write_text("# 舊文件\n不應再匯入", encoding="utf-8")
    monkeypatch.setattr(service, "get_rag", lambda: fake_rag)

    import asyncio
    preview = service.validate_source_documents(include_documents=True)
    selected_id = next(row["source_id"] for row in preview["documents"] if row["path"] == "faq/keep.md")

    first = asyncio.run(service.rebuild_from_source_documents(selected_source_ids=[selected_id]))
    second = asyncio.run(service.rebuild_from_source_documents())

    assert first["selected_source_ids"] == [selected_id]
    assert first["imported"] == 1
    assert second["selection_source"] == "saved"
    assert second["imported"] == 1
    assert [row["source_id"] for row in fake_rag.documents] == [selected_id]


def test_rebuild_reconciles_deleted_sources_from_saved_selection(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    fake_rag = FakeRag()
    root = tmp_path / "rag_documents" / "faq"
    root.mkdir(parents=True)
    keep_path = root / "keep.md"
    legacy_path = root / "legacy.md"
    keep_path.write_text("# 保留\n有效內容", encoding="utf-8")
    legacy_path.write_text("# 舊文件\n之後會刪除", encoding="utf-8")
    monkeypatch.setattr(service, "get_rag", lambda: fake_rag)

    import asyncio
    preview = service.validate_source_documents(include_documents=True)
    source_ids = {row["path"]: row["source_id"] for row in preview["documents"]}
    asyncio.run(service.rebuild_from_source_documents(selected_source_ids=list(source_ids.values())))
    legacy_path.unlink()

    rebuilt = asyncio.run(service.rebuild_from_source_documents())

    assert rebuilt["status"] == "ok"
    assert rebuilt["selection_source"] == "saved"
    assert rebuilt["selected_source_ids"] == [source_ids["faq/keep.md"]]
    assert rebuilt["imported"] == 1
    assert [row["source_id"] for row in fake_rag.documents] == [source_ids["faq/keep.md"]]


def test_clear_index_saves_empty_selection_so_rebuild_does_not_restore_old_sources(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    fake_rag = FakeRag()
    root = tmp_path / "rag_documents" / "faq"
    root.mkdir(parents=True)
    (root / "legacy.md").write_text("# 舊文件\n不應再匯入", encoding="utf-8")
    monkeypatch.setattr(service, "get_rag", lambda: fake_rag)

    import asyncio
    cleared = asyncio.run(service.clear_index())
    rebuilt = asyncio.run(service.rebuild_from_source_documents())

    assert cleared["selected_source_ids"] == []
    assert rebuilt["selection_source"] == "saved"
    assert rebuilt["imported"] == 0
    assert fake_rag.documents == []


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
