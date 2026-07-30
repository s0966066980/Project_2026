from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .profile import PersistenceConfigurationError
from .registry import adapter_coverage
from .runtime import current_profile


def _path_evidence() -> dict[str, object]:
    profile = current_profile()
    paths = profile.runtime_paths
    return {
        name: {
            "configured": str(path),
            "exists": path.is_dir(),
            "mode": oct(path.stat().st_mode & 0o777) if path.exists() else "",
        }
        for name, path in (
            ("postgres_data", paths.postgres_data),
            ("postgres_wal_archive", paths.postgres_wal_archive),
            ("postgres_backups", paths.postgres_backups),
            ("sqlite", paths.sqlite),
            ("objects", paths.objects),
            ("rag_indexes", paths.rag_indexes),
            ("logs", paths.logs),
            ("exports", paths.exports),
            ("imports", paths.imports),
            ("tmp", paths.tmp),
        )
    }


def inspect_persistence() -> dict[str, Any]:
    try:
        profile = current_profile()
    except PersistenceConfigurationError as exc:
        return {
            "status": "failed",
            "error_code": "persistence_profile_invalid",
            "message": str(exc),
        }

    coverage = adapter_coverage(profile.backend)
    result: dict[str, Any] = {
        "status": "failed",
        "configured_backend": profile.backend,
        "effective_backend": profile.backend,
        "topology": profile.topology,
        "required_postgres_major": profile.postgres_required_major,
        "endpoint": profile.endpoint_summary(),
        "adapter_coverage": coverage,
        "runtime_paths": _path_evidence(),
        "connection": {"status": "not_checked"},
        "schema": {"status": "not_checked"},
        "topology_evidence": {"status": "not_checked"},
        "write_probe": latest_write_probe(),
    }
    if profile.backend == "sqlite":
        result["connection"] = {
            "status": "ok" if profile.runtime_paths.sqlite_database.parent.is_dir() else "failed",
            "database": str(profile.runtime_paths.sqlite_database),
        }
        result["schema"] = {"status": "failed", "error_code": "sqlite_full_schema_not_available"}
        result["topology_evidence"] = {"status": "ok", "mode": "single-file"}
        result["error_code"] = "adapter_coverage_incomplete"
        return result

    try:
        from repositories import postgres_utils

        with postgres_utils.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT current_setting('server_version_num') AS version_num,
                       current_database() AS database_name,
                       pg_is_in_recovery() AS in_recovery
                """
            )
            server = cursor.fetchone() or {}
            major = int(server.get("version_num") or 0) // 10000
            cursor.execute(
                """
                SELECT application_name, state, sync_state,
                       COALESCE(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn), 0) AS lag_bytes
                FROM pg_stat_replication
                ORDER BY application_name
                """
            )
            replicas = [dict(row) for row in cursor.fetchall()]
        result["connection"] = {
            "status": "ok" if major == profile.postgres_required_major else "failed",
            "server_major": major,
            "database": str(server.get("database_name") or ""),
            "primary": not bool(server.get("in_recovery")),
        }
        if major != profile.postgres_required_major:
            result["connection"]["error_code"] = "postgres_major_mismatch"

        from modules.runtime_persistence.migrations import inspect_schema

        plan = inspect_schema()
        schema_clean = plan.is_valid and not plan.pending_versions
        result["schema"] = {
            "status": "ok" if schema_clean else "failed",
            "head": postgres_utils.migration_files()[-1].stem,
            "applied_count": len(plan.applied_versions),
            "pending": list(plan.pending_versions),
            "errors": list(plan.errors),
        }

        if profile.topology == "single":
            topology_ok = not bool(server.get("in_recovery"))
            result["topology_evidence"] = {
                "status": "ok" if topology_ok else "failed",
                "mode": "single",
                "replica_count": len(replicas),
                "production_ha": False,
            }
        else:
            synchronous = [row for row in replicas if row.get("sync_state") in {"sync", "quorum"}]
            asynchronous = [row for row in replicas if row.get("sync_state") == "async"]
            topology_ok = not bool(server.get("in_recovery")) and bool(synchronous) and bool(asynchronous)
            result["topology_evidence"] = {
                "status": "ok" if topology_ok else "failed",
                "mode": "ha",
                "replica_count": len(replicas),
                "synchronous_count": len(synchronous),
                "asynchronous_count": len(asynchronous),
                "replicas": replicas,
                "production_ha": topology_ok,
            }
        ready = bool(
            coverage["complete"]
            and result["connection"]["status"] == "ok"
            and result["schema"]["status"] == "ok"
            and result["topology_evidence"]["status"] == "ok"
        )
        result["status"] = "ok" if ready else "failed"
        if not ready:
            result["error_code"] = "persistence_not_ready"
        return result
    except Exception:
        result["connection"] = {"status": "failed", "error_code": "database_unavailable"}
        result["error_code"] = "database_unavailable"
        return result


def _write_probe_path() -> Path:
    return current_profile().runtime_paths.logs / "persistence-write-probe.json"


def latest_write_probe() -> dict[str, Any] | None:
    try:
        path = _write_probe_path()
        if not path.is_file() or path.is_symlink():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return dict(value) if isinstance(value, dict) else None
    except Exception:
        return None


def run_write_probe() -> dict[str, Any]:
    profile = current_profile()
    if not profile.is_postgresql:
        raise RuntimeError("PostgreSQL is required for the deployment write probe")
    from repositories import postgres_utils

    with postgres_utils.connect() as connection, connection.cursor() as cursor:
        cursor.execute("CREATE TEMP TABLE persistence_write_probe (value INTEGER) ON COMMIT DROP")
        cursor.execute("INSERT INTO persistence_write_probe (value) VALUES (1)")
        cursor.execute("SELECT value FROM persistence_write_probe")
        if int((cursor.fetchone() or {}).get("value") or 0) != 1:
            raise RuntimeError("Persistence write probe did not read its transaction-local value")
        connection.rollback()
    evidence = {
        "status": "ok",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "endpoint_fingerprint": profile.endpoint_summary().get("fingerprint", ""),
        "durable_test_data_retained": False,
    }
    path = _write_probe_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return evidence
