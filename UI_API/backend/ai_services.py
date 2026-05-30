import os
import asyncio
import hashlib
import requests
import json
import re
import tempfile
import base64
import math
import time
import wave
import audioop
import threading
from collections import OrderedDict
import edge_tts
import whisper

import config

try:
    from google import genai
except Exception:
    genai = None

os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "quiet")

whisper_model = None
_whisper_thread_lock = threading.Lock()
_tts_cache = OrderedDict()
_TTS_CACHE_LIMIT = 64
_gemini_client = None
_gemini_cooldown_until = 0.0
_gemini_last_error = ""


class _suppress_native_stderr:
    """Temporarily silence native FFmpeg/OpenCV stderr noise from malformed WebM chunks."""
    def __enter__(self):
        self._saved_fd = None
        self._devnull_fd = None
        try:
            self._saved_fd = os.dup(2)
            self._devnull_fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(self._devnull_fd, 2)
        except OSError:
            self._cleanup()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._saved_fd is not None:
                os.dup2(self._saved_fd, 2)
        except OSError:
            pass
        self._cleanup()

    def _cleanup(self):
        for fd_name in ("_saved_fd", "_devnull_fd"):
            fd = getattr(self, fd_name, None)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
                setattr(self, fd_name, None)


async def _run_process(args: list[str], timeout: float | None = None, capture_stderr: bool = False) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE if capture_stderr else asyncio.subprocess.DEVNULL
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"process timeout: {' '.join(args[:2])}")
    if proc.returncode != 0:
        detail = (stderr or b"").decode("utf-8", errors="ignore")[-600:] if capture_stderr else ""
        raise RuntimeError(f"process failed ({proc.returncode}): {' '.join(args[:2])} {detail}".strip())
    return (stderr or b"").decode("utf-8", errors="ignore") if capture_stderr else ""


async def async_probe_media(file_path: str) -> dict:
    result = {
        "valid": False,
        "has_audio": False,
        "has_video": False,
        "duration_sec": 0.0,
        "error": "",
    }
    if not file_path or not os.path.exists(file_path):
        result["error"] = "media_missing"
        return result
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error",
            "-print_format", "json",
            "-show_format", "-show_streams",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8)
        if proc.returncode != 0:
            detail = (stderr or b"").decode("utf-8", errors="ignore")
            lower_detail = detail.lower()
            if "ebml header parsing failed" in lower_detail or "invalid data found" in lower_detail:
                result["error"] = "invalid_media_data"
            elif "moov atom not found" in lower_detail:
                result["error"] = "incomplete_media_file"
            else:
                result["error"] = "ffprobe_failed"
            return result
        data = json.loads((stdout or b"{}").decode("utf-8", errors="ignore") or "{}")
        streams = data.get("streams") if isinstance(data.get("streams"), list) else []
        result["has_audio"] = any(stream.get("codec_type") == "audio" for stream in streams)
        result["has_video"] = any(stream.get("codec_type") == "video" for stream in streams)
        try:
            result["duration_sec"] = round(float((data.get("format") or {}).get("duration") or 0), 3)
        except Exception:
            result["duration_sec"] = 0.0
        result["valid"] = bool(streams) and (result["has_audio"] or result["has_video"])
        if not result["valid"]:
            result["error"] = "no_media_stream"
        return result
    except Exception as e:
        result["error"] = str(e)
        return result


async def _convert_media_to_wav(file_path: str, wav_path: str):
    max_sec = float(config.get("WHISPER_MAX_AUDIO_SEC", 18))
    await _run_process([
        "ffmpeg", "-y", "-i", file_path,
        "-t", str(max_sec),
        "-vn", "-sn", "-dn",
        "-af", "aresample=async=1:first_pts=0",
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav_path
    ])


def _is_empty_audio_error(error: Exception) -> bool:
    text = str(error or "").lower()
    return "0 elements" in text or "cannot reshape tensor" in text


def _is_whisper_sequence_error(error: Exception) -> bool:
    text = str(error or "").lower()
    return (
        "key and value must have the same sequence length" in text
        or "expected key.size(1) == value.size(1)" in text
    )


def _wav_duration_seconds(path: str) -> float:
    try:
        with wave.open(path, "rb") as wav_file:
            frame_count = wav_file.getnframes()
            frame_rate = wav_file.getframerate() or 0
            if frame_count <= 0 or frame_rate <= 0:
                return 0.0
            return frame_count / float(frame_rate)
    except Exception:
        return 0.0


