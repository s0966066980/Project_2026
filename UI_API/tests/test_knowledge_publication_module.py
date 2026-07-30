import sqlite3
from uuid import uuid4

import pytest
from modules.knowledge_publication import (
    KnowledgePublicationModule,
    PublicationError,
    SQLitePublicationStore,
    TransientPublicationError,
)

from models.commercial_scope import CommercialScope


class RecordingPublicationJobs:
    def __init__(self):
        self.attempt_ids: list[str] = []

    def enqueue(self, *, attempt_id: str, scope: CommercialScope) -> str:
        self.attempt_ids.append(attempt_id)
        return f"job-{attempt_id}"


class ScriptedPublicationArtifacts:
    def __init__(self):
        self.built: list[str] = []
        self.cleaned: list[str] = []
        self.cleanup_error: Exception | None = None
        self.build_error: Exception | None = None

    def build(self, *, attempt: dict, item: dict) -> dict:
        if self.build_error is not None:
            raise self.build_error
        artifact_ref = f"artifact:{attempt['attempt_id']}"
        self.built.append(artifact_ref)
        return {
            "artifact_ref": artifact_ref,
            "content_checksum": item["checksum"],
            "index_version": "index-v1",
            "chunking_version": "chunk-v1",
            "embedding_version": "embedding-v1",
            "reranker_version": "reranker-v1",
            "preset_version": "preset-v1",
        }

    def cleanup(self, *, artifact_ref: str) -> None:
        self.cleaned.append(artifact_ref)
        if self.cleanup_error is not None:
            raise self.cleanup_error

    def is_compatible(self, *, artifact: dict, item: dict) -> bool:
        return artifact == {
            "artifact_ref": artifact["artifact_ref"],
            "content_checksum": item["checksum"],
            "index_version": "index-v1",
            "chunking_version": "chunk-v1",
            "embedding_version": "embedding-v1",
            "reranker_version": "reranker-v1",
            "preset_version": "preset-v1",
        }


def test_request_publication_is_durable_and_enqueues_one_attempt(tmp_path):
    database = tmp_path / "knowledge-publication.sqlite3"
    scope = CommercialScope(tenant_id=uuid4(), store_id=uuid4())
    jobs = RecordingPublicationJobs()
    publication = KnowledgePublicationModule(
        store=SQLitePublicationStore(database),
        jobs=jobs,
    )

    draft = publication.create_draft(
        scope=scope,
        category="store_and_hours",
        content_type="knowledge_article",
        title="Breakfast hours",
        content="Breakfast is served until 10:30.",
        actor="admin-a",
    )
    batch = publication.request_publication(
        scope=scope,
        item_ids=[draft["item_id"], "ki_missing"],
        actor="admin-a",
    )

    result = batch["results"][0]
    assert result["status"] == "indexing"
    assert batch["results"][1] == {
        "item_id": "ki_missing",
        "status": "skipped",
        "reason": "knowledge_item_not_found",
    }
    assert jobs.attempt_ids == [result["attempt_id"]]

    reopened = KnowledgePublicationModule(
        store=SQLitePublicationStore(database),
        jobs=RecordingPublicationJobs(),
    )
    item = reopened.get_item(scope=scope, item_id=draft["item_id"])
    attempt = reopened.get_attempt(scope=scope, attempt_id=result["attempt_id"])

    assert item["status"] == "indexing"
    assert attempt["phase"] == "build"
    assert attempt["status"] == "in_progress"
    assert attempt["job_id"] == f"job-{result['attempt_id']}"

    listing = reopened.list_items(scope=scope)
    durable_batch = reopened.get_batch(scope=scope, batch_id=batch["batch_id"])
    assert listing["total"] == 1
    assert listing["items"][0]["item_id"] == draft["item_id"]
    assert durable_batch["results"][0]["attempt_id"] == result["attempt_id"]


