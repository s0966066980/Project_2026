"""將菜單所有品項批次匯入 RAG。
執行：conda run -n emotion_ui python tools/import_menu_to_rag.py
"""
import asyncio
import sys
import os

# config.py 在 UI_API/，backend/ 在 UI_API/backend/
_repo    = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_root    = os.path.join(_repo, "UI_API")
_backend = os.path.join(_root, "backend")
sys.path.insert(0, _root)
sys.path.insert(0, _backend)

from repositories.menu_repository import get_menu
from services.rag_provider import get_rag


def _item_to_doc(item: dict) -> str:
    """把一道菜的欄位轉成 RAG 可查詢的純文字段落。"""
    lines = [
        f"品項名稱：{item.get('name', '')}",
        f"菜單 ID：{item.get('id', '')}",
        f"分類：{item.get('category', '')}",
        f"價格：${item.get('price', '—')}",
    ]
    if item.get("description"):
        lines.append(f"描述：{item['description']}")
    if item.get("nutrition"):
        lines.append(f"營養資訊：{item['nutrition']}")
    if item.get("prep_time_minutes"):
        lines.append(f"製作時間：約 {item['prep_time_minutes']} 分鐘")
    if item.get("aliases"):
        lines.append(f"常見別名：{' / '.join(item['aliases'])}")
    if item.get("availability_note"):
        lines.append(f"供應說明：{item['availability_note']}")
    if item.get("price_note"):
        lines.append(f"價格說明：{item['price_note']}")
    return "\n".join(lines)


async def main():
    items = get_menu()
    rag = get_rag()
    total = len(items)
    print(f"開始匯入 {total} 道菜單品項到 RAG…")

    ok = err = 0
    for i, item in enumerate(items, 1):
        iid  = item.get("id", f"unknown_{i}")
        name = item.get("name", "")
        doc  = _item_to_doc(item)
        try:
            await rag.add_document(
                content     = doc,
                source_id   = f"menu_{iid}",
                source_type = "menu_item",
                metadata    = {
                    "item_id"  : iid,
                    "name"     : name,
                    "category" : item.get("category", ""),
                    "price"    : str(item.get("price", "")),
                },
            )
            ok += 1
            print(f"  [{i:3}/{total}] ✓ {iid} {name}")
        except Exception as e:
            err += 1
            print(f"  [{i:3}/{total}] ✗ {iid} {name}：{e}")

    count = await rag.count()
    print(f"\n完成！成功 {ok} 筆，失敗 {err} 筆。RAG 目前共 {count} 筆文件。")


if __name__ == "__main__":
    asyncio.run(main())
