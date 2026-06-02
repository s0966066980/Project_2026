import os
import asyncio
import requests
from requests.adapters import HTTPAdapter
import json
import re
import time

import config

_ollama_session: requests.Session | None = None


def _get_ollama_session() -> requests.Session:
    global _ollama_session
    if _ollama_session is None:
        s = requests.Session()
        adapter = HTTPAdapter(pool_connections=2, pool_maxsize=4)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        _ollama_session = s
    return _ollama_session

try:
    from google import genai
except Exception:
    genai = None

_gemini_client = None
_gemini_cooldown_until = 0.0
_gemini_last_error = ""


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


def _ask_ollama_local(system_prompt: str, user_prompt: str, response_tag: str = "", model_name: str = "", temperature: float | None = None) -> dict:
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
        response = _get_ollama_session().post(config.OLLAMA_API_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
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
    """本地 Ollama 專用入口。語音、AI 推播、介入分析一律使用這條路徑。"""
    return _ask_ollama_local(system_prompt, user_prompt, response_tag, model_name, temperature=None)


def init_gemini_client():
    if not config.GEMINI_API_KEY:
        print("Gemini client 預載略過: 未設定 GEMINI_API_KEY / GOOGLE_API_KEY")
        return False
    _get_gemini_client()
    return True