def test_in_progress_attempt_can_be_idempotently_reenqueued(tmp_path):
    scope = CommercialScope(tenant_id=uuid4(), store_id=uuid4())
    jobs = RecordingPublicationJobs()
    publication = KnowledgePublicationModule(
        store=SQLitePublicationStore(tmp_path / "knowledge-publication.sqlite3"),
        jobs=jobs,
    )
    draft = publication.create_draft(
        scope=scope,
        category="membership",
        content_type="policy_rule",
        title="Member discount",
        content="Members receive a 9 percent discount.",
        actor="admin-a",
    )
    requested = publication.request_publication(
        scope=scope,
        item_ids=[draft["item_id"]],
        actor="admin-a",
    )
    attempt_id = requested["results"][0]["attempt_id"]

    recovered = publication.ensure_attempt_enqueued(
        scope=scope,
        attempt_id=attempt_id,
        actor="admin-a",
    )

    assert recovered == {
        "attempt_id": attempt_id,
        "status": "indexing",
        "phase": "build",
        "job_id": f"job-{attempt_id}",
    }
    assert jobs.attempt_ids == [attempt_id, attempt_id]


def test_run_attempt_publishes_verified_artifact_atomically(tmp_path):
    database = tmp_path / "knowledge-publication.sqlite3"
    scope = CommercialScope(tenant_id=uuid4(), store_id=uuid4())
    artifacts = ScriptedPublicationArtifacts()
    publication = KnowledgePublicationModule(
        store=SQLitePublicationStore(database),
        jobs=RecordingPublicationJobs(),
        artifacts=artifacts,
    )
    draft = publication.create_draft(
        scope=scope,
        category="payment_and_invoice",
        content_type="policy_rule",
        title="Receipt policy",
        content="Receipts are available at the counter.",
        actor="admin-a",
    )
    attempt_id = publication.request_publication(
        scope=scope,
        item_ids=[draft["item_id"]],
        actor="admin-a",
    )["results"][0]["attempt_id"]

    result = publication.run_attempt(
        scope=scope,
        attempt_id=attempt_id,
        actor="worker",
    )

    assert result == {
        "attempt_id": attempt_id,
        "status": "published",
        "phase": "complete",
        "retryable": False,
    }
    assert publication.get_item(scope=scope, item_id=draft["item_id"])["status"] == "published"
    assert publication.get_published(scope=scope, item_id=draft["item_id"])["artifact_ref"] == f"artifact:{attempt_id}"
    assert publication.get_attempt(scope=scope, attempt_id=attempt_id)["phase"] == "complete"
    assert artifacts.built == [f"artifact:{attempt_id}"]
    assert artifacts.cleaned == []


def test_cleanup_failure_keeps_new_version_published_and_resumes_cleanup(tmp_path):
    database = tmp_path / "knowledge-publication.sqlite3"
    scope = CommercialScope(tenant_id=uuid4(), store_id=uuid4())
    artifacts = ScriptedPublicationArtifacts()
    publication = KnowledgePublicationModule(
        store=SQLitePublicationStore(database),
        jobs=RecordingPublicationJobs(),
        artifacts=artifacts,
    )
    first = publication.create_draft(
        scope=scope,
        category="store_and_hours",
        content_type="knowledge_article",
        title="Hours",
        content="Open until 21:00.",
        actor="admin-a",
    )
    first_attempt = publication.request_publication(
        scope=scope, item_ids=[first["item_id"]], actor="admin-a"
    )["results"][0]["attempt_id"]
    publication.run_attempt(scope=scope, attempt_id=first_attempt, actor="worker")

    second = publication.revise_draft(
        scope=scope,
        item_id=first["item_id"],
        expected_row_revision=publication.get_item(scope=scope, item_id=first["item_id"])["row_revision"],
        category="store_and_hours",
        content_type="knowledge_article",
        title="Hours",
        content="Open until 22:00.",
        actor="admin-b",
    )
    second_attempt = publication.request_publication(
        scope=scope, item_ids=[second["item_id"]], actor="admin-b"
    )["results"][0]["attempt_id"]
    artifacts.cleanup_error = RuntimeError("vector store temporarily unavailable")

    result = publication.run_attempt(scope=scope, attempt_id=second_attempt, actor="worker")

    item = publication.get_item(scope=scope, item_id=first["item_id"])
    assert result["status"] == "published"
    assert result["phase"] == "cleanup"
    assert result["retryable"] is True
    assert item["status"] == "published"
    assert [version["status"] for version in item["versions"]] == ["retired", "published"]
    assert publication.get_published(scope=scope, item_id=first["item_id"])["version"] == 2

    artifacts.cleanup_error = None
    resumed = publication.run_attempt(scope=scope, attempt_id=second_attempt, actor="worker")
    assert resumed["phase"] == "complete"
    assert resumed["retryable"] is False
    assert artifacts.cleaned == [f"artifact:{first_attempt}", f"artifact:{first_attempt}"]