def _wav_has_enough_audio(path: str, min_duration: float | None = None) -> bool:
    if not path or not os.path.exists(path):
        return False
    if min_duration is None:
        min_duration = float(config.get("WHISPER_MIN_AUDIO_SEC", 0.45))
    return _wav_duration_seconds(path) >= min_duration


def _wav_rms_db(path: str) -> float:
    try:
        with wave.open(path, "rb") as wav_file:
            sample_width = wav_file.getsampwidth() or 2
            frames = wav_file.readframes(wav_file.getnframes())
        if not frames:
            return -120.0
        rms = audioop.rms(frames, sample_width)
        if rms <= 0:
            return -120.0
        max_amp = float((1 << (8 * sample_width - 1)) - 1)
        return 20.0 * math.log10(min(1.0, rms / max_amp))
    except Exception:
        return -120.0


def _audio_is_too_quiet(path: str) -> bool:
    threshold = float(config.get("WHISPER_LOW_AUDIO_DB", -48))
    return _wav_rms_db(path) < threshold


_WHISPER_HALLUCINATION_PATTERNS = [
    "字幕", "字幕組", "聽打", "請訂閱", "點贊", "按讚", "分享", "開啟小鈴鐺",
    "感謝收看", "謝謝觀看", "下集再見", "我們下次見", "by bwd6",
    "amara.org", "ming pao", "明鏡", "小編", "轉發", "打賞",
]


def _whisper_quality_reject_reason(result: dict | None) -> str:
    if not isinstance(result, dict):
        return ""
    segments = result.get("segments")
    if not isinstance(segments, list) or not segments:
        return ""

    no_speech_values = [
        float(seg.get("no_speech_prob"))
        for seg in segments
        if isinstance(seg, dict) and seg.get("no_speech_prob") is not None
    ]
    if no_speech_values and min(no_speech_values) >= float(config.get("WHISPER_MAX_NO_SPEECH_PROB", 0.68)):
        return "no_speech_prob_high"

    avg_logprobs = [
        float(seg.get("avg_logprob"))
        for seg in segments
        if isinstance(seg, dict) and seg.get("avg_logprob") is not None
    ]
    if avg_logprobs and max(avg_logprobs) < float(config.get("WHISPER_MIN_AVG_LOGPROB", -1.15)):
        return "avg_logprob_low"

    compression_ratios = [
        float(seg.get("compression_ratio"))
        for seg in segments
        if isinstance(seg, dict) and seg.get("compression_ratio") is not None
    ]
    if compression_ratios and max(compression_ratios) > float(config.get("WHISPER_MAX_COMPRESSION_RATIO", 2.6)):
        return "compression_ratio_high"
    return ""


def _sanitize_transcript(text: str, result: dict | None = None) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    lower = cleaned.lower()
    if any(pattern.lower() in lower for pattern in _WHISPER_HALLUCINATION_PATTERNS):
        return ""
    reject_reason = _whisper_quality_reject_reason(result)
    if reject_reason:
        print(f"⚠️ Whisper 信心不足，略過本次辨識: {reject_reason}")
        return ""
    meaningful = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", cleaned)
    if len(meaningful) < 2:
        return ""
    repeated = re.sub(r"[\s，。,.!?！？、]", "", cleaned)
    if len(repeated) >= 8 and len(set(repeated)) <= 2:
        return ""
    return cleaned


