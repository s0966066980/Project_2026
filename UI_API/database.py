import os
import json
import time
import uuid
from datetime import datetime
import config
import rag_service
from repositories import log_repository, menu_repository
from services import recommendation_service

def _now_iso():
    return datetime.now().isoformat()


_HISTORY_CACHE_TTL_SEC = 30.0
_history_cache: dict[str, tuple[float, object]] = {}


def _cached_history(key: str, builder):
    now = time.time()
    cached = _history_cache.get(key)
    if cached and now - cached[0] < _HISTORY_CACHE_TTL_SEC:
        return cached[1]
    value = builder()
    _history_cache[key] = (now, value)
    return value



def build_menu_item_text(item):
    prep_minutes = item.get("prep_time_minutes", item.get("prep_minutes", ""))
    return (
        f"ID: {item.get('id')}\n"
        f"名稱: {item.get('name')}\n"
        f"描述: {item.get('description')}\n"
        f"營養: {item.get('nutrition', '')}\n"
        f"製作時間: {prep_minutes}分鐘\n"
        f"價格: {item.get('price')}元"
    )

def build_full_menu_context() -> str:
    menu_items = menu_repository.get_menu()
    if not menu_items:
        return "【完整菜單白名單】目前沒有菜單資料。"
    lines = ["【完整菜單白名單】", "只能使用以下餐點 ID 與名稱，不得創造其他餐點。"]
    for item in menu_items:
        lines.append(build_menu_item_text(item))
    return "\n\n".join(lines)

def _active_rag_documents():
    return [doc for doc in get_rag_docs() if not doc.get("deleted")]

def get_global_rag_context(source_types: tuple[str, ...] = ("manual",)) -> str:
    """Manual RAG docs are treated as global operating rules, not vector-only facts."""
    docs = [
        doc for doc in _active_rag_documents()
        if doc.get("source_type") in source_types
    ]
    if not docs:
        return ""
    lines = ["【RAG 全域規則】", "以下規則每次都必須遵守，優先級高於一般檢索補充："]
    for idx, doc in enumerate(docs[-12:], 1):
        text = (doc.get("reviewed_text") or doc.get("source_text") or "").strip()
        if text:
            lines.append(f"{idx}. {text}")
    return "\n".join(lines)

def _ensure_rag_docs_from_menu(menu_items):
    os.makedirs(config.LEARNING_DATA_DIR, exist_ok=True)
    if not os.path.exists(config.RAG_DOCS_JSON_PATH):
        save_rag_docs([])
        return True
    return False

def init_rag_system(force_rebuild: bool = False):
    print("Initializing RAG System...")
    os.makedirs(config.LEARNING_DATA_DIR, exist_ok=True)
    default_menu = [{"id": "M00", "name": "預設餐點", "description": "請至後台設定", "nutrition": "無", "price": 0}]
    menu_items = menu_repository.ensure_default_menu(default_menu)
    created_rag_docs = _ensure_rag_docs_from_menu(menu_items)
    if created_rag_docs:
        force_rebuild = True

    rag_service.init(_active_rag_documents(), force_rebuild=force_rebuild)

def update_menu(new_menu_data, rebuild_rag: bool = True):
    """Save menu to disk. By default rebuilds RAG synchronously; callers that
    want to defer the rebuild (typically request handlers) should pass
    rebuild_rag=False and trigger a background rebuild themselves."""
    menu_repository.save_menu(new_menu_data)
    if rebuild_rag:
        init_rag_system(force_rebuild=True)


def retrieve_menu_from_rag(query: str, emotion_desc: str = "") -> str:
    global_context = get_global_rag_context()

    def fallback_context():
        menu_items = menu_repository.get_menu()
        if not menu_items:
            return global_context or "Cannot retrieve from database."
        context = "【參考菜單資訊】\n"
        for idx, item in enumerate(menu_items[:int(config.get("RAG_TOP_K", 3))]):
            context += (
                f"選項 {idx+1}:\n"
                f"ID: {item.get('id')}\n"
                f"名稱: {item.get('name')}\n"
                f"描述: {item.get('description')}\n"
                f"製作時間: {item.get('prep_time_minutes', item.get('prep_minutes', ''))}分鐘\n"
                f"價格: {item.get('price')}元\n\n"
            )
        return "\n\n".join(part for part in [global_context, context.strip()] if part)

    try:
        result = rag_service.retrieve(query, emotion_desc)
    except Exception as e:
        print(f"⚠️ RAG 查詢失敗，改用菜單 fallback: {e}")
        return fallback_context()

    return "\n\n".join(part for part in [global_context, result.get("context", "").strip()] if part)

