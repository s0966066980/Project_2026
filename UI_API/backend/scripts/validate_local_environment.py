#!/usr/bin/env python3
"""Validate local runtime profiles. Prints PASS/WARN/FAIL only — never secret values."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

PROFILES = {
    "local-dev": {
        "APP_ENV": "development",
        "DATABASE_BACKEND": "postgresql",
        "DATABASE_TOPOLOGY": "single",
        "SECURITY_ENFORCED": "false",
        "require_database_url": True,
        "require_redis": False,
    },
    "local-postgres": {
        "APP_ENV": "development",
        "DATABASE_BACKEND": "postgresql",
        "DATABASE_TOPOLOGY": "single",
        "SECURITY_ENFORCED": "false",
        "require_database_url": True,
        "require_redis": False,
    },
    "local-full": {
        "APP_ENV": "development",
        "DATABASE_BACKEND": "postgresql",
        "DATABASE_TOPOLOGY": "single",
        "SECURITY_ENFORCED": "true",
        "require_database_url": True,
        "require_redis": True,
        "require_no_demo": True,
    },
    "local-pilot": {
        "APP_ENV": "pilot",
        "DATABASE_BACKEND": "postgresql",
        "DATABASE_TOPOLOGY": "single",
        "SECURITY_ENFORCED": "true",
        "require_database_url": True,
        "require_redis": False,
        "require_no_demo": True,
    },
    "test": {
        "APP_ENV": "test",
        "DATABASE_BACKEND": "sqlite",
        "DATABASE_TOPOLOGY": "single",
        "SECURITY_ENFORCED": "false",
        "require_database_url": False,
        "require_redis": False,
    },
    "ci": {
        "APP_ENV": "test",
        "DATABASE_BACKEND": "sqlite",
        "DATABASE_TOPOLOGY": "single",
        "SECURITY_ENFORCED": "false",
        "require_database_url": False,
        "require_redis": False,
    },
}


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def _token_configured(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return text.upper() not in {"CHANGE_ME", "CHANGEME", "TODO", "REPLACE_ME"}


def apply_profile(name: str) -> dict[str, str]:
    if name not in PROFILES:
        raise SystemExit(f"FAIL: unknown profile {name}")
    profile = PROFILES[name]
    resolved = {
        # A named profile owns its identity and safety boundary. Ambient .env
        # values may provide credentials and paths, but cannot silently turn a
        # local-pilot validation into a development/SQLite validation.
        "APP_ENV": str(profile["APP_ENV"]),
        "DATABASE_BACKEND": str(profile["DATABASE_BACKEND"]),
        "DATABASE_TOPOLOGY": str(profile["DATABASE_TOPOLOGY"]),
        "SECURITY_ENFORCED": str(profile["SECURITY_ENFORCED"]),
        "DATABASE_URL": _env("DATABASE_URL"),
        "DATABASE_URL_FILE": _env("DATABASE_URL_FILE"),
        "REDIS_URL": _env("REDIS_URL"),
        "ENABLE_DEMO_ROUTES": "true" if name == "local-dev" else "false",
        "ENABLE_TEST_ROUTES": "true" if name in {"local-dev", "test", "ci"} else "false",
        "ENABLE_DEBUG_ROUTES": "false",
        "APP_PROFILE": name,
        "PAYMENT_BACKEND": _env("PAYMENT_BACKEND", "manual"),
        "POS_BACKEND": _env("POS_BACKEND", "manual"),
        "OBJECT_STORAGE_BACKEND": _env("OBJECT_STORAGE_BACKEND", "local" if name != "local-dev" else "memory"),
    }
    return resolved


def validate(name: str) -> int:
    profile = PROFILES[name]
    resolved = apply_profile(name)
    fails = 0
    warns = 0

    def pass_(msg: str) -> None:
        print(f"PASS: {msg}")

    def warn(msg: str) -> None:
        nonlocal warns
        warns += 1
        print(f"WARN: {msg}")

    def fail(msg: str) -> None:
        nonlocal fails
        fails += 1
        print(f"FAIL: {msg}")

    print(f"profile={name}")
    print(f"INFO: APP_ENV={resolved['APP_ENV']}")
    print(f"INFO: DATABASE_BACKEND={resolved['DATABASE_BACKEND']}")
    print(f"INFO: DATABASE_TOPOLOGY={resolved['DATABASE_TOPOLOGY']}")
    print(f"INFO: SECURITY_ENFORCED={resolved['SECURITY_ENFORCED']}")

    if _env("MEMBER_STORAGE_BACKEND") or _env("DATABASE_PORT"):
        fail("legacy MEMBER_STORAGE_BACKEND / DATABASE_PORT must be removed")
    elif resolved["DATABASE_BACKEND"] not in {"sqlite", "postgresql"}:
        fail("DATABASE_BACKEND must be sqlite or postgresql")
    else:
        pass_("storage backend recognized")

    if profile.get("require_database_url"):
        url_file = Path(resolved["DATABASE_URL_FILE"]) if resolved["DATABASE_URL_FILE"] else None
        if _token_configured(resolved["DATABASE_URL"]) or (url_file is not None and url_file.is_file()):
            pass_("DATABASE_URL or DATABASE_URL_FILE configured")
        else:
            fail("DATABASE_URL or DATABASE_URL_FILE required for this profile")
    else:
        pass_("DATABASE_URL not required")

    if profile.get("require_redis"):
        if _token_configured(resolved["REDIS_URL"]):
            pass_("REDIS_URL configured")
        else:
            fail("REDIS_URL required for local-full")
    else:
        if _token_configured(resolved["REDIS_URL"]):
            pass_("REDIS_URL optional present")
        else:
            warn("REDIS_URL not set (optional)")

    if profile.get("require_no_demo"):
        if resolved["ENABLE_DEMO_ROUTES"].lower() in {"1", "true", "yes", "on"}:
            fail(f"ENABLE_DEMO_ROUTES must be false for {name}")
        else:
            pass_("demo routes disabled")
        if resolved["ENABLE_DEBUG_ROUTES"].lower() in {"1", "true", "yes", "on"}:
            fail(f"ENABLE_DEBUG_ROUTES must be false for {name}")
        else:
            pass_("debug routes disabled")

    if resolved["DATABASE_BACKEND"] == "postgresql":
        url_file = Path(resolved["DATABASE_URL_FILE"]) if resolved["DATABASE_URL_FILE"] else None
        if not _token_configured(resolved["DATABASE_URL"]) and not (url_file is not None and url_file.is_file()):
            fail("postgresql backend without DATABASE_URL or DATABASE_URL_FILE")

    if name == "local-pilot":
        # Run the same fail-closed safety contract used by UI_API startup. The
        # validator must never report a pilot profile as safe when main.py
        # would reject it for missing identity, scope, or signing material.
        os.environ.update(resolved)
        try:
            import config

            config.validate_startup_config()
        except RuntimeError as exc:
            fail(f"startup safety contract: {exc}")
        else:
            pass_("startup safety contract")

    print(f"summary: fail={fails} warn={warns}")
    return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Project_2026 local profiles")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="local-dev",
        help="Profile to validate (default local-dev)",
    )
    parser.add_argument("--list", action="store_true", help="List profiles")
    parser.add_argument(
        "--no-env-files",
        action="store_true",
        help="Do not load the supported UI_API/.env and repository .env files (isolated tests only)",
    )
    args = parser.parse_args(argv)
    if args.list:
        for name, meta in PROFILES.items():
            print(f"{name}: storage={meta['DATABASE_BACKEND']} redis_required={meta.get('require_redis')}")
        return 0
    if not args.no_env_files:
        from modules.runtime_persistence import load_environment_files

        load_environment_files(ROOT.parent)
    return validate(args.profile)


if __name__ == "__main__":
    raise SystemExit(main())
