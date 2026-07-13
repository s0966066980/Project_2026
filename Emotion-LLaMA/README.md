# Emotion-LLaMA 模型服務

`Emotion-LLaMA/` 是 Project_2026 的可選情緒分析執行單元。UI_API 可將 `EMOTION_PROVIDER` 設為 `emotion_llama`，透過 HTTP 呼叫模型服務。

## 責任

- 載入 Emotion-LLaMA 模型與本機 checkpoint。
- 接收影像/影片相關推論請求。
- 回傳 UI_API 可正規化的情緒描述。
- 提供模型層健康與錯誤資訊。

不負責：

- 寫入會員、訂單、活動或營運資料。
- 決定推薦、價格、付款或介入的最終商業規則。
- 保存不必要的原始影像、音訊或 PII。

## 結構

```text
Emotion-LLaMA/
├── app_EmotionLlamaClient.py
├── eval_configs/
├── minigpt4/
├── checkpoints/        # 本機權重，不提交 Git
└── requirements.txt
```

## 安裝

```bash
conda create -n emotion_ollama python=3.10 -y
conda activate emotion_ollama
pip install -r Emotion-LLaMA/requirements.txt
```

GPU/CUDA/PyTorch 版本需依部署環境確認。

## 啟動

建議：

```bash
bash scripts/start_emotion_llama.sh
```

單獨啟動：

```bash
cd Emotion-LLaMA
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889
```

實際 Interpreter 可用腳本環境變數設定，避免在正式文件依賴單一使用者絕對路徑。

## 整合與商用規則

- UI_API 應透過 Emotion Port/Adapter 呼叫，不讓核心 domain 依賴模型 SDK。
- 商用部署使用獨立 process、container 或 GPU node。
- 建立 timeout、並行限制、健康檢查、fallback、structured error 與 latency/error metrics。
- Request/response contract 需版本化並做 schema validation。
- 模型不可用時，核心點餐流程應可降級，不得整體失效。
- 模型權重、原始碼、資料集與衍生模型的商業授權需獨立確認。
- 影像/影片保存需符合告知、同意、用途、最小收集與保留政策。

架構決策見 [`docs/adr/0003-ai-provider-port-adapter.md`](../docs/adr/0003-ai-provider-port-adapter.md)。
