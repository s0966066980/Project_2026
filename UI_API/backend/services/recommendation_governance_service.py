"""Govern recommendation/promotion strategies, experiments, and event quality."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import config
from models.recommendation_governance import (
    ExperimentAssignment,
    RecommendationEventRecord,
    StrategyStatus,
    StrategyVersion,
)


class RecommendationGovernanceError(ValueError):
    """Invalid strategy, experiment, or event contract."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "recommendation_strategies.json"


def _events_path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "recommendation_governance_events.json"


def _load_json(path: Path, default: list) -> list:
    if not path.exists():
        return list(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(default)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("items") or data.get("events") or data.get("strategies") or [])
    return list(default)


def _save_json(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _to_strategy(row: dict[str, Any]) -> StrategyVersion:
    return StrategyVersion(
        strategy_id=str(row["strategy_id"]),
        version=int(row["version"]),
        status=StrategyStatus(str(row["status"])),
        scope_tenant_id=UUID(row["scope_tenant_id"]) if row.get("scope_tenant_id") else None,
        scope_store_id=UUID(row["scope_store_id"]) if row.get("scope_store_id") else None,
        eligibility=dict(row.get("eligibility") or {}),
        ranking_config=dict(row.get("ranking_config") or {}),
        effective_from=str(row.get("effective_from") or ""),
        effective_to=str(row.get("effective_to") or ""),
        created_at=str(row.get("created_at") or ""),
        reviewed_at=str(row.get("reviewed_at") or ""),
        published_at=str(row.get("published_at") or ""),
        history=list(row.get("history") or []),
    )


def create_strategy_draft(
    *,
    strategy_id: str,
    eligibility: dict[str, Any],
    ranking_config: dict[str, Any],
    tenant_id: UUID | None = None,
    store_id: UUID | None = None,
    effective_from: str = "",
    effective_to: str = "",
    actor: str = "system",
) -> StrategyVersion:
    rows = _load_json(_path(), [])
    sid = str(strategy_id or "").strip() or f"strategy-{uuid4().hex[:8]}"
    versions = [int(r.get("version") or 0) for r in rows if r.get("strategy_id") == sid]
    version = max(versions, default=0) + 1
    row = {
        "strategy_id": sid,
        "version": version,
        "status": StrategyStatus.DRAFT.value,
        "scope_tenant_id": str(tenant_id) if tenant_id else None,
        "scope_store_id": str(store_id) if store_id else None,
        "eligibility": dict(eligibility or {}),
        "ranking_config": dict(ranking_config or {}),
        "effective_from": effective_from,
        "effective_to": effective_to,
        "created_at": _now(),
        "reviewed_at": "",
        "published_at": "",
        "history": [{"event": "created", "actor": actor, "at": _now()}],
    }
    rows.append(row)
    _save_json(_path(), rows)
    return _to_strategy(row)


def submit_strategy(strategy_id: str, version: int, *, actor: str = "system") -> StrategyVersion:
    return _set_status(strategy_id, version, StrategyStatus.REVIEW, actor=actor, event="submitted", reviewed=True)


def publish_strategy(strategy_id: str, version: int, *, actor: str = "system") -> StrategyVersion:
    rows = _load_json(_path(), [])
    target = None
    for row in rows:
        if row.get("strategy_id") == strategy_id and int(row.get("version") or 0) == int(version):
            target = row
            break
    if target is None:
        raise RecommendationGovernanceError("strategy_not_found")
    if target.get("status") not in {
        StrategyStatus.REVIEW.value,
        StrategyStatus.DRAFT.value,
        StrategyStatus.PAUSED.value,
    }:
        raise RecommendationGovernanceError("invalid_publish_status")
    now = _now()
    for row in rows:
        if (
            row.get("strategy_id") == strategy_id
            and row.get("status") == StrategyStatus.PUBLISHED.value
            and int(row.get("version") or 0) != int(version)
        ):
            row["status"] = StrategyStatus.RETIRED.value
            history = list(row.get("history") or [])
            history.append({"event": "superseded", "actor": actor, "at": now})
            row["history"] = history
    target["status"] = StrategyStatus.PUBLISHED.value
    target["published_at"] = now
    history = list(target.get("history") or [])
    history.append({"event": "published", "actor": actor, "at": now})
    target["history"] = history
    _save_json(_path(), rows)
    return _to_strategy(target)


def pause_strategy(strategy_id: str, version: int, *, actor: str = "system") -> StrategyVersion:
    return _set_status(strategy_id, version, StrategyStatus.PAUSED, actor=actor, event="paused")


def rollback_strategy(strategy_id: str, to_version: int, *, actor: str = "system") -> StrategyVersion:
    rows = _load_json(_path(), [])
    target = None
    for row in rows:
        if row.get("strategy_id") == strategy_id and int(row.get("version") or 0) == int(to_version):
            target = row
            break
    if target is None:
        raise RecommendationGovernanceError("rollback_target_missing")
    if target.get("status") not in {
        StrategyStatus.PUBLISHED.value,
        StrategyStatus.RETIRED.value,
        StrategyStatus.PAUSED.value,
    }:
        raise RecommendationGovernanceError("rollback_target_invalid")
    now = _now()
    for row in rows:
        if row.get("strategy_id") == strategy_id and row.get("status") == StrategyStatus.PUBLISHED.value:
            row["status"] = StrategyStatus.RETIRED.value
            history = list(row.get("history") or [])
            history.append({"event": "retired_for_rollback", "actor": actor, "at": now})
            row["history"] = history
    target["status"] = StrategyStatus.PUBLISHED.value
    target["published_at"] = now
    history = list(target.get("history") or [])
    history.append({"event": "rollback_publish", "actor": actor, "at": now})
    target["history"] = history
    _save_json(_path(), rows)
    return _to_strategy(target)


def is_eligible(
    strategy: StrategyVersion,
    *,
    tenant_id: UUID | None,
    store_id: UUID | None,
    now: datetime | None = None,
    timezone_name: str = "Asia/Taipei",
) -> bool:
    if strategy.status is not StrategyStatus.PUBLISHED:
        return False
    if strategy.scope_tenant_id and tenant_id and strategy.scope_tenant_id != tenant_id:
        return False
    if strategy.scope_store_id and store_id and strategy.scope_store_id != store_id:
        return False
    clock = now or datetime.now(ZoneInfo(timezone_name))
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=ZoneInfo(timezone_name))
    eligibility = strategy.eligibility or {}
    days = eligibility.get("days_of_week")
    if isinstance(days, list) and days:
        # Monday=0 ... Sunday=6
        if clock.weekday() not in {int(day) for day in days}:
            return False
    start = strategy.effective_from
    end = strategy.effective_to
    if start:
        start_dt = datetime.fromisoformat(start)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if clock < start_dt:
            return False
    if end:
        end_dt = datetime.fromisoformat(end)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        if clock > end_dt:
            return False
    return True


