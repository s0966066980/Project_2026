"""
Emotion-LLaMA Gradio Client — 精簡 API 版
只保留透過 REST API 執行推論所需的最小功能。

正確呼叫流程（依據 conversation.py 實際實作）：
  1. 建立 Conversation
  2. append_message 加入 video placeholder
  3. chat.encode_img(img_list)  ← img_list[0] = video_path string
                                   內部 pop 字串、處理 video+audio、append tensor 回 img_list
  4. chat.ask(question, conv)
  5. chat.answer(conv, img_list)
"""

import argparse
import os
import subprocess
import tempfile
import threading
import time
import torch


# =========================================================
# 解析命令行參數
# =========================================================
def parse_args():
    parser = argparse.ArgumentParser(description="Emotion-LLaMA Gradio Server")
    parser.add_argument("--cfg-path", default="eval_configs/demo.yaml", help="配置文件路徑")
    parser.add_argument("--port", type=int, default=7889, help="監聽 port")
    parser.add_argument("--options", nargs="+", help="覆蓋配置設定，格式為 xxx=yyy")
    args, _ = parser.parse_known_args()
    return args


# =========================================================
# 模型懶加載（避免 import 時觸發 CUDA 初始化）
# =========================================================
_chat = None
_infer_lock = threading.Lock()


def is_allowed_video_path(path: str) -> bool:
    allowed_dir = os.getenv("EMOTION_LLAMA_ALLOWED_VIDEO_DIR") or tempfile.gettempdir()
    try:
        real_path = os.path.realpath(path or "")
        real_allowed_dir = os.path.realpath(allowed_dir)
        return os.path.commonpath([real_path, real_allowed_dir]) == real_allowed_dir
    except Exception:
        return False


def is_readable_video(path: str) -> tuple[bool, str]:
    try:
        import cv2

        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            cap.release()
            return False, "video_unreadable"
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return False, "video_empty"
        return True, ""
    except Exception as e:
        return False, f"opencv_check_failed: {e}"


