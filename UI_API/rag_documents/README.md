# RAG Source Documents

This directory stores the version-controlled source documents used to rebuild the RAG knowledge base.

The live vector database is generated under `UI_API/learning_data/chroma_rag/` and should not be edited manually or committed to Git.

## Recommended Formats

- Markdown (`.md`) for policies, FAQ, menu notes, SOP, and customer-service knowledge.
- JSON (`.json`) for structured promotions, menu supplements, and rule-like knowledge.
- CSV (`.csv`) for tabular nutrition, allergen, pricing, and store-policy data.

## Directory Guide

```text
rag_documents/
├── customer_service/  # Service recovery scripts, refund rules, escalation notes
├── faq/               # Common customer questions and approved answers
├── menu/              # Menu supplements, descriptions, aliases, pairing guidance
├── nutrition/         # Nutrition, allergen, ingredients, dietary notes
├── promotions/        # Campaigns, coupons, member offers, valid dates
└── store_policy/      # Opening hours, payment, pickup, refund, kiosk rules
```

## Rebuild

Use the Admin dashboard instead of a command-line import script:

1. Open Admin.
2. Go to `RAG 知識庫`.
3. Click `清空 Chroma 並重新讀取 RAG 文件`.

The backend reads Markdown, JSON, CSV, and TXT files from this directory and rebuilds `UI_API/learning_data/chroma_rag/`.

## Writing Pattern

Keep each document focused and explicit:

```text
標題：早餐供應時間
分類：營業規則
內容：早餐供應時間為每日 05:00 至 10:30。
限制條件：部分店鋪與特殊節日可能不同。
相關品項：滿福堡、薯餅、熱咖啡
```

Prefer concrete dates, item IDs, category names, and constraints over long prose.