def _read_binary_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def _resolve_local_path(path: str) -> str:
    if os.path.isabs(path or ""):
        return path
    candidates = [
        os.path.abspath(path or ""),
        os.path.join(os.path.dirname(__file__), path or "")
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[-1]

def _normalize_language(raw_language: str = "", text: str = "") -> str:
    """將 Whisper 語言偵測壓成產品只支援的 zh / en。"""
    raw = (raw_language or "").lower()
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    latin_count = len(re.findall(r"[A-Za-z]", text or ""))

    if raw.startswith("en"):
        return "en"
    if raw.startswith(("zh", "cn", "yue")) or cjk_count > 0:
        return "zh"
    if latin_count > cjk_count:
        return "en"
    return "zh"

def init_whisper():
    global whisper_model
    if whisper_model is None:
        model_size = config.get("WHISPER_MODEL_SIZE", "base")
        print(f"載入 Whisper ({model_size}) 模型中...")
        try:
            whisper_model = whisper.load_model(model_size)
        except Exception as e:
            print(f"Whisper 模型載入失敗: {e}")
            whisper_model = None


def _transcribe_with_whisper(path: str, **kwargs) -> dict:
    if whisper_model is None:
        return {}
    initial_prompt = str(config.get("WHISPER_INITIAL_PROMPT", "") or "").strip()
    options = {
        "fp16": False,
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "verbose": False,
        "compression_ratio_threshold": float(config.get("WHISPER_MAX_COMPRESSION_RATIO", 2.6)),
        "logprob_threshold": float(config.get("WHISPER_MIN_AVG_LOGPROB", -1.15)),
        "no_speech_threshold": float(config.get("WHISPER_MAX_NO_SPEECH_PROB", 0.68)),
    }
    if initial_prompt:
        options["initial_prompt"] = initial_prompt
    options.update(kwargs)
    with _whisper_thread_lock:
        return whisper_model.transcribe(path, **options)


def init_gemini_client():
    if not config.GEMINI_API_KEY:
        print("Gemini client 預載略過: 未設定 GEMINI_API_KEY / GOOGLE_API_KEY")
        return False
    _get_gemini_client()
    return True

async def async_safe_transcribe_with_language(file_path: str) -> dict:
    """辨識語音並偵測語言，回傳產品支援的 {text, language}，language 只會是 zh 或 en。"""
    init_whisper()
    if not whisper_model:
        return {"text": "", "language": "zh", "raw_language": ""}
    wav_path = file_path + "_safe.wav"
    try:
        probe = await async_probe_media(file_path)
        if not probe.get("valid") or not probe.get("has_audio"):
            print(f"⚠️ 語音輸入無效或沒有音軌，略過 Whisper 辨識: {probe.get('error') or 'no_audio'}")
            return {"text": "", "language": "zh", "raw_language": ""}
        await _convert_media_to_wav(file_path, wav_path)
        if not _wav_has_enough_audio(wav_path):
            print("⚠️ 語音內容為空或過短，略過 Whisper 辨識。")
            return {"text": "", "language": "zh", "raw_language": ""}
        if _audio_is_too_quiet(wav_path):
            print("⚠️ 語音音量過低，略過 Whisper 辨識。")
            return {"text": "", "language": "zh", "raw_language": ""}
        result = await asyncio.to_thread(_transcribe_with_whisper, wav_path, task="transcribe")
        text = _sanitize_transcript(result.get("text", ""), result)
        raw_lang = result.get("language", "")
        lang = _normalize_language(raw_lang, text)
        return {"text": text, "language": lang, "raw_language": raw_lang}
    except Exception as e:
        if _is_empty_audio_error(e):
            print("⚠️ 語音內容為空或過短，略過 Whisper 辨識。")
            return {"text": "", "language": "zh", "raw_language": ""}
        if _is_whisper_sequence_error(e):
            print(f"⚠️ Whisper 解碼狀態錯誤，略過本次語音辨識: {e}")
            return {"text": "", "language": "zh", "raw_language": ""}
        print(f"⚠️ 語音辨識失敗: {e}")
        try:
            result = await asyncio.to_thread(_transcribe_with_whisper, file_path, task="transcribe")
            text = _sanitize_transcript(result.get("text", ""), result)
            raw_lang = result.get("language", "")
            return {"text": text, "language": _normalize_language(raw_lang, text), "raw_language": raw_lang}
        except Exception as e2:
            if _is_empty_audio_error(e2):
                print("⚠️ 語音內容為空或過短，略過 Whisper 辨識。")
                return {"text": "", "language": "zh", "raw_language": ""}
            if _is_whisper_sequence_error(e2):
                print(f"⚠️ Whisper 解碼狀態錯誤，略過本次語音辨識: {e2}")
                return {"text": "", "language": "zh", "raw_language": ""}
            print(f"⚠️ 直接辨識也失敗: {e2}")
            return {"text": "", "language": "zh", "raw_language": ""}
    finally:
        if os.path.exists(wav_path):
            await asyncio.to_thread(os.remove, wav_path)


def _strip_think_blocks(content: str) -> str:
    """剝除 qwen3 / 思維模型輸出的 <think>...</think> block，避免干擾 JSON 擷取。"""
    return re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE).strip()


