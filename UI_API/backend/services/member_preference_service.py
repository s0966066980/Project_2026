"""會員偏好摘要工具。

此層只把會員紀錄整理成推薦/語音可用的精簡上下文，不負責推薦排序、
LLM 呼叫或 HTTP request 處理。
"""

from collections import Counter

from capabilities import catalog
from capabilities.member import member_service


def empty_preference_summary() -> dict:
    return {
        "has_member": False,
        "phone_masked": "",
        "nickname": "",
        "visit_count": 0,
        "total_spend": 0,
        "avg_spend": 0,
        "usual_item_ids": [],
        "usual_items": [],
        "recent_item_ids": [],
        "last_order_item_ids": [],
        "last_order_items": [],
        "preferred_categories": [],
        "frequent_pairs": [],
    }


def _unique_ordered(values: list[str], limit: int | None = None) -> list[str]:
    seen = set()
    rows = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        rows.append(value)
        if limit is not None and len(rows) >= limit:
            break
    return rows


def _order_completed(order: dict) -> bool:
    status = order.get("order_status")
    if isinstance(status, str) and status:
        return status == "completed"
    if isinstance(order.get("is_completed"), bool):
        return bool(order.get("is_completed"))
    return True


def _recent_item_ids(member: dict, limit: int = 5) -> list[str]:
    saved_recent_ids = [str(item_id) for item_id in (member.get("recent_item_ids") or []) if item_id]
    if saved_recent_ids:
        return _unique_ordered(saved_recent_ids, limit)

    ids = []
    for order in reversed(member.get("orders") or []):
        if not _order_completed(order):
            continue
        ids.extend([str(iid) for iid in (order.get("cart_ids") or []) if iid])
        if len(ids) >= limit:
            break
    return _unique_ordered(ids, limit)


def _last_order_item_ids(member: dict, limit: int = 8) -> list[str]:
    for order in reversed(member.get("orders") or []):
        if not _order_completed(order):
            continue
        return _unique_ordered([str(iid) for iid in (order.get("cart_ids") or []) if iid], limit)
    return []


def _items_from_ids(item_ids: list[str]) -> list[dict]:
    if not item_ids:
        return []
    menu_by_id = {str(item.get("id")): item for item in catalog.list_active_items() if item.get("id")}
    rows = []
    for item_id in item_ids:
        item = menu_by_id.get(item_id)
        if not item:
            continue
        rows.append(
            {
                "id": item_id,
                "name": str(item.get("name") or ""),
                "category": str(item.get("category") or ""),
            }
        )
    return rows


def _preferred_categories(member: dict, usual_items: list[dict], limit: int = 3) -> list[str]:
    category_freq = member.get("category_freq") or {}
    if category_freq:
        ranked_categories = [
            category
            for category, _ in sorted(category_freq.items(), key=lambda kv: int(kv[1] or 0), reverse=True)
            if category
        ]
        return ranked_categories[:limit]

    counts = Counter()
    for item in usual_items:
        category = str(item.get("category") or "").strip()
        if category:
            counts[category] += int(item.get("count") or 1)
    return [category for category, _ in counts.most_common(limit)]


