"""Deterministic contracts for Knowledge publication artifact cleanup."""

import pytest

from modules.knowledge_publication.module import TransientPublicationError
from modules.knowledge_publication.runtime import RagPublicationArtifacts

pytestmark = [pytest.mark.unit, pytest.mark.contract]


class _Provider:
    def __init__(self, *, fail_on_add: int | None = None, fail_delete: bool = False):
        self.fail_on_add = fail_on_add
        self.fail_delete = fail_delete
        self.added: list[tuple[str, str, dict]] = []
        self.deleted: list[str] = []

    async def add_document(self, content, *, source_id, source_type, metadata):
        if self.fail_on_add == len(self.added) + 1:
            raise RuntimeError("provider_write_failed")
        self.added.append((source_id, content, metadata))

    async def delete_document(self, document_id):
        if self.fail_delete:
            return False
        self.deleted.append(document_id)
        return True


ATTEMPT = {
    "attempt_id": "attempt-1",
    "tenant_id": "tenant-1",
    "store_id": "store-1",
}
ITEM = {
    "item_id": "item-1",
    "version": 3,
    "category": "store_and_hours",
    "content_type": "question_answer",
    "title": "Opening hours",
    "checksum": "checksum-1",
    "chunks": [
        {"chunk_id": "c1", "content": "We open at ten."},
        {"chunk_id": "c2", "content": "We close at ten."},
    ],
}


def test_build_and_cleanup_round_trip_carries_each_chunk_and_scope_metadata():
    provider = _Provider()
    artifacts = RagPublicationArtifacts(provider=provider)

    artifact = artifacts.build(attempt=ATTEMPT, item=ITEM)

    assert artifact["document_ids"] == ["kp:attempt-1:c1", "kp:attempt-1:c2"]
    assert [row[0] for row in provider.added] == artifact["document_ids"]
    assert all(row[2]["tenant_id"] == "tenant-1" for row in provider.added)
    assert all(row[2]["store_id"] == "store-1" for row in provider.added)
    assert all(row[2]["knowledge_item_id"] == "item-1" for row in provider.added)
    assert artifacts.is_compatible(artifact=artifact, item=ITEM)

    artifacts.cleanup(artifact_ref=artifact["artifact_ref"])

    assert provider.deleted == artifact["document_ids"]


def test_a_partial_build_deletes_already_written_chunks_before_failing():
    provider = _Provider(fail_on_add=2)
    artifacts = RagPublicationArtifacts(provider=provider)

    with pytest.raises(TransientPublicationError):
        artifacts.build(attempt=ATTEMPT, item=ITEM)

    assert provider.deleted == ["kp:attempt-1:c2", "kp:attempt-1:c1"]


def test_a_cleanup_the_provider_refuses_is_not_reported_as_done():
    """Retirement is only complete when the documents are really gone.

    `delete_document` returning False means the index still holds the chunk.
    Swallowing that would mark an item retired while its content stays
    answerable, which is the one outcome retirement exists to prevent.
    """

    artifact = RagPublicationArtifacts(provider=_Provider()).build(attempt=ATTEMPT, item=ITEM)
    provider = _Provider(fail_delete=True)
    artifacts = RagPublicationArtifacts(provider=provider)

    with pytest.raises(TransientPublicationError) as refused:
        artifacts.cleanup(artifact_ref=artifact["artifact_ref"])

    assert "artifact_cleanup_failed" in str(refused.value)
    assert provider.deleted == []


def test_an_artifact_reference_that_is_not_a_document_list_is_refused():
    artifacts = RagPublicationArtifacts(provider=_Provider())

    with pytest.raises(RuntimeError) as refused:
        artifacts.cleanup(artifact_ref="not json at all")

    assert "invalid_publication_artifact_ref" in str(refused.value)