def _quick_quality_check(path: str) -> tuple[bool, str]:
    """
    OpenCV 快篩：亮度 + 動態檢查。
    通過 → (True, "")；不通過 → (False, reason)。
    reason: "too_dark" | "no_motion" | "quality_check_error"
    """
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            cap.release()
            return False, "quality_check_error"

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        # 均勻取最多 5 幀
        positions = list(range(0, max(frame_count, 1), max(1, frame_count // 5)))[:5]

        brightnesses = []
        grays = []
        for pos in positions:
            if frame_count > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightnesses.append(float(gray.mean()))
            grays.append(cv2.resize(gray, (80, 45)))
        cap.release()

        if not brightnesses:
            return False, "quality_check_error"

        # 亮度門檻：平均亮度 < 15/255 視為太暗
        avg_brightness = sum(brightnesses) / len(brightnesses)
        if avg_brightness < 15.0:
            return False, "too_dark"

        # 動態門檻：幀差分 < 0.003 視為完全靜止（無人）
        if len(grays) >= 2:
            diffs = [
                float(cv2.absdiff(grays[i], grays[i + 1]).mean()) / 255.0
                for i in range(len(grays) - 1)
            ]
            avg_diff = sum(diffs) / len(diffs)
            if avg_diff < 0.003:
                return False, "no_motion"

        return True, ""
    except Exception as e:
        print(f"⚠️ quality_check 失敗（略過，繼續推論）: {e}")
        return True, ""  # 快篩失敗時保守通過，不阻擋推論


def _try_extract_structured(text: str) -> dict:
    """
    嘗試從 Emotion-LLaMA 的自由文字回應解析結構化資料。
    支援兩種格式：
      1. 標籤格式：「FACIAL: ...\nBODY: ...\nEMOTION: ...」
      2. JSON 格式：{"facial": ..., "emotion": ...}（若模型剛好輸出）
    永遠回傳包含 description 的 dict；欄位可能為空字串但不為 None。
    """
    import json as _json
    import re as _re

    result = {
        "facial": "",
        "body": "",
        "vocal": "",
        "emotion": "",
        "intensity": "",
        "description": text,
    }

    # 嘗試解析 JSON
    try:
        json_match = _re.search(r'\{[^{}]+\}', text, _re.DOTALL)
        if json_match:
            parsed = _json.loads(json_match.group())
            for key in ("facial", "body", "vocal", "emotion", "intensity"):
                if key in parsed:
                    result[key] = str(parsed[key]).strip()
            return result
    except Exception:
        pass

    # 解析標籤格式（FACIAL: ... / BODY: ... 等）
    label_map = {
        "FACIAL": "facial",
        "BODY": "body",
        "VOCAL": "vocal",
        "EMOTION": "emotion",
        "INTENSITY": "intensity",
    }
    for label, key in label_map.items():
        pattern = _re.compile(
            rf'{label}\s*[:\-]\s*(.+?)(?=\n[A-Z]{{3,}}[:\-]|$)',
            _re.IGNORECASE | _re.DOTALL,
        )
        match = pattern.search(text)
        if match:
            result[key] = match.group(1).strip().strip('[]').strip()

    return result


def _ffmpeg_sanitize_video(path: str, keep_audio: bool = True) -> tuple[str, str | None]:
    fd, output_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-fflags", "+genpts", "-i", path, "-t", os.getenv("EMOTION_LLAMA_MAX_INPUT_SEC", "4"),
        "-vf", "fps=4,scale=320:-2:force_original_aspect_ratio=decrease",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-avoid_negative_ts", "make_zero", "-movflags", "+faststart",
    ]
    if keep_audio:
        cmd += [
            "-af", "aresample=async=1:first_pts=0,asetpts=N/SR/TB",
            "-c:a", "aac", "-ar", "16000", "-ac", "1",
        ]
    else:
        cmd += ["-an"]
    cmd.append(output_path)
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=30)
        return output_path, output_path
    except Exception as e:
        try:
            os.remove(output_path)
        except OSError:
            pass
        print(f"⚠️ Emotion-LLaMA 影片正規化失敗 keep_audio={keep_audio}: {e}")
        return path, None


def _encode_video_with_retry(chat, video_path: str):
    cleanup_paths = []
    safe_path, cleanup = _ffmpeg_sanitize_video(video_path, keep_audio=True)
    if cleanup:
        cleanup_paths.append(cleanup)
    img_list = [safe_path]
    try:
        print(f"🎬 開始 encode video: {safe_path}")
        chat.encode_img(img_list)
        return img_list, cleanup_paths
    except Exception as first_error:
        print(f"⚠️ 含音訊影片 encode 失敗，改用無音訊安全影片重試: {first_error}")
        for path in cleanup_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        cleanup_paths = []
        safe_path, cleanup = _ffmpeg_sanitize_video(video_path, keep_audio=False)
        if cleanup:
            cleanup_paths.append(cleanup)
        img_list = [safe_path]
        print(f"🎬 開始 encode video(no-audio): {safe_path}")
        chat.encode_img(img_list)
        return img_list, cleanup_paths


def get_chat():
    global _chat
    if _chat is not None:
        return _chat

    from minigpt4.common.config import Config
    from minigpt4.common.registry import registry
    from minigpt4.conversation.conversation import Chat

    args = parse_args()
    cfg = Config(args)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🔧 使用裝置: {device}")
    if device == "cuda":
        torch.backends.cudnn.benchmark = True
        torch.backends.cuda.matmul.allow_tf32 = True

    model_config = cfg.model_cfg
    model_cls = registry.get_model_class(model_config.arch)
    model = model_cls.from_config(model_config).to(device)
    if device == "cuda":
        model = model.half()
        try:
            model = torch.compile(model, mode="reduce-overhead")
            print("✅ torch.compile 啟用（第一次推論會 warm-up ~30s）")
        except Exception as e:
            print(f"⚠️ torch.compile 不可用，跳過: {e}")
    model.eval()

    vis_processor_cfg = cfg.datasets_cfg.feature_face_caption.vis_processor.train
    vis_processor = registry.get_processor_class(
        vis_processor_cfg.name
    ).from_config(vis_processor_cfg)

    _chat = Chat(model, vis_processor, device=device)
    print("✅ Emotion-LLaMA 模型載入完成")
    _warmup_model()
    return _chat


def _warmup_model() -> None:
    """模型載入後立即觸發 torch.compile warm-up，避免首位顧客等到 ~30s。"""
    import subprocess
    import tempfile
    fd, dummy_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=black:size=320x240:duration=1:rate=4",
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
            "-t", "1", "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", dummy_path,
        ], check=True, timeout=15)
        print("🔥 執行模型預熱推論...")
        process_video_question(dummy_path, "warmup", skip_quality_check=True)
        print("✅ 模型預熱完成")
    except Exception as e:
        print(f"⚠️ 模型預熱失敗（不影響功能）: {e}")
    finally:
        try:
            os.remove(dummy_path)
        except OSError:
            pass


