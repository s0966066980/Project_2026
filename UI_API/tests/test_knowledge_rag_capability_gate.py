"""Knowledge/RAG's gate: answer from the index, or say nothing.

The Module Independence Gate for Knowledge/RAG asks for ingestion, duplicate
documents, index rebuild, a missing index, provider timeout, malicious or
invalid document handling, an empty retrieval result, an unavailable provider,
and one prohibition: **RAG may not write ordering**.

Retrieval is exercised against a fake provider on purpose. The question here is
what this capability does with what a provider returns — drop a weak hit, fall
back, refuse — and a real embedded index would answer a different question
(whether Chroma works) while making the answers non-deterministic.
"""

import ast
import asyncio
import pathlib
import uuid

import pytest

from models.commercial_scope import CommercialScope
from modules.knowledge_publication import _knowledge_service as knowledge
from modules.knowledge_publication._knowledge_service import RagKnowledgeError

pytestmark = [pytest.mark.unit, pytest.mark.contract]

TENANT = uuid.UUID("00000000-0000-4000-8000-000000000001")
STORE = uuid.UUID("00000000-0000-4000-8000-000000000002")
SCOPE = CommercialScope(TENANT, STORE)


class _Provider:
    """A RAG provider that answers exactly what a test tells it to."""

    def __init__(self, *, by_strategy=None, results=None, fail_with=None):
        self.by_strategy = by_strategy or {}
        self.results = results if results is not None else []
        self.fail_with = fail_with
        self.searches: list[dict] = []
        self.documents: list[dict] = []

    async def search(self, query, *, strategy, top_k, tenant_id, store_id):
        self.searches.append(
            {"query": query, "strategy": strategy, "top_k": top_k, "tenant_id": tenant_id, "store_id": store_id}
        )
        if self.fail_with is not None:
            raise self.fail_with
        if strategy in self.by_strategy:
            outcome = self.by_strategy[strategy]
            if isinstance(outcome, Exception):
                raise outcome
            return {"results": outcome}
        return {"results": self.results}

    async def add_document(self, content, *, source_id, source_type, metadata):
        self.documents.append(
            {"content": content, "source_id": source_id, "source_type": source_type, "metadata": metadata}
        )


def _hit(score, *, item_id="know_1", title="Opening hours"):
    return {
        "score": score,
        "content": "We open at ten.",
        "source_type": "knowledge_article",
        "metadata": {"knowledge_item_id": item_id, "title": title, "category": "store", "chunk_id": "c1"},
    }


@pytest.fixture
def provider(monkeypatch):
    """Install a fake provider and skip the read-repair the store would drive."""

    installed = _Provider()
    monkeypatch.setattr(knowledge, "get_rag", lambda: installed)
    monkeypatch.setattr(knowledge, "_published_config", lambda scope: None)

    async def _no_repair(**_kwargs):
        return None

    monkeypatch.setattr(knowledge, "ensure_published_index_visible", _no_repair)
    return installed


def _retrieve(**kwargs):
    return asyncio.run(knowledge.test_retrieval(scope=SCOPE, **kwargs))


# --- what counts as an answer ----------------------------------------------


def test_a_hit_below_the_relevance_threshold_is_not_an_answer(provider):
    """A weak match presented as knowledge is worse than no answer."""

    threshold = knowledge.POLICY_THRESHOLDS["hybrid_rrf"]["balanced"]
    provider.results = [_hit(threshold / 2)]

    answer = _retrieve(query="when do you open")

    assert answer["results"] == []
    assert answer["total"] == 0


def test_a_hit_at_the_threshold_is_kept(provider):
    threshold = knowledge.POLICY_THRESHOLDS["hybrid_rrf"]["balanced"]
    provider.results = [_hit(threshold)]

    answer = _retrieve(query="when do you open")

    assert answer["total"] == 1
    assert answer["results"][0]["rank"] == 1
    assert answer["results"][0]["item_id"] == "know_1"


def test_a_hit_with_no_score_is_dropped_rather_than_ranked_first(provider):
    """An unscored row cannot be compared, so it cannot be trusted."""

    provider.results = [{"content": "unscored", "metadata": {}}, _hit(0.9)]

    answer = _retrieve(query="when do you open")

    assert answer["total"] == 1
    assert answer["results"][0]["content"] == "We open at ten."


