# R1-Omni 多模態情緒服務

`R1-Omni/` 是 Project_2026 唯一的多模態情緒分析執行單元，透過 `r1_omni_server.py` 提供 UI_API 可使用的 HTTP 推論能力。

此服務是可選 local provider，不是 checkout 必要條件。

## 責任

- 載入本機 R1-Omni 模型權重。
- 接收影片/多模態推論請求。
- 回傳可正規化的情緒分析結果。

不負責：

- 寫入會員、訂單、活動或營運資料。
- 直接決定推薦、價格、付款或介入結果。
- 保存不必要的原始媒體或 PII。

## 結構

```text
R1-Omni/
├── r1_omni_server.py
├── humanomni/
├── models/             # 本機權重，不提交 Git
├── scripts/
├── src/
├── yamls/
└── requirements.txt
```

## Docker Runtime

R1-Omni 不使用主機 Conda。`docker/R1-Omni.Dockerfile` 提供 CPU 與 NVIDIA GPU targets，完整 Project stack 由 Repository 根目錄執行：

```bash
bash docker/scripts/setup.sh        # GPU，主要路徑
bash docker/scripts/setup.sh --cpu  # CPU 相容模式
```

必要權重由主機提供，預設位置：

```text
R1-Omni/models/
├── R1-Omni-0.5B/
├── bert-base-uncased/
├── siglip-base-patch16-224/
└── whisper-large-v3/
```

權重不會進入 image，Compose 會唯讀掛載至 `/models`。完整必要檔案清單見 [Repository README](../README.md#r1-omni-權重)。

只重建並啟動 R1 GPU service：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  up --build -d --wait r1-omni
```

## 現行 API 合約

```text
POST /predict

request:
{ video_path, question, skip_quality_check }

response:
{ result: string }
```

UI_API 會將 `result` 正規化為 facial、body、vocal、emotion、intensity 與 description 等欄位。長期應改為版本化且明確的結構化 response，避免依賴自由文字解析。

## 整合與商用規則

- UI_API 透過 Multimodal Evidence Port/Adapter 呼叫，不讓核心 domain 依賴模型 SDK。
- R1-Omni 只以獨立 Docker service 部署；UI_API 透過內部 service URL 呼叫。
- 建立 timeout、並行限制、健康檢查、fallback、structured error 與 latency/error metrics。
- 模型不可用時，核心點餐流程應可降級。
- 不以未驗證的 client file path 作為長期跨服務 contract；正式部署應使用受控 upload/object reference。
- 模型權重、原始碼、資料集與衍生模型的商業授權需獨立確認。
- 影像、影片、音訊與情緒結果遵守最小收集、明確用途與保留政策。

目前 UI_API provider/gateway 與 capability 邊界見 [UI_API 核心應用](../UI_API/README.md#架構方向)。
