"""The three RAG flows Batch P1 keeps, exercised on an empty knowledge base.

There is no RAG content in this deployment — every knowledge table is empty and
the vector collection holds zero embeddings — so these build their own data
rather than assuming any exists. That is also the state a store starts in, which
makes it the case worth covering: the flows have to work from nothing.
"""

import asyncio

import pytest
from modules.knowledge_publication.module import KnowledgePublicationModule, PublicationError
from modules.knowledge_publication.sqlite_store import SQLitePublicationStore
from modules.retrieval_check.module import RetrievalCheckError, RetrievalCheckModule, RetrievalIdentity
from modules.retrieval_check.sqlite_store import SQLiteRetrievalCheckStore

from models.commercial_scope import LEGACY_DEFAULT_SCOPE

SCOPE = LEGACY_DEFAULT_SCOPE
ACTOR = "admin-1"


class _Jobs:
    """Publication is asynchronous; the queue is not what these flows are about."""

    def __init__(self):
        self.enqueued: list[str] = []

    def enqueue(self, *, attempt_id: str, scope) -> str:
        self.enqueued.append(attempt_id)
        return f"job-{attempt_id}"


@pytest.fixture()
def knowledge(tmp_path):
    return KnowledgePublicationModule(
        store=SQLitePublicationStore(tmp_path / "knowledge.sqlite3"),
        jobs=_Jobs(),
    )


def _draft(module, *, title="營業時間", content="問題：幾點營業？\n\n答案：每日 10:00 至 22:00。"):
    return module.create_draft(
        scope=SCOPE,
        category="store_and_hours",
        content_type="question_answer",
        title=title,
        content=content,
        actor=ACTOR,
    )


class TestKnowledgeItemCrud:
    def test_an_empty_store_lists_nothing_rather_than_failing(self, knowledge):
        assert knowledge.list_items(scope=SCOPE)["items"] == []

    # The editor's category and type vocabularies used to arrive through the studio
    # aggregate P1 retires. The list that owns these items carries them now, so the
    # form still renders without a second round trip.
    def test_the_list_carries_the_vocabularies_the_editor_needs(self, knowledge):
        metadata = knowledge.list_items(scope=SCOPE)["metadata"]

        assert {row["id"] for row in metadata["categories"]} >= {"store_and_hours", "other"}
        assert {row["id"] for row in metadata["content_types"]} >= {"question_answer", "policy_rule"}
        assert all(row["label"] for row in metadata["categories"])

    def test_a_draft_is_created_and_readable(self, knowledge):
        created = _draft(knowledge)

        item = knowledge.get_item(scope=SCOPE, item_id=created["item_id"])

        assert item["title"] == "營業時間"
        assert item["category"] == "store_and_hours"
        assert [row["item_id"] for row in knowledge.list_items(scope=SCOPE)["items"]] == [created["item_id"]]

    def test_a_revision_requires_the_row_the_editor_was_looking_at(self, knowledge):
        created = _draft(knowledge)

        knowledge.revise_draft(
            scope=SCOPE,
            item_id=created["item_id"],
            expected_row_revision=created["row_revision"],
            category="store_and_hours",
            content_type="question_answer",
            title="營業時間（更新）",
            content="問題：幾點營業？\n\n答案：每日 09:00 至 22:00。",
            actor=ACTOR,
        )

        assert knowledge.get_item(scope=SCOPE, item_id=created["item_id"])["title"] == "營業時間（更新）"

    def test_a_stale_revision_is_refused_rather_than_overwriting(self, knowledge):
        created = _draft(knowledge)
        knowledge.revise_draft(
            scope=SCOPE,
            item_id=created["item_id"],
            expected_row_revision=created["row_revision"],
            category="store_and_hours",
            content_type="question_answer",
            title="第一次修改",
            content="問題：幾點營業？\n\n答案：每日 09:00 至 22:00。",
            actor=ACTOR,
        )

        with pytest.raises(PublicationError):
            knowledge.revise_draft(
                scope=SCOPE,
                item_id=created["item_id"],
                expected_row_revision=created["row_revision"],
                category="store_and_hours",
                content_type="question_answer",
                title="用過期版本覆蓋",
                content="問題：幾點營業？\n\n答案：每日 08:00 至 22:00。",
                actor=ACTOR,
            )

    # Near-duplicate knowledge is what makes retrieval ambiguous, so the author is
    # warned and has to say they meant it.
    def test_near_duplicate_content_is_refused_until_overridden(self, knowledge):
        _draft(knowledge)
        similar = "問題：幾點營業？\n\n答案：每日 10:00 至 22:30。"

        with pytest.raises(PublicationError) as refused:
            _draft(knowledge, title="營業時間（相似）", content=similar)
        assert refused.value.args[0] == "near_duplicate"

        allowed = knowledge.create_draft(
            scope=SCOPE,
            category="store_and_hours",
            content_type="question_answer",
            title="營業時間（相似）",
            content=similar,
            actor=ACTOR,
            override_near_duplicate=True,
        )
        assert allowed["item_id"]

    # Byte-identical content is never a judgement call, so the override does not
    # apply to it — otherwise the index would hold two rows that can only compete.
    def test_identical_content_is_refused_even_with_the_override(self, knowledge):
        _draft(knowledge)

        with pytest.raises(PublicationError) as refused:
            knowledge.create_draft(
                scope=SCOPE,
                category="store_and_hours",
                content_type="question_answer",
                title="營業時間（完全相同）",
                content="問題：幾點營業？\n\n答案：每日 10:00 至 22:00。",
                actor=ACTOR,
                override_near_duplicate=True,
            )
        assert refused.value.args[0] == "exact_duplicate"

    def test_deleting_an_unpublished_draft_leaves_the_store_empty(self, knowledge):
        created = _draft(knowledge)

        knowledge.delete(
            scope=SCOPE,
            item_id=created["item_id"],
            expected_row_revision=created["row_revision"],
            actor=ACTOR,
        )

        assert knowledge.list_items(scope=SCOPE)["items"] == []


