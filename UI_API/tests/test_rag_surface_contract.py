"""The RAG surface P1 keeps, written as something that fails when it changes.

Batch P1 narrows RAG to three flows: Knowledge Item CRUD, one published retrieval
method, and an ad hoc retrieval test. Everything else — pre-pilot evaluation runs,
test-case libraries, bulk import/export, the studio view — goes.

Removing an endpoint has to update this file, which is the point: the reduction
becomes a deliberate edit with a diff rather than something that quietly happens,
and anything added back shows up as an unexpected path.
"""

from routes.v1_routes import create_router

# Knowledge Item CRUD, including the retirement step that makes deletion safe.
KNOWLEDGE_ITEM_PATHS = {
    "/api/v1/rag/knowledge",
    "/api/v1/rag/knowledge/{item_id}",
    "/api/v1/rag/knowledge/{item_id}/retire",
}

# One published retrieval method, plus the pending publish work P1 preserves.
PUBLISHED_RETRIEVAL_PATHS = {
    "/api/v1/rag/knowledge/publish",
    "/api/v1/rag/knowledge/publication-attempts/{attempt_id}/resume",
    "/api/v1/rag/retrieval/configurations",
    "/api/v1/rag/retrieval/configurations/{version}",
}

# The ad hoc retrieval test an operator runs against what is published.
AD_HOC_RETRIEVAL_PATHS = {
    "/api/v1/rag/retrieval/test",
    "/api/v1/rag/retrieval/checks/{check_id}/confirm",
}

RETAINED_PATHS = KNOWLEDGE_ITEM_PATHS | PUBLISHED_RETRIEVAL_PATHS | AD_HOC_RETRIEVAL_PATHS

# Removed in P1. Named rather than merely absent, so re-adding one is a visible
# edit to this list instead of a quiet regrowth of the surface.
RETIRED_PATHS = {
    "/api/v1/rag/studio",
    "/api/v1/rag/knowledge/chunk-preview",
    "/api/v1/rag/knowledge/export",
    "/api/v1/rag/knowledge/import",
    "/api/v1/rag/test-cases",
    "/api/v1/rag/test-cases/import",
    "/api/v1/rag/evaluation-runs",
    "/api/v1/rag/evaluation-runs/{run_id}/cancel",
    "/api/v1/rag/evaluation-runs/{run_id}/export",
    # Reported only which retrieval test cases a deletion would break. With the
    # test-case library gone it could answer nothing but "none affected".
    "/api/v1/rag/knowledge/{item_id}/deletion-impact",
}


def _rag_paths() -> set[str]:
    return {route.path for route in create_router({}).routes if "/rag/" in route.path}


def test_every_rag_path_is_either_retained_or_scheduled_for_removal():
    """A new RAG endpoint must be classified before it ships."""
    unclassified = _rag_paths() - RETAINED_PATHS - RETIRED_PATHS

    assert unclassified == set(), f"RAG paths outside the P1 decision: {sorted(unclassified)}"


def test_the_three_retained_flows_are_present():
    paths = _rag_paths()

    assert KNOWLEDGE_ITEM_PATHS <= paths, sorted(KNOWLEDGE_ITEM_PATHS - paths)
    assert PUBLISHED_RETRIEVAL_PATHS <= paths, sorted(PUBLISHED_RETRIEVAL_PATHS - paths)
    assert AD_HOC_RETRIEVAL_PATHS <= paths, sorted(AD_HOC_RETRIEVAL_PATHS - paths)


def test_the_retired_flows_are_gone():
    """Evaluation runs, test-case libraries, bulk import/export and the studio view."""
    still_present = _rag_paths() & RETIRED_PATHS

    assert still_present == set(), f"RAG paths P1 removed are back: {sorted(still_present)}"


def test_the_surface_is_exactly_the_retained_set():
    assert _rag_paths() == RETAINED_PATHS


def test_retained_and_retired_sets_do_not_overlap():
    assert RETAINED_PATHS & RETIRED_PATHS == set()
