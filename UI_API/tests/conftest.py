"""Shared test bootstrap for the public backend contract suite."""

import os
import sys
from pathlib import Path

# The Project Analyst Sidecar is a separate service at the repository root, and
# deliberately not importable by the application: nothing under UI_API/backend
# may reach into it. Its contract still has to be gated by the same required
# checks as the code that calls it, so the suite can import it even though the
# application cannot.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_BACKEND", "sqlite")
os.environ.setdefault("DATABASE_URL", "")
os.environ["DATABASE_URL_FILE"] = ""
os.environ["MIGRATION_DATABASE_URL_FILE"] = ""
os.environ.setdefault("ENABLE_NGROK", "false")
os.environ.setdefault("ENABLE_DIAGNOSTIC_ROUTES", "false")