def test_retire_removes_pointer_before_cleanup_and_cleanup_can_resume(tmp_path):
    database = tmp_path / "knowledge-publication.sqlite3"
    scope = CommercialScope(tenant_id=uuid4(), store_id=uuid4())
    artifacts = ScriptedPublicationArtifacts()
    publication = KnowledgePublicationModule(
        store=SQLitePublicationStore(database),
        jobs=RecordingPublicationJobs(),
        artifacts=artifacts,
    )
    draft = publication.create_draft(
        scope=scope,
        category="store_and_hours",
        content_type="knowledge_article",
        title="Hours",
        content="Open until 21:00.",
        actor="admin-a",
    )
    attempt_id = publication.request_publication(
        scope=scope, item_ids=[draft["item_id"]], actor="admin-a"
    )["results"][0]["attempt_id"]
    publication.run_attempt(scope=scope, attempt_id=attempt_id, actor="worker")
    published = publication.get_item(scope=scope, item_id=draft["item_id"])
    artifacts.cleanup_error = RuntimeError("provider unavailable")

    retired = publication.retire(
        scope=scope,
        item_id=draft["item_id"],
        expected_row_revision=published["row_revision"],
        actor="admin-b",
    )

    assert retired["status"] == "retired"
    assert retired["cleanup_status"] == "pending"
    assert publication.published_attempt_ids(scope=scope) == set()
    with pytest.raises(PublicationError) as missing:
        publication.get_published(scope=scope, item_id=draft["item_id"])
    assert missing.value.code == "published_knowledge_not_found"

    artifacts.cleanup_error = None
    resumed = publication.resume_retirement_cleanup(
        scope=scope,
        cleanup_id=retired["cleanup_id"],
        actor="publication-worker",
    )
    assert resumed["cleanup_status"] == "complete"
    assert artifacts.cleaned == [f"artifact:{attempt_id}", f"artifact:{attempt_id}"]


def test_csv_import_validates_all_rows_before_atomic_insert(tmp_path):
    scope = CommercialScope(tenant_id=uuid4(), store_id=uuid4())
    publication = KnowledgePublicationModule(
        store=SQLitePublicationStore(tmp_path / "knowledge-publication.sqlite3"),
        jobs=RecordingPublicationJobs(),
    )
    csv_text = (
        "title,category,content_type,content\n"
        "Hours,store_and_hours,knowledge_article,Open until nine.\n"
        "Broken,custom,knowledge_article,Invalid category.\n"
    )

    with pytest.raises(PublicationError) as error:
        publication.import_csv(scope=scope, csv_text=csv_text, actor="admin-a")

    assert error.value.code == "import_validation_failed"
    assert publication.list_items(scope=scope)["total"] == 0


