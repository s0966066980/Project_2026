# Project_2026 — Smart Ordering Kiosk

單店本地端 Kiosk Pilot：Modular Monolith，本機 / LAN 原生 process。

## Overview

- **Kiosk**：菜單、購物車、會員、推薦、語音、結帳
- **Admin**：登入、設定、供應、活動、訂單、RAG、裝置
- **Backend**：`/api/v1` → Module Application API → Port → PostgreSQL / Local adapters
- **Optional AI**：Ollama、Emotion-LLaMA / R1-Omni（不阻擋 Checkout）
