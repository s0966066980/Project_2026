# UI_API frontend 模組說明

`frontend/` 是 UI_API 的瀏覽器端程式，包含 Kiosk、Admin、共用 API client、共用樣式與圖片資源。

## 主要結構

```text
frontend/
├── admin/          # Admin 後台
├── kiosk/         # Kiosk 顧客自助點餐端
├── shared/         # 共用 API client / UI helper / style
├── menu_images/    # 菜單圖片
├── mcd_categories/ # 分類圖片
└── package.json    # 前端工具
```

## 維護規則

- Kiosk 與 Admin 不互相 import。
- 共用 HTTP、API、realtime 與 UI helper 放在 `shared/`。
- 大型畫面應拆成 modules，不要把所有 rendering 塞在單一檔案。
- 前端變更後至少執行 `node --check`。
