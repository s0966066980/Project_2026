import threading

import config
from bootstrap.processes import kill_stray_ngrok, port_is_in_use
from bootstrap.startup import ensure_ollama


def print_runtime_banner(pos_port: int, admin_port: int, local_host: str):
    def _check_emotion_llama() -> str:
        import urllib.request
        try:
            urllib.request.urlopen(f"{config.EMOTION_LLAMA_GRADIO_URL}/health", timeout=1)
            return "✅ 開啟"
        except Exception:
            return "❌ 未開啟"

    model_name = config.get("MODEL_NAME", "qwen3.5:4b")
    voice_model = config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b")
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
    print(f"🖥️ POS local URL:   http://{local_host}:{pos_port}/pos")
    print(f"🛠️ Admin local URL: http://{local_host}:{admin_port}/admin")


def maybe_start_ngrok(pos_port: int):
    if not (config.ENABLE_NGROK and config.NGROK_AUTHTOKEN):
        return
    try:
        from pyngrok import ngrok

        ngrok.set_auth_token(config.NGROK_AUTHTOKEN)
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
                err_text = str(connect_err)
                recoverable = any(
                    marker in err_text
                    for marker in ("ERR_NGROK_334", "already online", "ERR_NGROK_108", "simultaneous")
                )
                if recoverable:
                    ngrok.kill()
                    kill_stray_ngrok()
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


def run_dev_servers(app):
    import sys
    import uvicorn

    ensure_ollama(
        model=config.get("MODEL_NAME", "qwen3.5:4b"),
        voice_model=config.get("VOICE_ASSIST_MODEL", "qwen3.5:4b"),
    )

    host = config.APP_HOST
    pos_port = int(config.APP_PORT)
    admin_port = int(config.ADMIN_PORT)
    local_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    ports = [pos_port]
    if admin_port not in ports:
        ports.append(admin_port)

    available_ports = []
    for port in ports:
        if port_is_in_use(host, port):
            print(f"ℹ️ Port {port} 已有 API 服務在執行，略過此入口。")
        else:
            available_ports.append(port)
    if not available_ports:
        print("ℹ️ 所有入口都已由既有程序佔用，略過重複啟動。")
        sys.exit(0)

    print_runtime_banner(pos_port, admin_port, local_host)
    maybe_start_ngrok(pos_port)
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

