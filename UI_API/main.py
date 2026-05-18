import asyncio
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
    menu_routes,
    rag_routes,
    recommendation_routes,
    voice_routes,
    monitor_routes,
)


@asynccontextmanager
async def lifespan(app):
    await _background_init()
    yield


app = FastAPI(title="Smart Kiosk POS API", version="9.0", lifespan=lifespan)

_emotion_semaphore = asyncio.Semaphore(1)
_yolo_semaphore = asyncio.Semaphore(1)
_ollama_semaphore = asyncio.Semaphore(1)
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
app.include_router(monitor_routes.create_router(_deps))


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
    port = int(config.APP_PORT)
    print("\n" + "=" * 65)
    print(f"🚀 API Server starting on http://{host}:{port}")
    if _port_is_in_use(host, port):
        print(f"ℹ️ Port {port} 已有 API 服務在執行，略過重複啟動。")
        print("=" * 65 + "\n")
        sys.exit(0)

    if config.ENABLE_NGROK and config.NGROK_AUTHTOKEN:
        try:
            from pyngrok import ngrok

            ngrok.set_auth_token(config.NGROK_AUTHTOKEN)
            tunnel = ngrok.connect(port)
            print(f"🌍 Public HTTPS URL: {tunnel.public_url}")
        except ImportError:
            print("ℹ️ pyngrok 未安裝，略過外網 tunnel。")
        except Exception:
            print("ℹ️ ngrok endpoint 已被其他程序使用或暫時不可用；本機 API 照常啟動。")
    else:
        print("ℹ️ ngrok 未啟用，只啟動本機 API。")
    print("=" * 65 + "\n")
    uvicorn.run(app, host=host, port=port)