def _frequent_pairs(member: dict, limit: int = 3) -> list[dict]:
    pair_freq = member.get("pair_freq") or {}
    if not pair_freq:
        return []
    menu_by_id = {str(item.get("id")): item for item in catalog.list_active_items() if item.get("id")}
    rows = []
    for pair_key, count in sorted(pair_freq.items(), key=lambda kv: int(kv[1] or 0), reverse=True):
        item_ids = [part for part in str(pair_key).split("|") if part]
        if len(item_ids) != 2:
            continue
        items = []
        for item_id in item_ids:
            menu_item = menu_by_id.get(item_id)
            if not menu_item:
                break
            items.append(
                {
                    "id": item_id,
                    "name": str(menu_item.get("name") or ""),
                    "category": str(menu_item.get("category") or ""),
                }
            )
        if len(items) != 2:
            continue
        rows.append(
            {
                "item_ids": item_ids,
                "items": items,
                "count": int(count or 0),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def build_preference_summary(member: dict | None, limit: int = 5) -> dict:
    if not member:
        return empty_preference_summary()

    usual_items = member_service.build_usuals(member, limit=limit)
    visit_count = int(member.get("visit_count", 0) or 0)
    total_spend = int(member.get("total_spend", 0) or 0)
    last_order_item_ids = _last_order_item_ids(member, limit=limit)
    summary = empty_preference_summary()
    summary.update(
        {
            "has_member": True,
            "phone_masked": member_service.mask_phone(member.get("phone", "")),
            "nickname": str(member.get("nickname", "") or ""),
            "visit_count": visit_count,
            "total_spend": total_spend,
            "avg_spend": total_spend // visit_count if visit_count else 0,
            "usual_item_ids": [str(item.get("id")) for item in usual_items if item.get("id")],
            "usual_items": [
                {
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("name") or ""),
                    "category": str(item.get("category") or ""),
                    "count": int(item.get("count") or 0),
                }
                for item in usual_items
                if item.get("id")
            ],
            "recent_item_ids": _recent_item_ids(member, limit=limit),
            "last_order_item_ids": last_order_item_ids,
            "last_order_items": _items_from_ids(last_order_item_ids),
            "preferred_categories": _preferred_categories(member, usual_items),
            "frequent_pairs": _frequent_pairs(member),
        }
    )
    return summary


def format_member_prompt_section(summary: dict | None) -> str:
    """回傳可注入 LLM prompt 的會員摘要，不包含完整手機或原始訂單 JSON。"""
    if not summary or not summary.get("has_member"):
        return ""

    lines = ["【會員偏好摘要】"]
    nickname = summary.get("nickname")
    if nickname:
        lines.append(f"會員暱稱：{nickname}")
    usual_names = [item.get("name", "") for item in summary.get("usual_items", []) if item.get("name")][:3]
    if usual_names:
        lines.append(f"常點：{'、'.join(usual_names)}")
    usual_items = [item for item in summary.get("usual_items", []) if item.get("id") and item.get("name")][:5]
    if usual_items:
        lines.append("【會員常點 ID】")
        lines.extend(
            f"{item['id']}｜{item['name']}｜{item.get('category') or '未分類'}｜常點 {int(item.get('count') or 0)} 次"
            for item in usual_items
        )
    last_order_items = [item for item in summary.get("last_order_items", []) if item.get("id") and item.get("name")][:5]
    if last_order_items:
        lines.append("【最近完成訂單 ID】")
        lines.extend(f"{item['id']}｜{item['name']}｜{item.get('category') or '未分類'}" for item in last_order_items)
    categories = [c for c in summary.get("preferred_categories", []) if c]
    if categories:
        lines.append(f"偏好分類：{'、'.join(categories)}")
    frequent_pairs = [pair for pair in summary.get("frequent_pairs", []) if len(pair.get("items") or []) == 2][:3]
    if frequent_pairs:
        pair_names = [
            " + ".join(item.get("name", "") for item in pair.get("items", []) if item.get("name"))
            for pair in frequent_pairs
        ]
        pair_names = [name for name in pair_names if name]
        if pair_names:
            lines.append(f"常見搭配：{'、'.join(pair_names)}")
    if summary.get("avg_spend"):
        lines.append(f"平均客單：約 ${int(summary['avg_spend'])}")
    lines.append("請優先參考會員偏好回答推薦問題，但不得捏造菜單不存在的品項。")
    lines.append("顧客詢問「常吃的」「上次點的」時，先依上述 ID 與名稱回答。")
    lines.append("顧客要求加入常點或上次訂單但語意不明確時，先用一句話確認；取得明確確認後才輸出 cart_actions。")
    return "\n".join(lines)
