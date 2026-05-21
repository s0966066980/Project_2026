import asyncio
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


@asynccontextmanager
async def lifespan(app):
    await _background_init()
    yield


app = FastAPI(title="Smart Kiosk POS API", version="9.0", lifespan=lifespan)

_emotion_semaphore = asyncio.Semaphore(1)
_yolo_semaphore = asyncio.Semaphore(1)
_ollama_semaphore = asyncio.Semaphore(1)
_background_init_lock = threading.Lock()
_background_init_done = False
_emotion_cache = {}
_recommend_cache = {}
_rag_rebuild_task = None


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

async def _background_init():
    global _background_init_done
    with _background_init_lock:
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

    def _print_ngrok_tunnel(tunnel, label: str = "POS", path: str = "/pos", token: str = ""):
        public_url = str(getattr(tunnel, "public_url", "") or tunnel)
        if not public_url:
            return
        print(f"🌍 {label} ngrok URL: {public_url}{path}")
        if token:
            print(f"🔐 {label} token URL: {public_url}{path}?token={token}")

    _print_access_urls()
    if config.ENABLE_NGROK and config.NGROK_AUTHTOKEN:
        try:
            from pyngrok import ngrok

            ngrok.set_auth_token(config.NGROK_AUTHTOKEN)
            pos_tunnel = ngrok.connect(pos_port)
            _print_ngrok_tunnel(pos_tunnel, "POS", "/pos", config.POS_DEMO_TOKEN)
            print(f"🧪 Demo tool URL:   {pos_tunnel.public_url}/demo-tool")
            if admin_port != pos_port:
                admin_tunnel = ngrok.connect(admin_port)
                _print_ngrok_tunnel(admin_tunnel, "Admin", "/admin", config.ADMIN_DEMO_TOKEN)
        except ImportError:
            print("ℹ️ pyngrok 未安裝，略過外網 tunnel。")
        except Exception as e:
            print(f"⚠️ ngrok tunnel 啟動失敗，本機 API 照常啟動: {e}")
            try:
                from pyngrok import ngrok

                tunnels = ngrok.get_tunnels()
                if tunnels:
                    print("ℹ️ 目前偵測到既有 ngrok tunnel：")
                    for existing_tunnel in tunnels:
                        public_url = str(getattr(existing_tunnel, "public_url", "") or existing_tunnel)
                        config_desc = str(getattr(existing_tunnel, "config", "") or "")
                        print(f"🌍 Existing ngrok URL: {public_url} ({config_desc})")
                else:
                    print("ℹ️ 沒有可列出的既有 ngrok tunnel。")
            except Exception as list_error:
                print(f"ℹ️ 無法列出既有 ngrok tunnel: {list_error}")
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
