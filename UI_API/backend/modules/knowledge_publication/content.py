from __future__ import annotations

from typing import Any

from .module import PublicationError

CATEGORIES: tuple[dict[str, str], ...] = (
    {"id": "store_and_hours", "label": "門市與營業資訊", "icon": "store"},
    {"id": "menu_and_products", "label": "菜單與商品", "icon": "utensils"},
    {"id": "promotions", "label": "優惠與活動", "icon": "tag"},
    {"id": "payment_and_invoice", "label": "付款與發票", "icon": "receipt"},
    {"id": "membership", "label": "會員與權益", "icon": "user-check"},
    {"id": "order_and_pickup", "label": "訂單與取餐", "icon": "bag-shopping"},
    {"id": "delivery", "label": "外送服務", "icon": "truck"},
    {"id": "nutrition_and_allergens", "label": "營養與過敏原", "icon": "wheat-awn"},
    {"id": "other", "label": "其他", "icon": "folder"},
)

CONTENT_TYPES: tuple[dict[str, str], ...] = (
    {
        "id": "knowledge_article",
        "label": "知識文章",
        "description": "適合說明門市、商品或服務資訊。",
        "template": "主題\n\n請在這裡輸入完整說明，可使用小標題分段。",
    },
    {
        "id": "question_answer",
        "label": "問答",
        "description": "適合一個常見問題與直接答案。",
        "template": "問題：\n\n答案：",
    },
    {
        "id": "policy_rule",
        "label": "政策規則",
        "description": "適合限制、資格與例外條件。",
        "template": "規則名稱\n\n適用條件：\n規則內容：\n例外情況：",
    },
    {
        "id": "operating_procedure",
        "label": "作業流程",
        "description": "適合依序執行的工作步驟。",
        "template": "流程名稱\n\n1. 第一步\n2. 第二步\n3. 第三步",
    },
)


def normalize_values(*, category: str, content_type: str, title: str, content: str) -> dict[str, Any]:
    normalized_category = str(category or "").strip()
    if normalized_category not in {row["id"] for row in CATEGORIES}:
        raise PublicationError("invalid_category")
    normalized_type = str(content_type or "").strip()
    if normalized_type not in {row["id"] for row in CONTENT_TYPES}:
        raise PublicationError("invalid_content_type")
    normalized_content = str(content or "").strip()
    if not normalized_content:
        raise PublicationError("content_required")
    if len(normalized_content) > 200_000:
        raise PublicationError("content_too_long")
    normalized_title = str(title or "").strip()
    if not normalized_title:
        normalized_title = next(
            (line.strip(" #\t") for line in normalized_content.splitlines() if line.strip()),
            "未命名知識",
        )
    return {
        "category": normalized_category,
        "content_type": normalized_type,
        "title": normalized_title[:160],
        "content": normalized_content,
        "chunks": chunk_content(normalized_content, normalized_type),
    }


def chunk_content(content: str, content_type: str) -> list[dict[str, Any]]:
    text = str(content or "").strip()
    if not text:
        raise PublicationError("content_required")
    if content_type == "question_answer":
        parts = [text]
    elif content_type == "operating_procedure":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        groups: list[str] = []
        current: list[str] = []
        for line in lines:
            begins_step = line[:1].isdigit() and ("." in line[:4] or "、" in line[:4])
            if begins_step and current:
                groups.append("\n".join(current))
                current = []
            current.append(line)
            if len(current) >= 4:
                groups.append("\n".join(current))
                current = []
        if current:
            groups.append("\n".join(current))
        parts = groups or [text]
    else:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        parts = []
        buffer = ""
        target = 700 if content_type == "knowledge_article" else 500
        for paragraph in paragraphs or [text]:
            if buffer and len(buffer) + len(paragraph) > target:
                parts.append(buffer)
                buffer = ""
            buffer = f"{buffer}\n\n{paragraph}".strip()
        if buffer:
            parts.append(buffer)
    return [
        {
            "chunk_id": f"chunk-{index}",
            "position": index,
            "content": part,
            "characters": len(part),
        }
        for index, part in enumerate(parts, start=1)
    ]
