# R1-Omni 模組說明

`R1-Omni/` 是可選的多模態情緒分析服務，透過 `r1_omni_server.py` 提供與 UI_API 相容的 `/predict` HTTP 合約。

## 模組責任

- 載入本機 R1-Omni 模型權重。
- 接收 UI_API 傳入的影片路徑與問題。
- 回傳結構化情緒分析結果。
- 作為 Emotion-LLaMA 的替代 provider。

## 主要結構

```text
R1-Omni/
├── r1_omni_server.py       # /predict server
├── humanomni/              # 模型推論程式
├── models/                 # 本機模型權重
├── scripts/                # R1-Omni 原始訓練/微調腳本
├── src/                    # 原始子專案程式
├── yamls/                  # 模型設定
└── requirements.txt        # R1-Omni 依賴
```

## 安裝

```bash
conda create -n r1omni python=3.10 -y
conda activate r1omni
pip install -r R1-Omni/requirements.txt
```

GPU / CUDA 版本的 PyTorch 可能需要依照本機 CUDA 版本另外安裝。

## 啟動

建議從專案根目錄使用腳本：

```bash
bash scripts/start_r1_omni.sh
```

單獨啟動：

```bash
/home/oliver/anaconda3/envs/r1omni/bin/python R1-Omni/r1_omni_server.py --port 7890
```

## API 合約

```text
POST /predict
body: { video_path, question, skip_quality_check }
return: { result: string }
```

`result` 會被 UI_API 的 emotion service 解析成 facial、body、vocal、emotion、intensity 與 description。

## 維護重點

- 模型服務應獨立於 UI_API process。
- 商用部署時建議使用獨立 GPU 節點或容器。
- 模型權重與第三方授權需獨立確認。
- 不建議把訓練資料或大型 checkpoint 納入一般應用部署包。
