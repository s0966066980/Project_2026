import requests
from requests.adapters import HTTPAdapter
from typing import Iterator
import json
import re
import time

import config

_ollama_session: requests.Session | None = None


def _get_ollama_session() -> requests.Session:
    global _ollama_session
    if _ollama_session is None:
        s = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=int(config.get("OLLAMA_POOL_CONNECTIONS", 2)),
            pool_maxsize=int(config.get("OLLAMA_POOL_MAXSIZE", 4)),
        )
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        _ollama_session = s
    return _ollama_session


def warm_ollama_model(model_name: str) -> dict:
    """Load a local model without generating text and keep it ready for voice traffic."""
    model = str(model_name or "").strip()
    if not model:
        return {"status": "skipped", "reason": "missing_model"}
    started = time.perf_counter()
    try:
        response = _get_ollama_session().post(
            config.OLLAMA_API_URL,
            json={
                "model": model,
                "prompt": "",
                "stream": False,
                "keep_alive": str(config.get("OLLAMA_KEEP_ALIVE", "30m") or "30m"),
                "options": {"num_predict": 0},
            },
            timeout=int(config.get("OLLAMA_TIMEOUT", 120)),
        )
        response.raise_for_status()
        return {
            "status": "ready",
            "model": model,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:
        return {
            "status": "error",
            "model": model,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "message": str(exc)[:200],
        }

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


def _parse_llm_json_response(content: str, response_tag: str = "") -> dict:
    parsed = _repair_and_extract_json(content)
    if parsed is not None:
        if response_tag:
            parsed["_response_tag"] = response_tag
        parsed["_raw_content"] = content
        return parsed
    return {"error": "找不到 JSON 格式的輸出", "raw_content": content}


def _ask_ollama_local(system_prompt: str, user_prompt: str, response_tag: str = "", model_name: str = "", temperature: float | None = None, num_predict: int | None = None) -> dict:
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
        "keep_alive": str(config.get("OLLAMA_KEEP_ALIVE", "30m") or "30m"),
        "options": {
            "temperature": float(config.get("OLLAMA_TEMPERATURE", 0.8)) if temperature is None else float(temperature),
            "num_predict": num_predict if num_predict is not None else int(config.get("OLLAMA_NUM_PREDICT", 220))
        }
    }
    try:
        response = _get_ollama_session().post(config.OLLAMA_API_URL, json=payload, timeout=int(config.get("OLLAMA_TIMEOUT", 120)))
        response.raise_for_status()
        content = response.json().get("response", "")
        if config.get("OLLAMA_LOG_RAW", False):
            print(f"📝 Ollama{'['+response_tag+']' if response_tag else ''} 原始回應:\n{content[:400]}\n{'='*40}")

        return _parse_llm_json_response(content, response_tag)

    except Exception as e:
        print(f"❌ Ollama 請求失敗: {e}")
        return {"error": str(e), "raw_content": "無法連線至 Ollama"}


def ask_ollama(system_prompt: str, user_prompt: str, response_tag: str = "", model_name: str = "", num_predict: int | None = None) -> dict:
    """本地 Ollama 專用入口。語音、AI 推播、介入分析一律使用這條路徑。"""
    return _ask_ollama_local(system_prompt, user_prompt, response_tag, model_name, temperature=None, num_predict=num_predict)


def stream_ollama_tokens(
    system_prompt: str,
    user_prompt: str,
    model_name: str = "",
    num_predict: int | None = None,
) -> Iterator[str]:
    """同步 generator：從 Ollama 串流 API 逐 token yield 字串。"""
    enforced_system = _enforced_json_system_prompt(system_prompt)
    payload = {
        "model": model_name or config.get("MODEL_NAME", "llama3.2"),
        "prompt": f"【系統指令】\n{enforced_system}\n\n{user_prompt}",
        "stream": True,
        "format": "json",
        "think": False,
        "keep_alive": str(config.get("OLLAMA_KEEP_ALIVE", "30m") or "30m"),
        "options": {
            "temperature": float(config.get("OLLAMA_TEMPERATURE", 0.8)),
            "num_predict": num_predict if num_predict is not None else int(config.get("OLLAMA_NUM_PREDICT", 220)),
        },
    }
    try:
        response = _get_ollama_session().post(
            config.OLLAMA_API_URL, json=payload, stream=True,
            timeout=int(config.get("OLLAMA_TIMEOUT", 120)),
        )
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                token = data.get("response", "")
                if token:
                    yield token
                if data.get("done"):
                    break
    except Exception as e:
        print(f"❌ Ollama 串流失敗: {e}")


def parse_llm_json(content: str, tag: str = "") -> dict:
    """公開版 JSON 解析，供串流語音等模組直接使用。"""
    return _parse_llm_json_response(content, tag)


def ask_ollama_raw_text(system_prompt: str, user_prompt: str, model_name: str = "") -> dict:
    """自由文字回應（不強制 JSON），供管理後台測試頁使用。"""
    payload = {
        "model": model_name or config.get("MODEL_NAME", "llama3.2"),
        "prompt": f"[系統]\n{system_prompt}\n\n[使用者]\n{user_prompt}",
        "stream": False,
        "think": False,
        "options": {
            "temperature": float(config.get("OLLAMA_TEMPERATURE", 0.8)),
            "num_predict": int(config.get("OLLAMA_NUM_PREDICT", 512)),
        },
    }
    try:
        t0 = time.time()
        response = _get_ollama_session().post(
            config.OLLAMA_API_URL, json=payload, timeout=int(config.get("OLLAMA_TIMEOUT", 120))
        )
        response.raise_for_status()
        text = _strip_think_blocks(response.json().get("response", ""))
        return {"text": text, "latency_ms": int((time.time() - t0) * 1000),
                "provider": "ollama", "model": payload["model"]}
    except Exception as e:
        return {"error": str(e), "text": "", "latency_ms": 0}


