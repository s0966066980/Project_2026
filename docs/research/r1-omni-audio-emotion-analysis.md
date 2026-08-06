# R1-Omni 是否能可靠做純音訊情緒分析

## 摘要

結論先講：**不能根據目前一手證據，判定 R1-Omni 已被證明可「可靠」執行純音訊情緒分析**。較精確的說法是：

1. **Upstream 模型原生能力**：有原生 `audio` 推理路徑，但官方公開文件與論文主軸仍是 **video+audio 的多模態情緒辨識**，沒有提供足夠的純音訊受控驗證。  
2. **本地服務宣告能力**：本地 contract 與 `/health` **有宣告 `audio_only`**，adapter 也會把 `media_mode` 傳給 `/predict`。  
3. **是否已被驗證且可靠**：**沒有**。本地測試是 adapter/降級 contract 測試，不是實際 `audio_only` 正確率或穩定性驗證；目前產品路徑也幾乎都走 `video_audio`。

## 三層判定

| 面向 | 判定 | 依據 |
| --- | --- | --- |
| 1. Upstream 原生能力 | **有，但證據只到「可跑」而非「可靠」** | 底層 `mm_infer` 支援 `modal='audio'`，並在 audio mode 使用 `<audio>` token；但官方 README / model card 公開推理例子仍是 `video_audio`，且 README 的 ToDo 仍列出 `single-video and single-audio modality data`。見 [R1-Omni/humanomni/__init__.py](/home/oliver/Project_2026/R1-Omni/humanomni/__init__.py:41)、[官方 README](https://github.com/HumanMLLM/R1-Omni)、[官方 model card](https://huggingface.co/StarJiaxing/R1-Omni-0.5B)、[paper](https://arxiv.org/pdf/2503.05379.pdf)。 |
| 2. 本地服務宣告 `audio_only` 能力 | **有宣告，但目前不是主要實際路徑** | request schema 定義 `media_mode: "video_audio" | "audio_only"`，gateway 會把 `media_mode` 傳到 `/predict`，本地 `r1_omni_server` 的 `/health` 也宣告 `["audio_only", "video_audio"]`。但 `analyze_event()` 未覆寫 `media_mode`，因此走預設 `video_audio`；`analyze_live_diagnostic()` 也明確要求 `video_audio`。見 [multimodal_evidence.py](/home/oliver/Project_2026/UI_API/backend/models/multimodal_evidence.py:10)、[multimodal_evidence_gateway.py](/home/oliver/Project_2026/UI_API/backend/services/multimodal_evidence_gateway.py:29)、[emotion_service.py](/home/oliver/Project_2026/UI_API/backend/services/emotion_service.py:143)、[r1_omni_server.py](/home/oliver/Project_2026/R1-Omni/r1_omni_server.py:198)。 |
| 3. 是否已被驗證且可靠 | **否** | 本地 `test_r1_omni_contract.py` 只測 fake adapter 的正常/降級行為，沒有真實音訊、沒有 `audio_only`、沒有準確率或穩定性測試；設定合約也不允許把 `r1_omni` 暴露成可選 provider。見 [test_r1_omni_contract.py](/home/oliver/Project_2026/UI_API/tests/test_r1_omni_contract.py:1)、[test_settings_contract.py](/home/oliver/Project_2026/UI_API/tests/test_settings_contract.py:8)。 |

## 純音訊是怎麼餵給模型的

不是「先包成靜態影片檔再送進模型」；較準確的描述是：

- 本地 `r1_omni_server` 在 `media_mode="audio_only"` 時，**不做影片正規化，也不建立空白影片檔包裝**；它直接對同一路徑抽音訊，並以 `modal="audio"` 呼叫 `mm_infer`，且 `video_tensor=None`。[r1_omni_server.py](/home/oliver/Project_2026/R1-Omni/r1_omni_server.py:198)
- 但在底層 `mm_infer`，`modal == 'audio'` 時仍會放入一個**全零的 video tensor placeholder**，同時使用 `<audio>` token。也就是說，**介面上是 native audio mode，但模型實作仍保留一個零值視覺槽位**，不是完全沒有 vision slot。[humanomni/__init__.py](/home/oliver/Project_2026/R1-Omni/humanomni/__init__.py:41)
- 官方 repo 內附的 `inference.py` 也顯示其公開推理腳本對 audio-only 並不成熟：CLI 仍要求 `--video_path`，且先做 `processor['video'](...)`，之後才根據 `args.modal` 決定是否同時抽音訊。[R1-Omni/inference.py](/home/oliver/Project_2026/R1-Omni/inference.py:11)

**因此：它不是 blank/static video wrapper 檔案方案；但也不是完全脫離視覺輸入位形的純音訊實作。**

## 是否依賴語音語意（speech semantics）

### Upstream

Upstream 論文與公開說明把任務描述成 **visual + audio** 的情緒辨識，並多次把語音內容、語氣、字幕文本一起拿來解釋推論；但**沒有提供受控實驗去分離「語意內容」與「純聲學/副語言線索」的貢獻**。[paper](https://arxiv.org/pdf/2503.05379.pdf)、[官方 README](https://github.com/HumanMLLM/R1-Omni)、[官方 model card](https://huggingface.co/StarJiaxing/R1-Omni-0.5B)

### 本地服務

本地語音助手路徑**通常會依賴 speech semantics**，因為：

- `_build_ordering_emotion_question()` 會把 `speech_text` 直接嵌進 prompt 的 `STT 資料` 欄位。[emotion_service.py](/home/oliver/Project_2026/UI_API/backend/services/emotion_service.py:80)
- `_analyze_current_voice_emotion_pair()` 預設模式是 `media_plus_stt`；只有在沒 transcript 或關閉 `EMOTION_INCLUDE_STT` 時才退回 `media_only`，`paired` 模式甚至同時跑有/無 STT 兩條路。[voice_service.py](/home/oliver/Project_2026/UI_API/backend/services/voice_service.py:115)

補充：本地 `admin_live_diagnostic` 有刻意避免把逐字稿餵回 evidence prompt，並寫明「只依輸入媒體判斷」；但它依然**明確要求 `video_audio`，不是 `audio_only`**。[emotion_service.py](/home/oliver/Project_2026/UI_API/backend/services/emotion_service.py:582)

## 受控證據到底有什麼

### 有的

- 官方 paper 提供整體情緒辨識結果，包含 RAVDESS 指標，證明模型對某些情緒資料集有表現。[paper](https://arxiv.org/pdf/2503.05379.pdf)
- 本地程式碼有後續評估掛鉤，例如 `exact_label_agreement`，但要有至少 30 個可用人工標註才算 `measured`。[emotion_service.py](/home/oliver/Project_2026/UI_API/backend/services/emotion_service.py:560)

### 沒有的

- **沒有本地 `audio_only` 單元測試、整合測試、回歸測試。**
- **沒有本地 checked-in benchmark 結果證明純音訊可靠。**
- **沒有 upstream 論文中的 audio-only ablation 或 modality-isolation study。**
- 官方 repo 內的 `eval_ravedess.py` 雖然是 RAVDESS 評估，但實作仍同時取 `video_tensor` 與 `audio_tensor`，並以 `modal='video_audio'` 呼叫 `mm_infer`；它**不是 audio-only 驗證**。[eval_ravedess.py](/home/oliver/Project_2026/R1-Omni/humanomni/eval/eval_ravedess.py:170)

## 本地產品路徑的實際限制

- 語音背景情緒分析在排程時，會先用 `ffprobe` 檢查檔案是否有可解碼的 **video track**；沒有就直接返回，不進行情緒分析。這代表目前主要語音產品路徑**不接受真正「純音訊檔」作為情緒分析輸入**。[voice_service.py](/home/oliver/Project_2026/UI_API/backend/services/voice_service.py:49)
- `analyze_event()` 建立 `MultimodalEvidenceRequest` 時沒有設定 `media_mode`，因此沿用 dataclass 預設 `video_audio`。[multimodal_evidence.py](/home/oliver/Project_2026/UI_API/backend/models/multimodal_evidence.py:10)、[emotion_service.py](/home/oliver/Project_2026/UI_API/backend/services/emotion_service.py:143)

## 結論

如果問題是「**R1-Omni 能不能可靠做純音訊情緒分析？**」：

- **Upstream 模型層**：可以說它**具備 audio mode 的原生推理能力**，但官方公開證據仍不足以支持「可靠純音訊情緒分析」這個較強主張。
- **本地服務層**：可以說它**宣告了 `audio_only` capability**，而且 server 端真的有對應路徑；但目前應用層主要呼叫鏈沒有把這條路徑當成正式產品能力使用。
- **驗證/可靠性層**：**沒有足夠受控證據**。本地沒有真實 `audio_only` 測試與準確率驗證；upstream 也沒有把 audio-only 與 video+audio 清楚分離後的可靠性證明。

換句話說，**目前最保守且可被一手證據支撐的結論是：R1-Omni 有「可執行的 audio path」，但沒有被證明是「可靠的純音訊情緒分析能力」。**

## Sources

- 本地 service / adapter / contracts / tests
  - [UI_API/backend/models/multimodal_evidence.py](/home/oliver/Project_2026/UI_API/backend/models/multimodal_evidence.py:10)
  - [UI_API/backend/services/multimodal_evidence_gateway.py](/home/oliver/Project_2026/UI_API/backend/services/multimodal_evidence_gateway.py:29)
  - [UI_API/backend/services/emotion_service.py](/home/oliver/Project_2026/UI_API/backend/services/emotion_service.py:80)
  - [UI_API/backend/services/voice_service.py](/home/oliver/Project_2026/UI_API/backend/services/voice_service.py:49)
  - [UI_API/tests/test_r1_omni_contract.py](/home/oliver/Project_2026/UI_API/tests/test_r1_omni_contract.py:1)
  - [UI_API/tests/test_settings_contract.py](/home/oliver/Project_2026/UI_API/tests/test_settings_contract.py:8)
- 本地 checked-in R1-Omni 原始碼
  - [R1-Omni/r1_omni_server.py](/home/oliver/Project_2026/R1-Omni/r1_omni_server.py:198)
  - [R1-Omni/humanomni/__init__.py](/home/oliver/Project_2026/R1-Omni/humanomni/__init__.py:41)
  - [R1-Omni/inference.py](/home/oliver/Project_2026/R1-Omni/inference.py:11)
  - [R1-Omni/humanomni/eval/eval_ravedess.py](/home/oliver/Project_2026/R1-Omni/humanomni/eval/eval_ravedess.py:170)
- 官方來源
  - [HumanMLLM/R1-Omni 官方 repository](https://github.com/HumanMLLM/R1-Omni)
  - [StarJiaxing/R1-Omni-0.5B 官方 model card](https://huggingface.co/StarJiaxing/R1-Omni-0.5B)
  - [R1-Omni 論文（arXiv 2503.05379）](https://arxiv.org/pdf/2503.05379.pdf)