# =========================================================
# 核心推論函式
# =========================================================
def process_video_question(video_path: str, question: str, skip_quality_check: bool = False) -> str:
    """
    依據 conversation.py 的實際 API 實作正確推論流程：

    Chat.encode_img(img_list):
      - 接受 1 個參數 img_list
      - img_list[0] 為 video path string（會被 pop 掉）
      - 內部處理 video frame + audio feature
      - 處理完後將 tensor append 回 img_list

    Chat.ask(text, conv):
      - 將問題加入 conversation

    Chat.answer(conv, img_list, **kargs):
      - 生成回答
    """
    start_ts = time.time()
    from minigpt4.conversation.conversation import Conversation, SeparatorStyle

    if not video_path or not os.path.exists(video_path):
        return f"[EMOTION_LLAMA_ERROR] video_not_found: {video_path}"
    if not is_allowed_video_path(video_path):
        return f"[EMOTION_LLAMA_ERROR] path_not_allowed: {video_path}"
    if skip_quality_check:
        video_ok, video_error = is_readable_video(video_path)
        if not video_ok:
            return f"[EMOTION_LLAMA_ERROR] {video_error}: {video_path}"
    else:
        quality_ok, quality_reason = _quick_quality_check(video_path)
        if not quality_ok:
            print(f"⚠️ Emotion-LLaMA 品質快篩未通過: {quality_reason}")
            prefix = "[EMOTION_LLAMA_ERROR]" if quality_reason == "quality_check_error" else "[EMOTION_LLAMA_SKIP]"
            return f"{prefix} {quality_reason}"

    chat = get_chat()

    try:
        # Step 1: 建立 Conversation
        chat_state = Conversation(
            system="",
            roles=(r"<s>[INST] ", r" [/INST]"),
            messages=[],
            offset=2,
            sep_style=SeparatorStyle.SINGLE,
            sep="",
        )

        # Step 2: 加入 video placeholder
        chat_state.append_message(
            chat_state.roles[0],
            "<video><VideoHere></video> <feature><FeatureHere></feature>"
        )

        # Step 3: encode_img — 傳入 [video_path]，內部自動處理 video+audio。
        # 對事件觸發短片段先做 ffmpeg 時間軸正規化；若音訊仍不穩，改用無音訊影片重試一次。
        cleanup_paths = []
        try:
            img_list, cleanup_paths = _encode_video_with_retry(chat, video_path)
            print(f"✅ encode 完成，img_list[0] shape: {img_list[0].shape}")
        finally:
            for path in cleanup_paths:
                try:
                    os.remove(path)
                except OSError:
                    pass

        # Step 4: 加入問題
        chat.ask(question, chat_state)

        # Step 5: 生成回答
        with _infer_lock, torch.inference_mode():
            response, _ = chat.answer(
                conv=chat_state,
                img_list=img_list,
                temperature=float(os.getenv("EMOTION_LLAMA_TEMPERATURE", "0.2")),
                max_new_tokens=int(os.getenv("EMOTION_LLAMA_MAX_NEW_TOKENS", "50")),
                max_length=int(os.getenv("EMOTION_LLAMA_MAX_LENGTH", "1600")),
                num_beams=int(os.getenv("EMOTION_LLAMA_NUM_BEAMS", "1")),
            )

        # 淨化輸出
        for tag in ["<s>", "</s>", "[INST]", "[/INST]", "<video>", "</video>", "<feature>", "</feature>"]:
            response = response.replace(tag, "")
        response = response.strip()

        # 解析結構化資料，回傳 JSON 字串讓下游穩定解析
        import json as _json
        structured = _try_extract_structured(response)
        result_json = _json.dumps(structured, ensure_ascii=False)

        elapsed_ms = int((time.time() - start_ts) * 1000)
        print(f"✅ 推論完成: elapsed_ms={elapsed_ms}, emotion={structured.get('emotion')}, response={response[:80]}")
        return result_json

    except Exception as e:
        print(f"❌ 推論失敗: {e}")
        return f"[EMOTION_LLAMA_ERROR] inference_failed: {e}"


if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    from pydantic import BaseModel

    class _InferRequest(BaseModel):
        video_path: str
        question: str
        skip_quality_check: bool = False

    api = FastAPI()

    @api.get("/health")
    def _health():
        return {"status": "ok"}

    @api.post("/predict")
    def _predict(req: _InferRequest):
        result = process_video_question(req.video_path, req.question, req.skip_quality_check)
        return {"result": result}

    args = parse_args()
    print("🔧 Emotion-LLaMA 推論設定:")
    print(f"  EMOTION_LLAMA_TEMPERATURE={os.getenv('EMOTION_LLAMA_TEMPERATURE', '0.2')}")
    print(f"  EMOTION_LLAMA_MAX_NEW_TOKENS={os.getenv('EMOTION_LLAMA_MAX_NEW_TOKENS', '50')}")
    print(f"  EMOTION_LLAMA_MAX_LENGTH={os.getenv('EMOTION_LLAMA_MAX_LENGTH', '1600')}")
    print(f"  EMOTION_LLAMA_NUM_BEAMS={os.getenv('EMOTION_LLAMA_NUM_BEAMS', '1')}")
    print(f"  port={args.port}")
    print("🔄 預先載入 Emotion-LLaMA 模型...")
    get_chat()
    uvicorn.run(api, host="0.0.0.0", port=args.port)
