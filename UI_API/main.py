import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app_factory import create_app

from bootstrap.server import run_dev_servers

app = create_app()


if __name__ == "__main__":
    run_dev_servers(app)
