import os


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(BACKEND_DIR)
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")

TUNNEL_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]"
    r"|([a-zA-Z0-9-]+\.)*ngrok(-free)?\.(app|io)"
    r"|([a-zA-Z0-9-]+\.)*trycloudflare\.com"
    r"|([a-zA-Z0-9-]+\.)*loca\.lt"
    r")(:[0-9]+)?$"
)

STATIC_CACHE_PREFIX = "/static/"

