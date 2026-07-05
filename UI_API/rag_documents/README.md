# RAG documents 模組說明

`rag_documents/` 是 RAG 知識庫的原始文件來源。Admin 後台可清空 Chroma 並重新讀取此目錄內容。

## 重要規則

後端 `rag_document_service` 會略過 `README.md`，因此本 README 只做說明，不會被寫入 Chroma。

可被讀取的知識文件格式：

- `.txt`
- `.json`
- `.csv`
- `.md`、`.markdown`

本次文件整理後，為了避免規劃文件與知識文件混雜，RAG 知識內容優先使用 `.txt`、`.json`、`.csv`。

## 主要目錄

```text
rag_documents/
├── faq/            # 常見問題
├── menu/           # 菜單搭配與說明
├── nutrition/      # 營養與過敏原
├── promotions/     # 結構化活動與 verified offer
└── store_policy/   # 門市規則
```

## 已保留的知識內容

- `faq/payment.txt`：支付與結帳常見問題。
- `menu/pairing-guidance.txt`：菜單搭配推薦原則。
- `store_policy/opening-hours.txt`：早餐與一般菜單供應時間。
- `nutrition/example-allergen.csv`：過敏原示例。
- `promotions/example-member-offer.json`：會員活動示例。

## 重建方式

1. 開啟 Admin。
2. 進入 `RAG 知識庫`。
3. 點擊 `清空 Chroma 並重新讀取 RAG 文件`。

## 維護規則

- 活動與優惠優先使用 JSON，讓推薦系統可以驗證 item id、category、日期與狀態。
- FAQ、政策與菜單說明可使用 TXT。
- 不要把未確認的折扣或優惠寫入知識庫。
- 商用環境應建立發布審核流程。
