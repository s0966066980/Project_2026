"""Admin LLM diagnostics: send one prompt to a named half of the provider chain.

The provider and model named here are a Diagnostic Provider Override — a one-shot parameter
for this request only. Nothing is persisted, and the store's Text Model Routing Policy is
untouched, which is why the gateway adapters are called directly rather than through
llm_gateway_service.generate()'s policy-driven chain.
"""

import database
import requests

import config
from models.llm import LLMAdapterResult, LLMRequest
from services import llm_gateway_service, llm_routing_service

# The provider chain has exactly two halves; a diagnostic prompt may name either one.
SUPPORTED_DIAGNOSTIC_PROVIDERS = frozenset({"ollama", llm_routing_service.CLOUD_PROVIDER})


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


def _override_model(provider: str, model: str) -> str:
    """Resolve the model this diagnostic will actually run, so the reported model cannot
    disagree with the one that answered."""

    if model:
        return model
    return llm_routing_service.model_for(provider, voice=True)


def _flatten(result: LLMAdapterResult) -> dict:
    """Render one adapter result in the flat shape the Admin diagnostic chat already reads."""

    meta = {
        "provider": result.provider,
        "model": result.model,
        "latency_ms": int(result.latency_ms),
    }
    if result.safe_error:
        message = llm_gateway_service.describe_safe_error(result.safe_error)
        # A diagnostic exists to show what the provider actually said; when the reply arrived
        # but could not be parsed, the raw body is the finding, not noise to be swallowed.
        body = str(result.content or "").strip()
        if body:
            message = f"{message}\n模型原始回覆：{body[:1000]}"
        return {"error": message, "text": "", **meta}

    payload = dict(result.parsed or {})
    payload.setdefault("text", result.content)
    payload.update(meta)
    return payload


def ask_voice_style(
    provider: str,
    model: str,
    system_prompt: str,
    user_text: str,
    history: list[dict],
) -> dict:
    """模擬語音模式：注入菜單白名單，強制 JSON 輸出，解析 ai_response / cart_actions。"""
    adapter = llm_gateway_service.default_adapters().get(provider)
    if adapter is None:
        return {
            "error": f"沒有「{provider}」這個提供者的連線實作。",
            "text": "",
            "provider": provider,
            "model": model,
            "latency_ms": 0,
        }

    resolved_model = _override_model(provider, model)
    result = adapter.generate(
        LLMRequest(
            task="voice_assist",
            system_prompt=system_prompt or _get_default_voice_prompt(),
            user_prompt=_build_voice_user_prompt(user_text, history),
            model_name=resolved_model,
            expect_json=True,
            response_tag="ADMIN_LLM_DIAGNOSTIC",
            prompt_version="admin-diagnostic-v1",
            timeout_seconds=60.0,
            # A diagnostic reports the first attempt verbatim; a silent retry would hide the
            # intermittent failure the operator is here to see.
            max_retries=0,
        )
    )
    return _flatten(result)
