"""以 LLM 起草推薦詞——這是唯一允許模型碰推播文案的地方（見 ADR-0016）。

Kiosk 端只查表，不會走到這裡。單筆產生與一鍵批次共用同一段邏輯，避免兩條路徑對字數限制、
促銷用語規則或截斷處理各有一套解讀。
"""

import re

import config
from models.llm import LLMRequest
from services import llm_gateway_service, llm_routing_service, rag_guard_service


def _text(value) -> str:
    return str(value or "").strip()


# Gateway 的 safe_error 是給程式判斷的代碼，直接丟到畫面上等於要操作者去猜。
# 每一條都必須說明「發生什麼」以及「可以怎麼辦」。
_FAILURE_MESSAGES = {
    "response_truncated": (
        "模型還沒寫完就達到長度上限。推理型模型（例如 gpt-oss、nemotron）的思考過程會佔用同一份額度，"
        "請到「AI 模型」分頁改用非推理型模型，或縮短推薦詞字數上限。"
    ),
    "missing_credential": "雲端模型缺少 API 金鑰。請在 .env 設定 NVIDIA_API_KEY 後重啟服務。",
    "provider_timeout": "模型回應逾時。請稍後再試，或改用較小的模型。",
    "invalid_provider_payload": "模型回應的格式無法解析。可能是模型不支援 JSON 輸出，請改用其他模型。",
}


def failure_message(safe_error: str) -> str:
    code = _text(safe_error)
    detail = _FAILURE_MESSAGES.get(code) or (f"模型回報：{code}" if code else "模型沒有回覆內容。")
    return f"產生推薦詞失敗。{detail}"


def build_prompt(item: dict, *, slot: str, offer: dict | None, text_min: int, text_max: int) -> str:
    detail = "、".join(
        filter(
            None,
            [
                f"名稱：{_text(item.get('name'))}",
                f"分類：{_text(item.get('category'))}",
                f"介紹：{_text(item.get('description'))}",
                f"營養：{_text(item.get('nutrition'))}",
            ],
        )
    )
    if slot == "campaign" and offer:
        rule = (
            f"此餐點適用的活動：{_text(offer.get('title'))}。"
            f"文案可以提到這個活動，但不得自行新增活動未載明的折扣、金額或期限。"
        )
    else:
        rule = (
            "文案絕對不可出現優惠、折扣、特價、促銷、買一送一、限時優惠、加購價、半價等字眼，"
            "只描述餐點本身的口味、份量與適合的情境。"
        )
    return (
        f"【餐點資料】{detail}\n\n"
        f"請寫一句繁體中文促購短句，至少 {text_min} 字、最多 {text_max} 字。{rule}"
        f'直接輸出 JSON：{{"push_text":"..."}}'
    )


def draft_copy(
    item: dict,
    *,
    slot: str = "base",
    offer: dict | None = None,
) -> tuple[str, str, list[str]]:
    """回傳 (推薦詞, 錯誤訊息, 未驗證促銷用語)。錯誤訊息非空時代表這一筆失敗。"""

    text_min = int(config.get("AI_PUSH_TEXT_MIN", 18))
    text_max = int(config.get("AI_PUSH_TEXT_MAX", 34))
    response = llm_gateway_service.generate(
        LLMRequest(
            task="ai_push_copy",
            system_prompt=str(config.get("AI_PUSH_SYSTEM_PROMPT") or ""),
            user_prompt=build_prompt(item, slot=slot, offer=offer, text_min=text_min, text_max=text_max),
            model_policy=llm_routing_service.configured_policy(),
            timeout_seconds=float(config.get("OLLAMA_TIMEOUT", 30) or 30),
            prompt_version="push_copy_authoring-v1",
            expect_json=True,
            response_tag="AI_PUSH",
            model_name=str(config.get("MODEL_NAME", "qwen3.5:4b") or "qwen3.5:4b"),
            # Reasoning models bill their hidden thinking against this same budget, and a
            # 40-50 character sentence can easily cost 700+ tokens of it. Sizing this off the
            # sentence length alone truncated the answer before it was ever written.
            max_tokens=max(2048, text_max * 8),
            max_retries=0,
            scope_safe_context={"item_id": _text(item.get("id")), "slot": slot},
        ),
    )
    parsed = response.parsed if isinstance(response.parsed, dict) else {}
    draft = re.sub(r"\s+", " ", _text(parsed.get("push_text")))[: text_max * 2]
    if response.safe_error or not draft:
        return "", failure_message(response.safe_error), []
    terms = rag_guard_service.unverified_promotion_terms(draft) if slot == "base" else []
    return draft, "", terms
