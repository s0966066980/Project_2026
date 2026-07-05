# Admin frontend 模組說明

`frontend/admin/` 是門市後台介面。

## 主要功能

- 系統設定。
- 會員管理。
- RAG 知識庫管理。
- 結構化活動管理。
- 推薦事件 dashboard。
- 供應狀態管理。
- 健康檢查與維運工具。

## 主要檔案

- `admin.html`：Admin 頁面結構。
- `admin.js`：Admin 互動、API 呼叫與 rendering。

## 後續拆分方向

```text
admin/modules/
├── membersAdmin.js
├── ragAdmin.js
├── promotionsAdmin.js
├── recommendationEventsAdmin.js
├── healthAdmin.js
└── settingsAdmin.js
```

## 維護規則

- Admin 可以顯示診斷資訊，但不要暴露顧客端不需要的模型細節。
- 高風險操作需要 audit log。
- 清空 Chroma、刪除活動、匯出會員等功能需要權限控制。
