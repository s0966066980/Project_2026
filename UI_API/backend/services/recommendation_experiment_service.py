"""Deterministic recommendation experiment assignment."""

import hashlib

import config

DEFAULT_EXPERIMENT_ID = "recommendation_strategy_v1"
DEFAULT_VARIANTS = [
    {"variant_id": "control", "strategy": "weighted_random", "traffic": 50},
    {"variant_id": "ranked", "strategy": "ranked_top_score", "traffic": 50},
]


def _safe_text(value, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _safe_int(value, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except Exception:
        return default


def _normalized_variants() -> list[dict]:
    raw_variants = config.get("RECOMMENDATION_EXPERIMENT_VARIANTS", DEFAULT_VARIANTS)
    variants = raw_variants if isinstance(raw_variants, list) else []
    rows = []
    for row in variants:
        if not isinstance(row, dict):
            continue
        variant_id = _safe_text(row.get("variant_id"))
        strategy = _safe_text(row.get("strategy"))
        traffic = _safe_int(row.get("traffic"), 0)
        if not variant_id or not strategy or traffic <= 0:
            continue
        rows.append(
            {
                "variant_id": variant_id,
                "strategy": strategy,
                "traffic": traffic,
            }
        )
    return rows or list(DEFAULT_VARIANTS)


def _bucket(experiment_id: str, session_id: str, total: int) -> int:
    key = f"{experiment_id}:{session_id or 'anonymous'}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % max(1, total)


def assign(session_id: str, experiment_id: str | None = None) -> dict:
    enabled = bool(config.get("RECOMMENDATION_EXPERIMENT_ENABLED", False)) and bool(
        config.get("RECOMMENDATION_EXPERIMENT_CONFIGURED", False)
    )
    normalized_experiment_id = _safe_text(
        experiment_id or config.get("RECOMMENDATION_EXPERIMENT_ID", DEFAULT_EXPERIMENT_ID),
        DEFAULT_EXPERIMENT_ID,
    )
    variants = _normalized_variants()
    if not enabled:
        variant = variants[0]
        return {
            "enabled": False,
            "experiment_id": "",
            "variant_id": "",
            "strategy": variant["strategy"],
        }

    total = sum(_safe_int(row.get("traffic"), 0) for row in variants) or 1
    position = _bucket(normalized_experiment_id, session_id, total)
    cursor = 0
    selected = variants[-1]
    for row in variants:
        cursor += _safe_int(row.get("traffic"), 0)
        if position < cursor:
            selected = row
            break
    return {
        "enabled": True,
        "experiment_id": normalized_experiment_id,
        "variant_id": selected["variant_id"],
        "strategy": selected["strategy"],
    }
