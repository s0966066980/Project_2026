"""知識真刪除：先下架清索引再移除紀錄，稽核保留。"""

import os
import tempfile

import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE as SCOPE
from modules.knowledge_publication.module import KnowledgePublicationModule, PublicationError
from modules.knowledge_publication.sqlite_store import SQLitePublicationStore


class _Artifacts:
    def __init__(self):
        self.cleaned: list[str] = []

    def build(self, **_kwargs):
        return {
            "artifact_ref": '["a"]',
            "index_version": "v1",
            "embedding_version": "e1",
            "chunking_version": "c1",
        }

    def cleanup(self, *, artifact_ref):
        self.cleaned.append(artifact_ref)


class _Jobs:
    def enqueue(self, **_kwargs):
        return "job-1"


@pytest.fixture
def module():
    store = SQLitePublicationStore(os.path.join(tempfile.mkdtemp(), "kp.db"))
    artifacts = _Artifacts()
    return KnowledgePublicationModule(store=store, artifacts=artifacts, jobs=_Jobs()), store, artifacts


def _draft(module, title="測試知識", content="這是一筆測試知識內容"):
    return module.create_draft(
        scope=SCOPE, category="promotions", content_type="policy_rule",
        title=title, content=content, actor="tester",
    )


def test_deleting_a_draft_removes_it_from_the_list(module):
    mod, store, _ = module
    row = _draft(mod)

    mod.delete(scope=SCOPE, item_id=row["item_id"], expected_row_revision=row["row_revision"], actor="tester")

    assert store.list_items(scope=SCOPE) == []
    with pytest.raises(PublicationError) as exc:
        store.get_item(scope=SCOPE, item_id=row["item_id"])
    assert exc.value.code == "knowledge_item_not_found"


def test_deletion_keeps_the_audit_trail(module):
    """稽核必須留下，否則無從得知是誰把某筆知識刪掉的。"""

    mod, store, _ = module
    row = _draft(mod)

    mod.delete(scope=SCOPE, item_id=row["item_id"], expected_row_revision=row["row_revision"], actor="tester")

    assert [event["event_type"] for event in store.list_audit(scope=SCOPE, item_id=row["item_id"])]


def test_deleting_a_published_item_clears_its_index_first(module, monkeypatch):
    """已發布的知識若只刪紀錄不清索引，內容會變成沒有主人卻仍被檢索到。"""

    mod, store, artifacts = module
    row = _draft(mod)
    retired: list[str] = []

    # 直接讓它看起來是已發布狀態，聚焦驗證 delete 的分支選擇。
    monkeypatch.setattr(
        store, "get_item",
        lambda *, scope, item_id: {"item_id": item_id, "published_version": 3, "row_revision": 1},
    )
    monkeypatch.setattr(
        mod, "retire",
        lambda *, scope, item_id, expected_row_revision, actor: retired.append(item_id),
    )
    purged: list[str] = []
    monkeypatch.setattr(store, "purge_item", lambda *, scope, item_id: purged.append(item_id))

    mod.delete(scope=SCOPE, item_id=row["item_id"], expected_row_revision=1, actor="tester")

    assert retired == [row["item_id"]], "已發布的知識必須先退役以清掉索引"
    assert purged == [row["item_id"]]


def test_deleting_an_unpublished_item_skips_retirement(module, monkeypatch):
    """草稿沒有索引可清，多跑一次退役只會白白失敗。"""

    mod, store, _ = module
    row = _draft(mod)
    retired: list[str] = []
    monkeypatch.setattr(
        mod, "retire",
        lambda **kwargs: retired.append(kwargs.get("item_id")),
    )

    mod.delete(scope=SCOPE, item_id=row["item_id"], expected_row_revision=row["row_revision"], actor="tester")

    assert retired == []
    assert store.list_items(scope=SCOPE) == []


def test_purge_respects_foreign_key_order(module):
    """發布過的知識在 publication_attempts 留有列，刪除順序錯了會直接違反外鍵。"""

    mod, store, _ = module
    row = _draft(mod)
    mod.request_publication(scope=SCOPE, item_ids=[row["item_id"]], actor="tester", retry_failures_only=False)

    # 不應拋出 IntegrityError
    store.purge_item(scope=SCOPE, item_id=row["item_id"])

    assert store.list_items(scope=SCOPE) == []
