import requests
import time

import ai_services
import config
import database


def list_ollama_models() -> list[str]:
    try:
        res = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        res.raise_for_status()
        data = res.json()
        return [m.get("name") or m.get("model", "") for m in data.get("models", []) if m.get("name") or m.get("model")]
    except Exception:
        return []


def _build_voice_user_prompt(user_text: str, history: list[dict]) -> str:
    """組合與語音模式相同的 user_prompt（含對話歷史 + 菜單白名單）。"""
    menu_context = database.build_compact_menu_context()

    history_lines = []
    for m in history:
        role = "顧客" if m.get("role") == "user" else "系統"
        history_lines.append(f"{role}：{m.get('content', '')}")

    parts = []
    if history_lines:
        parts.append("【對話歷史（最近幾輪）】\n" + "\n".join(history_lines))
    parts.append(f"【顧客語音輸入】\n{user_text}")
    parts.append(menu_context)
    return "\n\n".join(parts)


def _get_default_voice_prompt() -> str:
    return config.get("VOICE_ASSIST_SYSTEM_PROMPT", "")


def ask_voice_style(
    provider: str,
    model: str,
    system_prompt: str,
    user_text: str,
    history: list[dict],
) -> dict:
    """模擬語音模式：注入菜單白名單，強制 JSON 輸出，解析 ai_response / cart_actions。"""
    sp = system_prompt or _get_default_voice_prompt()
    user_prompt = _build_voice_user_prompt(user_text, history)

    t0 = time.time()
    if provider == "nvidia_nim":
        raw = _ask_nvidia_nim_text(sp, user_prompt, model)
    else:
        raw = ai_services.ask_ollama(sp, user_prompt, model_name=model)

    latency_ms = int((time.time() - t0) * 1000)
    raw["latency_ms"] = raw.get("latency_ms", latency_ms)
    raw["provider"] = raw.get("provider") or provider
    raw["model"] = raw.get("model") or model or config.get("VOICE_ASSIST_MODEL", config.get("MODEL_NAME", ""))
    return raw


def _ask_nvidia_nim_text(system_prompt: str, user_prompt: str, model: str) -> dict:
    default_model = "meta/llama-3.1-8b-instruct"
    base_url = str(config.NVIDIA_API_BASE_URL or "https://integrate.api.nvidia.com/v1").rstrip("/")
    api_key = config.NVIDIA_API_KEY
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model or default_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    try:
        t0 = time.time()
        res = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=60)
        res.raise_for_status()
        text = res.json()["choices"][0]["message"]["content"]
        parsed = ai_services.parse_llm_json(text, "TEST_NVIDIA_NIM")
        if isinstance(parsed, dict) and "error" not in parsed:
            parsed["latency_ms"] = int((time.time() - t0) * 1000)
            parsed["provider"] = "nvidia_nim"
            parsed["model"] = model or default_model
            return parsed
        return {"text": text, "latency_ms": int((time.time() - t0) * 1000),
                "provider": "nvidia_nim", "model": model or default_model}
    except Exception as e:
        return {"error": str(e), "text": "", "latency_ms": 0}
