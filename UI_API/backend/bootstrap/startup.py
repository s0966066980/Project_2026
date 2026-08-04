import asyncio
import threading

import ai_services
import config


_background_init_done = False
_background_init_claim_lock = threading.Lock()
_background_init_ready = threading.Event()


async def background_init():
    global _background_init_done
    with _background_init_claim_lock:
        should_initialize = not _background_init_done
        if should_initialize:
            _background_init_done = True

    if should_initialize:
        try:
            await _background_init_once()
        finally:
            # The kiosk and admin servers run in separate event-loop threads.
            # Do not let either port report startup complete before the shared
            # voice/RAG warm-up attempt has finished.
            _background_init_ready.set()
        return

    await asyncio.to_thread(_background_init_ready.wait)


async def _background_init_once():
    tasks = []

    async def _cleanup_voice_turns():
        try:
            from modules.voice_turn.runtime import cleanup_expired
            await asyncio.to_thread(cleanup_expired)
        except Exception as e:
            print(f"⚠️ Voice Turn retention cleanup 失敗（不影響服務）: {e}")
    tasks.append(_cleanup_voice_turns())

    async def _dispatch_checkout_outbox():
        try:
            from modules.checkout_confirmation.runtime import dispatch_outbox
            await asyncio.to_thread(dispatch_outbox)
        except Exception as e:
            print(f"⚠️ Checkout outbox dispatch 失敗（不影響已確認訂單）: {e}")
    tasks.append(_dispatch_checkout_outbox())

    if config.get("STT_PROVIDER", "faster_whisper") != "openai_compatible":
        async def _init_stt():
            try:
                from services.stt_service import FasterWhisperSTT
                await asyncio.to_thread(FasterWhisperSTT()._init)
                print("✅ STT 模型預載完成")
            except Exception as e:
                print(f"⚠️ STT 預載失敗（不影響服務）: {e}")
        tasks.append(_init_stt())

    if config.get("TTS_PROVIDER", "edge") == "melo":
        async def _init_tts():
            try:
                from services.tts_service import MeloTTSProvider
                await asyncio.to_thread(MeloTTSProvider()._init)
                print("✅ TTS 模型預載完成")
            except Exception as e:
                print(f"⚠️ TTS 預載失敗（不影響服務）: {e}")
        tasks.append(_init_tts())

    if config.get("RAG_ENABLED", False):
        async def _init_rag():
            try:
                from services.rag_provider import get_rag
                await asyncio.to_thread(get_rag()._init)
                count = await get_rag().count()
                print(f"✅ RAG 模型預載完成（文件數：{count}）")
            except Exception as e:
                print(f"⚠️ RAG 預載失敗（不影響服務）: {e}")
        tasks.append(_init_rag())

        async def _cleanup_knowledge_artifacts():
            try:
                from modules.knowledge_publication.runtime import cleanup_expired_artifacts
                await asyncio.to_thread(cleanup_expired_artifacts)
            except Exception as e:
                print(f"⚠️ Knowledge artifact retention cleanup 失敗（不影響服務）: {e}")
        tasks.append(_cleanup_knowledge_artifacts())

    if config.get("VOICE_LLM_PREWARM_ENABLED", True):
        async def _init_voice_llm():
            model = str(config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b") or "qwen3.5:4b")
            result = await asyncio.to_thread(ai_services.warm_ollama_model, model)
            if result.get("status") == "ready":
                print(f"✅ 語音 LLM 預熱完成（{model}, {result.get('latency_ms')}ms）")
            else:
                print(f"⚠️ 語音 LLM 預熱失敗（不影響服務）: {result.get('message') or result.get('reason')}")
        tasks.append(_init_voice_llm())

    if tasks:
        await asyncio.gather(*tasks)


def ensure_ollama(
    model: str = "qwen3.5:4b",
    voice_model: str = "qwen3.5:4b",
    extra_models: list | None = None,
):
    import socket as _sock
    import subprocess as _sp
    import time as _t

    def _ollama_running() -> bool:
        try:
            with _sock.create_connection(("127.0.0.1", 11434), timeout=1):
                return True
        except OSError:
            return False

    def _add_model(specs: dict[str, list[str]], name: str, purpose: str):
        clean_name = str(name or "").strip()
        if not clean_name:
            return
        specs.setdefault(clean_name, [])
        if purpose and purpose not in specs[clean_name]:
            specs[clean_name].append(purpose)

    specs: dict[str, list[str]] = {}
    _add_model(specs, model, "local LLM for menu Q&A and voice assist fallback")
    _add_model(specs, voice_model, "voice assist LLM")
    for item in extra_models or []:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            _add_model(specs, item[0], str(item[1]))
        else:
            _add_model(specs, item, "additional local model")

    if not _ollama_running():
        print("⏳ Ollama 未偵測到，正在啟動 ollama serve ...")
        _sp.Popen(["ollama", "serve"], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, start_new_session=True)
        for _ in range(20):
            _t.sleep(0.5)
            if _ollama_running():
                print("✅ ollama serve 已啟動")
                break
        else:
            print("⚠️ ollama serve 啟動超時，請手動執行。")
            return
    else:
        print("✅ ollama serve 已在執行中")

    def _pull():
        if not specs:
            print("ℹ️ 沒有需要預載的 Ollama 模型。")
            return
        print("📦 Ollama 預載模型清單（已去重）：")
        for name, purposes in specs.items():
            print(f"  - {name}: {'; '.join(purposes)}")
        for name, purposes in specs.items():
            try:
                result = _sp.run(["ollama", "pull", name], capture_output=True, text=True, timeout=300)
                purpose_text = "; ".join(purposes)
                if result.returncode == 0:
                    print(f"✅ ollama pull {name} 完成（{purpose_text}）")
                else:
                    print(f"⚠️ ollama pull {name} 失敗：{result.stderr.strip()}")
            except _sp.TimeoutExpired:
                print(f"⚠️ ollama pull {name} 超時，請手動執行。")
            except FileNotFoundError:
                print("⚠️ ollama 指令不存在，請確認 ollama 已安裝。")
                break

    threading.Thread(target=_pull, name="ollama-pull", daemon=True).start()
