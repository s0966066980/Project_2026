"""Resolve the store's configured text-model routing into a policy the gateway can execute.

The settings document holds the operator's intent — a fault-tolerance policy between the local
Ollama runtime and NVIDIA NIM, the sole cloud text provider. NVIDIA NIM's credential is never
part of that intent; it is read from the environment so it stays out of the versioned,
broadcast settings document.
"""

from __future__ import annotations

import config
from models.llm import LLMModelPolicy

_POLICY_BY_NAME = {
    "local_first": LLMModelPolicy.LOCAL_FIRST,
    "cloud_first": LLMModelPolicy.CLOUD_FIRST,
    "local_only": LLMModelPolicy.LOCAL_ONLY,
    "cloud_only": LLMModelPolicy.CLOUD_ONLY,
}

POLICY_LABELS = {
    "local_first": "本機優先",
    "cloud_first": "雲端優先",
    "local_only": "僅本機",
    "cloud_only": "僅雲端",
}

CLOUD_PROVIDER = "nvidia_nim"
CLOUD_PROVIDER_LABEL = "NVIDIA NIM"


def configured_policy() -> LLMModelPolicy:
    name = str(config.get("LLM_ROUTING_POLICY", "local_first") or "").strip().lower()
    return _POLICY_BY_NAME.get(name, LLMModelPolicy.LOCAL_FIRST)


def uses_cloud(policy: LLMModelPolicy | None = None) -> bool:
    return (policy or configured_policy()) is not LLMModelPolicy.LOCAL_ONLY


def allows_local(policy: LLMModelPolicy | None = None) -> bool:
    return (policy or configured_policy()) is not LLMModelPolicy.CLOUD_ONLY


def local_model(*, voice: bool = False) -> str:
    key = "VOICE_ASSIST_MODEL" if voice else "MODEL_NAME"
    return str(config.get(key, "qwen3.5:4b") or "qwen3.5:4b")


def cloud_model(*, voice: bool = False) -> str:
    key = "NIM_VOICE_MODEL" if voice else "NIM_MODEL_NAME"
    return str(config.get(key, "meta/llama-3.1-8b-instruct") or "meta/llama-3.1-8b-instruct")


def model_for(provider: str, *, voice: bool = False) -> str:
    return local_model(voice=voice) if provider == "ollama" else cloud_model(voice=voice)


def _ollama_reachable(timeout: float = 2.0) -> tuple[bool, str]:
    import requests

    try:
        response = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        response.raise_for_status()
    except Exception:
        return False, "無法連線到 Ollama 服務。"
    return True, ""


def _probe(provider: str, model: str) -> dict:
    from models.llm import LLMRequest
    from services import llm_gateway_service

    adapter = llm_gateway_service.default_adapters().get(provider)
    if adapter is None:
        return {"provider": provider, "model": model, "ok": False, "latency_ms": 0, "detail": "沒有這個提供者的連線實作。"}
    result = adapter.generate(LLMRequest(
        task="connectivity_probe",
        system_prompt="Reply with the JSON object {\"ok\": true} and nothing else.",
        user_prompt="ping",
        timeout_seconds=15.0,
        prompt_version="connectivity-probe-v1",
        expect_json=False,
        model_name=model,
        max_tokens=16,
        max_retries=0,
    ))
    detail = {
        "missing_credential": "缺少 API 金鑰，未送出請求。",
        "provider_timeout": "請求逾時。",
        "invalid_provider_payload": "回應格式無法解析。",
        "response_truncated": "回應在寫完前就達到長度上限。推理型模型的思考過程也會佔用額度，請改用非推理型模型。",
    }.get(result.safe_error, result.safe_error)
    return {
        "provider": provider,
        "model": result.model or model,
        "ok": not result.safe_error,
        "latency_ms": int(result.latency_ms),
        "detail": detail,
    }


def connectivity_test() -> dict:
    """Probe every provider in the configured chain. Reads settings; writes none."""

    policy = configured_policy()
    results = []
    if allows_local(policy):
        results.append(_probe("ollama", local_model()))
    if uses_cloud(policy):
        results.append(_probe(CLOUD_PROVIDER, cloud_model()))
    serving = [row for row in results if row["ok"]]
    summary = ""
    if not serving:
        summary = "目前設定下沒有任何提供者可以服務，AI 功能會全面失效。"
    elif len(serving) < len(results):
        failed = "、".join(
            (CLOUD_PROVIDER_LABEL if r["provider"] == CLOUD_PROVIDER else r["provider"])
            for r in results if not r["ok"]
        )
        summary = f"{failed} 無法服務，所有請求都會由其餘提供者承擔。"
    return {"results": results, "all_ok": len(serving) == len(results), "summary": summary}


def readiness() -> dict:
    """Report whether each half of the chain can actually serve, without sending a prompt."""

    policy = configured_policy()
    local_ok, local_detail = _ollama_reachable()
    cloud_ok = bool(config.NVIDIA_API_KEY)
    cloud_detail = "" if cloud_ok else "環境變數 NVIDIA_API_KEY 未設定。"

    blocking = []
    if allows_local(policy) and not local_ok:
        blocking.append("local")
    if uses_cloud(policy) and not cloud_ok:
        blocking.append("cloud")
    return {
        "policy": str(config.get("LLM_ROUTING_POLICY", "local_first")),
        "policy_label": POLICY_LABELS.get(str(config.get("LLM_ROUTING_POLICY", "local_first")), ""),
        "cloud_provider": CLOUD_PROVIDER,
        "cloud_provider_label": CLOUD_PROVIDER_LABEL,
        # NIM Model Catalog: the curated model choices Admin offers for NIM_MODEL_NAME /
        # NIM_VOICE_MODEL. Admin-added Custom NIM Model Entries live in the settings document
        # itself (NIM_CUSTOM_TEXT_MODELS / NIM_CUSTOM_VOICE_MODELS), not here.
        "nim_text_model_catalog": list(config.NIM_TEXT_MODEL_CATALOG),
        "nim_voice_model_catalog": list(config.NIM_VOICE_MODEL_CATALOG),
        "local": {
            "ready": local_ok,
            "used": allows_local(policy),
            "model": local_model(),
            "detail": local_detail,
        },
        "cloud": {
            "ready": cloud_ok,
            "used": uses_cloud(policy),
            "model": cloud_model(),
            "credential_env": "NVIDIA_API_KEY",
            "detail": cloud_detail,
        },
        # A policy is only degraded when a half it actually relies on cannot serve.
        "degraded": bool(blocking),
        "blocking": blocking,
    }
