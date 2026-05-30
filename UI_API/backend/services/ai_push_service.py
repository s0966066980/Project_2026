"""AI 推播服務 — 透過 Ollama 生成底部欄推播餐點與理由。"""
import asyncio
import re

import ai_services
import config
from repositories import menu_repository
from services.recommendation_service import clean_menu_id

_PRIORITY_CATS = {"超值全餐", "極選系列", "點心", "飲料", "麥當勞分享盒"}


def _price(item: dict) -> int:
    try:
        return int(float(item.get("price") or 0))
    except Exception:
        return 0


def _menu_context(items: list[dict], limit: int = 80) -> str:
    candidates = [i for i in items if i.get("id") and i.get("name")]
    preferred  = [i for i in candidates if str(i.get("category") or "") in _PRIORITY_CATS]
    rows = [
        f"{i['id']}｜{i['name']}｜{i.get('category', '')}｜${_price(i)}"
        for i in (preferred or candidates)[:limit]
    ]
    return "\n".join(rows)


def _fallback_item(items: list[dict], exclude: set) -> dict:
    candidates = [i for i in items if i.get("id") and i["id"] not in exclude and _price(i) > 0]
    for cat in ["超值全餐", "極選系列", "點心"]:
        hit = next((i for i in candidates if i.get("category") == cat), None)
        if hit:
            return hit
    return candidates[0] if candidates else (items[0] if items else {})


async def generate(session_id: str, ollama_semaphore, exclude_ids: list[str] | None = None) -> dict:
    """
    呼叫 Ollama 選出 1 個推薦餐點並生成促購短句。
    回傳 {"recommendation_id": "MCDxxx", "push_text": "...", "status": "success|fallback"}
    """
    items    = await asyncio.to_thread(menu_repository.get_menu)
    ids      = [i["id"] for i in items if i.get("id")]
    by_id    = {i["id"]: i for i in items if i.get("id")}
    exclude  = set(exclude_ids or [])
    fallback = _fallback_item(items, exclude)
    fb_id    = fallback.get("id") or (ids[0] if ids else "")
    fb_name  = fallback.get("name") or "推薦餐點"

    if not ids:
        return {"status": "error", "message": "menu is empty"}

    system = (
        "你是麥當勞自助點餐機的 AI 推播助手。"
        "只能從菜單白名單選 1 個餐點，不能發明不存在的餐點。"
        '輸出純 JSON：{"recommendation_id":"MCDxxx","push_text":"繁體中文促購短句"}。'
    )
    user = (
        "【菜單白名單】\n"
        f"{_menu_context(items)}\n\n"
        f"【本次排除 ID】{', '.join(exclude) or '無'}\n"
        "請挑 1 個適合現在推播的餐點。"
        "push_text：繁體中文、18–34 字、自然熱情促購語氣，不要出現 JSON 以外的文字。"
    )

    try:
        async with ollama_semaphore:
            raw = await asyncio.get_running_loop().run_in_executor(
                None,
                ai_services.ask_ollama,
                system, user, "AI_PUSH",
                config.get("MODEL_NAME", "qwen3.5:4b"),
            )
    except Exception as exc:
        raw = {"error": str(exc)}

    if isinstance(raw, list):
        raw = next((r for r in raw if isinstance(r, dict)), {})
    if not isinstance(raw, dict) or "error" in raw:
        return {
            "status": "fallback",
            "session_id": session_id,
            "recommendation_id": fb_id,
            "push_text": f"{fb_name}現在很適合來一份，搭配點餐超值！",
        }

    sel_id = clean_menu_id(
        raw.get("recommendation_id") or raw.get("id") or raw.get("menu_id"), ids
    )
    if not sel_id or sel_id in exclude:
        sel_id = fb_id

    selected  = by_id.get(sel_id) or fallback
    push_text = re.sub(r"\s+", " ", str(raw.get("push_text") or "")).strip()[:60]
    if not push_text:
        push_text = f"{selected.get('name') or fb_name}現在很適合來一份！"

    return {
        "status": "success",
        "session_id": session_id,
        "recommendation_id": sel_id,
        "push_text": push_text,
    }