def get_rag_docs():
    try:
        with open(config.RAG_DOCS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def save_rag_docs(docs):
    os.makedirs(config.LEARNING_DATA_DIR, exist_ok=True)
    with open(config.RAG_DOCS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=4)



def upsert_reviewed_rag_doc(source_type: str, source_id: str, source_text: str, review_result: dict, metadata: dict | None = None):
    docs = get_rag_docs()
    now = _now_iso()
    reviewed_text = (review_result.get("reviewed_text") or source_text).strip()
    status = review_result.get("status", "approved")
    notes = review_result.get("notes", "")

    existing = next(
        (doc for doc in docs if doc.get("source_type") == source_type and doc.get("source_id") == source_id and not doc.get("deleted")),
        None
    )
    if existing:
        existing.update({
            "source_text": source_text,
            "reviewed_text": reviewed_text,
            "review_status": status,
            "review_notes": notes,
            "metadata": metadata or existing.get("metadata", {}),
            "updated_at": now
        })
        doc = existing
    else:
        doc = {
            "id": str(uuid.uuid4()),
            "source_type": source_type,
            "source_id": source_id,
            "source_text": source_text,
            "reviewed_text": reviewed_text,
            "review_status": status,
            "review_notes": notes,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
            "deleted": False
        }
        docs.append(doc)

    save_rag_docs(docs)
    log_repository.append_rag_review_log({
        "timestamp": now,
        "doc_id": doc["id"],
        "source_type": source_type,
        "source_id": source_id,
        "source_text": source_text,
        "reviewed_text": reviewed_text,
        "review_status": status,
        "review_notes": notes,
        "metadata": metadata or {},
        "raw_review": review_result.get("_raw_content", "")
    })
    return doc

def delete_rag_doc(doc_id: str, rebuild: bool = True):
    docs = get_rag_docs()
    changed = False
    for doc in docs:
        if doc.get("id") == doc_id:
            doc["deleted"] = True
            doc["updated_at"] = _now_iso()
            changed = True
            break
    if changed:
        save_rag_docs(docs)
        if rebuild:
            init_rag_system(force_rebuild=True)
    return changed

def _build_successful_experiences() -> str:
    try:
        logs = log_repository.get_session_logs()
        successes = [log for log in logs if log.get("is_success", False)][-3:]
        if not successes:
            return "尚無歷史成功經驗。"
        exp_text = "【過去成功的推播範例】\n"
        for s in successes:
            exp_text += f"- 當顧客歷史情緒包含「{s.get('emotions_summary', '')}」，推播了餐點 {s.get('pushed_ids')} 並且顧客最終購買了 {s.get('final_cart_ids')}。\n"
        return exp_text
    except Exception:
        return "經驗資料庫讀取失敗。"


def get_successful_experiences() -> str:
    """提取過去成功的推薦經驗作為 Ollama 的學習依據"""
    return _cached_history("successful_experiences", _build_successful_experiences)


def _build_order_pairing_context(limit: int = 8) -> str:
    logs = log_repository.get_session_logs()
    paired_orders = []
    item_counts = {}
    for log in logs[-80:]:
        cart_ids = log.get("final_cart_ids") or []
        if not isinstance(cart_ids, list):
            continue
        unique_ids = sorted(set(cart_ids))
        for item_id in unique_ids:
            item_counts[item_id] = item_counts.get(item_id, 0) + 1
        if len(unique_ids) >= 2:
            paired_orders.append(unique_ids)

    menu_names = {str(item.get("id")): item.get("name", "") for item in menu_repository.get_menu()}
    lines = ["【歷史點餐紀錄】"]
    if item_counts:
        popular = sorted(item_counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        lines.append("常被購買品項：" + "、".join(
            f"{item_id}({menu_names.get(item_id, '')})x{count}" for item_id, count in popular
        ))
    if paired_orders:
        lines.append("常見搭配購物車：")
        for ids in paired_orders[-limit:]:
            lines.append("- " + " + ".join(f"{item_id}({menu_names.get(item_id, '')})" for item_id in ids))
    if len(lines) == 1:
        lines.append("目前尚無足夠歷史點餐紀錄，請根據菜單類型做合理搭配。")
    return "\n".join(lines)


def get_order_pairing_context(limit: int = 8) -> str:
    return _cached_history(f"order_pairing:{limit}", lambda: _build_order_pairing_context(limit))

def record_final_checkout(
    session_id: str,
    pushed_ids: list,
    cart_ids: list,
    session_history: list,
):
    """
    結帳時進行全局評估，策略：每位顧客只記錄一筆結果。
    判斷標準：本次服務期間，所有推播過的餐點，只要有任一出現在最終購物車中，即視為成功。
    不記錄每次推播細節，避免同一顧客多次推播造成統計膨脹。
    """
    log_entry = recommendation_service.build_checkout_log_entry(
        session_id=session_id,
        pushed_ids=pushed_ids,
        cart_ids=cart_ids,
        session_history=session_history,
    )
    return log_repository.append_session_log(log_entry)



def clear_rag_storage():
    """Clear reviewed RAG docs, review logs, and all Chroma versions, then rebuild menu docs."""
    rag_service.release()
    for path in [
        config.RAG_DOCS_JSON_PATH,
        config.RAG_REVIEW_LOG_PATH,
        config.RAG_VECTOR_META_PATH,
    ]:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
    rag_service.clear_vector_storage()
    init_rag_system(force_rebuild=True)
    return True

def load_pdf_chunks(file_path: str, file_name: str = "") -> list[dict]:
    return rag_service.load_pdf_chunks(file_path, file_name)
