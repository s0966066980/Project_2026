"""PostgreSQL evidence for Knowledge publication retirement cleanup."""

import os
import uuid

import pytest

from models.commercial_scope import CommercialScope
from modules.knowledge_publication.module import KnowledgePublicationModule
from modules.knowledge_publication.postgres_store import PostgresPublicationStore
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.security]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="knowledge retirement evidence requires PostgreSQL",
    )
)

SCOPE = CommercialScope(
    uuid.UUID("00000000-0000-4000-8000-000000000001"),
    uuid.UUID("00000000-0000-4000-8000-000000000002"),
    uuid.UUID("00000000-0000-4000-8000-000000000003"),
)
ACTOR = "knowledge-retirement-gate"


class _Jobs:
    def enqueue(self, *, attempt_id: str, scope) -> str:
        return f"job-{attempt_id}"


class _Artifacts:
    def __init__(self):
        self.cleaned: list[str] = []

    def build(self, *, attempt: dict, item: dict) -> dict:
        return {
            "artifact_ref": f"artifact://{attempt['attempt_id']}",
            "document_ids": [f"doc:{attempt['attempt_id']}"],
            "content_checksum": item["checksum"],
        }

    def cleanup(self, *, artifact_ref: str) -> None:
        self.cleaned.append(artifact_ref)

    def is_compatible(self, *, artifact: dict, item: dict) -> bool:
        return artifact.get("content_checksum") == item["checksum"]


def test_postgres_retirement_removes_pointer_cleans_artifact_and_records_audit():
    artifacts = _Artifacts()
    module = KnowledgePublicationModule(
        store=PostgresPublicationStore(),
        jobs=_Jobs(),
        artifacts=artifacts,
    )
    created = module.create_draft(
        scope=SCOPE,
        category="store_and_hours",
        content_type="question_answer",
        title=f"Retirement gate {uuid.uuid4()}",
        content=f"Question: retirement gate {uuid.uuid4()}?\n\nAnswer: yes.",
        actor=ACTOR,
    )

    try:
        batch = module.request_publication(scope=SCOPE, item_ids=[created["item_id"]], actor=ACTOR)
        attempt_id = batch["results"][0]["attempt_id"]
        published = module.run_attempt(scope=SCOPE, attempt_id=attempt_id, actor=ACTOR)
        assert published["status"] == "published"

        before_retirement = module.get_item(scope=SCOPE, item_id=created["item_id"])
        retired = module.retire(
            scope=SCOPE,
            item_id=created["item_id"],
            expected_row_revision=before_retirement["row_revision"],
            actor=ACTOR,
        )

        assert retired["cleanup_status"] == "complete"
        assert artifacts.cleaned == [f"artifact://{attempt_id}"]
        after_retirement = module.get_item(scope=SCOPE, item_id=created["item_id"])
        assert after_retirement["published_version"] is None
        assert after_retirement["status"] == "retired"
        assert after_retirement["row_revision"] == before_retirement["row_revision"] + 1

        cleanup = module._store.get_retirement_cleanup(  # noqa: SLF001 - verify persisted PostgreSQL state
            scope=SCOPE,
            cleanup_id=retired["cleanup_id"],
        )
        assert cleanup["status"] == "complete"
        audit_events = [
            event["event_type"]
            for event in module._store.list_audit(  # noqa: SLF001
                scope=SCOPE,
                item_id=created["item_id"],
            )
        ]
        assert audit_events[-3:] == ["published", "retired", "retirement_cleanup_completed"]

        resumed = module.resume_retirement_cleanup(
            scope=SCOPE,
            cleanup_id=retired["cleanup_id"],
            actor=ACTOR,
        )
        assert resumed["cleanup_status"] == "complete"
        assert artifacts.cleaned == [f"artifact://{attempt_id}"]
    finally:
        module._store.purge_item(scope=SCOPE, item_id=created["item_id"])  # noqa: SLF001
