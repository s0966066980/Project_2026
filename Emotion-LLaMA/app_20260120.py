import argparse
import os
import cv2
import numpy as np
import time
import torch
import gradio as gr
import subprocess
import json
import datetime
import requests # 新增：用於呼叫 EmoLLM API

from minigpt4.common.config import Config
from minigpt4.common.registry import registry
from minigpt4.conversation.conversation import Conversation, SeparatorStyle, Chat

# --- 全域變數 ---
temp_video_path = "temp_webcam_capture.mp4"
temp_silent_path = "temp_silent.mp4"

# 檔案路徑設定
LOG_FILE = "emotion_history_log.json"
LIVE_STATUS_FILE = "emotion_live.json"
# EmoLLM API 設定
EMOLLM_API_URL = "http://localhost:23333/v1/chat/completions"

# --- 模型載入 ---
def parse_args():
    parser = argparse.ArgumentParser(description="Demo")
    parser.add_argument("--cfg-path", default='eval_configs/demo.yaml', help="配置文件路徑。")
    parser.add_argument("--options", nargs="+", help="覆蓋配置文件中的某些設置。")
    args = parser.parse_args()
    return args

def load_model():
    print("正在載入 Emotion-LLaMA 模型，請稍候...")
    args = parse_args()
    cfg = Config(args)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    model_config = cfg.model_cfg
    model_cls = registry.get_model_class(model_config.arch)
    model = model_cls.from_config(model_config).to(device)
    
    vis_processor_cfg = cfg.datasets_cfg.feature_face_caption.vis_processor.train
    vis_processor = registry.get_processor_class(vis_processor_cfg.name).from_config(vis_processor_cfg)
    
    model.eval()
    chat = Chat(model, vis_processor, device=device)
    print(f"模型載入完成。運行裝置: {device}")
    return chat, device

try:
    chat, device = load_model()
except Exception as e:
    print(f"Warning: Model load failed. Error: {e}")
    chat = None

# --- 輔助功能 ---

def map_to_dfew(text):
    text = text.lower()
    if any(x in text for x in ["happy", "smile", "joy", "laugh", "delight", "cheerful"]):
        return "Happy"
    elif any(x in text for x in ["sad", "cry", "grief", "depress", "unhappy", "tear"]):
        return "Sad"
    elif any(x in text for x in ["angry", "mad", "furious", "rage", "annoy"]):
        return "Angry"
    elif any(x in text for x in ["surprise", "shock", "amaze", "astonish"]):
        return "Surprise"
    elif any(x in text for x in ["disgust", "yuck", "awful", "repulsive"]):
        return "Disgust"
    elif any(x in text for x in ["fear", "scared", "afraid", "terror", "discomfort", "nervous"]):
        return "Fear"
    else:
        return "Neutral"

def save_log(description, category, emollm_advice, source_type):
    record = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source_type,
        "description": description,
        "dfew_category": category,
        "emollm_advice": emollm_advice
    }
    data = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            pass
    data.append(record)
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def update_html_status(category, description):
    status = {
        "emotion": category,
        "description": description,
        "timestamp": time.time()
    }
    with open(LIVE_STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False)

# --- EmoLLM API 串接邏輯 (新增部分) ---

