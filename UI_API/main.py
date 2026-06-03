import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
import ai_services
from routes import (
    core_routes,
    emotion_routes,
    debug_routes,
    demo_routes,
    menu_routes,
    ai_push_routes,
    voice_routes,
    rag_routes,
    interaction_routes,
    realtime_routes,
    mood_routes,
)

# Allow same-origin requests over any ngrok/cloudflared/localhost tunnel URL so the
# app behaves identically whether opened locally or through an HTTPS tunnel.
_TUNNEL_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]"
    r"|([a-zA-Z0-9-]+\.)*ngrok(-free)?\.(app|io)"
    r"|([a-zA-Z0-9-]+\.)*trycloudflare\.com"
    r"|([a-zA-Z0-9-]+\.)*loca\.lt"
    r")(:[0-9]+)?$"
)
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")


@asynccontextmanager
async def lifespan(app):
    await _background_init()
    yield


app = FastAPI(title="Smart Kiosk POS API", version="9.0", lifespan=lifespan)


class LoopBoundSemaphore:
    """Lazily create an asyncio.Semaphore for the current running event loop."""

    def __init__(self, value: int = 1):
        self.value = value
        self._loop = None
        self._semaphore = None

    def _current(self):
        loop = asyncio.get_running_loop()
        if self._loop is not loop or self._semaphore is None:
            self._loop = loop
            self._semaphore = asyncio.Semaphore(self.value)
        return self._semaphore

    def locked(self) -> bool:
        try:
            return self._current().locked()
        except RuntimeError:
            return False

    async def __aenter__(self):
        await self._current().acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._current().release()


_ollama_semaphore = LoopBoundSemaphore(1)
_background_init_done = False


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=_TUNNEL_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response

async def _background_init():
    global _background_init_done
    if _background_init_done:
        return
    _background_init_done = True
    await _background_init_once()


async def _background_init_once():
    tasks = []

    # STT 預載（provider 不是 openai_compatible 才需要本地模型）
    if config.get("STT_PROVIDER", "faster_whisper") != "openai_compatible":
        async def _init_stt():
            try:
                from services.stt_service import FasterWhisperSTT
                await asyncio.to_thread(FasterWhisperSTT()._init)
                print("✅ STT 模型預載完成")
            except Exception as e:
                print(f"⚠️ STT 預載失敗（不影響服務）: {e}")
        tasks.append(_init_stt())

    # TTS 預載（只有 melo 需要本地模型）
    if config.get("TTS_PROVIDER", "edge") == "melo":
        async def _init_tts():
            try:
                from services.tts_service import MeloTTSProvider
                await asyncio.to_thread(MeloTTSProvider()._init)
                print("✅ TTS 模型預載完成")
            except Exception as e:
                print(f"⚠️ TTS 預載失敗（不影響服務）: {e}")
        tasks.append(_init_tts())

    # RAG Embedding 模型預載（RAG_ENABLED=true 時）
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

    # Gemini client 預載（選用）
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


def _route_dependencies() -> dict:
    return {
        "ollama_semaphore": _ollama_semaphore,
    }


_deps = _route_dependencies()
app.include_router(core_routes.create_router(_deps))
app.include_router(menu_routes.create_router(_deps))
app.include_router(voice_routes.create_router(_deps))
app.include_router(rag_routes.create_router(_deps))

app.include_router(ai_push_routes.create_router(_deps))
app.include_router(emotion_routes.create_router(_deps))
app.include_router(interaction_routes.create_router(_deps))
app.include_router(realtime_routes.create_router(_deps))
app.include_router(demo_routes.create_router(_deps))
app.include_router(mood_routes.create_router(_deps))
if config.get("ENABLE_DEBUG_ROUTES", False):
    app.include_router(debug_routes.create_router(_deps))


def _ensure_ollama(
    model: str = "qwen3.5:4b",
    voice_model: str = "qwen3.5:4b",
    extra_models: list | None = None,
):
    """Start ollama serve and pull each required model once, with purpose logging."""
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


