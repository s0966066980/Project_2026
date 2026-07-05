# Emotion-LLaMA 模組說明

`Emotion-LLaMA/` 是可選的情緒分析模型服務。UI_API 可透過啟動腳本將 `EMOTION_PROVIDER` 切換為 `emotion_llama`，並呼叫 Emotion-LLaMA 的 `/predict` 服務。

## 模組責任

- 提供情緒分析模型推論能力。
- 接收 UI_API 傳入的影片或影像分析請求。
- 回傳可被 UI_API 解析的情緒描述。
- 作為 POS 風險事件與情緒分析流程的可選模型 backend。

## 主要結構

```text
Emotion-LLaMA/
├── app_EmotionLlamaClient.py   # 推論服務入口
├── eval_configs/               # 推論設定
├── minigpt4/                   # 模型相關程式
├── checkpoints/                # 本機模型權重
└── requirements.txt            # Python 依賴
```

## 安裝

```bash
conda create -n emotion_ollama python=3.10 -y
conda activate emotion_ollama
pip install -r Emotion-LLaMA/requirements.txt
```

## 啟動

建議從專案根目錄使用腳本：

```bash
bash scripts/start_emotion_llama.sh
```

單獨啟動：

```bash
cd Emotion-LLaMA
/home/oliver/anaconda3/envs/emotion_ollama/bin/python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889
```

## 維護重點

- 模型服務不應直接寫入 UI_API 的業務資料。
- 商用部署建議與 UI_API 分開 process 或容器。
- 模型權重、資料集與原始專案授權需在商用前獨立確認。
- 大型 checkpoint 不應放入 production image 的應用層。
