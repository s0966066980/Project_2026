import asyncio
import json
import re

import ai_services
import config
from utils.text_utils import to_traditional_lite


def _looks_like_menu_json(text: str) -> bool:
    lower = str(text or "").lower()
    return (
        ("{" in lower and "}" in lower)
        and any(key in lower for key in ['"price"', "'price'", '"description"', "'description'", '"name"', "'name'", '"id"', "'id'"])
    )


def _reviewed_text_is_corrupted(source_text: str, reviewed_text: str, source_type: str) -> bool:
    reviewed = str(reviewed_text or "")
    source = str(source_text or "")
    if not reviewed.strip():
        return True
    if source_type == "manual" and not source.lstrip().startswith(("{", "[")) and _looks_like_menu_json(reviewed):
        return True
    if source_type in ("manual", "customer_service", "voice_order") and len(reviewed) > max(80, len(source) * 3):
        return True
    if source_type == "manual":
        source_terms = [x for x in re.findall(r"[\u4e00-\u9fff]{2,}", source) if len(x) >= 2]
        if source_terms and not any(term in reviewed for term in source_terms[:4]):
            return True
    return False


def sanitize_rag_review_result(source_text: str, source_type: str, result: dict) -> dict:
    clean = dict(result or {})
    reviewed_text = clean.get("reviewed_text", source_text)
    if isinstance(reviewed_text, (dict, list)):
        reviewed_text = json.dumps(reviewed_text, ensure_ascii=False)
    reviewed_text = to_traditional_lite(str(reviewed_text or source_text).strip())
    source_text_trad = to_traditional_lite(source_text)

    if _reviewed_text_is_corrupted(source_text_trad, reviewed_text, source_type):
        reviewed_text = source_text_trad.strip()
        clean["status"] = "revised"
        clean["notes"] = "Ollama 審查結果疑似改寫成不存在的菜單或格式異常，已保留原始規則文本。"

    clean["reviewed_text"] = reviewed_text
    clean["notes"] = to_traditional_lite(clean.get("notes", ""))
    if not clean.get("status"):
        clean["status"] = "approved"
    return clean


async def review_rag_text(source_text: str, source_type: str, source_id: str, ollama_semaphore=None) -> dict:
    if not config.get("RAG_REVIEW_ENABLED", True):
        return {
            "status": "approved",
            "reviewed_text": source_text,
            "notes": "RAG review disabled.",
        }

    system_prompt = (
        "你是智慧點餐系統的 RAG 文本審查員。\n"
        "請審查輸入文本，移除或修正任何可能造成 AI 幻覺的內容。\n"
        "若是菜單資料，必須保留真實 ID、名稱、價格、描述，不得新增不存在的餐點。\n"
        "若來源類型是 manual，該文本是系統規則或後台補充知識，不是菜單資料；禁止改寫成 id/name/price/description JSON，也禁止創造餐點。\n"
        "若來源類型是 voice_order，該文本是顧客語音點餐對話紀錄；請保留顧客說法、系統回覆、成功加入購物車的餐點與 cart_actions，修正簡體字與明顯錯字即可，不得創造菜單品項。\n"
        "所有中文都必須使用繁體中文，禁止輸出簡體字。\n"
        "輸出只能是合法 JSON：\n"
        "{\n"
        "  \"status\": \"approved 或 revised 或 rejected\",\n"
        "  \"reviewed_text\": \"審查後可保存到 RAG 的版本\",\n"
        "  \"notes\": \"審查原因或修改摘要\"\n"
        "}"
    )
    user_prompt = (
        f"【來源類型】{source_type}\n"
        f"【來源 ID】{source_id}\n\n"
        f"【待審查文本】\n{source_text}"
    )

    async def _ask():
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, ai_services.ask_ollama, system_prompt, user_prompt, "RAG_REVIEW"
        )

    if ollama_semaphore:
        async with ollama_semaphore:
            result = await _ask()
    else:
        result = await _ask()

    if "error" in result:
        return sanitize_rag_review_result(source_text, source_type, {
            "status": "review_failed",
            "reviewed_text": source_text,
            "notes": result.get("error", "RAG review failed."),
            "_raw_content": result.get("raw_content", ""),
        })
    if not result.get("reviewed_text"):
        result["reviewed_text"] = source_text
    if not result.get("status"):
        result["status"] = "approved"
    return sanitize_rag_review_result(source_text, source_type, result)
