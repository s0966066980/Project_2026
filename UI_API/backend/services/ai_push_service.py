"""AI 推播服務 — 透過 Ollama 生成底部欄推播餐點與理由。"""
import asyncio
import re
import time

import ai_services
import config
from repositories import menu_repository
from services.recommendation_service import clean_menu_id
from services.mood_service import get_mood_context

_menu_cache: dict = {"items": None, "ts": 0.0}


async def _get_menu_cached() -> list:
    now = time.monotonic()
    ttl = float(config.get("VOICE_MENU_CACHE_TTL_SEC", 60.0))
    if _menu_cache["items"] is None or now - _menu_cache["ts"] > ttl:
        _menu_cache["items"] = await asyncio.to_thread(menu_repository.get_menu)
        _menu_cache["ts"] = now
    return _menu_cache["items"]


def _price(item: dict) -> int:
    try:
        return int(float(item.get("price") or 0))
    except Exception:
        return 0


def _menu_context(items: list[dict], limit: int = 80) -> str:
    priority_cats = set(config.get("AI_PUSH_PRIORITY_CATS", []))
    candidates = [i for i in items if i.get("id") and i.get("name")]
    preferred  = [i for i in candidates if str(i.get("category") or "") in priority_cats]
    rows = [
        f"{i['id']}｜{i['name']}｜{i.get('category', '')}｜${_price(i)}"
        for i in (preferred or candidates)[:limit]
    ]
    return "\n".join(rows)


def _fallback_item(items: list[dict], exclude: set) -> dict:
    priority_cats = config.get("AI_PUSH_PRIORITY_CATS", [])
    candidates = [i for i in items if i.get("id") and i["id"] not in exclude and _price(i) > 0]
    for cat in priority_cats:
        hit = next((i for i in candidates if i.get("category") == cat), None)
        if hit:
            return hit
    return candidates[0] if candidates else (items[0] if items else {})


async def generate(session_id: str, ollama_semaphore, exclude_ids: list[str] | None = None, num_predict_override: int | None = None) -> dict:
    """
    呼叫 Ollama 選出 1 個推薦餐點並生成促購短句。
    回傳 {"recommendation_id": "MCDxxx", "push_text": "...", "status": "success|fallback"}
    """
    items   = await _get_menu_cached()
    by_id   = {i["id"]: i for i in items if i.get("id")}
    ids     = list(by_id)
    exclude = set(exclude_ids or [])
    fallback = _fallback_item(items, exclude)
    fb_id    = fallback.get("id") or (ids[0] if ids else "")
    fb_name  = fallback.get("name") or "推薦餐點"

    if not ids:
        return {"status": "error", "message": "menu is empty"}

    # RAG context（活動/特惠/主打資訊）
    rag_section = ""
    if config.get("RAG_ENABLED", False):
        try:
            from services.rag_provider import get_rag
            rag_context = await get_rag().query("推薦 活動 特惠 主打 套餐", top_k=2)
            if rag_context:
                rag_section = f"{rag_context}\n\n"
        except Exception:
            pass

    system = config.get("AI_PUSH_SYSTEM_PROMPT")
    mood_context = get_mood_context(session_id)
    mood_section = f"【顧客心情參考】\n{mood_context}\n\n" if mood_context else ""
    user = (
        f"{mood_section}"
        f"{rag_section}"
        "【菜單白名單】\n"
        f"{_menu_context(items)}\n\n"
        f"【本次排除 ID】{', '.join(exclude) or '無'}\n"
        "請挑 1 個適合現在推播的餐點。"
        f"push_text 必須是繁體中文，字數至少 {config.get('AI_PUSH_TEXT_MIN', 18)} 字、最多 {config.get('AI_PUSH_TEXT_MAX', 34)} 字，"
        f"不足 {config.get('AI_PUSH_TEXT_MIN', 18)} 字視為無效，請自然熱情地促購，不要出現 JSON 以外的文字。"
    )

    # push 獨立 token 預算：max 字數 × 4（中文 token 比 + JSON 結構 + 安全餘裕）
    _push_num_predict = num_predict_override if num_predict_override is not None else max(
        int(config.get("OLLAMA_NUM_PREDICT", 220)),
        int(config.get("AI_PUSH_TEXT_MAX", 34)) * 4
    )

    try:
        async with ollama_semaphore:
            raw = await asyncio.to_thread(
                ai_services.ask_ollama,
                system, user, "AI_PUSH",
                config.get("MODEL_NAME", "qwen3.5:4b"),
                _push_num_predict,
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
    _hard_cap = int(config.get("AI_PUSH_TEXT_MAX", 34)) * 2  # 給 LLM 一倍餘裕，仍有上限
    push_text = re.sub(r"\s+", " ", str(raw.get("push_text") or "")).strip()[:_hard_cap]
    if not push_text:
        push_text = f"{selected.get('name') or fb_name}現在很適合來一份！"

    return {
        "status": "success",
        "session_id": session_id,
        "recommendation_id": sel_id,
        "push_text": push_text,
    }


async def generate_three(session_id: str, ollama_semaphore) -> list[dict]:
    """呼叫 generate() 三次，累積 exclude_ids 確保不重複，回傳含 name/price/image 的完整項目清單。"""
    items_map = {i["id"]: i for i in await _get_menu_cached() if i.get("id")}
    results = []
    exclude: list[str] = []
    for _ in range(3):
        rec = await generate(session_id, ollama_semaphore, exclude_ids=exclude, num_predict_override=80)
        rec_id = rec.get("recommendation_id", "")
        if rec_id:
            exclude.append(rec_id)
        menu_item = items_map.get(rec_id, {})
        results.append({
            "id": rec_id,
            "name": menu_item.get("name", ""),
            "price": menu_item.get("price", 0),
            "image": menu_item.get("official_image_url") or menu_item.get("image", ""),
            "push_text": rec.get("push_text", ""),
            "category": menu_item.get("category", ""),
        })
    return results
