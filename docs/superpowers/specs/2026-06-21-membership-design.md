# 會員制（Membership）設計規格

**日期：** 2026-06-21
**狀態：** 設計定稿，待實作計畫
**作者：** Oliver + Claude

## 目標

在自助點餐 kiosk 引入第一個「持久性顧客身分」：顧客按「開始點餐」後可選擇**會員點餐**（手機號碼登入／快速註冊）或**直接點餐**（維持現狀）。會員的歷史點餐紀錄會驅動個人化推薦（常點加權 + 「您的常點」快速重點 + LLM context 注入），後台新增「會員」分頁查看每位會員的光臨、消費與常點紀錄。

## 背景：目前系統現況

- **身分是暫時的**：`session_id` 為隨機 `pos_xxxxx`，結帳後 `archive_session` 即丟棄。唯一持久紀錄是 `session_logs.json`（每筆結帳一列）。
- **推薦是全域的**：`ai_push_service._weighted_pick` 將全域 TOP3 熱門品項（`popular_service` 跨所有 `session_logs` 統計）加權 3 倍，與顧客個人無關。
- **kiosk 入口**：`startupOverlay` → `startBtn`（開始點餐）的 `ui.startBtn.onclick` 直接載入菜單進入點餐頁。
- **後台**：單一 FastAPI `app` 同時掛在 8000/8001 兩個 port；admin 端點以 `require_admin_token(request)` 保護（非分離 app）。側邊欄目前 4 個分頁：統計／設定／RAG／Emotion-LLaMA。

會員制即是在此之上疊加一層「以手機號碼為主鍵的持久會員檔案」，**完全不影響訪客流程**。

## 全域約束（Global Constraints）

- **分層職責**：routes 只解析請求 + 呼叫 service；service 不直接讀寫 JSON（透過 repository）；repository 不放業務邏輯、不做 AI 呼叫。
- **菜單白名單**：「您的常點」與個人化推薦的品項一律來自 `menu.json`（MCDxxx），不允許 LLM 幻覺餐點。
- **XSS**：會員暱稱為使用者輸入，render 進 DOM（kiosk 歡迎列、後台表格）一律用 `textContent` / `escapeHTML`，不得用 innerHTML 直接插入。
- **隱私**：kiosk 顯示顧客自己輸入的完整手機號碼；**後台一律遮罩中間碼**（`0912-***-678`）。
- **port 隔離**：8000=POS、8001=admin 邏輯不動。會員登入/註冊為 POS 端點（公開）；會員列表/詳情為 admin 端點（`require_admin_token`）。
- **讀設定統一用 `config.get("KEY")`**，新增動態設定走 `DEFAULT_SETTINGS`；POS 需讀的 key 加入 `PUBLIC_SETTINGS_KEYS`。
- **不在 checkout 加阻擋邏輯**：會員紀錄更新為結帳成功後的「附帶副作用」，失敗或逾時都不得阻擋結帳完成。
- **功能可關閉**：`MEMBER_ENABLED=false` 時，kiosk 跳過選擇頁直接進菜單（等同現狀），後台會員分頁可隱藏。
- **ES module 安全**：跨模組 import 只在函式體內解參用（沿用現有 state.js / 循環 import 慣例）。

## 資料模型

### 新檔案：`learning_data/members.json`（runtime，不提交 git）

會員紀錄陣列，每筆：

```json
{
  "phone": "0912345678",
  "nickname": "小明",
  "created_at": "2026-03-01T10:00:00",
  "visit_count": 12,
  "total_spend": 3720,
  "last_visit_at": "2026-06-20T18:42:00",
  "item_freq": { "MCD001": 8, "MCD012": 6, "MCD030": 5 },
  "orders": [
    { "timestamp": "2026-06-20T18:42:00", "cart_ids": ["MCD001", "MCD021"], "total": 200, "is_success": true }
  ]
}
```

- `phone`：主鍵，正規化為純 10 碼數字字串。
- `item_freq`：**個人化的唯一真實來源**——以「光臨次數」累積：每次結帳對 `final_cart_ids`（前端 `getCartIds()` 回傳 **去重的 id 集合**，不含數量）中每個 id 各 +1。語意為「該會員有幾次點餐包含此品項」，正好對應「您的常點」的 `×N` 顯示。「您的常點」與推薦加權都讀它。
- `orders`：近期訂單（上限 `MEMBER_ORDERS_KEEP`，預設 20），僅供後台詳情顯示。可與 `item_freq` 分歧（item_freq 為完整累積，orders 被裁切），這是刻意設計。
- `visit_count` / `total_spend` / `last_visit_at`：結帳成功時遞增/更新的執行統計。

### Session → 會員綁定（記憶體）

