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
import gradio as gr


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


def _ffmpeg_sanitize_video(path: str, keep_audio: bool = True) -> tuple[str, str | None]:
    fd, output_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-fflags", "+genpts", "-i", path, "-t", os.getenv("EMOTION_LLAMA_MAX_INPUT_SEC", "12"),
        "-vf", "fps=8,scale=640:-2:force_original_aspect_ratio=decrease",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
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
    model.eval()

    vis_processor_cfg = cfg.datasets_cfg.feature_face_caption.vis_processor.train
    vis_processor = registry.get_processor_class(
        vis_processor_cfg.name
    ).from_config(vis_processor_cfg)

    _chat = Chat(model, vis_processor, device=device)
    print("✅ Emotion-LLaMA 模型載入完成")
    return _chat


# =========================================================
# 核心推論函式
# =========================================================
def process_video_question(video_path: str, question: str) -> str:
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
    video_ok, video_error = is_readable_video(video_path)
    if not video_ok:
        return f"[EMOTION_LLAMA_ERROR] {video_error}: {video_path}"

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
                max_new_tokens=int(os.getenv("EMOTION_LLAMA_MAX_NEW_TOKENS", "120")),
                max_length=int(os.getenv("EMOTION_LLAMA_MAX_LENGTH", "1600")),
                num_beams=int(os.getenv("EMOTION_LLAMA_NUM_BEAMS", "1")),
            )

        # 淨化輸出
        for tag in ["<s>", "</s>", "[INST]", "[/INST]", "<video>", "</video>", "<feature>", "</feature>"]:
            response = response.replace(tag, "")
        response = response.strip()

        elapsed_ms = int((time.time() - start_ts) * 1000)
        print(f"✅ 推論完成: elapsed_ms={elapsed_ms}, response={response[:150]}")
        return response

    except Exception as e:
        print(f"❌ 推論失敗: {e}")
        return f"[EMOTION_LLAMA_ERROR] inference_failed: {e}"


# =========================================================
# Gradio 介面與啟動
# =========================================================
if __name__ == "__main__":
    args = parse_args()

    print("🔧 Emotion-LLaMA 推論設定:")
    print(f"  EMOTION_LLAMA_TEMPERATURE={os.getenv('EMOTION_LLAMA_TEMPERATURE', '0.2')}")
    print(f"  EMOTION_LLAMA_MAX_NEW_TOKENS={os.getenv('EMOTION_LLAMA_MAX_NEW_TOKENS', '120')}")
    print(f"  EMOTION_LLAMA_MAX_LENGTH={os.getenv('EMOTION_LLAMA_MAX_LENGTH', '1600')}")
    print(f"  EMOTION_LLAMA_NUM_BEAMS={os.getenv('EMOTION_LLAMA_NUM_BEAMS', '1')}")
    print(f"  port={args.port}")

    print("🔄 預先載入 Emotion-LLaMA 模型...")
    get_chat()

    iface = gr.Interface(
        fn=process_video_question,
        inputs=[
            gr.Textbox(label="視頻路徑", placeholder="例如：/tmp/video.webm"),
            gr.Textbox(label="問題", placeholder="例如：視頻中的人物表達了什麼情緒？"),
        ],
        outputs=gr.Textbox(label="模型回答"),
        title="Emotion-LLaMA API",
        allow_flagging="never",
    )

    # 必須關閉 queue，否則 Gradio 回傳 event_id 而非 data
    iface.launch(
        server_name="0.0.0.0",
        server_port=args.port,
        share=False,
        show_error=True,
    )