def test_a_stricter_policy_admits_less(provider):
    provider.results = [_hit(knowledge.POLICY_THRESHOLDS["hybrid_rrf"]["balanced"])]

    balanced = _retrieve(query="hours", relevance_policy="balanced")
    strict = _retrieve(query="hours", relevance_policy="strict")

    assert balanced["total"] == 1
    assert strict["total"] == 0, "strict admitted a hit that only cleared the balanced bar"


def test_an_empty_index_answers_empty_rather_than_failing(provider):
    provider.results = []

    answer = _retrieve(query="anything")

    assert answer["results"] == []
    assert answer["total"] == 0
    assert answer["expected_hit"] is None


# --- refusals ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"method": "telepathy"}, "invalid_retrieval_method"),
        ({"top_k": 999}, "invalid_top_k"),
        ({"relevance_policy": "whatever"}, "invalid_relevance_policy"),
    ],
)
def test_an_unsupported_request_is_refused_by_name(provider, kwargs, code):
    with pytest.raises(RagKnowledgeError) as refused:
        _retrieve(query="hours", **kwargs)

    assert refused.value.code == code
    assert provider.searches == [], "an invalid request still reached the provider"


# --- degradation ------------------------------------------------------------


def test_a_failing_strategy_falls_back_and_says_that_it_did(provider):
    """Degrading quietly is how a worse answer gets mistaken for a good one."""

    provider.by_strategy = {"hybrid_rrf": TimeoutError("provider timeout"), "bm25": [_hit(0.9)]}

    answer = _retrieve(query="hours", method="hybrid_rrf")

    assert answer["effective_method"] == "bm25"
    assert answer["fallback_used"] == "bm25"
    assert answer["method"] == "hybrid_rrf", "the answer no longer says what was asked for"
    assert answer["total"] == 1


def test_a_caller_that_refuses_fallback_gets_the_failure(provider):
    provider.by_strategy = {"hybrid_rrf": TimeoutError("provider timeout")}

    with pytest.raises(TimeoutError):
        _retrieve(query="hours", method="hybrid_rrf", fallback_enabled=False)

    assert [search["strategy"] for search in provider.searches] == ["hybrid_rrf"]


def test_a_provider_that_is_down_raises_rather_than_inventing_an_answer(provider):
    """Every strategy failed. There is no answer, and none may be fabricated."""

    provider.fail_with = ConnectionError("ollama is unavailable")

    with pytest.raises(ConnectionError):
        _retrieve(query="hours", method="hybrid_reranker")

    assert [search["strategy"] for search in provider.searches] == ["hybrid_reranker", "hybrid_rrf", "bm25"]


def test_retrieval_is_always_asked_for_within_one_store(provider):
    provider.results = [_hit(0.9)]

    _retrieve(query="hours")

    assert provider.searches[0]["tenant_id"] == str(TENANT)
    assert provider.searches[0]["store_id"] == str(STORE)


# --- the published index ----------------------------------------------------


class _Publication:
    """A publication store holding one published item."""

    def __init__(self, *, artifact_ref, chunks, attempt_id="att_1"):
        self.attempt_id = attempt_id
        self.artifact_ref = artifact_ref
        self.chunks = chunks

    def published_attempt_ids(self, *, scope):
        return {self.attempt_id}

    def list_items(self, *, scope):
        return {
            "items": [
                {
                    "item_id": "know_1",
                    "published_version": 3,
                    "content_type": "knowledge_article",
                    "category": "store",
                    "title": "Opening hours",
                    "chunks": self.chunks,
                }
            ]
        }

    def get_published(self, *, scope, item_id):
        return {"attempt_id": self.attempt_id, "artifact_ref": self.artifact_ref}


def _repair(publication, provider):
    knowledge.reset_runtime_index_visibility_for_tests()
    return asyncio.run(
        knowledge.ensure_published_index_visible(scope=SCOPE, publication_module=publication, provider=provider)
    )