class TestPublishedRetrievalMethod:
    def test_publishing_a_draft_enqueues_exactly_one_attempt(self, tmp_path):
        jobs = _Jobs()
        module = KnowledgePublicationModule(
            store=SQLitePublicationStore(tmp_path / "knowledge.sqlite3"), jobs=jobs
        )
        created = _draft(module)

        batch = module.request_publication(scope=SCOPE, item_ids=[created["item_id"]], actor=ACTOR)

        assert len(batch["results"]) == 1
        assert batch["results"][0]["status"] == "indexing"
        assert jobs.enqueued == [batch["results"][0]["attempt_id"]]

    def test_a_repeated_item_id_does_not_publish_twice(self, tmp_path):
        jobs = _Jobs()
        module = KnowledgePublicationModule(
            store=SQLitePublicationStore(tmp_path / "knowledge.sqlite3"), jobs=jobs
        )
        created = _draft(module)

        batch = module.request_publication(
            scope=SCOPE, item_ids=[created["item_id"], created["item_id"]], actor=ACTOR
        )

        assert len(batch["results"]) == 1
        assert len(jobs.enqueued) == 1

    # A queue that refuses the work must leave visible pending publish work rather
    # than an attempt that looks enqueued and never runs.
    def test_a_failed_enqueue_is_recorded_as_a_failure(self, tmp_path):
        class _RefusingJobs:
            def enqueue(self, *, attempt_id: str, scope) -> str:
                raise RuntimeError("queue_unavailable")

        module = KnowledgePublicationModule(
            store=SQLitePublicationStore(tmp_path / "knowledge.sqlite3"), jobs=_RefusingJobs()
        )
        created = _draft(module)

        batch = module.request_publication(scope=SCOPE, item_ids=[created["item_id"]], actor=ACTOR)

        assert batch["results"][0]["status"] == "index_failed"
        assert "queue_unavailable" in batch["results"][0]["reason"]

    def test_nothing_is_published_before_an_attempt_commits(self, knowledge):
        created = _draft(knowledge)
        knowledge.request_publication(scope=SCOPE, item_ids=[created["item_id"]], actor=ACTOR)

        assert knowledge.published_attempt_ids(scope=SCOPE) == set()


class _Engine:
    def __init__(self, hits=None):
        self._hits = hits if hits is not None else []
        self.queries: list[str] = []

    async def retrieve(self, *, scope, query, method, top_k, relevance_policy):
        self.queries.append(query)
        return {"method": method or "hybrid", "hits": list(self._hits)}


class _Identities:
    def current(self, *, scope) -> RetrievalIdentity:
        return RetrievalIdentity(index_identity="kiosk_rag", configuration_version=1, configuration={})


class TestAdHocRetrievalTest:
    def _module(self, tmp_path, engine):
        return RetrievalCheckModule(
            store=SQLiteRetrievalCheckStore(tmp_path / "checks.sqlite3"),
            engine=engine,
            identities=_Identities(),
        )

    def test_a_blank_query_is_refused_before_reaching_the_engine(self, tmp_path):
        engine = _Engine()
        module = self._module(tmp_path, engine)

        with pytest.raises(RetrievalCheckError):
            asyncio.run(module.execute(scope=SCOPE, query="   "))

        assert engine.queries == []

    # An empty knowledge base is the current state, and asking it a question is a
    # valid operator action that must answer "nothing", not fail.
    def test_an_empty_index_returns_no_hits_rather_than_an_error(self, tmp_path):
        module = self._module(tmp_path, _Engine(hits=[]))

        result = asyncio.run(module.execute(scope=SCOPE, query="營業時間"))

        assert result["hits"] == []
        assert result["check_id"]

    def test_a_check_records_what_was_asked(self, tmp_path):
        engine = _Engine(hits=[{"item_id": "item-1", "score": 0.9}])
        module = self._module(tmp_path, engine)

        result = asyncio.run(module.execute(scope=SCOPE, query="營業時間"))

        assert engine.queries == ["營業時間"]
        assert result["hits"] == [{"item_id": "item-1", "score": 0.9}]
