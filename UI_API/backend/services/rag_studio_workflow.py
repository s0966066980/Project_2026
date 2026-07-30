"""RAG Studio workflow read model.

This composes, but does not own, publication, retrieval configuration, and
retrieval-check state into one operator-facing sequence.
"""

from __future__ import annotations

from typing import Any


def _step(
    step_id: str,
    title: str,
    *,
    state: str,
    detail: str,
    tab: str,
    action: str = "",
    reason: str = "",
    attempt_id: str = "",
) -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "state": state,
        "detail": detail,
        "tab": tab,
        "action": action,
        "reason": reason,
        "attempt_id": attempt_id,
    }


def build_workflow(
    *,
    publication: dict[str, Any],
    published_configuration: dict[str, Any] | None,
    readiness_confirmation: dict[str, Any] | None,
) -> dict[str, Any]:
    total_items = int(publication.get("total_items") or 0)
    published_items = int(publication.get("published_items") or 0)
    attempts = list(publication.get("recent_publication_attempts") or [])
    active = next(
        (row for row in attempts if row.get("status") in {"in_progress", "cleanup_pending"}),
        None,
    )
    failed = next(
        (row for row in attempts if row.get("status") in {"index_failed", "publication_failed"}),
        None,
    )

    author = _step(
        "author",
        "建立門市知識草稿",
        state="complete" if total_items else "pending",
        detail=(f"已有 {total_items} 筆知識項目。" if total_items else "先新增第一筆門市知識並儲存草稿。"),
        tab="knowledge",
        action="" if total_items else "add",
    )

    if published_items:
        publish = _step(
            "publish",
            "發布並完成索引",
            state="complete",
            detail=f"已有 {published_items} 筆 Published 知識可供正式檢索。",
            tab="knowledge",
        )
    elif active and active.get("job_status") == "missing":
        publish = _step(
            "publish",
            "發布並完成索引",
            state="blocked",
            detail="發布嘗試存在，但可靠工作佇列找不到對應 job；請重新排入索引。",
            tab="knowledge",
            action="resume-publication",
            reason="publication_job_missing",
            attempt_id=str(active.get("attempt_id") or ""),
        )
    elif active:
        job_status = str(active.get("job_status") or "pending")
        publish = _step(
            "publish",
            "發布並完成索引",
            state="active",
            detail=f"索引工作正在處理（phase: {active.get('phase') or 'build'}；job: {job_status}）。",
            tab="knowledge",
        )
    elif failed:
        publish = _step(
            "publish",
            "發布並完成索引",
            state="blocked",
            detail="最近一次發布失敗；選取失敗項目後執行「只重試失敗」。",
            tab="knowledge",
            reason=str(failed.get("status") or "publication_failed"),
        )
    else:
        publish = _step(
            "publish",
            "發布並完成索引",
            state="pending" if total_items else "locked",
            detail=("選取草稿並發布，等待狀態變成 Published。" if total_items else "完成知識草稿後才能發布。"),
            tab="knowledge",
        )

    configuration = _step(
        "configuration",
        "發布正式檢索設定",
        state="complete" if published_configuration else ("pending" if published_items else "locked"),
        detail=(
            f"正式設定 v{published_configuration.get('version')} 已發布。"
            if published_configuration
            else "選擇檢索方法、Top K 與相關性政策後發布。"
            if published_items
            else "至少一筆知識成為 Published 後再發布檢索設定。"
        ),
        tab="methods",
    )

    confirmation = _step(
        "confirm",
        "測試並確認正式結果",
        state="complete" if readiness_confirmation else ("pending" if published_items and published_configuration else "locked"),
        detail=(
            "目前正式索引與設定已有人工確認證據。"
            if readiness_confirmation
            else "使用正式設定取得至少一筆結果，再確認該結果快照。"
            if published_items and published_configuration
            else "知識與檢索設定完成後才能建立正式就緒證據。"
        ),
        tab="tests",
    )

    steps = [author, publish, configuration, confirmation]
    next_step = next((step["id"] for step in steps if step["state"] != "complete"), None)
    return {
        "ready": next_step is None,
        "completed": sum(step["state"] == "complete" for step in steps),
        "total": len(steps),
        "next_step": next_step,
        "steps": steps,
    }