def test_a_published_item_reaches_the_query_process_chunk_for_chunk():
    publication = _Publication(
        artifact_ref='["doc_a", "doc_b"]',
        chunks=[{"content": "We open at ten."}, {"content": "We close at nine."}],
    )
    provider = _Provider()

    _repair(publication, provider)

    assert [document["source_id"] for document in provider.documents] == ["doc_a", "doc_b"]
    assert all(document["metadata"]["tenant_id"] == str(TENANT) for document in provider.documents)
    assert all(document["metadata"]["store_id"] == str(STORE) for document in provider.documents)
    assert all(document["metadata"]["publication_attempt_id"] == "att_1" for document in provider.documents)


def test_repairing_the_same_publication_twice_indexes_it_once():
    """Read-repair is per publication token, not per query."""

    publication = _Publication(artifact_ref='["doc_a"]', chunks=[{"content": "We open at ten."}])
    provider = _Provider()

    _repair(publication, provider)
    asyncio.run(
        knowledge.ensure_published_index_visible(scope=SCOPE, publication_module=publication, provider=provider)
    )

    assert len(provider.documents) == 1


@pytest.mark.parametrize(
    "artifact_ref",
    ["not json at all", '{"doc_a": 1}', '["doc_a", "doc_b"]'],
    ids=["unparseable", "not-a-list", "wrong-length"],
)
def test_an_index_that_does_not_match_its_item_is_refused(artifact_ref):
    """A half-published index must not be served as if it were whole.

    The third case is the dangerous one: valid JSON, right shape, one document
    short of the chunks it claims to cover. Indexing it would answer from a
    document that belongs to a different chunk.
    """

    publication = _Publication(artifact_ref=artifact_ref, chunks=[{"content": "only one chunk"}])
    provider = _Provider()

    with pytest.raises(RagKnowledgeError) as refused:
        _repair(publication, provider)

    assert refused.value.code == "published_index_artifact_invalid"
    assert provider.documents == [], "a mismatched index was partially applied"


def test_an_item_that_was_never_published_is_not_indexed():
    """A draft is not knowledge; only the published pointer may reach the index."""

    publication = _Publication(artifact_ref='["doc_a"]', chunks=[{"content": "draft"}])
    publication.list_items = lambda *, scope: {"items": [{"item_id": "know_1", "published_version": None}]}
    provider = _Provider()

    _repair(publication, provider)

    assert provider.documents == []


# --- the prohibition --------------------------------------------------------

BACKEND = pathlib.Path(__file__).resolve().parents[1] / "backend"
KNOWLEDGE_TREES = (
    BACKEND / "modules" / "knowledge_publication",
    BACKEND / "modules" / "retrieval_check",
    BACKEND / "modules" / "retrieval_configuration",
    BACKEND / "capabilities" / "knowledge_rag",
)
ORDERING_ROOTS = {
    "capabilities.ordering",
    "modules.cart",
    "modules.checkout_confirmation",
    "modules.ordering_entry",
    "modules.checkout_confirmation.adapters.orders",
}


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def test_knowledge_never_reaches_into_ordering():
    """RAG may inform an answer; it may not touch a transaction.

    Checked at every nesting depth of the import, so `modules.cart.anything`
    is caught as well as `modules.cart` itself.
    """

    offenders: list[str] = []
    for tree in KNOWLEDGE_TREES:
        for source in tree.rglob("*.py"):
            for imported in _imported_modules(source):
                if any(imported == root or imported.startswith(f"{root}.") for root in ORDERING_ROOTS):
                    offenders.append(f"{source.relative_to(BACKEND)} imports {imported}")

    assert offenders == [], "knowledge reached into ordering: " + "; ".join(offenders)


def test_the_prohibition_is_checked_against_names_that_exist():
    """A guard listing modules nobody has would pass forever.

    Ordering was reorganised once already in this project; a rule naming the
    old layout would have kept passing while checking nothing.
    """

    missing = [
        root
        for root in ORDERING_ROOTS
        if not (BACKEND / pathlib.Path(*root.split("."))).exists()
        and not (BACKEND / pathlib.Path(*root.split("."))).with_suffix(".py").exists()
    ]

    assert missing == [], f"the prohibition names modules that no longer exist: {missing}"