def get_emollm_advice(category, description):
    """
    呼叫 EmoLLM API 獲取安撫建議
    """
    system_prompt = (
        "你是一位溫柔、具備高度同理心的客服專員。"
        "目前的客人他對於氣氛和情緒很敏感，喜歡優雅與和諧。"
        "如果他感到難過或生氣，請用堅定但溫柔的語氣支持他，避免說教，多用『我們』、『我在』這類詞彙。"
        "如果偵測到他很開心，請陪她一起慶祝這份快樂。"
        "請生成3種簡短暖心的回應。"
    )
    
    user_prompt = (
        f"視覺系統分析顯示使用者目前的情緒為【{category}】。\n"
        f"詳細的視覺描述特徵如下：{description}。\n"
        "請生成3種簡短暖心的回應。"
    )

    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "emollm-llama3",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 300
    }
    
    try:
        response = requests.post(EMOLLM_API_URL, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"(EmoLLM API Error: {response.status_code})"
    except:
        return "(EmoLLM API 未啟動或連線失敗，使用備用規則)"

# --- 影片生成功能 (保留原本邏輯) ---

def add_audio_via_ffmpeg(video_input, video_output):
    from shutil import which
    if which('ffmpeg') is None:
        print("Error: FFmpeg not found.")
        return False
    command = [
        'ffmpeg', '-y', '-i', video_input,
        '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
        '-c:v', 'copy', '-c:a', 'aac', '-shortest', video_output
    ]
    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg Error: {e}")
        return False

def save_frame_as_video(frame_rgb, duration=1.0):
    if frame_rgb is None: return None
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    height, width, _ = frame_bgr.shape
    fps = 30.0
    frames_count = int(fps * duration)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
    out = cv2.VideoWriter(temp_silent_path, fourcc, fps, (width, height))
    for _ in range(frames_count):
        out.write(frame_bgr)
    out.release()
    success = add_audio_via_ffmpeg(temp_silent_path, temp_video_path)
    return temp_video_path if success else temp_silent_path

# --- 核心邏輯 ---

def run_inference(video_path, question):
    if chat is None: return "模型未載入", "Neutral"
    
    chat_state = Conversation(
        system="", roles=(r"<s>[INST] ", r" [/INST]"),
        messages=[], offset=2, sep_style=SeparatorStyle.SINGLE, sep="",
    )
    chat_state.append_message(chat_state.roles[0], "<video><VideoHere></video> " + question)
    img_list = [video_path]
    
    try:
        chat.encode_img(img_list)
        response = chat.answer(
            conv=chat_state, img_list=img_list,
            temperature=0.2, max_new_tokens=500, max_length=2000
        )[0]
        category = map_to_dfew(response)
        return response, category
    except Exception as e:
        print(f"Inference Error: {e}")
        return f"Error: {str(e)}", "Error"

def process_one_shot(image, question, duration_sec):
    if image is None:
        yield "⚠️ 錯誤：未偵測到鏡頭畫面", "Waiting", gr.update(interactive=True)
        return

    # 階段 1
    yield "🔄 正在生成影像特徵 (轉換中)...", "Processing...", gr.update(interactive=False)
    start_time = time.time()
    
    # 階段 2 (圖片轉影片)
    video_path = save_frame_as_video(image, duration=duration_sec)
    if not video_path:
        yield "❌ 影片處理失敗", "Error", gr.update(interactive=True)
        return

    # 階段 3 (視覺推論)
    yield "👁️ AI 正在分析情緒...", "Analyzing...", gr.update(interactive=False)
    description, category = run_inference(video_path, question)
    
    # 階段 4 (心理安撫 - 新增步驟)
    yield f"🧠 晨晨 (EmoLLM) 正在思考回應...", category, gr.update(interactive=False)
    emollm_advice = get_emollm_advice(category, description)
    
    cost_time = time.time() - start_time
    
    # 記錄
    save_log(description, category, emollm_advice, "Realtime-VideoMode")
    update_html_status(category, description)
    
    # 階段 5 (組合輸出)
    final_output = (
        f"✅ 分析完成 (耗時 {cost_time:.2f}s)\n\n"
        f"📝 **視覺描述**: {description}\n\n"
        f"💊 **建議**: {emollm_advice}"
    )
    yield final_output, category, gr.update(interactive=True)

def process_uploaded_video(video_path, question):
    if not video_path:
        return "請先上傳影片", "None"
    
    # 1. 視覺分析
    description, category = run_inference(video_path, question)
    
    # 2. 心理建議 (新增)
    emollm_advice = get_emollm_advice(category, description)
    
    save_log(description, category, emollm_advice, "Video Upload")
    update_html_status(category, description)
    
    final_output = (
        f"📝 **視覺描述**: {description}\n\n"
        f"💊 **建議**: {emollm_advice}"
    )
    return final_output, category

# --- Gradio UI 構建 ---

with gr.Blocks(title="Emotion AI Hub (EmoLLM Integrated)", css="footer {visibility: hidden}") as demo:
    
    gr.Markdown("# 🎭 AI Emotion Recognition System")
    
    # --- 1. 首頁 ---
    with gr.Group() as home_group:
        gr.Markdown("### 請選擇啟動模式")
        with gr.Row():
            btn_start_realtime = gr.Button("🚀 啟動即時分析 (Webcam)", variant="primary", size="lg")
            btn_start_upload = gr.Button("📂 導入測試影片", variant="secondary", size="lg")
            
    # --- 2. Realtime 頁面 ---
    with gr.Group(visible=False) as realtime_group:
        gr.Markdown("### 🔴 Realtime Emotion Analysis")
        gr.Markdown("模式：截取當下畫面並轉換為影片進行分析 (已整合 EmoLLM 安撫建議)")
        
        with gr.Row():
            with gr.Column(scale=1):
                cam_input = gr.Image(source="webcam", streaming=True, label="即時監控", type="numpy", mirror_webcam=True)
                
                with gr.Row():
                    duration_slider = gr.Slider(minimum=1, maximum=10, value=5, step=1, label="模擬影片長度 (秒)")
                    
                rt_question = gr.Textbox(label="Prompt", value="Describe the emotion and facial expression.", interactive=True)
                
                with gr.Row():
                    rt_start_btn = gr.Button("▶️ 開始分析", variant="primary")
                    rt_stop_btn = gr.Button("⏹️ 停止", variant="stop")

            with gr.Column(scale=1):
                rt_output_text = gr.Textbox(label="AI 分析狀態/結果", lines=10, value="準備就緒")
                rt_output_class = gr.Label(label="DFEW 情緒分類")
                rt_back_btn = gr.Button("⬅️ 返回首頁")

        analyze_event = rt_start_btn.click(
            fn=process_one_shot,
            inputs=[cam_input, rt_question, duration_slider],
            outputs=[rt_output_text, rt_output_class, rt_start_btn]
        )
        
        rt_stop_btn.click(fn=None, cancels=[analyze_event])

    # --- 3. 影片上傳頁面 ---
    with gr.Group(visible=False) as video_group:
        gr.Markdown("### 🎬 Video File Analysis")
        with gr.Row():
            with gr.Column():
                vid_input = gr.Video(label="上傳測試影片", source="upload")
                vid_question = gr.Textbox(label="Prompt", value="Describe the emotion.use 20 words.", interactive=True)
                vid_analyze_btn = gr.Button("開始分析", variant="primary")
            
            with gr.Column():
                vid_output_text = gr.Textbox(label="分析結果", lines=10)
                vid_output_class = gr.Label(label="DFEW 分類")
                vid_back_btn = gr.Button("⬅️ 返回首頁")

        vid_analyze_btn.click(
            fn=process_uploaded_video,
            inputs=[vid_input, vid_question],
            outputs=[vid_output_text, vid_output_class]
        )

    # --- 頁面切換邏輯 ---
    def show_realtime():
        return {home_group: gr.update(visible=False), realtime_group: gr.update(visible=True), video_group: gr.update(visible=False)}

    def show_video():
        return {home_group: gr.update(visible=False), realtime_group: gr.update(visible=False), video_group: gr.update(visible=True)}

    def show_home():
        return {home_group: gr.update(visible=True), realtime_group: gr.update(visible=False), video_group: gr.update(visible=False)}

    btn_start_realtime.click(fn=show_realtime, outputs=[home_group, realtime_group, video_group])
    btn_start_upload.click(fn=show_video, outputs=[home_group, realtime_group, video_group])
    rt_back_btn.click(fn=show_home, outputs=[home_group, realtime_group, video_group])
    vid_back_btn.click(fn=show_home, outputs=[home_group, realtime_group, video_group])

if __name__ == "__main__":
    if not os.path.exists(LIVE_STATUS_FILE):
        with open(LIVE_STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"emotion": "Neutral", "description": "System Ready"}, f)
            
    print(f"啟動 Gradio 應用程式 (Video Mode + EmoLLM Integrated)...")
    demo.queue().launch(server_name="0.0.0.0", server_port=7889, share=True)