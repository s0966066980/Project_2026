# 後續改善例子與可新增模組

本文件集中整理目前專案後續可改善方向，以及可以新增的模組範例。目標是讓專案更接近商用部署、降低耦合、提高可測試性，並讓 Admin 與 Kiosk 的責任更清楚。

## 一、前端大型檔案拆分

### 目前狀況

- `UI_API/frontend/admin/admin.js` 承載會員、RAG、活動、推薦事件、設定與健康檢查。
- `UI_API/frontend/admin/admin.html` 同時承載多個後台區塊。
- `UI_API/frontend/kiosk/app.js` 仍集中 Kiosk 啟動、推薦、會員、語音、購物車與 checkout 協調。
- `UI_API/frontend/shared/styles.css` 同時包含 Kiosk、Admin 與共用樣式。

### 建議新增模組

```text
UI_API/frontend/admin/modules/
├── membersAdmin.js
├── ragAdmin.js
├── promotionsAdmin.js
├── recommendationEventsAdmin.js
├── healthAdmin.js
└── settingsAdmin.js

UI_API/frontend/kiosk/modules/
├── menuController.js
├── cartController.js
├── memberSessionController.js
├── recommendationDisplayController.js
├── voiceOrderingController.js
└── checkoutController.js
```

### 實作原則

- 先抽 API client，再抽 rendering，再抽 state。
- 保持既有 DOM id 與 API contract。
- 每拆一個模組就跑 JS 語法檢查與相關測試。

## 二、推薦系統商用化

### 目前狀況

推薦已整合會員偏好、熱門品項、活動、供應狀態、RAG offer 與事件紀錄，但仍需要更完整的策略控制與成效分析。

### 可新增模組

```text
UI_API/backend/services/recommendation_policy_service.py
UI_API/backend/services/recommendation_metrics_service.py
UI_API/backend/repositories/recommendation_metrics_repository.py
UI_API/backend/routes/recommendation_policy_routes.py
```

### 功能方向

- 推薦策略版本管理。
- 推薦命中率、忽略率、轉換率統計。
- 會員推薦與整體推薦的權重調整。
- 活動推薦與一般搭配推薦的優先序控制。
- Admin 可調整策略權重並查看效果。

## 三、會員商用安全

### 目前狀況

會員目前以手機登入為主。這符合目前需求，但商用上線前應補強安全與稽核。

### 可新增模組

```text
UI_API/backend/services/member_auth_policy_service.py
UI_API/backend/repositories/member_security_repository.py
UI_API/backend/routes/member_security_routes.py
```

### 功能方向

- 手機登入風險控管。
- per-phone / per-device rate limit。
- 會員資料查詢 audit trail。
- 未來可接 OTP 或 PIN，但目前不強制。

## 四、RAG 知識治理

### 目前狀況

RAG 已支援 Admin 更新與 Chroma 重建，但商用需要更完整的文件審核與版本治理。

### 可新增模組

```text
UI_API/backend/services/rag_version_service.py
UI_API/backend/repositories/rag_version_repository.py
UI_API/backend/routes/rag_version_routes.py
```

### 功能方向

- RAG 文件版本紀錄。
- 發布前審核流程。
- RAG rebuild 成功率與耗時紀錄。
- 回復上一版知識庫。
- 將 markdown 知識文件改以 txt/json/csv 管理，README 只做說明。

## 五、Admin 權限與操作稽核

### 目前狀況

Admin 已有 token 與 audit log 基礎，但尚未形成完整角色權限。

### 可新增模組

```text
UI_API/backend/services/admin_permission_service.py
UI_API/backend/repositories/admin_user_repository.py
UI_API/backend/routes/admin_user_routes.py
```

### 功能方向

- Admin 使用者帳號。
- 角色權限：店長、營運、客服、工程維運。
- 高風險操作二次確認。
- 匯出、刪除、清空 Chroma 等操作完整稽核。

## 六、部署與監控

### 目前狀況

目前以本機 shell script 啟動為主，適合開發與 demo。商用應拆成多服務。

### 可新增模組

```text
deploy/
├── docker-compose.yml
├── nginx/
├── systemd/
└── monitoring/
```

### 功能方向

- UI_API、PostgreSQL、Ollama、Emotion-LLaMA / R1-Omni 分開部署。
- 健康檢查 endpoint 接監控。
- PostgreSQL 自動備份與還原演練。
- log retention 與錯誤告警。

## 七、測試補強

### 目前狀況

後端測試覆蓋推薦、會員、RAG、健康檢查與安全邊界。前端目前以語法檢查為主。

### 可新增模組

```text
UI_API/tests/browser/
├── test_kiosk_startup.py
├── test_member_login_flow.py
├── test_recommendation_card.py
└── test_admin_rag_flow.py
```

### 功能方向

- Playwright Kiosk smoke test。
- Admin RAG rebuild smoke test。
- 會員登入與 checkout 流程測試。
- 推薦卡片曝光與事件紀錄測試。

## 建議執行順序

1. 先拆 Admin 前端大型檔案。
2. 再拆 Kiosk 前端大型檔案。
3. 補推薦 metrics 與策略管理。
4. 補 Admin 權限與操作稽核。
5. 補 RAG 版本治理。
6. 建立 Docker / systemd / monitoring 部署模板。
7. 補 browser smoke test。
