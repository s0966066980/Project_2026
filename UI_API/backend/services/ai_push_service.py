"""AI 推播服務 — 透過 Ollama 生成底部欄推播餐點與理由。"""
import asyncio
import random
import re
import time

import ai_services
import config
from repositories import menu_repository
from services import member_service
from services.popular_service import get_top_items

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


def _weighted_pick(items: list[dict], exclude: set, top_weight: int = 3, member_ids=None) -> dict | None:
    """加權隨機選品：TOP3 權重 top_weight 倍、會員常點權重 MEMBER_PUSH_WEIGHT 倍，其餘等機率。"""
    candidates = [i for i in items if i.get("id") and i["id"] not in exclude and _price(i) > 0]
    if not candidates:
        return None
    top_ids = {t["id"] for t in get_top_items(3)}
    member_set = set(member_ids or [])
    member_weight = int(config.get("MEMBER_PUSH_WEIGHT", 4))
    pool = []
    for item in candidates:
        weight = 1
        if item["id"] in top_ids:
            weight = max(weight, top_weight)
        if item["id"] in member_set:
            weight = max(weight, member_weight)
        pool.extend([item] * weight)
    return random.choice(pool)


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

    # 加權隨機選品：TOP3 品項機率提高，其他等機率
    member = member_service.get_session_member(session_id)
    member_ids = member_service.member_top_ids(member) if member else []
    picked = await asyncio.to_thread(_weighted_pick, items, exclude, 3, member_ids)
    if not picked:
        picked = fallback
    sel_id   = picked.get("id") or fb_id
    sel_name = picked.get("name") or fb_name

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
    member_section = ""
    if member:
        ctx = member_service.member_push_context(member)
        if ctx:
            member_section = f"{ctx}\n\n"
    user = (
        f"{rag_section}"
        f"{member_section}"
        f"【指定推播餐點】{sel_id}｜{sel_name}\n\n"
        f"push_text 必須是繁體中文，字數至少 {config.get('AI_PUSH_TEXT_MIN', 18)} 字、最多 {config.get('AI_PUSH_TEXT_MAX', 34)} 字，"
        f"自然熱情地促購此餐點，不要出現 JSON 以外的文字。"
        f'直接輸出：{{"recommendation_id":"{sel_id}","push_text":"..."}}'
    )

    # push 獨立 token 預算
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

    _hard_cap = int(config.get("AI_PUSH_TEXT_MAX", 34)) * 2
    if not isinstance(raw, dict) or "error" in raw:
        push_text = f"{sel_name}現在很適合來一份，搭配點餐超值！"
        status = "fallback"
    else:
        push_text = re.sub(r"\s+", " ", str(raw.get("push_text") or "")).strip()[:_hard_cap]
        if not push_text:
            push_text = f"{sel_name}現在很適合來一份！"
        status = "success"

    return {
        "status": status,
        "session_id": session_id,
        "recommendation_id": sel_id,
        "push_text": push_text,
    }


async def generate_three(session_id: str, ollama_semaphore) -> list[dict]:
    """呼叫 generate() 三次，累積 exclude_ids 確保不重複，回傳含 name/price/image 的完整項目清單。
    generate() 依賴 prompt 告知 Ollama 排除清單，但模型不保證遵守；
    此層作為最後防線：若拿到重複或空 ID，直接從剩餘白名單隨機補一品。
    """
    items_map = {i["id"]: i for i in await _get_menu_cached() if i.get("id")}
    all_ids = [i for i in items_map if items_map[i].get("price", 0) > 0]
    results = []
    used_ids: set[str] = set()
    exclude: list[str] = []

    for _ in range(3):
        rec = await generate(session_id, ollama_semaphore, exclude_ids=exclude, num_predict_override=80)
        rec_id = rec.get("recommendation_id", "")

        # 後置去重：若 ID 無效或已出現，從剩餘可用品項隨機補取
        if not rec_id or rec_id not in items_map or rec_id in used_ids:
            available = [i for i in all_ids if i not in used_ids]
            if available:
                rec_id = random.choice(available)
                rec["push_text"] = f"{items_map[rec_id].get('name', '推薦餐點')}現在很適合來一份！"

        if rec_id:
            used_ids.add(rec_id)
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
