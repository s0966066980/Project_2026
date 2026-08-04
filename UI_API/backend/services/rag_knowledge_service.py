"""Legacy Retrieval Configuration, Test Case, Evaluation and Health service.

Knowledge Version publication is owned by ``modules.knowledge_publication``.
The remaining contexts are migrated independently because their rules differ.
"""

from __future__ import annotations

import csv
import io
import math
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from models.commercial_scope import CommercialScope
from repositories import rag_studio_repository
from services import worker_service
from services.rag_provider import get_rag

CATEGORIES: tuple[dict[str, str], ...] = (
    {"id": "store_and_hours", "label": "門市與營業資訊", "icon": "store"},
    {"id": "menu_and_products", "label": "菜單與商品", "icon": "utensils"},
    {"id": "promotions", "label": "優惠與活動", "icon": "tag"},
    {"id": "payment_and_invoice", "label": "付款與發票", "icon": "receipt"},
    {"id": "membership", "label": "會員與權益", "icon": "user-check"},
    {"id": "order_and_pickup", "label": "訂單與取餐", "icon": "bag-shopping"},
    {"id": "delivery", "label": "外送服務", "icon": "truck"},
    {"id": "nutrition_and_allergens", "label": "營養與過敏原", "icon": "wheat-awn"},
    {"id": "other", "label": "其他", "icon": "folder"},
)
CONTENT_TYPES: tuple[dict[str, str], ...] = (
    {
        "id": "knowledge_article",
        "label": "知識文章",
        "description": "適合說明門市、商品或服務資訊。",
        "template": "主題\n\n請在這裡輸入完整說明，可使用小標題分段。",
    },
    {
        "id": "question_answer",
        "label": "問答",
        "description": "適合一個常見問題與直接答案。",
        "template": "問題：\n\n答案：",
    },
    {
        "id": "policy_rule",
        "label": "政策規則",
        "description": "適合限制、資格與例外條件。",
        "template": "規則名稱\n\n適用條件：\n規則內容：\n例外情況：",
    },
    {
        "id": "operating_procedure",
        "label": "作業流程",
        "description": "適合依序執行的工作步驟。",
        "template": "流程名稱\n\n1. 第一步\n2. 第二步\n3. 第三步",
    },
)
METHODS: tuple[dict[str, Any], ...] = (
    {
        "id": "bm25",
        "label": "BM25 關鍵字",
        "use_case": "品名、代碼、時間與精確字詞",
        "limitation": "不擅長同義詞與口語改寫",
    },
    {
        "id": "dense",
        "label": "Dense 語意向量",
        "use_case": "自然語句、同義詞與口語問法",
        "limitation": "精確代碼或罕見名稱可能較弱",
    },
    {
        "id": "hybrid_rrf",
        "label": "Hybrid RRF",
        "use_case": "兼顧關鍵字與語意的一般門市問答",
        "limitation": "融合排序不會重新理解候選內容",
        "recommended_baseline": True,
    },
    {
        "id": "hybrid_reranker",
        "label": "Hybrid + Reranker",
        "use_case": "高準確度、內容相近的知識集合",
        "limitation": "延遲與運算成本較高",
    },
)
RELEVANCE_POLICIES = ("lenient", "balanced", "strict")
TOP_K_VALUES = (3, 5, 10)
VALID_STATUSES = {"draft", "indexing", "published", "index_failed", "retired"}
BENCHMARK_DEPTH = 10
PRESET_VERSION = "rag-preset-2026.1"
CHUNKING_VERSION = "content-aware-2026.1"
INDEX_VERSION = "shared-multi-method-2026.1"
POLICY_THRESHOLDS = {
    "bm25": {"lenient": 0.05, "balanced": 0.20, "strict": 0.50},
    "dense": {"lenient": 0.30, "balanced": 0.45, "strict": 0.60},
    # A first-place hit from one healthy retrieval channel scores 1 / 61.
    # Balanced must retain that result; strict continues to require stronger
    # (typically multi-channel) agreement.
    "hybrid_rrf": {"lenient": 0.012, "balanced": 0.016, "strict": 0.025},
    # Production calibration keeps a natural-language paraphrase that scores
    # about 0.32 while lenient still rejects unrelated single-document hits.
    "hybrid_reranker": {"lenient": 0.20, "balanced": 0.30, "strict": 0.50},
}


