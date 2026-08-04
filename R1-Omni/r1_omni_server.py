"""
 R1-Omni /predict 伺服器。

合約（與 UI_API/backend/services/emotion_service.py 的 _call_http 對齊）：
  POST /predict  {video_path, question, skip_quality_check, media_mode}
       → {"result": <字串>}
  result 內容：
    成功  → JSON 字串 {"facial","body","vocal","emotion","intensity","description"}
    錯誤  → "[R1_OMNI_ERROR] ..."
    跳過  → "[R1_OMNI_SKIP] ..."

R1-Omni 原生輸出 <think>…</think><answer>情緒</answer>：
  <answer> → emotion，<think> → description。
  若模型回自由文字（無 <answer>），emotion 留空、description 帶全文，
  讓 emotion_service 的 Ollama 後備流程再補結構化欄位。

啟動：
  /home/oliver/anaconda3/envs/r1omni/bin/python r1_omni_server.py --port 7890
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

# 模型皆為本地檔，強制離線避免連 HF（與 inference.py 一致）
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)                 # 讓 humanomni 套件可被 import、相對模型路徑可用
sys.path.insert(0, HERE)

MODEL_PATH = os.path.join(HERE, "models", "R1-Omni-0.5B")
BERT_PATH = os.path.join(HERE, "models", "bert-base-uncased")

# R1-Omni 訓練時使用的標準指令；POS 未帶 question 時的後備
DEFAULT_INSTRUCT = (
    "As an emotional recognition expert; throughout the video, which emotion "
    "conveyed by the characters is the most obvious to you? Output the thinking "
    "process in <think> </think> and final emotion in <answer> </answer> tags."
)

_model = None
_processor = None
_tokenizer = None
_bert_tokenizer = None
_infer_lock = threading.Lock()   # 單 GPU 模型，序列化推論


def load_model() -> None:
    """懶加載：第一次呼叫（或啟動預載）時載入模型。"""
    global _model, _processor, _tokenizer, _bert_tokenizer
    if _model is not None:
        return
    from humanomni import model_init
    from humanomni.utils import disable_torch_init
    from transformers import BertTokenizer

    print(f"🔄 載入 R1-Omni 模型: {MODEL_PATH}")
    disable_torch_init()
    _bert_tokenizer = BertTokenizer.from_pretrained(BERT_PATH)
    _model, _processor, _tokenizer = model_init(MODEL_PATH)
    print("✅ R1-Omni 模型載入完成")


def is_allowed_video_path(path: str) -> bool:
    """只允許讀取受信任目錄下的影片，防止任意檔案讀取（path traversal）。

    POS 上傳的截片由後端寫進系統 tempdir（見 emotion_routes.py），
    故預設允許目錄為 tempdir；可用 R1_OMNI_ALLOWED_VIDEO_DIR 覆寫。
    """
    allowed_dir = os.getenv("R1_OMNI_ALLOWED_VIDEO_DIR") or tempfile.gettempdir()
    try:
        real_path = os.path.realpath(path or "")
        real_allowed_dir = os.path.realpath(allowed_dir)
        return os.path.commonpath([real_path, real_allowed_dir]) == real_allowed_dir
    except Exception:
        return False


def _sanitize_video(path: str) -> tuple[str, str | None]:
    """
    用 ffmpeg 把輸入影片重新編碼成乾淨的 mp4（重建時間戳、丟壞幀）。

    POS rolling-buffer 截下的 .webm 常缺 duration/frame-count 元資料，
    decord（R1-Omni 的影片讀取器）會直接讀取失敗。先正規化即可解決。
    回傳 (可用路徑, 需清理的暫存路徑或 None)。失敗時回傳原路徑。
    """
    fd, out_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-err_detect", "ignore_err",
        "-fflags", "+genpts+discardcorrupt+igndts",
        "-i", path,
        "-t", os.getenv("R1_OMNI_MAX_INPUT_SEC", "10"),
        "-vf", "scale=448:-2:force_original_aspect_ratio=decrease",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-avoid_negative_ts", "make_zero", "-movflags", "+faststart",
        "-af", "aresample=async=1:first_pts=0,asetpts=N/SR/TB",
        "-c:a", "aac", "-ar", "16000", "-ac", "1",
        out_path,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, text=True, timeout=30)
        return out_path, out_path
    except Exception as e:
        try:
            os.remove(out_path)
        except OSError:
            pass
        print(f"⚠️ R1-Omni 影片正規化失敗（改用原檔）: {e}")
        return path, None


def _parse_output(out: str) -> dict:
    """R1-Omni 文字輸出 → 結構化欄位。"""
    out = str(out or "").strip()
    think = re.search(r"<think>(.*?)</think>", out, re.DOTALL)
    answer = re.search(r"<answer>(.*?)</answer>", out, re.DOTALL)
    emotion = answer.group(1).strip() if answer else ""
    description = think.group(1).strip() if think else out
    return {
        "facial": "",
        "body": "",
        "vocal": "",
        "emotion": emotion,
        "intensity": "",
        "description": description,
    }


def process_video_question(
    video_path: str,
    question: str,
    skip_quality_check: bool = False,
    media_mode: str = "video_audio",
) -> str:
    """核心推論：回傳給下游的 result 字串。"""
    if not video_path or not os.path.exists(video_path):
        return f"[R1_OMNI_ERROR] video_not_found: {video_path}"
    if not is_allowed_video_path(video_path):
        return f"[R1_OMNI_ERROR] path_not_allowed: {video_path}"

    load_model()
    instruct = question.strip() if (question and question.strip()) else DEFAULT_INSTRUCT
    start_ts = time.time()
    normalized_mode = str(media_mode or "video_audio").strip().lower()
    if normalized_mode not in {"video_audio", "audio_only"}:
        return f"[R1_OMNI_ERROR] unsupported_media_mode: {normalized_mode}"
    # 影音輸入先正規化再交給 decord；audio-only 不建立空白影像包裝。
    safe_path, cleanup_path = (
        (video_path, None)
        if normalized_mode == "audio_only"
        else _sanitize_video(video_path)
    )
    try:
        from humanomni import mm_infer
        with _infer_lock:
            audio = _processor["audio"](safe_path)[0]
            video_tensor = None if normalized_mode == "audio_only" else _processor["video"](safe_path)
            output = mm_infer(
                video_tensor,
                instruct,
                model=_model,
                tokenizer=_tokenizer,
                modal="audio" if normalized_mode == "audio_only" else "video_audio",
                question=instruct,
                bert_tokeni=_bert_tokenizer,
                do_sample=False,
                audio=audio,
            )
        structured = _parse_output(output)
        elapsed_ms = int((time.time() - start_ts) * 1000)
        print(f"✅ R1-Omni 推論完成: elapsed_ms={elapsed_ms}, "
              f"emotion={structured.get('emotion')!r}, raw={str(output)[:80]!r}")
        return json.dumps(structured, ensure_ascii=False)
    except Exception as e:
        print(f"❌ R1-Omni 推論失敗: {e}")
        return f"[R1_OMNI_ERROR] inference_failed: {e}"
    finally:
        if cleanup_path:
            try:
                os.remove(cleanup_path)
            except OSError:
                pass


def parse_args():
    parser = argparse.ArgumentParser(description="R1-Omni /predict Server")
    parser.add_argument("--port", type=int, default=7890, help="監聽 port")
    parser.add_argument("--host", default="0.0.0.0", help="監聽 host")
    args, _ = parser.parse_known_args()
    return args


if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    from pydantic import BaseModel

    class _InferRequest(BaseModel):
        video_path: str
        question: str = ""
        skip_quality_check: bool = False
        media_mode: str = "video_audio"

    api = FastAPI()

    @api.get("/health")
    def _health():
        return {
            "status": "ok",
            "model_loaded": _model is not None,
            "capabilities": ["audio_only", "video_audio"],
        }

    @api.post("/predict")
    def _predict(req: _InferRequest):
        result = process_video_question(
            req.video_path,
            req.question,
            req.skip_quality_check,
            req.media_mode,
        )
        return {"result": result}

    args = parse_args()
    print(f"🔧 R1-Omni 推論伺服器  port={args.port}")
    print("🔄 預先載入 R1-Omni 模型…")
    load_model()
    uvicorn.run(api, host=args.host, port=args.port)
