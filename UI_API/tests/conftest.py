"""Shared test bootstrap for the public backend contract suite."""

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_BACKEND", "sqlite")
os.environ.setdefault("DATABASE_URL", "")
os.environ["DATABASE_URL_FILE"] = ""
os.environ["MIGRATION_DATABASE_URL_FILE"] = ""
os.environ.setdefault("ENABLE_NGROK", "false")
os.environ.setdefault("ENABLE_DIAGNOSTIC_ROUTES", "false")
