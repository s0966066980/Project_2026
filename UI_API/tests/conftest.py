"""Shared test bootstrap for the public backend contract suite."""

import os
import sys
from pathlib import Path

# The repository root stays importable for tests that reach tooling outside
# `UI_API/backend` (the sidecar that used to live here is gone; see ADR-0066).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_BACKEND", "sqlite")
os.environ.setdefault("DATABASE_URL", "")
os.environ["DATABASE_URL_FILE"] = ""
os.environ["MIGRATION_DATABASE_URL_FILE"] = ""
os.environ.setdefault("ENABLE_NGROK", "false")
os.environ.setdefault("ENABLE_DIAGNOSTIC_ROUTES", "false")