沿用現有 `session_db`（記憶體 dict）模式：`member_service` 維護記憶體 `_session_member: dict[session_id → phone]`。
- 登入/註冊成功時寫入綁定。
- `ai_push` / voice / checkout 以 `session_id` 反查會員，**現有端點簽章不需大改**。
- `archive_session`（結帳）時清除綁定。

## 後端架構（依分層）

### Repository：`backend/repositories/member_repository.py`
JSON 存取（atomic write，沿用 `log_repository` 的 tmp+rename + mtime cache 模式）。
- `get_all_members() -> list`
- `get_member(phone) -> dict | None`
- `upsert_member(record) -> dict`
- 無業務邏輯、無 AI 呼叫。

### Service：`backend/services/member_service.py`
業務邏輯主體：
- `normalize_phone(raw) -> str`：去非數字、驗證 10 碼。
- `mask_phone(phone) -> str`：`0912-***-678`（後台用）。
- `login(session_id, phone) -> dict`：查會員；存在則綁定 session、回傳 `{found, member}`（含 `usuals`）；不存在回 `{found: false}`。
- `register(session_id, phone, nickname) -> dict`：暱稱留空時自動給 `會員{phone後4碼}`；建立 record、綁定、回傳 member（usuals 空）。
- `build_usuals(member, limit) -> list`：依 `item_freq` 排序、join `menu_repository` 取 name/price/image，過白名單，回傳前 `MEMBER_USUALS_COUNT` 筆（含 `count`）。
- `get_session_member(session_id) -> dict | None`：供 ai_push/voice/checkout 反查。
- `finalize_checkout(session_id, final_cart_ids, total, is_success)`：結帳成功後更新 visit_count/total_spend/last_visit/item_freq/orders，清除綁定。**total 不能由 `cart_ids` 反推**（id 已去重、不含數量），由前端結帳時送出的 `cart_total` 帶入（見下方 checkout 整合）。
- `member_push_context(member) -> str`：產生 LLM 注入字串（如「此顧客為會員 小明，常點：大麥克套餐、薯條」）。
- `admin_list() -> list` / `admin_detail(phone) -> dict`：後台聚合（含遮罩、常點排行、近期訂單）。

### Routes：`backend/routes/member_routes.py`（`create_router(deps)` 沿用既有 pattern）
POS 端點（公開，prefix `/api`）：
- `POST /api/member/login` — body: `session_id`, `phone` → `{found, member?}`。
- `POST /api/member/register` — body: `session_id`, `phone`, `nickname?` → `{member}`。

Admin 端點（`require_admin_token`）：
- `GET /api/members` — 列表（遮罩手機、暱稱、visit_count、total_spend、last_visit、top favorites）。
- `GET /api/members/{phone}` — 詳情（profile、item_freq 排行、近期 orders）。

於 `main.py` 以 `app.include_router(member_routes.create_router(_deps))` 掛載。

### 個人化整合點（修改既有檔案）

1. **「您的常點」列**：login/register response 直接帶 `usuals`，前端 render，一鍵加入沿用現有購物車 add。
2. **常點加權**：`ai_push_service._weighted_pick` 增加參數或在 `generate()` 內以 `session_id` 反查會員；若有綁定會員，將其 `item_freq` top 品項加入加權池（權重 `MEMBER_PUSH_WEIGHT`，預設 4，與全域 TOP3 並存）。
3. **LLM context 注入**：`ai_push_service.generate()` 組 `user` prompt 時，若有綁定會員，插入 `member_service.member_push_context(member)` 一行，讓 push_text 帶會員名與常點。
4. **結帳整合**：
   - `POST /api/checkout` 新增 Form 欄位 `cart_total`（前端以既有 `cartManager.getCartTotal()` 計算後送出），`process_checkout` 多收一參數往下傳。
   - `checkout_service.process_checkout` 在記錄 log 後，若 `member_service.get_session_member(session_id)` 有值，呼叫 `finalize_checkout(session_id, cart_list, cart_total, is_success)`。此為附帶副作用，**任何失敗都不得阻擋結帳回應**（try/except 包覆，沿用既有 timeout 容錯風格）。

### 設定（`config.DEFAULT_SETTINGS` 新增）

| key | 預設 | 公開? | 說明 |
|---|---|---|---|
| `MEMBER_ENABLED` | `true` | 是 | 總開關；false 時 kiosk 跳過選擇頁、後台隱藏會員分頁 |
| `MEMBER_USUALS_COUNT` | `8` | 是 | 「您的常點」顯示品項數 |
| `MEMBER_PUSH_WEIGHT` | `4` | 否 | 會員常點品項於 ai_push 加權倍率 |
| `MEMBER_ORDERS_KEEP` | `20` | 否 | 每位會員保留近期訂單筆數 |

`MEMBER_ENABLED`、`MEMBER_USUALS_COUNT` 加入 `PUBLIC_SETTINGS_KEYS`。

## 前端架構

