import asyncio
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
import ai_services
import database
from routes import (
    core_routes,
    customer_service_routes,
    emotion_routes,
    demo_routes,
    menu_routes,
    rag_routes,
    recommendation_routes,
    voice_routes,
    multimodal_routes,
    interaction_routes,
    realtime_routes,
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
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


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


_emotion_semaphore = LoopBoundSemaphore(1)
_yolo_semaphore = LoopBoundSemaphore(1)
_ollama_semaphore = LoopBoundSemaphore(1)
_background_init_done = False
_emotion_cache = {}
_recommend_cache = {}
_rag_rebuild_task = None


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=_TUNNEL_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

async def _background_init():
    global _background_init_done
    if _background_init_done:
        return
    _background_init_done = True
    await _background_init_once()


async def _background_init_once():
    loop = asyncio.get_running_loop()

    async def _init_rag():
        try:
            await loop.run_in_executor(None, database.init_rag_system)
            print("✅ RAG 系統背景初始化完成")
        except Exception as e:
            print(f"❌ RAG 背景初始化失敗: {e}")

    async def _preload_whisper():
        try:
            await loop.run_in_executor(None, ai_services.init_whisper)
            print("✅ Whisper 模型背景預載完成")
        except Exception as e:
            print(f"❌ Whisper 背景預載失敗: {e}")

    async def _preload_yolo():
        try:
            ok = await loop.run_in_executor(None, ai_services.init_yolo_detector)
            if ok:
                print("✅ YOLO11 nano 模型背景預載完成")
        except Exception as e:
            print(f"❌ YOLO 背景預載失敗: {e}")

    async def _preload_gemini_client():
        if config.get("ENABLE_GEMINI_OPTIONS", False) is not True:
            return
        try:
            ok = await loop.run_in_executor(None, ai_services.init_gemini_client)
            if ok:
                print("✅ Gemini client 背景初始化完成")
        except Exception as e:
            print(f"❌ Gemini client 背景初始化失敗: {e}")

    await asyncio.gather(_init_rag(), _preload_whisper(), _preload_yolo(), _preload_gemini_client())


async def _safe_rebuild_rag(reason: str = ""):
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, database.init_rag_system, True)
        if reason:
            print(f"✅ RAG rebuilt: {reason}")
    except Exception as e:
        print(f"❌ RAG rebuild failed{f' ({reason})' if reason else ''}: {e}")


def _schedule_rag_rebuild(reason: str = ""):
    global _rag_rebuild_task
    if _rag_rebuild_task and not _rag_rebuild_task.done():
        return
    _rag_rebuild_task = asyncio.create_task(_safe_rebuild_rag(reason))


def _route_dependencies() -> dict:
    return {
        "emotion_cache": _emotion_cache,
        "emotion_semaphore": _emotion_semaphore,
        "ollama_semaphore": _ollama_semaphore,
        "recommend_cache": _recommend_cache,
        "safe_rebuild_rag": _safe_rebuild_rag,
        "schedule_rag_rebuild": _schedule_rag_rebuild,
        "yolo_semaphore": _yolo_semaphore,
    }


_deps = _route_dependencies()
app.include_router(core_routes.create_router(_deps))
app.include_router(menu_routes.create_router(_deps))
app.include_router(rag_routes.create_router(_deps))
app.include_router(voice_routes.create_router(_deps))
app.include_router(customer_service_routes.create_router(_deps))
app.include_router(recommendation_routes.create_router(_deps))
app.include_router(emotion_routes.create_router(_deps))
app.include_router(demo_routes.create_router(_deps))
app.include_router(interaction_routes.create_router(_deps))
app.include_router(multimodal_routes.create_router(_deps))
app.include_router(realtime_routes.create_router(_deps))


if __name__ == "__main__":
    import socket
    import sys
    import uvicorn

    def _port_is_in_use(host: str, port: int) -> bool:
        check_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((check_host, port)) == 0

    host = config.APP_HOST
    pos_port = int(config.APP_PORT)
    admin_port = int(config.ADMIN_PORT)
    ports = [pos_port]
    if admin_port not in ports:
        ports.append(admin_port)
    print("\n" + "=" * 65)
    print(f"🚀 POS client starting on http://{host}:{pos_port}")
    print(f"🚀 Admin console starting on http://{host}:{admin_port}")
    available_ports = []
    for port in ports:
        if _port_is_in_use(host, port):
            print(f"ℹ️ Port {port} 已有 API 服務在執行，略過此入口。")
        else:
            available_ports.append(port)
    if not available_ports:
        print("ℹ️ 所有入口都已由既有程序佔用，略過重複啟動。")
        print("=" * 65 + "\n")
        sys.exit(0)

    def _print_access_urls():
        local_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        print(f"🖥️ POS local URL:   http://{local_host}:{pos_port}/pos")
        print(f"🛠️ Admin local URL: http://{local_host}:{admin_port}/admin")
        if pos_port != admin_port:
            print(f"   (Admin 也可由 POS port 直接造訪：http://{local_host}:{pos_port}/admin)")

    def _print_tunnel_paths(public_url: str):
        """Single ngrok tunnel covers /pos, /admin, /demo-tool — same FastAPI app."""
        if not public_url:
            return
        public_url = public_url.rstrip("/")
        print(f"🌍 ngrok public URL: {public_url}")
        print(f"   🖥️  POS:        {public_url}/pos"
              + (f"?token={config.POS_DEMO_TOKEN}" if config.POS_DEMO_TOKEN else ""))
        print(f"   🛠️  Admin:      {public_url}/admin"
              + (f"?token={config.ADMIN_DEMO_TOKEN}" if config.ADMIN_DEMO_TOKEN else ""))
        print(f"   🧪 Demo tool:  {public_url}/demo-tool")
        print("   ℹ️  若 ngrok free tier 出現警告頁，按 Visit Site 即可進入。")

    _print_access_urls()
    if config.ENABLE_NGROK and config.NGROK_AUTHTOKEN:
        try:
            from pyngrok import ngrok

            ngrok.set_auth_token(config.NGROK_AUTHTOKEN)
            existing = []
            try:
                existing = ngrok.get_tunnels()
            except Exception:
                existing = []
            tunnel_url = ""
            for tunnel in existing:
                config_data = getattr(tunnel, "config", {}) or {}
                addr = str(config_data.get("addr") if isinstance(config_data, dict) else "")
                if addr.endswith(f":{pos_port}") or addr.endswith(f"://localhost:{pos_port}"):
                    tunnel_url = str(getattr(tunnel, "public_url", "") or "")
                    break
            if not tunnel_url:
                tunnel = ngrok.connect(pos_port)
                tunnel_url = str(getattr(tunnel, "public_url", "") or "")
            _print_tunnel_paths(tunnel_url)
        except ImportError:
            print("ℹ️ pyngrok 未安裝，略過外網 tunnel。")
        except Exception as e:
            print(f"⚠️ ngrok tunnel 啟動失敗，本機 API 照常啟動: {e}")
            try:
                from pyngrok import ngrok

                for existing_tunnel in ngrok.get_tunnels() or []:
                    public_url = str(getattr(existing_tunnel, "public_url", "") or "")
                    if public_url:
                        print(f"🌍 既有 ngrok tunnel: {public_url}")
            except Exception:
                pass
    else:
        if config.NGROK_AUTHTOKEN:
            print("ℹ️ ngrok token 已設定，但 ENABLE_NGROK=false；若要顯示外網網址，請設定 ENABLE_NGROK=true 後重啟。")
        else:
            print("ℹ️ ngrok 未啟用，只啟動本機 API。")
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
