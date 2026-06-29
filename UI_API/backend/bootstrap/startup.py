import asyncio
import threading

import ai_services
import config


_background_init_done = False


async def background_init():
    global _background_init_done
    if _background_init_done:
        return
    _background_init_done = True
    await _background_init_once()


async def _background_init_once():
    tasks = []

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

    if config.get("ENABLE_GEMINI_OPTIONS", False):
        async def _init_gemini():
            try:
                ok = await asyncio.to_thread(ai_services.init_gemini_client)
                if ok:
                    print("✅ Gemini client 背景初始化完成")
            except Exception as e:
                print(f"❌ Gemini client 背景初始化失敗: {e}")
        tasks.append(_init_gemini())

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