if __name__ == "__main__":
    import socket
    import sys
    import uvicorn

    _ensure_ollama(
        model=config.get("MODEL_NAME", "qwen3.5:4b"),
        voice_model=config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b"),
    )

    def _port_is_in_use(host: str, port: int) -> bool:
        check_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((check_host, port)) == 0

    host = config.APP_HOST
    pos_port = int(config.APP_PORT)
    admin_port = int(config.ADMIN_PORT)
    local_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    ports = [pos_port]
    if admin_port not in ports:
        ports.append(admin_port)

    available_ports = []
    for port in ports:
        if _port_is_in_use(host, port):
            print(f"ℹ️ Port {port} 已有 API 服務在執行，略過此入口。")
        else:
            available_ports.append(port)
    if not available_ports:
        print("ℹ️ 所有入口都已由既有程序佔用，略過重複啟動。")
        sys.exit(0)

    # ── 功能模組狀態 ──────────────────────────────────────
    def _check_emotion_llama() -> str:
        import urllib.request
        try:
            urllib.request.urlopen(f"{config.EMOTION_LLAMA_GRADIO_URL}/health", timeout=1)
            return "✅ 開啟"
        except Exception:
            return "❌ 未開啟"

    model_name   = config.get("MODEL_NAME", "qwen3.5:4b")
    voice_model  = config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b")
    stt_provider = config.get("STT_PROVIDER", "faster_whisper")
    tts_provider = config.get("TTS_PROVIDER", "edge")
    emotion_stat = _check_emotion_llama()

    print("\n" + "=" * 65)
    print("📋 功能模組狀態")
    print(f"   🤖 LLM          : {model_name}")
    print(f"   🎙️  語音 LLM     : {voice_model}")
    print(f"   👂 STT          : {stt_provider}")
    print(f"   🔊 TTS          : {tts_provider}")
    print(f"   👁️  Emotion-LLaMA: {emotion_stat}")
    print()

    # ── 存取網址 ──────────────────────────────────────────
    print(f"🖥️ POS local URL:   http://{local_host}:{pos_port}/pos")
    print(f"🛠️ Admin local URL: http://{local_host}:{admin_port}/admin")

    if config.ENABLE_NGROK and config.NGROK_AUTHTOKEN:
        try:
            from pyngrok import ngrok

            ngrok.set_auth_token(config.NGROK_AUTHTOKEN)

            # 尋找現有 tunnel（避免重複開）
            tunnel_url = ""
            try:
                for t in ngrok.get_tunnels():
                    addr = str((getattr(t, "config", {}) or {}).get("addr", ""))
                    if f":{pos_port}" in addr:
                        tunnel_url = str(getattr(t, "public_url", "") or "")
                        break
            except Exception:
                pass

            if not tunnel_url:
                try:
                    t = ngrok.connect(pos_port)
                    tunnel_url = str(getattr(t, "public_url", "") or "")
                except Exception as connect_err:
                    # 上次 main.py 被 kill 後 ngrok agent 殘留，endpoint 仍在雲端，
                    # 重啟時拿不到舊 tunnel 但 connect 被拒 (ERR_NGROK_334)。
                    # 殺掉舊 agent 再重試一次。
                    if "ERR_NGROK_334" in str(connect_err) or "already online" in str(connect_err):
                        ngrok.kill()
                        t = ngrok.connect(pos_port)
                        tunnel_url = str(getattr(t, "public_url", "") or "")
                    else:
                        raise

            if tunnel_url:
                public_url = tunnel_url.rstrip("/")
                print(f"🖥️  POS:    {public_url}/pos"
                      + (f"?token={config.POS_DEMO_TOKEN}" if config.POS_DEMO_TOKEN else ""))
                print(f"🛠️  Admin:  {public_url}/admin"
                      + (f"?token={config.ADMIN_DEMO_TOKEN}" if config.ADMIN_DEMO_TOKEN else ""))
        except ImportError:
            print("ℹ️ pyngrok 未安裝，略過外網 tunnel。")
        except Exception as e:
            print(f"⚠️ ngrok 啟動失敗（本機照常）: {e}")

    print("=" * 65 + "\n")

    servers = [
        uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info"))
        for port in available_ports
    ]
    threads = [
        threading.Thread(target=server.run, name=f"uvicorn-{port}", daemon=True)
        for server, port in zip(servers, available_ports)
    ]
    try:
        for thread in threads:
            thread.start()
        while any(thread.is_alive() for thread in threads):
            for thread in threads:
                thread.join(timeout=0.5)
    except KeyboardInterrupt:
        for server in servers:
            server.should_exit = True
        for thread in threads:
            thread.join(timeout=5)
        print("ℹ️ API Server stopped.")
