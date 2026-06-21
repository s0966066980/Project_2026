"""結帳服務：記錄結帳 log、回寫最近一筆未結案的介入結果，並編排結帳回應。

route 只負責解析 Form 欄位，實際編排在此層。
"""
import asyncio
from datetime import datetime

import database
from repositories import interaction_event_repository, log_repository, session_repository
from services import member_service


def _seconds_since_timestamp(timestamp: str) -> int:
    if not timestamp:
        return 0
    try:
        started_at = datetime.fromisoformat(str(timestamp))
        return max(0, int((datetime.now() - started_at).total_seconds()))
    except Exception:
        return 0


def _build_checkout_intervention_result(
    open_log: dict,
    checkout_success: bool,
    session_id: str,
    final_cart_ids: list | None = None,
) -> dict:
    result = dict(open_log.get("result") if isinstance(open_log.get("result"), dict) else {})
    barrier_result = open_log.get("barrier_result") if isinstance(open_log.get("barrier_result"), dict) else {}
    result.update({
        "session_id": session_id,
        "scenario_id": open_log.get("scenario_id") or barrier_result.get("scenario_id", ""),
        "scenario_label": open_log.get("scenario_label") or barrier_result.get("scenario_label", ""),
        "resolved": bool(checkout_success),
        "resolved_by": "checkout" if checkout_success else "",
        "checkout_success": bool(checkout_success),
        "payment_success": bool(checkout_success),
        "time_to_checkout_sec": _seconds_since_timestamp(open_log.get("timestamp", "")),
        "time_to_resolution_sec": _seconds_since_timestamp(open_log.get("timestamp", "")),
        "resolved_by_checkout": bool(checkout_success),
        "final_cart_ids": list(final_cart_ids or []),
    })
    if not checkout_success:
        result["resolved_by_checkout"] = False
    return result


def mark_latest_intervention_checkout(
    session_id: str,
    checkout_success: bool = True,
    final_cart_ids: list | None = None,
) -> dict | None:
    open_log = interaction_event_repository.find_latest_open_intervention(session_id)
    if not open_log:
        return None
    intervention_id = str(open_log.get("intervention_id") or "")
    if not intervention_id:
        return None
    result = _build_checkout_intervention_result(
        open_log,
        checkout_success,
        session_id,
        final_cart_ids,
    )
    return interaction_event_repository.update_intervention_result(intervention_id, result)


async def process_checkout(
    session_id: str,
    pushed_list: list,
    cart_list: list,
    ai_count: int,
    sources: list,
    cart_total: int = 0,
) -> dict:
    session_history = await asyncio.to_thread(session_repository.get_session_history, session_id)
    try:
        loop = asyncio.get_running_loop()
        log_entry = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                database.record_final_checkout,
                session_id,
                pushed_list,
                cart_list,
                session_history,
                ai_count,
                sources,
            ),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        log_entry = {"skipped": True}

    if not log_entry.get("skipped"):
        intervention_result = await asyncio.to_thread(
            mark_latest_intervention_checkout, session_id, True, cart_list
        )
    else:
        intervention_result = None
    if intervention_result:
        log_entry = dict(log_entry or {})
        log_entry["recommendation_result"] = {
            "session_id": session_id,
            "pushed_ids": pushed_list,
            "final_cart_ids": cart_list,
            "is_success": bool(log_entry.get("is_success", False)),
        }
        log_entry["intervention_result"] = intervention_result

    try:
        await asyncio.to_thread(
            member_service.finalize_checkout, session_id, cart_list, cart_total, bool(log_entry.get("is_success", False))
        )
    except Exception:
        pass

    order_number = len(log_repository.get_session_logs())
    session_repository.archive_session(session_id)
    return {
        "status": "success",
        "log": log_entry,
        "order_number": order_number,
        "session_id": session_id,
    }
