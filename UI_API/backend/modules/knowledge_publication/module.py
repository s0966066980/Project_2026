from __future__ import annotations

import csv
import hashlib
import io
from difflib import SequenceMatcher
from typing import Any, Protocol

from models.commercial_scope import CommercialScope


class PublicationError(RuntimeError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


class TransientPublicationError(RuntimeError):
    """An adapter failure that may be retried within the delivery budget."""


class PublicationStore(Protocol):
    def create_draft(self, *, scope: CommercialScope, values: dict[str, Any], actor: str) -> dict[str, Any]: ...

    def create_drafts(
        self, *, scope: CommercialScope, values: list[dict[str, Any]], actor: str
    ) -> list[dict[str, Any]]: ...

    def revise_draft(
        self,
        *,
        scope: CommercialScope,
        item_id: str,
        expected_row_revision: int,
        values: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]: ...

    def begin_batch(
        self,
        *,
        scope: CommercialScope,
        item_ids: list[str],
        actor: str,
        retry_failures_only: bool,
    ) -> dict[str, Any]: ...

    def attach_job(self, *, scope: CommercialScope, attempt_id: str, job_id: str) -> None: ...

    def fail_enqueue(self, *, scope: CommercialScope, attempt_id: str, actor: str, reason: str) -> None: ...

    def get_item(self, *, scope: CommercialScope, item_id: str) -> dict[str, Any]: ...

    def list_items(self, *, scope: CommercialScope) -> list[dict[str, Any]]: ...

    def get_batch(self, *, scope: CommercialScope, batch_id: str) -> dict[str, Any]: ...

    def list_attempts(self, *, scope: CommercialScope, limit: int) -> list[dict[str, Any]]: ...

    def list_audit(self, *, scope: CommercialScope, item_id: str) -> list[dict[str, Any]]: ...

    def get_attempt(self, *, scope: CommercialScope, attempt_id: str) -> dict[str, Any]: ...

    def record_artifact(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        artifact: dict[str, Any],
    ) -> None: ...

    def commit_publication(self, *, scope: CommercialScope, attempt_id: str, actor: str) -> dict[str, Any]: ...

    def complete_cleanup(self, *, scope: CommercialScope, attempt_id: str, actor: str) -> None: ...

    def get_published(self, *, scope: CommercialScope, item_id: str) -> dict[str, Any]: ...

    def list_published_attempt_ids(self, *, scope: CommercialScope) -> set[str]: ...

    def begin_retirement(
        self,
        *,
        scope: CommercialScope,
        item_id: str,
        expected_row_revision: int,
        actor: str,
    ) -> dict[str, Any]: ...

    def purge_item(self, *, scope: CommercialScope, item_id: str) -> None: ...

    def get_retirement_cleanup(self, *, scope: CommercialScope, cleanup_id: str) -> dict[str, Any]: ...

    def record_retirement_cleanup_error(self, *, scope: CommercialScope, cleanup_id: str, reason: str) -> None: ...

    def complete_retirement_cleanup(self, *, scope: CommercialScope, cleanup_id: str, actor: str) -> None: ...

    def fail_swap(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        actor: str,
        reason: str,
    ) -> None: ...

    def resume_attempt(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        actor: str,
        reuse_artifact: bool,
    ) -> dict[str, Any]: ...

    def record_retryable_error(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        error_code: str,
        reason: str,
    ) -> None: ...

    def fail_build(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        actor: str,
        error_code: str,
        reason: str,
    ) -> None: ...

    def list_expired_artifacts(self, *, cutoff: str, limit: int) -> list[dict[str, Any]]: ...
    def clear_expired_artifact(self, *, attempt_id: str, actor: str) -> None: ...


class PublicationJobs(Protocol):
    def enqueue(self, *, attempt_id: str, scope: CommercialScope) -> str: ...


class PublicationArtifacts(Protocol):
    def build(self, *, attempt: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]: ...

    def cleanup(self, *, artifact_ref: str) -> None: ...

    def is_compatible(self, *, artifact: dict[str, Any], item: dict[str, Any]) -> bool: ...


class KnowledgePublicationModule:
    """Owns Knowledge Version publication lifecycle and durable attempts."""

    def __init__(
        self,
        *,
        store: PublicationStore,
        jobs: PublicationJobs,
        artifacts: PublicationArtifacts | None = None,
    ):
        self._store = store
        self._jobs = jobs
        self._artifacts = artifacts

    def cleanup_expired_artifacts(self, *, cutoff: str, actor: str = "retention", limit: int = 100) -> dict[str, Any]:
        if self._artifacts is None:
            raise PublicationError("publication_artifact_adapter_required")
        rows = self._store.list_expired_artifacts(cutoff=cutoff, limit=max(1, min(int(limit), 500)))
        cleaned, failed = [], []
        for row in rows:
            try:
                self._artifacts.cleanup(artifact_ref=row["artifact_ref"])
                self._store.clear_expired_artifact(attempt_id=row["attempt_id"], actor=actor)
                cleaned.append(row["attempt_id"])
            except Exception:
                failed.append(row["attempt_id"])
        return {"cleaned_attempt_ids": cleaned, "failed_attempt_ids": failed}

    def create_draft(
        self,
        *,
        scope: CommercialScope,
        category: str,
        content_type: str,
        title: str,
        content: str,
        actor: str,
        override_near_duplicate: bool = False,
    ) -> dict[str, Any]:
        from .content import normalize_values

        values = normalize_values(
            category=category,
            content_type=content_type,
            title=title,
            content=content,
        )
        warning = self._duplicate_warning(scope=scope, content=values["content"])
        if warning and not override_near_duplicate:
            raise PublicationError("near_duplicate", details=warning)
        return self._store.create_draft(
            scope=scope,
            values=values,
            actor=actor,
        )

    def revise_draft(
        self,
        *,
        scope: CommercialScope,
        item_id: str,
        expected_row_revision: int,
        category: str,
        content_type: str,
        title: str,
        content: str,
        actor: str,
        override_near_duplicate: bool = False,
    ) -> dict[str, Any]:
        from .content import normalize_values

        values = normalize_values(
            category=category,
            content_type=content_type,
            title=title,
            content=content,
        )
        warning = self._duplicate_warning(scope=scope, content=values["content"], exclude_item_id=item_id)
        if warning and not override_near_duplicate:
            raise PublicationError("near_duplicate", details=warning)
        return self._store.revise_draft(
            scope=scope,
            item_id=item_id,
            expected_row_revision=expected_row_revision,
            values=values,
            actor=actor,
        )

    def _duplicate_warning(
        self, *, scope: CommercialScope, content: str, exclude_item_id: str = ""
    ) -> dict[str, Any] | None:
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        best: tuple[float, dict[str, Any]] | None = None
        for item in self._store.list_items(scope=scope):
            if item["item_id"] == exclude_item_id:
                continue
            if item["checksum"] == checksum:
                raise PublicationError(
                    "exact_duplicate",
                    details={"item_id": item["item_id"], "title": item["title"]},
                )
            ratio = SequenceMatcher(None, content.casefold(), str(item["content"]).casefold()).ratio()
            if ratio >= 0.75 and (best is None or ratio > best[0]):
                best = (ratio, item)
        if best is None:
            return None
        return {
            "item_id": best[1]["item_id"],
            "title": best[1]["title"],
            "similarity": round(best[0], 3),
        }

    def request_publication(
        self,
        *,
        scope: CommercialScope,
        item_ids: list[str],
        actor: str,
        retry_failures_only: bool = False,
    ) -> dict[str, Any]:
        batch = self._store.begin_batch(
            scope=scope,
            item_ids=list(dict.fromkeys(item_ids)),
            actor=actor,
            retry_failures_only=retry_failures_only,
        )
        for result in batch["results"]:
            if result["status"] not in {"indexing", "resuming"}:
                continue
            attempt_id = result["attempt_id"]
            if result["status"] == "resuming":
                self.retry_attempt(scope=scope, attempt_id=attempt_id, actor=actor)
            try:
                job_id = self._jobs.enqueue(attempt_id=attempt_id, scope=scope)
            except Exception as exc:
                safe_reason = str(exc or "publication_enqueue_failed")[:200]
                self._store.fail_enqueue(
                    scope=scope,
                    attempt_id=attempt_id,
                    actor=actor,
                    reason=safe_reason,
                )
                result.update(status="index_failed", reason=safe_reason)
                continue
            self._store.attach_job(
                scope=scope,
                attempt_id=attempt_id,
                job_id=job_id,
            )
            result["status"] = "indexing"
            result["job_id"] = job_id
        return batch

    def ensure_attempt_enqueued(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        actor: str,
    ) -> dict[str, Any]:
        """Idempotently restore queue delivery for an unfinished attempt."""
        attempt = self._store.get_attempt(scope=scope, attempt_id=attempt_id)
        if attempt["status"] != "in_progress":
            raise PublicationError(
                "publication_attempt_not_in_progress",
                details={"status": attempt["status"]},
            )
        try:
            job_id = self._jobs.enqueue(attempt_id=attempt_id, scope=scope)
        except Exception as exc:
            reason = str(exc or "publication_enqueue_failed")[:200]
            self._store.fail_enqueue(
                scope=scope,
                attempt_id=attempt_id,
                actor=actor,
                reason=reason,
            )
            raise PublicationError("publication_enqueue_failed") from exc
        self._store.attach_job(
            scope=scope,
            attempt_id=attempt_id,
            job_id=job_id,
        )
        return {
            "attempt_id": attempt_id,
            "status": "indexing",
            "phase": attempt["phase"],
            "job_id": job_id,
        }

    def get_item(self, *, scope: CommercialScope, item_id: str) -> dict[str, Any]:
        return self._store.get_item(scope=scope, item_id=item_id)

    def list_items(self, *, scope: CommercialScope) -> dict[str, Any]:
        rows = self._store.list_items(scope=scope)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        from .content import CATEGORIES

        published_counts = {
            category["id"]: sum(
                1 for row in rows if row["category"] == category["id"] and row["published_version"] is not None
            )
            for category in CATEGORIES
        }
        popular = sorted(
            enumerate(CATEGORIES),
            key=lambda entry: (-published_counts[entry[1]["id"]], entry[0]),
        )[:4]
        return {
            "items": rows,
            "popular_categories": [
                {**category, "published_count": published_counts[category["id"]]} for _, category in popular
            ],
            "counts": counts,
            "total": len(rows),
        }

    def import_csv(
        self,
        *,
        scope: CommercialScope,
        csv_text: str,
        actor: str,
        override_near_duplicates: bool = False,
    ) -> dict[str, Any]:
        from .content import normalize_values

        reader = csv.DictReader(io.StringIO(str(csv_text or "")))
        required = {"title", "category", "content_type", "content"}
        if set(reader.fieldnames or []) != required:
            raise PublicationError("invalid_import_columns", details={"required": sorted(required)})
        staged: list[dict[str, Any]] = []
        checksums: set[str] = set()
        errors: list[dict[str, Any]] = []
        for line, row in enumerate(reader, start=2):
            try:
                values = normalize_values(
                    category=row.get("category", ""),
                    content_type=row.get("content_type", ""),
                    title=row.get("title", ""),
                    content=row.get("content", ""),
                )
                warning = self._duplicate_warning(scope=scope, content=values["content"])
                if warning and not override_near_duplicates:
                    raise PublicationError("near_duplicate", details=warning)
                checksum = hashlib.sha256(values["content"].encode("utf-8")).hexdigest()
                if checksum in checksums:
                    raise PublicationError("exact_duplicate_in_batch")
                checksums.add(checksum)
                staged.append(values)
            except PublicationError as exc:
                errors.append({"line": line, "code": exc.code, "details": exc.details})
        if errors:
            raise PublicationError("import_validation_failed", details={"errors": errors})
        created = self._store.create_drafts(scope=scope, values=staged, actor=actor)
        return {"created": created, "count": len(created)}

    def export_csv(self, *, scope: CommercialScope) -> str:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "knowledge_item_id",
                "title",
                "category",
                "content_type",
                "status",
                "published_version",
            ],
        )
        writer.writeheader()
        for row in self._store.list_items(scope=scope):
            writer.writerow(
                {
                    "knowledge_item_id": row["item_id"],
                    "title": row["title"],
                    "category": row["category"],
                    "content_type": row["content_type"],
                    "status": row["status"],
                    "published_version": row["published_version"] or "",
                }
            )
        return output.getvalue()

    def get_batch(self, *, scope: CommercialScope, batch_id: str) -> dict[str, Any]:
        return self._store.get_batch(scope=scope, batch_id=batch_id)

    def audit_trail(self, *, scope: CommercialScope, item_id: str) -> list[dict[str, Any]]:
        return self._store.list_audit(scope=scope, item_id=item_id)

    def dashboard(self, *, scope: CommercialScope) -> dict[str, Any]:
        rows = self._store.list_items(scope=scope)
        published_items = sum(row["published_version"] is not None for row in rows)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        statuses = {row["status"] for row in rows}
        if "indexing" in statuses:
            index_health = "indexing"
        elif statuses & {"index_failed", "publication_failed"}:
            index_health = "degraded"
        elif published_items:
            index_health = "healthy"
        else:
            index_health = "empty"
        return {
            "total_items": len(rows),
            "published_items": published_items,
            "counts": counts,
            "index_health": index_health,
            "recent_publication_attempts": self._store.list_attempts(scope=scope, limit=5),
        }

    def get_attempt(self, *, scope: CommercialScope, attempt_id: str) -> dict[str, Any]:
        return self._store.get_attempt(scope=scope, attempt_id=attempt_id)

    def get_published(self, *, scope: CommercialScope, item_id: str) -> dict[str, Any]:
        return self._store.get_published(scope=scope, item_id=item_id)

    def published_attempt_ids(self, *, scope: CommercialScope) -> set[str]:
        return self._store.list_published_attempt_ids(scope=scope)

    def retire(
        self,
        *,
        scope: CommercialScope,
        item_id: str,
        expected_row_revision: int,
        actor: str,
    ) -> dict[str, Any]:
        if self._artifacts is None:
            raise PublicationError("publication_artifact_adapter_required")
        cleanup = self._store.begin_retirement(
            scope=scope,
            item_id=item_id,
            expected_row_revision=expected_row_revision,
            actor=actor,
        )
        return self._run_retirement_cleanup(scope=scope, cleanup=cleanup, actor=actor)

    def delete(
        self,
        *,
        scope: CommercialScope,
        item_id: str,
        expected_row_revision: int,
        actor: str,
    ) -> dict[str, Any]:
        """徹底移除一筆知識：先下架並清掉索引，再刪除紀錄本身。

        退役只是讓知識不再被檢索，紀錄仍留在列表裡；累積下來會讓操作者難以分辨什麼還算數。
        刪除必須先走完退役的清理，否則索引裡會殘留一份沒有主人的內容而繼續被檢索到。
        稽核事件保留在 knowledge_publication_audit，因此「誰在何時刪了什麼」仍可追溯。
        """

        item = self._store.get_item(scope=scope, item_id=item_id)
        # 只有已發布的知識才有索引要清；草稿與已退役的直接刪即可。
        if str(item.get("published_version") or ""):
            self.retire(
                scope=scope,
                item_id=item_id,
                expected_row_revision=expected_row_revision,
                actor=actor,
            )
        self._store.purge_item(scope=scope, item_id=item_id)
        return {"item_id": item_id, "deleted": True}

    def resume_retirement_cleanup(self, *, scope: CommercialScope, cleanup_id: str, actor: str) -> dict[str, Any]:
        cleanup = self._store.get_retirement_cleanup(scope=scope, cleanup_id=cleanup_id)
        return self._run_retirement_cleanup(scope=scope, cleanup=cleanup, actor=actor)

    def _run_retirement_cleanup(self, *, scope: CommercialScope, cleanup: dict[str, Any], actor: str) -> dict[str, Any]:
        if self._artifacts is None:
            raise PublicationError("publication_artifact_adapter_required")
        if cleanup["status"] == "complete":
            item = self._store.get_item(scope=scope, item_id=cleanup["item_id"])
            return {**item, "cleanup_id": cleanup["cleanup_id"], "cleanup_status": "complete"}
        try:
            self._artifacts.cleanup(artifact_ref=cleanup["artifact_ref"])
        except Exception as exc:
            self._store.record_retirement_cleanup_error(
                scope=scope,
                cleanup_id=cleanup["cleanup_id"],
                reason=str(exc or "retirement_cleanup_failed")[:200],
            )
            item = self._store.get_item(scope=scope, item_id=cleanup["item_id"])
            return {**item, "cleanup_id": cleanup["cleanup_id"], "cleanup_status": "pending"}
        self._store.complete_retirement_cleanup(scope=scope, cleanup_id=cleanup["cleanup_id"], actor=actor)
        item = self._store.get_item(scope=scope, item_id=cleanup["item_id"])
        return {**item, "cleanup_id": cleanup["cleanup_id"], "cleanup_status": "complete"}

    def run_attempt(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        actor: str,
        retry_budget_exhausted: bool = False,
    ) -> dict[str, Any]:
        if self._artifacts is None:
            raise PublicationError("publication_artifact_adapter_required")
        attempt = self._store.get_attempt(scope=scope, attempt_id=attempt_id)
        if attempt["phase"] == "build":
            item = self._store.get_item(scope=scope, item_id=attempt["item_id"])
            try:
                artifact = self._artifacts.build(attempt=attempt, item=item)
                if artifact.get("content_checksum") != item["checksum"]:
                    raise PublicationError("artifact_checksum_mismatch")
            except TransientPublicationError as exc:
                reason = str(exc or "transient_build_failure")[:200]
                if not retry_budget_exhausted:
                    self._store.record_retryable_error(
                        scope=scope,
                        attempt_id=attempt_id,
                        error_code="transient_build_failure",
                        reason=reason,
                    )
                    return {
                        "attempt_id": attempt_id,
                        "status": "indexing",
                        "phase": "build",
                        "retryable": True,
                    }
                self._store.fail_build(
                    scope=scope,
                    attempt_id=attempt_id,
                    actor=actor,
                    error_code="retry_budget_exhausted",
                    reason=reason,
                )
                return {
                    "attempt_id": attempt_id,
                    "status": "index_failed",
                    "phase": "build",
                    "retryable": False,
                }
            except Exception as exc:
                reason = str(exc or "index_build_failed")[:200]
                self._store.fail_build(
                    scope=scope,
                    attempt_id=attempt_id,
                    actor=actor,
                    error_code=getattr(exc, "code", "index_build_failed"),
                    reason=reason,
                )
                return {
                    "attempt_id": attempt_id,
                    "status": "index_failed",
                    "phase": "build",
                    "retryable": False,
                }
            self._store.record_artifact(
                scope=scope,
                attempt_id=attempt_id,
                artifact=artifact,
            )
            attempt = self._store.get_attempt(scope=scope, attempt_id=attempt_id)
        if attempt["phase"] == "swap":
            try:
                self._store.commit_publication(
                    scope=scope,
                    attempt_id=attempt_id,
                    actor=actor,
                )
            except Exception as exc:
                self._store.fail_swap(
                    scope=scope,
                    attempt_id=attempt_id,
                    actor=actor,
                    reason=str(exc or "publication_swap_failed")[:200],
                )
                return {
                    "attempt_id": attempt_id,
                    "status": "publication_failed",
                    "phase": "swap",
                    "retryable": False,
                }
            attempt = self._store.get_attempt(scope=scope, attempt_id=attempt_id)
        if attempt["phase"] == "cleanup":
            try:
                self._artifacts.cleanup(artifact_ref=attempt["cleanup_artifact_ref"])
            except Exception:
                return {
                    "attempt_id": attempt_id,
                    "status": "published",
                    "phase": "cleanup",
                    "retryable": True,
                }
            self._store.complete_cleanup(
                scope=scope,
                attempt_id=attempt_id,
                actor=actor,
            )
            attempt = self._store.get_attempt(scope=scope, attempt_id=attempt_id)
        return {
            "attempt_id": attempt_id,
            "status": attempt["status"],
            "phase": attempt["phase"],
            "retryable": attempt["status"] == "in_progress",
        }

    def retry_attempt(
        self,
        *,
        scope: CommercialScope,
        attempt_id: str,
        actor: str,
    ) -> dict[str, Any]:
        if self._artifacts is None:
            raise PublicationError("publication_artifact_adapter_required")
        attempt = self._store.get_attempt(scope=scope, attempt_id=attempt_id)
        if attempt["status"] not in {"index_failed", "publication_failed"}:
            raise PublicationError("publication_attempt_not_retryable")
        item = self._store.get_item(scope=scope, item_id=attempt["item_id"])
        reuse_artifact = bool(
            attempt["status"] == "publication_failed"
            and attempt["artifact_ref"]
            and self._artifacts.is_compatible(
                artifact=attempt["artifact_manifest"],
                item=item,
            )
        )
        return self._store.resume_attempt(
            scope=scope,
            attempt_id=attempt_id,
            actor=actor,
            reuse_artifact=reuse_artifact,
        )
