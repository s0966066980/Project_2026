"""PostgreSQL evidence for Knowledge duplicate-document handling."""

import os

import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.knowledge_publication.module import KnowledgePublicationModule, PublicationError
from modules.knowledge_publication.postgres_store import PostgresPublicationStore
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.security]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="knowledge duplicate evidence requires PostgreSQL",
    )
)

ACTOR = "knowledge-duplicate-gate"


class _Jobs:
    def enqueue(self, *, attempt_id: str, scope) -> str:
        return f"job-{attempt_id}"


def _draft(module, *, title: str, content: str, override_near_duplicate: bool = False):
    return module.create_draft(
        scope=LEGACY_DEFAULT_SCOPE,
        category="store_and_hours",
        content_type="question_answer",
        title=title,
        content=content,
        actor=ACTOR,
        override_near_duplicate=override_near_duplicate,
    )


def test_postgres_duplicate_document_policy_requires_explicit_override_and_rejects_exact_match():
    module = KnowledgePublicationModule(store=PostgresPublicationStore(), jobs=_Jobs())
    created = _draft(
        module,
        title="Opening hours",
        content="Question: when do we open?\n\nAnswer: every day from 10:00 to 22:00.",
    )
    created_ids = [created["item_id"]]
    similar = "Question: when do we open?\n\nAnswer: every day from 10:00 to 22:30."

    try:
        with pytest.raises(PublicationError) as near_duplicate:
            _draft(module, title="Opening hours (similar)", content=similar)
        assert near_duplicate.value.args[0] == "near_duplicate"

        allowed = _draft(
            module,
            title="Opening hours (similar)",
            content=similar,
            override_near_duplicate=True,
        )
        created_ids.append(allowed["item_id"])

        with pytest.raises(PublicationError) as exact_duplicate:
            _draft(
                module,
                title="Opening hours (copy)",
                content=similar,
                override_near_duplicate=True,
            )
        assert exact_duplicate.value.args[0] == "exact_duplicate"
    finally:
        for item_id in created_ids:
            item = module.get_item(scope=LEGACY_DEFAULT_SCOPE, item_id=item_id)
            module.delete(
                scope=LEGACY_DEFAULT_SCOPE,
                item_id=item_id,
                expected_row_revision=item["row_revision"],
                actor=ACTOR,
            )