def test_publication_failed_keeps_old_pointer_and_retry_reuses_verified_artifact(tmp_path):
    database = tmp_path / "knowledge-publication.sqlite3"
    scope = CommercialScope(tenant_id=uuid4(), store_id=uuid4())
    artifacts = ScriptedPublicationArtifacts()
    publication = KnowledgePublicationModule(
        store=SQLitePublicationStore(database),
        jobs=RecordingPublicationJobs(),
        artifacts=artifacts,
    )
    first = publication.create_draft(
        scope=scope,
        category="store_and_hours",
        content_type="knowledge_article",
        title="Hours",
        content="Open until 21:00.",
        actor="admin-a",
    )
    first_attempt = publication.request_publication(
        scope=scope, item_ids=[first["item_id"]], actor="admin-a"
    )["results"][0]["attempt_id"]
    publication.run_attempt(scope=scope, attempt_id=first_attempt, actor="worker")
    second = publication.revise_draft(
        scope=scope,
        item_id=first["item_id"],
        expected_row_revision=publication.get_item(scope=scope, item_id=first["item_id"])["row_revision"],
        category="store_and_hours",
        content_type="knowledge_article",
        title="Hours",
        content="Open until 22:00.",
        actor="admin-b",
    )
    second_attempt = publication.request_publication(
        scope=scope, item_ids=[second["item_id"]], actor="admin-b"
    )["results"][0]["attempt_id"]
    with sqlite3.connect(database) as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_publication_swap
            BEFORE UPDATE ON published_knowledge_pointers
            BEGIN
                SELECT RAISE(ABORT, 'simulated swap failure');
            END
            """
        )

    failed = publication.run_attempt(
        scope=scope, attempt_id=second_attempt, actor="worker"
    )

    assert failed["status"] == "publication_failed"
    assert failed["phase"] == "swap"
    assert publication.get_published(scope=scope, item_id=first["item_id"])["version"] == 1
    assert publication.get_item(scope=scope, item_id=first["item_id"])["status"] == "publication_failed"
    assert len(artifacts.built) == 2

    with sqlite3.connect(database) as conn:
        conn.execute("DROP TRIGGER reject_publication_swap")
    retry_batch = publication.request_publication(
        scope=scope,
        item_ids=[second["item_id"]],
        actor="admin-b",
        retry_failures_only=True,
    )
    resumed = publication.get_attempt(
        scope=scope, attempt_id=retry_batch["results"][0]["attempt_id"]
    )
    assert resumed["attempt_id"] == second_attempt
    assert retry_batch["results"][0]["attempt_id"] == second_attempt
    completed = publication.run_attempt(
        scope=scope, attempt_id=resumed["attempt_id"], actor="worker"
    )

    assert completed["status"] == "published"
    assert publication.get_published(scope=scope, item_id=first["item_id"])["version"] == 2
    assert len(artifacts.built) == 2


def test_transient_build_failure_only_becomes_index_failed_when_budget_is_exhausted(tmp_path):
    scope = CommercialScope(tenant_id=uuid4(), store_id=uuid4())
    artifacts = ScriptedPublicationArtifacts()
    artifacts.build_error = TransientPublicationError("embedding service unavailable")
    publication = KnowledgePublicationModule(
        store=SQLitePublicationStore(tmp_path / "knowledge-publication.sqlite3"),
        jobs=RecordingPublicationJobs(),
        artifacts=artifacts,
    )
    draft = publication.create_draft(
        scope=scope,
        category="menu_and_products",
        content_type="knowledge_article",
        title="Fries",
        content="Fries are available in three sizes.",
        actor="admin-a",
    )
    attempt_id = publication.request_publication(
        scope=scope, item_ids=[draft["item_id"]], actor="admin-a"
    )["results"][0]["attempt_id"]

    retrying = publication.run_attempt(
        scope=scope,
        attempt_id=attempt_id,
        actor="worker",
        retry_budget_exhausted=False,
    )
    assert retrying["status"] == "indexing"
    assert retrying["retryable"] is True
    assert publication.get_item(scope=scope, item_id=draft["item_id"])["status"] == "indexing"

    failed = publication.run_attempt(
        scope=scope,
        attempt_id=attempt_id,
        actor="worker",
        retry_budget_exhausted=True,
    )
    assert failed["status"] == "index_failed"
    assert failed["retryable"] is False
    assert publication.get_attempt(scope=scope, attempt_id=attempt_id)["safe_reason"] == "embedding service unavailable"