def assign_experiment_variant(
    *,
    experiment_id: str,
    assignment_key: str,
    variants: list[str],
    tenant_id: UUID | None = None,
    store_id: UUID | None = None,
    strategy_version: int | None = None,
) -> ExperimentAssignment:
    if not variants:
        raise RecommendationGovernanceError("variants_required")
    # Durable assignment: once a session is assigned, keep the same variant.
    durable_path = Path(config.LEARNING_DATA_DIR) / "recommendation_assignments.json"
    assignments = _load_json(durable_path, [])
    for row in assignments:
        if row.get("experiment_id") == experiment_id and row.get("session_ref") == assignment_key:
            return ExperimentAssignment(
                experiment_id=experiment_id,
                variant=str(row.get("variant_id") or variants[0]),
                assignment_key=assignment_key,
                deterministic=True,
            )
    key = f"{experiment_id}:{assignment_key}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(variants)
    assignment = ExperimentAssignment(
        experiment_id=experiment_id,
        variant=str(variants[index]),
        assignment_key=assignment_key,
        deterministic=True,
    )
    assignments.append(
        {
            "experiment_id": experiment_id,
            "session_ref": assignment_key,
            "variant_id": assignment.variant,
            "strategy_version": strategy_version,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "store_id": str(store_id) if store_id else None,
            "created_at": _now(),
        }
    )
    _save_json(durable_path, assignments)
    # Best-effort postgres durable path
    try:
        from repositories import postgres_utils

        if postgres_utils.use_postgres() and tenant_id is not None:
            from uuid import uuid4 as _uuid4

            from psycopg.types.json import Jsonb  # noqa: F401

            with postgres_utils.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO recommendation_assignments (
                        id, experiment_id, session_ref, variant_id, strategy_version, tenant_id, store_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (experiment_id, session_ref) DO NOTHING
                    """,
                    (
                        _uuid4(),
                        experiment_id,
                        assignment_key,
                        assignment.variant,
                        strategy_version,
                        tenant_id,
                        store_id,
                    ),
                )
                conn.commit()
    except Exception:
        pass
    return assignment


def record_event(event: RecommendationEventRecord) -> RecommendationEventRecord:
    rows = _load_json(_events_path(), [])
    # Idempotent on event_id
    for row in rows:
        if row.get("event_id") == event.event_id:
            return event
    rows.append(
        {
            "event_id": event.event_id,
            "strategy_version": event.strategy_version,
            "experiment_id": event.experiment_id,
            "variant": event.variant,
            "tenant_id": str(event.tenant_id) if event.tenant_id else None,
            "store_id": str(event.store_id) if event.store_id else None,
            "session_ref": event.session_ref,
            "member_ref": event.member_ref,
            "surface": event.surface,
            "rank": event.rank,
            "score": event.score,
            "reason_code": event.reason_code,
            "timestamp": event.timestamp,
            "event_type": event.event_type,
        }
    )
    _save_json(_events_path(), rows)
    return event


def data_quality_report(events: list[dict[str, Any]] | None = None) -> dict[str, int]:
    rows = events if events is not None else _load_json(_events_path(), [])
    seen: set[str] = set()
    duplicates = 0
    missing_strategy = 0
    exposure_before_conversion_ok = 0
    conversion_without_exposure = 0
    exposures: set[str] = set()
    for row in rows:
        event_id = str(row.get("event_id") or "")
        if event_id in seen:
            duplicates += 1
        elif event_id:
            seen.add(event_id)
        if not row.get("strategy_version"):
            missing_strategy += 1
        key = f"{row.get('session_ref')}:{row.get('strategy_version')}"
        event_type = str(row.get("event_type") or "")
        if event_type == "exposure":
            exposures.add(key)
        if event_type == "conversion":
            if key in exposures:
                exposure_before_conversion_ok += 1
            else:
                conversion_without_exposure += 1
    return {
        "duplicate_event_ids": duplicates,
        "missing_strategy_version": missing_strategy,
        "conversion_with_prior_exposure": exposure_before_conversion_ok,
        "conversion_without_exposure": conversion_without_exposure,
        "total_events": len(rows),
    }


def _set_status(
    strategy_id: str,
    version: int,
    status: StrategyStatus,
    *,
    actor: str,
    event: str,
    reviewed: bool = False,
) -> StrategyVersion:
    rows = _load_json(_path(), [])
    for row in rows:
        if row.get("strategy_id") == strategy_id and int(row.get("version") or 0) == int(version):
            row["status"] = status.value
            if reviewed:
                row["reviewed_at"] = _now()
            history = list(row.get("history") or [])
            history.append({"event": event, "actor": actor, "at": _now()})
            row["history"] = history
            _save_json(_path(), rows)
            return _to_strategy(row)
    raise RecommendationGovernanceError("strategy_not_found")
