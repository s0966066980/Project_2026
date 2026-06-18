"""統計聚合服務。

純函式：輸入 log / event 清單，輸出後台統計所需的彙總結構。
資料讀取由 route 透過 repository 取得後傳入，本層不做 I/O。
"""
from collections import Counter

from services import scenario_service


# ── session 統計（AI 推播成效 + 心情） ──────────────────────────────────
def compute_session_stats(logs: list) -> dict:
    total = len(logs)
    total_clicks = sum(int(l.get("ai_push_cart_count", 0)) for l in logs)
    success_count = sum(1 for l in logs if l.get("ai_push_success", False))
    failure_count = total - success_count
    rate = round(success_count / total, 4) if total > 0 else 0.0

    mood_sessions = sum(1 for l in logs if int(l.get("mood_score") or 0) > 0)
    mood_hit_rate = round(mood_sessions / total, 4) if total > 0 else 0.0
    mood_distribution = {str(i): 0 for i in range(1, 6)}
    for l in logs:
        score = int(l.get("mood_score") or 0)
        if 1 <= score <= 5:
            mood_distribution[str(score)] += 1

    sessions = [
        {
            "timestamp": l.get("timestamp", ""),
            "session_id": l.get("session_id", ""),
            "ai_push_cart_count": int(l.get("ai_push_cart_count", 0)),
            "ai_push_success": bool(l.get("ai_push_success", False)),
            "final_cart_ids": l.get("final_cart_ids", []),
            "cart_sources": l.get("cart_sources", []),
            "mood_score": int(l.get("mood_score") or 0),
            "mood_label": str(l.get("mood_label") or ""),
            "voice_turns": l.get("voice_turns", []),
        }
        for l in reversed(logs)
    ]
    return {
        "total_sessions": total,
        "total_ai_push_cart_clicks": total_clicks,
        "success_sessions": success_count,
        "failure_sessions": failure_count,
        "success_rate": rate,
        "mood_hit_rate": mood_hit_rate,
        "mood_sessions": mood_sessions,
        "mood_distribution": mood_distribution,
        "cumulative_score": success_count - failure_count,
        "sessions": sessions,
    }


# ── 互動障礙 / 介入統計 ─────────────────────────────────────────────────
ISSUE_EVENT_TYPES = {
    "page_dwell_timeout",
    "back_navigation",
    "invalid_touch",
    "payment_failed",
    "checkout_error",
    "customer_service_failed",
    "voice_order_failed",
    "menu_page_dwell_timeout",
    "category_switch_repeat",
    "recommendation_ignored",
}


def is_successful_intervention(log: dict) -> bool:
    result = log.get("result") if isinstance(log.get("result"), dict) else {}
    resolved_by = str(result.get("resolved_by") or "")
    return bool(
        result.get("checkout_success")
        or result.get("payment_success")
        or result.get("resolved")
        or result.get("resolved_by_checkout")
        or resolved_by in {"cart_add", "recommend_click", "payment_success", "checkout", "counter_payment"}
    )


def scenario_from_log(log: dict) -> str:
    if not isinstance(log, dict):
        return ""
    candidates = [
        log.get("scenario_id"),
        (log.get("barrier_result") or {}).get("scenario_id") if isinstance(log.get("barrier_result"), dict) else "",
        (log.get("intervention") or {}).get("scenario_id") if isinstance(log.get("intervention"), dict) else "",
        (log.get("result") or {}).get("scenario_id") if isinstance(log.get("result"), dict) else "",
    ]
    for candidate in candidates:
        normalized = scenario_service.normalize_scenario_id(candidate or "")
        if normalized in scenario_service.MAIN_SCENARIO_IDS:
            return normalized
    barrier = log.get("barrier_result") if isinstance(log.get("barrier_result"), dict) else {}
    return scenario_service.infer_scenario_from_barrier_state(barrier.get("barrier_state", ""))


def build_intervention_stats(logs: list, events: list | None = None) -> dict:
    barrier_counts = Counter()
    patent_category_counts = Counter()
    action_counts = Counter()
    patent_intervention_counts = Counter()
    intervention_page_counts = Counter()
    event_page_issue_counts = Counter()
    scenario_counts = Counter({scenario_id: 0 for scenario_id in scenario_service.MAIN_SCENARIO_IDS})
    scenario_success_counts = Counter({scenario_id: 0 for scenario_id in scenario_service.MAIN_SCENARIO_IDS})
    scenario_recent_logs = {scenario_id: [] for scenario_id in scenario_service.MAIN_SCENARIO_IDS}
    event_rows = events or []

    for log in logs:
        if not isinstance(log, dict):
            continue
        barrier = log.get("barrier_result") if isinstance(log.get("barrier_result"), dict) else {}
        intervention = log.get("intervention") if isinstance(log.get("intervention"), dict) else {}
        ui_context = log.get("ui_context") if isinstance(log.get("ui_context"), dict) else {}

        barrier_state = str(barrier.get("barrier_state") or "unknown")
        patent_category = str(barrier.get("patent_category") or "unknown")
        action = str(intervention.get("action") or "unknown")
        patent_intervention = str(intervention.get("patent_intervention_type") or "unknown")
        page_id = str(ui_context.get("page_id") or "unknown")
        barrier_counts[barrier_state] += 1
        patent_category_counts[patent_category] += 1
        action_counts[action] += 1
        patent_intervention_counts[patent_intervention] += 1
        intervention_page_counts[page_id] += 1
        scenario_id = scenario_from_log(log)
        if scenario_id in scenario_service.MAIN_SCENARIO_IDS:
            scenario_counts[scenario_id] += 1
            if is_successful_intervention(log):
                scenario_success_counts[scenario_id] += 1
            scenario_recent_logs[scenario_id].append(log)

    for event in event_rows:
        if not isinstance(event, dict):
            continue
        if str(event.get("event_type") or "") not in ISSUE_EVENT_TYPES:
            continue
        page_id = str(event.get("page_id") or "unknown")
        event_page_issue_counts[page_id] += 1

    total = len([row for row in logs if isinstance(row, dict)])
    success_count = sum(1 for row in logs if isinstance(row, dict) and is_successful_intervention(row))
    combined_page_counts = intervention_page_counts + event_page_issue_counts
    scenario_success_rate = {
        scenario_id: (
            round(scenario_success_counts[scenario_id] / scenario_counts[scenario_id], 4)
            if scenario_counts[scenario_id]
            else 0
        )
        for scenario_id in scenario_service.MAIN_SCENARIO_IDS
    }
    return {
        "total_interventions": total,
        "success_count": success_count,
        "success_rate": round(success_count / total, 4) if total else 0,
        "barrier_state_counts": dict(barrier_counts),
        "patent_category_counts": dict(patent_category_counts),
        "action_counts": dict(action_counts),
        "patent_intervention_counts": dict(patent_intervention_counts),
        "intervention_page_counts": dict(intervention_page_counts),
        "event_page_issue_counts": dict(event_page_issue_counts),
        "page_issue_counts": dict(combined_page_counts),
        "scenario_counts": dict(scenario_counts),
        "scenario_success_counts": dict(scenario_success_counts),
        "scenario_success_rate": scenario_success_rate,
        "scenario_recent_logs": {
            scenario_id: list(reversed(rows[-10:]))
            for scenario_id, rows in scenario_recent_logs.items()
        },
        "recent_logs": list(reversed(logs[-20:])),
        "recent_events": list(reversed(event_rows[-20:])),
    }