class RagKnowledgeError(ValueError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


class RagKnowledgeConflictError(RagKnowledgeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope_ids(scope: CommercialScope) -> tuple[UUID, UUID]:
    if scope.store_id is None:
        raise RagKnowledgeError("store_scope_required")
    return scope.tenant_id, scope.store_id


def _load(scope: CommercialScope) -> dict[str, Any]:
    tenant_id, store_id = _scope_ids(scope)
    return rag_studio_repository.load_state(tenant_id=tenant_id, store_id=store_id)


def _save(scope: CommercialScope, state: dict[str, Any], revision: int) -> dict[str, Any]:
    tenant_id, store_id = _scope_ids(scope)
    try:
        return rag_studio_repository.save_state(
            state,
            tenant_id=tenant_id,
            store_id=store_id,
            expected_revision=revision,
        )
    except rag_studio_repository.RagStudioConflictError as exc:
        raise RagKnowledgeConflictError("stale_state") from exc


def _valid_id(value: str, choices: tuple[dict[str, Any], ...], code: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in {str(row["id"]) for row in choices}:
        raise RagKnowledgeError(code)
    return normalized


def _published_version(item: dict[str, Any]) -> dict[str, Any] | None:
    version_number = item.get("published_version")
    return next(
        (
            row
            for row in item.get("versions") or []
            if int(row.get("version") or 0) == int(version_number or 0)
            and row.get("status") == "published"
        ),
        None,
    )




def _find_item(state: dict[str, Any], item_id: str) -> dict[str, Any]:
    item = next((row for row in state["items"] if row.get("item_id") == item_id), None)
    if not item:
        raise RagKnowledgeError("knowledge_item_not_found")
    return item




def metadata() -> dict[str, Any]:
    return {
        "categories": list(CATEGORIES),
        "content_types": list(CONTENT_TYPES),
        "methods": list(METHODS),
        "top_k_values": list(TOP_K_VALUES),
        "relevance_policies": list(RELEVANCE_POLICIES),
        "preset_version": PRESET_VERSION,
        "chunking_version": CHUNKING_VERSION,
        "index_version": INDEX_VERSION,
        "benchmark": {
            "depth": BENCHMARK_DEPTH,
            "policy": "balanced",
            "metrics": [
                "hit_rate_at_1",
                "hit_rate_at_3",
                "hit_rate_at_5",
                "mrr_at_5",
                "p95_latency_ms",
                "average_latency_ms",
                "zero_result_rate",
                "error_rate",
            ],
        },
    }




def list_configurations(scope: CommercialScope) -> dict[str, Any]:
    state = _load(scope)
    rows = list(reversed(state["configurations"]))
    published = next((row for row in rows if row.get("status") == "published"), None)
    return {"configurations": rows, "published": published}


def delete_configuration(
    *,
    scope: CommercialScope,
    version: int,
    actor: str,
) -> dict[str, Any]:
    state = _load(scope)
    revision = int(state["revision"])
    target = next(
        (
            row
            for row in state["configurations"]
            if int(row["version"]) == int(version)
        ),
        None,
    )
    if target is None:
        raise RagKnowledgeError("configuration_not_found")
    was_published = target.get("status") == "published"
    state["configurations"] = [
        row
        for row in state["configurations"]
        if int(row["version"]) != int(version)
    ]
    _save(scope, state, revision)
    return {
        "deleted_version": int(version),
        "was_published": was_published,
        "deleted_by": actor,
        "deleted_at": _now(),
    }


def publish_configuration(
    *,
    scope: CommercialScope,
    method: str,
    top_k: int,
    relevance_policy: str,
    actor: str,
    source_version: int | None = None,
) -> dict[str, Any]:
    state = _load(scope)
    revision = int(state["revision"])
    method = _valid_id(method, METHODS, "invalid_retrieval_method")
    if int(top_k) not in TOP_K_VALUES:
        raise RagKnowledgeError("invalid_top_k")
    if relevance_policy not in RELEVANCE_POLICIES:
        raise RagKnowledgeError("invalid_relevance_policy")
    if source_version is not None:
        source = next(
            (
                row
                for row in state["configurations"]
                if int(row["version"]) == int(source_version)
            ),
            None,
        )
        if not source:
            raise RagKnowledgeError("configuration_not_found")
        method = source["method"]
        top_k = int(source["top_k"])
        relevance_policy = source["relevance_policy"]
    for row in state["configurations"]:
        if row.get("status") == "published":
            row["status"] = "superseded"
    next_version = max(
        int(state.get("configuration_version_sequence") or 0),
        max(
            (int(existing["version"]) for existing in state["configurations"]),
            default=0,
        ),
    ) + 1
    state["configuration_version_sequence"] = next_version
    row = {
        "version": next_version,
        "status": "published",
        "method": method,
        "top_k": int(top_k),
        "relevance_policy": relevance_policy,
        "preset_version": PRESET_VERSION,
        "index_version": INDEX_VERSION,
        "published_at": _now(),
        "published_by": actor,
        "restored_from_version": source_version,
    }
    state["configurations"].append(row)
    _save(scope, state, revision)
    return row


def _published_config(state: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in reversed(state["configurations"])
            if row.get("status") == "published"
        ),
        None,
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(float(ordered[index]), 2)


def _filter_retrieval_rows(
    result: dict[str, Any],
    *,
    method: str,
    policy: str,
) -> tuple[list[dict[str, Any]], float]:
    """Apply the selected method's score scale before deciding on fallback."""
    threshold = POLICY_THRESHOLDS[method][policy]
    rows: list[dict[str, Any]] = []
    for hit in result.get("results") or []:
        score = hit.get("score")
        try:
            if score is None or float(score) < threshold:
                continue
        except (TypeError, ValueError):
            continue
        metadata = dict(hit.get("metadata") or {})
        rows.append(
            {
                **hit,
                "rank": len(rows) + 1,
                "item_id": metadata.get("knowledge_item_id", ""),
                "title": metadata.get("title", ""),
                "category": metadata.get("category", ""),
                "content_type": metadata.get("content_type", hit.get("source_type", "")),
                "chunk_id": metadata.get("chunk_id", ""),
            }
        )
    return rows, threshold


async def test_retrieval(
    *,
    scope: CommercialScope,
    query: str,
    method: str | None = None,
    top_k: int | None = None,
    relevance_policy: str | None = None,
    expected_knowledge_ids: list[str] | None = None,
    fallback_enabled: bool = True,
    record_online_health: bool = False,
) -> dict[str, Any]:
    state = _load(scope)
    config = _published_config(state) or {
        "method": "hybrid_rrf",
        "top_k": 5,
        "relevance_policy": "balanced",
        "version": None,
    }
    selected_method = _valid_id(method or config["method"], METHODS, "invalid_retrieval_method")
    selected_k = int(top_k or config["top_k"])
    if selected_k not in TOP_K_VALUES:
        raise RagKnowledgeError("invalid_top_k")
    policy = relevance_policy or config["relevance_policy"]
    if policy not in RELEVANCE_POLICIES:
        raise RagKnowledgeError("invalid_relevance_policy")
    tenant_id, store_id = _scope_ids(scope)
    started = time.perf_counter()
    fallback_used = ""
    chains = {
        "bm25": ["bm25"],
        "dense": ["dense", "bm25"],
        "hybrid_rrf": ["hybrid_rrf", "bm25"],
        "hybrid_reranker": ["hybrid_reranker", "hybrid_rrf", "bm25"],
    }
    attempts = chains[selected_method] if fallback_enabled else [selected_method]
    last_error: Exception | None = None
    result = None
    rows: list[dict[str, Any]] = []
    threshold = POLICY_THRESHOLDS[selected_method][policy]
    effective_method = selected_method
    for attempt in attempts:
        try:
            candidate = await get_rag().search(
                str(query or "").strip(),
                strategy=attempt,
                top_k=selected_k,
                tenant_id=str(tenant_id),
                store_id=str(store_id),
            )
            candidate_rows, candidate_threshold = _filter_retrieval_rows(
                candidate,
                method=attempt,
                policy=policy,
            )
            result = candidate
            rows = candidate_rows
            threshold = candidate_threshold
            if attempt != selected_method:
                fallback_used = attempt
            effective_method = attempt
            if rows or attempt == attempts[-1]:
                break
        except Exception as exc:
            last_error = exc
    if result is None:
        raise last_error or RagKnowledgeError("retrieval_unavailable")
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    expected = set(expected_knowledge_ids or [])
    ranks = [
        int(row["rank"]) for row in rows if row.get("item_id") in expected
    ]
    hit_rate = None if not expected else bool(ranks)
    revision = int(state["revision"])
    health = state["online_health"]
    if record_online_health:
        health["query_count"] += 1
        health["zero_result_count"] += int(not rows)
        health["latencies_ms"] = (health["latencies_ms"] + [latency_ms])[-500:]
        health["fallback_count"] += int(bool(fallback_used))
    if record_online_health:
        _save(scope, state, revision)
    return {
        "method": selected_method,
        "effective_method": effective_method,
        "top_k": selected_k,
        "relevance_policy": policy,
        "relevance_threshold": threshold,
        "fallback_used": fallback_used,
        "latency_ms": latency_ms,
        "results": rows,
        "total": len(rows),
        "expected_hit": hit_rate,
        "expected_rank": min(ranks) if ranks else None,
    }


def list_test_cases(scope: CommercialScope) -> dict[str, Any]:
    state = _load(scope)
    rows = []
    for test_case in state["test_cases"]:
        latest = test_case["revisions"][-1]
        expected_items = [
            _find_item(state, item_id)
            for item_id in latest["expected_knowledge_ids"]
            if any(row.get("item_id") == item_id for row in state["items"])
        ]
        valid = bool(expected_items) and all(
            _published_version(item) is not None for item in expected_items
        )
        categories = {item["category"] for item in expected_items}
        valid = valid and len(categories) == 1
        rows.append(
            {
                "test_case_id": test_case["test_case_id"],
                **latest,
                "valid": valid,
                "category": next(iter(categories), ""),
            }
        )
    return {"test_cases": rows, "total": len(rows)}


def save_test_case(
    *,
    scope: CommercialScope,
    question: str,
    expected_knowledge_ids: list[str],
    enabled: bool,
    actor: str,
    test_case_id: str = "",
) -> dict[str, Any]:
    state = _load(scope)
    revision = int(state["revision"])
    question = str(question or "").strip()
    if not question:
        raise RagKnowledgeError("question_required")
    expected = list(dict.fromkeys(str(row).strip() for row in expected_knowledge_ids if str(row).strip()))
    if not expected:
        raise RagKnowledgeError("expected_knowledge_required")
    items = [_find_item(state, item_id) for item_id in expected]
    if any(_published_version(item) is None for item in items):
        raise RagKnowledgeError("expected_knowledge_must_be_published")
    if len({item["category"] for item in items}) != 1:
        raise RagKnowledgeError("expected_knowledge_must_share_category")
    now = _now()
    test_case = next(
        (row for row in state["test_cases"] if row["test_case_id"] == test_case_id),
        None,
    )
    if not test_case:
        test_case = {"test_case_id": f"rtc_{uuid4().hex}", "revisions": []}
        state["test_cases"].append(test_case)
    row = {
        "revision": len(test_case["revisions"]) + 1,
        "question": question,
        "expected_knowledge_ids": expected,
        "enabled": bool(enabled),
        "created_at": now,
        "created_by": actor,
    }
    test_case["revisions"].append(row)
    _save(scope, state, revision)
    return {"test_case_id": test_case["test_case_id"], **row, "valid": True}


def import_test_cases_csv(*, scope: CommercialScope, csv_text: str, actor: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(str(csv_text or "")))
    required = {"question", "expected_knowledge_ids", "enabled"}
    if set(reader.fieldnames or []) != required:
        raise RagKnowledgeError("invalid_test_import_columns", details={"required": sorted(required)})
    staged = []
    errors = []
    state = _load(scope)
    for line, row in enumerate(reader, start=2):
        try:
            expected = [value.strip() for value in str(row.get("expected_knowledge_ids") or "").split("|") if value.strip()]
            items = [_find_item(state, item_id) for item_id in expected]
            if not items or any(_published_version(item) is None for item in items):
                raise RagKnowledgeError("expected_knowledge_must_be_published")
            if len({item["category"] for item in items}) != 1:
                raise RagKnowledgeError("expected_knowledge_must_share_category")
            enabled_text = str(row.get("enabled") or "").strip().lower()
            if enabled_text not in {"true", "false", "1", "0"}:
                raise RagKnowledgeError("invalid_enabled")
            staged.append(
                {
                    "question": str(row.get("question") or ""),
                    "expected_knowledge_ids": expected,
                    "enabled": enabled_text in {"true", "1"},
                }
            )
        except RagKnowledgeError as exc:
            errors.append({"line": line, "code": exc.code})
    if errors:
        raise RagKnowledgeError("test_import_validation_failed", details={"errors": errors})
    revision = int(state["revision"])
    created = []
    for staged_row in staged:
        now = _now()
        row = {
            "revision": 1,
            "question": staged_row["question"].strip(),
            "expected_knowledge_ids": staged_row["expected_knowledge_ids"],
            "enabled": staged_row["enabled"],
            "created_at": now,
            "created_by": actor,
        }
        test_case = {"test_case_id": f"rtc_{uuid4().hex}", "revisions": [row]}
        state["test_cases"].append(test_case)
        created.append({"test_case_id": test_case["test_case_id"], **row, "valid": True})
    _save(scope, state, revision)
    return {"created": created, "count": len(created)}


def start_evaluation(scope: CommercialScope, *, actor: str) -> dict[str, Any]:
    state = _load(scope)
    revision = int(state["revision"])
    cases = [
        row
        for row in list_test_cases(scope)["test_cases"]
        if row["enabled"] and row["valid"]
    ]
    run_id = f"rer_{uuid4().hex}"
    run = {
        "run_id": run_id,
        "status": "pending",
        "progress": 0,
        "created_at": _now(),
        "created_by": actor,
        "index_version": INDEX_VERSION,
        "preset_version": PRESET_VERSION,
        "methods": [row["id"] for row in METHODS],
        "test_case_snapshot": cases,
        "results": [],
        "recommendation": None,
    }
    state["evaluation_runs"].append(run)
    _save(scope, state, revision)
    tenant_id, store_id = _scope_ids(scope)
    job = worker_service.enqueue_job(
        tenant_id=tenant_id,
        store_id=store_id,
        job_type="rag.studio.evaluate",
        payload_ref={"run_id": run_id, "actor": actor},
        idempotency_key=f"rag-studio-evaluate:{store_id}:{run_id}",
        max_attempts=1,
        visibility_timeout_seconds=600,
    )
    current = _load(scope)
    persisted = next(row for row in current["evaluation_runs"] if row["run_id"] == run_id)
    persisted["job_id"] = str(job.job_id)
    _save(scope, current, int(current["revision"]))
    return persisted


def cancel_evaluation(scope: CommercialScope, *, run_id: str, actor: str) -> dict[str, Any]:
    state = _load(scope)
    run = next((row for row in state["evaluation_runs"] if row["run_id"] == run_id), None)
    if not run:
        raise RagKnowledgeError("evaluation_run_not_found")
    if run["status"] in {"succeeded", "failed", "cancelled"}:
        return run
    job_id = str(run.get("job_id") or "")
    if job_id:
        worker_service.cancel_job(UUID(job_id))
    run.update({"status": "cancelled", "cancelled_at": _now(), "cancelled_by": actor})
    _save(scope, state, int(state["revision"]))
    return run


def fail_evaluation(
    *, tenant_id: UUID, store_id: UUID, run_id: str, reason: str
) -> None:
    scope = CommercialScope(tenant_id=tenant_id, store_id=store_id)
    state = _load(scope)
    run = next((row for row in state["evaluation_runs"] if row["run_id"] == run_id), None)
    if not run:
        return
    run.update(
        {
            "status": "failed",
            "finished_at": _now(),
            "safe_error": str(reason or "")[:300],
        }
    )
    _save(scope, state, int(state["revision"]))


async def execute_evaluation_job(
    *, tenant_id: UUID, store_id: UUID, run_id: str
) -> dict[str, Any]:
    scope = CommercialScope(tenant_id=tenant_id, store_id=store_id)
    state = _load(scope)
    run = next((row for row in state["evaluation_runs"] if row["run_id"] == run_id), None)
    if not run:
        raise RagKnowledgeError("evaluation_run_not_found")
    run["status"] = "running"
    _save(scope, state, int(state["revision"]))
    cases = run["test_case_snapshot"]
    method_results = []
    for method_index, method in enumerate(run["methods"]):
        per_case = []
        for case in cases:
            try:
                result = await test_retrieval(
                    scope=scope,
                    query=case["question"],
                    method=method,
                    top_k=10,
                    relevance_policy="balanced",
                    expected_knowledge_ids=case["expected_knowledge_ids"],
                    fallback_enabled=False,
                )
                per_case.append(
                    {
                        "test_case_id": case["test_case_id"],
                        "hit": bool(result["expected_hit"]),
                        "rank": result["expected_rank"],
                        "latency_ms": result["latency_ms"],
                        "zero_result": result["total"] == 0,
                        "error": False,
                    }
                )
            except Exception:
                per_case.append(
                    {
                        "test_case_id": case["test_case_id"],
                        "hit": False,
                        "rank": None,
                        "latency_ms": 0,
                        "zero_result": True,
                        "error": True,
                    }
                )
        total = len(per_case)
        latencies = [row["latency_ms"] for row in per_case if not row["error"]]
        metrics = {
            "hit_rate_at_1": round(sum(row["rank"] == 1 for row in per_case) / total, 4) if total else 0,
            "hit_rate_at_3": round(sum(bool(row["rank"]) and row["rank"] <= 3 for row in per_case) / total, 4) if total else 0,
            "hit_rate_at_5": round(sum(bool(row["rank"]) and row["rank"] <= 5 for row in per_case) / total, 4) if total else 0,
            "mrr_at_5": round(sum((1 / row["rank"]) if row["rank"] and row["rank"] <= 5 else 0 for row in per_case) / total, 4) if total else 0,
            "p95_latency_ms": _percentile(latencies, 0.95),
            "average_latency_ms": round(statistics.fmean(latencies), 2) if latencies else 0,
            "zero_result_rate": round(sum(row["zero_result"] for row in per_case) / total, 4) if total else 0,
            "error_rate": round(sum(row["error"] for row in per_case) / total, 4) if total else 0,
        }
        method_results.append({"method": method, "metrics": metrics, "cases": per_case})
        current = _load(scope)
        current_run = next(row for row in current["evaluation_runs"] if row["run_id"] == run_id)
        current_run["progress"] = round(((method_index + 1) / len(run["methods"])) * 100)
        _save(scope, current, int(current["revision"]))
    categories = Counter(row.get("category") for row in cases)
    ready = (
        len(cases) >= 20
        and len(categories) >= 3
        and (max(categories.values(), default=0) / len(cases) <= 0.5 if cases else False)
    )
    ranked = sorted(
        method_results,
        key=lambda row: (
            -row["metrics"]["hit_rate_at_3"],
            -row["metrics"]["mrr_at_5"],
            row["metrics"]["p95_latency_ms"],
        ),
    )
    recommendations: list[str] = []
    if ready and ranked:
        best = ranked[0]["metrics"]
        best_key = (
            best["hit_rate_at_3"],
            best["mrr_at_5"],
            best["p95_latency_ms"],
        )
        recommendations = [
            row["method"]
            for row in ranked
            if (
                row["metrics"]["hit_rate_at_3"],
                row["metrics"]["mrr_at_5"],
                row["metrics"]["p95_latency_ms"],
            )
            == best_key
        ]
    recommendation = recommendations[0] if len(recommendations) == 1 else None
    current = _load(scope)
    current_run = next(row for row in current["evaluation_runs"] if row["run_id"] == run_id)
    current_run.update(
        {
            "status": "succeeded",
            "progress": 100,
            "finished_at": _now(),
            "results": method_results,
            "evaluation_ready": ready,
            "readiness": {
                "valid_cases": len(cases),
                "categories": len(categories),
                "largest_category_share": round(max(categories.values(), default=0) / len(cases), 4) if cases else 0,
            },
            "recommendation": recommendation,
            "recommendations": recommendations,
            "recommendation_tied": len(recommendations) > 1,
        }
    )
    _save(scope, current, int(current["revision"]))
    return current_run


def list_evaluation_runs(scope: CommercialScope) -> dict[str, Any]:
    state = _load(scope)
    return {"evaluation_runs": list(reversed(state["evaluation_runs"]))}


def export_evaluation_csv(scope: CommercialScope, *, run_id: str) -> str:
    state = _load(scope)
    run = next((row for row in state["evaluation_runs"] if row["run_id"] == run_id), None)
    if not run:
        raise RagKnowledgeError("evaluation_run_not_found")
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "row_type",
            "run_id",
            "method",
            "test_case_id",
            "hit",
            "rank",
            "latency_ms",
            "hit_rate_at_1",
            "hit_rate_at_3",
            "hit_rate_at_5",
            "mrr_at_5",
            "p95_latency_ms",
            "average_latency_ms",
            "zero_result_rate",
            "error_rate",
            "index_version",
            "preset_version",
        ],
    )
    writer.writeheader()
    for result in run.get("results") or []:
        metrics = result.get("metrics") or {}
        writer.writerow(
            {
                "row_type": "aggregate",
                "run_id": run_id,
                "method": result["method"],
                **metrics,
                "index_version": run.get("index_version", ""),
                "preset_version": run.get("preset_version", ""),
            }
        )
        for case in result.get("cases") or []:
            writer.writerow(
                {
                    "row_type": "case",
                    "run_id": run_id,
                    "method": result["method"],
                    "test_case_id": case["test_case_id"],
                    "hit": case["hit"],
                    "rank": case["rank"] or "",
                    "latency_ms": case["latency_ms"],
                    "index_version": run.get("index_version", ""),
                    "preset_version": run.get("preset_version", ""),
                }
            )
    return output.getvalue()


def dashboard(scope: CommercialScope) -> dict[str, Any]:
    state = _load(scope)
    published_items = sum(_published_version(item) is not None for item in state["items"])
    config = _published_config(state)
    index_healthy = state.get("index_health") == "healthy"
    readiness_checks = [
        {"id": "knowledge", "label": "至少一筆已發布知識", "complete": published_items > 0},
        {"id": "configuration", "label": "已發布檢索設定", "complete": config is not None},
        {"id": "index", "label": "索引健康", "complete": index_healthy and published_items > 0},
        {"id": "test", "label": "已確認目前正式檢索結果", "complete": False},
    ]
    health = state["online_health"]
    query_count = int(health["query_count"])
    latencies = [float(value) for value in health["latencies_ms"]]
    return {
        "readiness": {
            "ready": all(row["complete"] for row in readiness_checks),
            "completed": sum(row["complete"] for row in readiness_checks),
            "total": len(readiness_checks),
            "checks": readiness_checks,
        },
        "published_method": config["method"] if config else None,
        "published_configuration_version": config["version"] if config else None,
        "index_health": state.get("index_health", "empty"),
        "published_items": published_items,
        "online_health": {
            "query_count": query_count,
            "zero_result_rate": round(health["zero_result_count"] / query_count, 4) if query_count else 0,
            "p95_latency_ms": _percentile(latencies, 0.95),
            "error_rate": round(health["error_count"] / query_count, 4) if query_count else 0,
            "fallback_count": health["fallback_count"],
            "published_configuration_version": config["version"] if config else None,
        },
        "recent_jobs": [
            {
                "run_id": row["run_id"],
                "status": row["status"],
                "progress": row["progress"],
                "created_at": row["created_at"],
            }
            for row in list(reversed(state["evaluation_runs"]))[:5]
        ],
    }