def _repair_and_extract_json(content: str) -> dict | None:
    """
    強健 JSON 擷取器：
    0. 剝除 <think>...</think> block（qwen3 / thinking models）
    1. 直接 parse
    2. 剝 markdown fence
    3. 括號深度追蹤
    4. 若仍截斷，用 state machine 安全補上引號/括號
    """
    if not content or not isinstance(content, str):
        return None

    # step 0: strip thinking blocks emitted by qwen3-family models
    content = _strip_think_blocks(content)
    if not content:
        return None

    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        pass

    fence = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', content)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    start = content.find('{')
    if start == -1:
        print(f"⚠️ 找不到 JSON，Ollama 原始輸出:\n{content}")
        return None

    fragment = content[start:]
    depth = 0
    in_string = False
    escape_next = False
    end_idx = -1
    for i, ch in enumerate(fragment):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end_idx = i
                break

    if end_idx != -1:
        candidate = fragment[:end_idx + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 仍截斷：state machine 已知道是否還在字串中、還缺幾個結尾 }
    if 0 < depth <= 5:
        repaired = fragment
        # 截斷在字串中 → 先補結束引號
        if in_string:
            if escape_next:
                # 截斷在 escape 字元後（例如 "...\\）— 移除尾部不完整的反斜線
                repaired = repaired.rstrip("\\")
            repaired += '"'
        # 移除尾端可能造成 parse error 的開放結構（例如 "key": 或結尾逗號）
        stripped = repaired.rstrip()
        if stripped.endswith((',', ':')):
            stripped = stripped[:-1].rstrip()
        repaired = stripped + ('}' * depth)
        try:
            result = json.loads(repaired)
            if isinstance(result, dict):
                print(f"🔧 JSON 自動修復成功（補了 {depth} 個括號）")
                return result
        except json.JSONDecodeError:
            pass

    print(f"⚠️ 找不到 JSON，Ollama 原始輸出:\n{content}")
    return None


def _enforced_json_system_prompt(system_prompt: str) -> str:
    return (
        system_prompt.rstrip()
        + "\n\n⚠️ 輸出規則：只輸出一個完整合法的 JSON 物件，確保所有括號都正確閉合，不要有任何 Markdown 符號或說明文字。"
    )


def _resolve_gemini_model(model_name: str = "") -> str:
    candidate = str(model_name or "").strip()
    if candidate.startswith(("gemini-", "gemma-")):
        return candidate
    return config.get("GEMINI_MODEL_NAME", "gemini-3-flash-preview")


def _get_gemini_client():
    global _gemini_client
    if genai is None:
        raise RuntimeError("尚未安裝 google-genai，請先執行 pip install google-genai")
    if _gemini_client is None:
        kwargs = {}
        if config.GEMINI_API_KEY:
            kwargs["api_key"] = config.GEMINI_API_KEY
        _gemini_client = genai.Client(**kwargs)
    return _gemini_client


def _parse_llm_json_response(content: str, response_tag: str = "") -> dict:
    parsed = _repair_and_extract_json(content)
    if parsed is not None:
        if response_tag:
            parsed["_response_tag"] = response_tag
        parsed["_raw_content"] = content
        return parsed
    return {"error": "找不到 JSON 格式的輸出", "raw_content": content}


def _extract_retry_delay_sec(error_text: str) -> int:
    retry_match = re.search(r"'retryDelay':\s*'(\d+)s'", error_text)
    if not retry_match:
        retry_match = re.search(r"retry in ([0-9.]+)s", error_text, re.IGNORECASE)
    if retry_match:
        try:
            return max(1, int(float(retry_match.group(1))) + 2)
        except Exception:
            pass
    return int(config.get("GEMINI_COOLDOWN_SEC", 60))


def _is_gemini_quota_error(error_text: str) -> bool:
    lowered = str(error_text or "").lower()
    return (
        "429" in lowered
        or "resource_exhausted" in lowered
        or "quota" in lowered
        or ("rate" in lowered and "limit" in lowered)
    )


def _is_gemini_internal_error(error_text: str) -> bool:
    lowered = str(error_text or "").lower()
    return "500" in lowered or "internal" in lowered or "internal error" in lowered


def _is_gemini_unavailable_error(error_text: str) -> bool:
    lowered = str(error_text or "").lower()
    return (
        "503" in lowered
        or "unavailable" in lowered
        or "high demand" in lowered
        or "overloaded" in lowered
        or "try again later" in lowered
    )


def _gemini_cooldown_remaining() -> int:
    return max(0, int(_gemini_cooldown_until - time.time()))


def _generate_gemini_content(
    system_prompt: str,
    user_prompt: str,
    model: str,
    force_json_mime: bool = True,
) -> str:
    client = _get_gemini_client()
    contents = f"【系統指令】\n{_enforced_json_system_prompt(system_prompt)}\n\n{user_prompt}"
    kwargs = {
        "model": model,
        "contents": contents,
    }
    if force_json_mime:
        from google.genai import types as genai_types

        config_kwargs = {
            "temperature": float(config.get("OLLAMA_TEMPERATURE", 0.8)),
            "max_output_tokens": int(config.get("GEMINI_NUM_PREDICT", 512)),
            "response_mime_type": "application/json",
        }
        kwargs["config"] = genai_types.GenerateContentConfig(**config_kwargs)
    response = client.models.generate_content(**kwargs)
    return getattr(response, "text", "") or ""


def _should_use_gemini_json_mime(model: str) -> bool:
    if str(model or "").startswith("gemma-"):
        return False
    return bool(config.get("GEMINI_USE_JSON_MIME", False))


def _ask_ollama_local(system_prompt: str, user_prompt: str, response_tag: str = "", model_name: str = "", temperature: float = None) -> dict:
    """呼叫本機 Ollama 並強制擷取 JSON。"""
    enforced_system = (
        _enforced_json_system_prompt(system_prompt)
    )
    payload = {
        "model": model_name or config.get("MODEL_NAME", "llama3.2"),
        "prompt": f"【系統指令】\n{enforced_system}\n\n{user_prompt}",
        "stream": False,
        "format": "json",
        "think": False,          # disable thinking mode for qwen3/thinking models (Ollama ≥0.5.1)
        "options": {
            "temperature": float(config.get("OLLAMA_TEMPERATURE", 0.8)) if temperature is None else float(temperature),
            "num_predict": int(config.get("OLLAMA_NUM_PREDICT", 220))
        }
    }
    try:
        response = requests.post(config.OLLAMA_API_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
        response.raise_for_status()
        content = response.json().get("response", "")
        if config.get("OLLAMA_LOG_RAW", False):
            print(f"📝 Ollama{'['+response_tag+']' if response_tag else ''} 原始回應:\n{content[:400]}\n{'='*40}")

        return _parse_llm_json_response(content, response_tag)

    except Exception as e:
        print(f"❌ Ollama 請求失敗: {e}")
        return {"error": str(e), "raw_content": "無法連線至 Ollama"}


def ask_gemini(system_prompt: str, user_prompt: str, response_tag: str = "", model_name: str = "") -> dict:
    """呼叫 Gemini API，回傳格式與 Ollama 路徑一致。"""
    global _gemini_cooldown_until, _gemini_last_error
    model = _resolve_gemini_model(model_name)
    try:
        remaining = _gemini_cooldown_remaining()
        if remaining > 0:
            return {
                "error": f"Gemini API 暫停呼叫中，{remaining} 秒後重試。",
                "raw_content": _gemini_last_error or "Gemini API cooldown",
                "_provider_error": "gemini_cooldown",
            }
        force_json_mime = _should_use_gemini_json_mime(model)
        content = _generate_gemini_content(
            system_prompt,
            user_prompt,
            model,
            force_json_mime,
        )
        if config.get("OLLAMA_LOG_RAW", False):
            print(f"📝 Gemini[{model}]{'['+response_tag+']' if response_tag else ''} 原始回應:\n{content[:400]}\n{'='*40}")
        return _parse_llm_json_response(content, response_tag)
    except Exception as e:
        error_text = str(e)
        print(f"⚠️ Gemini API 請求失敗，將依設定使用備援: {error_text}")
        if _is_gemini_quota_error(error_text):
            retry_sec = _extract_retry_delay_sec(error_text)
            _gemini_cooldown_until = time.time() + retry_sec
            _gemini_last_error = error_text
            return {
                "error": f"Gemini API 額度或速率限制，{retry_sec} 秒內改用備援。",
                "raw_content": error_text,
                "_provider_error": "gemini_rate_limited",
                "_retry_after_sec": retry_sec,
            }
        if _is_gemini_internal_error(error_text):
            retry_sec = int(config.get("GEMINI_COOLDOWN_SEC", 60))
            _gemini_cooldown_until = time.time() + retry_sec
            _gemini_last_error = error_text
            return {
                "error": f"Gemini API 服務端暫時錯誤，{retry_sec} 秒內改用備援。",
                "raw_content": error_text,
                "_provider_error": "gemini_internal",
                "_retry_after_sec": retry_sec,
            }
        if _is_gemini_unavailable_error(error_text):
            retry_sec = _extract_retry_delay_sec(error_text)
            _gemini_cooldown_until = time.time() + retry_sec
            _gemini_last_error = error_text
            return {
                "error": f"Gemini API 暫時繁忙，{retry_sec} 秒內改用備援。",
                "raw_content": error_text,
                "_provider_error": "gemini_unavailable",
                "_retry_after_sec": retry_sec,
            }
        return {"error": error_text, "raw_content": "無法連線至 Gemini API", "_provider_error": "gemini_failed"}


def ask_ollama(system_prompt: str, user_prompt: str, response_tag: str = "", model_name: str = "") -> dict:
    """本地 Ollama 專用入口。推薦、RAG 審查與背景整理一律使用這條路徑。"""
    return _ask_ollama_local(system_prompt, user_prompt, response_tag, model_name, temperature=None)


def ask_llm(
    system_prompt: str,
    user_prompt: str,
    response_tag: str = "",
    model_name: str = "",
    provider: str = "",
    temperature: float = None,
) -> dict:
    """
    問答類功能專用 LLM 入口。
    QA_AI_PROVIDER=ollama 時走本地 Ollama；QA_AI_PROVIDER=gemini 時走 Gemini API。
    """
    provider = str(provider or config.get("QA_AI_PROVIDER", "ollama") or "ollama").lower()
    if provider == "gemini":
        gemini_result = ask_gemini(system_prompt, user_prompt, response_tag, model_name)
        if "error" not in gemini_result:
            return gemini_result
        if config.get("GEMINI_FALLBACK_TO_OLLAMA", True):
            print("↩️ Gemini 不可用，改用本地 Ollama 備援。")
            fallback = _ask_ollama_local(system_prompt, user_prompt, response_tag, "", temperature=temperature)
            if "error" not in fallback:
                fallback["_fallback_from"] = "gemini"
                fallback["_gemini_error"] = gemini_result.get("error", "")
            return fallback
        return gemini_result
    return _ask_ollama_local(system_prompt, user_prompt, response_tag, model_name, temperature=temperature)


async def generate_tts_audio_base64(text: str, lang: str = "zh") -> str:
    """根據偵測語言選擇對應 TTS 語音"""
    if lang == "en":
        voice = config.get("TTS_VOICE_EN", "en-US-JennyNeural")
    else:
        voice = config.get("TTS_VOICE", "zh-TW-HsiaoChenNeural")

    text_digest = hashlib.sha1(str(text or "").encode("utf-8")).hexdigest()
    cache_key = f"{lang}:{voice}:{text_digest}"
    if config.get("ENABLE_TTS_CACHE", True) and cache_key in _tts_cache:
        _tts_cache.move_to_end(cache_key)
        return _tts_cache[cache_key]

    temp_path = ""
    try:
        communicate = edge_tts.Communicate(text, voice)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
            temp_path = temp_file.name
        await communicate.save(temp_path)
        audio_bytes = await asyncio.to_thread(_read_binary_file, temp_path)
        encoded = base64.b64encode(audio_bytes).decode('utf-8')
        if config.get("ENABLE_TTS_CACHE", True):
            _tts_cache[cache_key] = encoded
            _tts_cache.move_to_end(cache_key)
            while len(_tts_cache) > _TTS_CACHE_LIMIT:
                _tts_cache.popitem(last=False)
        return encoded
    except Exception as e:
        print(f"⚠️ TTS 產生失敗: {e}")
        return ""
    finally:
        if temp_path and os.path.exists(temp_path):
            await asyncio.to_thread(os.remove, temp_path)
def check_emotion_llama_status(timeout: float = 2.0) -> dict:
    url = config.EMOTION_LLAMA_GRADIO_URL.rstrip("/")
    try:
        response = requests.get(url, timeout=timeout)
        return {
            "available": response.status_code < 500,
            "status_code": response.status_code,
            "url": url,
            "message": "Emotion-LLaMA 推論服務可連線",
        }
    except Exception as e:
        return {
            "available": False,
            "status_code": 0,
            "url": url,
            "message": str(e),
        }


def list_ollama_models(timeout: float = 3.0) -> list[str]:
    try:
        base = config.OLLAMA_API_URL.split("/api/")[0].rstrip("/")
        response = requests.get(f"{base}/api/tags", timeout=timeout)
        response.raise_for_status()
        rows = response.json().get("models", [])
        names = [str(row.get("name") or "").strip() for row in rows if row.get("name")]
        return names
    except Exception:
        return []