### 新模組：`frontend/pos/member.js`（ES module）
會員流程獨立模組，避免 app.js 膨脹（沿用 P5 模組化慣例）：
- 選擇頁、手機登入、快速註冊三個 overlay 的顯示/事件。
- 呼叫 `/api/member/login`、`/api/member/register`。
- render「您的常點」列與頂部會員列。
- import `state` from `state.js`、共用 api/ui，與 app.js 既有 export（cartManager、sessionId、getRuntimeSettings 等）。

### `state.js` 新增欄位
- `member: null`（登入後為 `{phone, nickname, visit_count, usuals: [...]}`）。

### `index.html` 新增畫面（沿用 startupOverlay 的 overlay 模式）
- `memberChoiceOverlay`（畫面 1：會員/訪客選擇）
- `memberLoginOverlay`（畫面 2：手機數字鍵盤 + 略過逃生口）
- `memberRegisterOverlay`（畫面 3：快速註冊）
- 菜單頂部會員列 + 「您的常點」橫向列容器（畫面 4）。

### 流程改動：`ui.startBtn.onclick`
- 若 `MEMBER_ENABLED`：按「開始點餐」→ 顯示 `memberChoiceOverlay`（不立即進菜單）。
  - 選「直接點餐」→ 走現有 init（媒體權限、loadMenu、進菜單），`state.member = null`。
  - 選「會員點餐」→ `memberLoginOverlay` → 登入/註冊成功 → 走現有 init + render 會員列與「您的常點」。
  - 登入頁「略過，直接點餐」→ 等同訪客。
- 若 `MEMBER_ENABLED=false`：維持現狀（直接進菜單）。
- 重型 init（媒體、菜單載入、aiPush、passive listener）在做出選擇後才執行。

### Admin（`admin.html` / `admin.js`）
- 側邊欄新增第 5 個 `nav-item`：`data-page="members"`（👤 會員），`MEMBER_ENABLED=false` 時隱藏。
- 列表頁：4 張統計卡（總會員數／本週活躍／平均客單／最愛品項）+ 搜尋框 + 表格（手機遮罩/暱稱/光臨/累計消費/最近光臨/常點品項/查看）。fetch `GET /api/members`。
- 詳情頁：左欄 profile + 常點排行長條，右欄近期訂單（含「推播命中」沿用 `is_success`）。fetch `GET /api/members/{phone}`。
- 暱稱/品名 render 一律 `escHtml`。

## 錯誤處理

- 手機號碼格式錯誤（非 10 碼）→ 登入頁就地提示，不送 request。
- `members.json` 不存在或損毀 → repository 回空陣列（沿用 `log_repository._read_list` 容錯）。
- `finalize_checkout` 任何例外 → 記 log 但結帳照常回成功。
- ai_push 反查會員失敗 → 退回現有全域加權行為（個人化是加分，不是必要路徑）。
- `MEMBER_ENABLED=false` → 所有會員端點仍存在但前端不觸發；後台分頁隱藏。

## 測試策略

無前端測試框架，JS 以 `node --check` 驗證語法 + 人工瀏覽器驗證。後端：
- `member_service`：`normalize_phone` / `mask_phone` / `build_usuals`（排序+白名單+上限）/ `finalize_checkout`（item_freq 累積、orders 裁切、visit/spend 遞增）/ `register` 暱稱預設。
- `member_repository`：upsert 後可 get、atomic write 不損毀。
- ai_push 加權：有會員綁定時常點品項進入加權池。
- checkout 整合：finalize 例外不影響結帳回應。
- `python3 -m py_compile` 全數通過。

## 範圍外（YAGNI）

- 會員點數/紅利系統、會員專屬價格與優惠（本次未選）。
- email / 生日 / 性別等額外註冊欄位。
- 跨裝置同步、會員登出後台編輯/刪除（後台僅檢視）。
- QR code / 實體卡識別。

## 已知安全性限制（原型階段刻意接受）

會員登入（`POST /api/member/login`）僅以手機號碼識別，**無第二因子**。後果：

- **帳號列舉**：回應 `{found: true/false}` 會洩漏某手機是否為會員（自助註冊流程本身也會，難以完全消除）。
- **冒用**：任何人在 kiosk 輸入他人手機即可被綁定為該會員，讀取其「您的常點」與點餐紀錄，並以其身分影響推薦。

資料屬低敏感（暱稱 + 點餐紀錄，無付款資料 / 個資），且本系統為原型。經與需求方確認後，**原型階段接受此風險並記錄**（2026-06-22）。

**正式上線前必須補強**（擇一或併用）：
- 簡訊 OTP：登入時發送驗證碼，驗證通過才 `bind_session` 並回傳 profile；未驗證者僅回 `{found: bool}`。
- 註冊時設定 PIN：登入需「手機 + PIN」。
- 對 `/api/member/login` 做 per-IP / per-phone rate limit 與失敗稽核。
```
