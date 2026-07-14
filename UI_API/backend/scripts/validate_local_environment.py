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
        "MEMBER_STORAGE_BACKEND": "json",
        "SECURITY_ENFORCED": "false",
        "require_database_url": False,
        "require_redis": False,
    },
    "local-postgres": {
        "APP_ENV": "development",
        "MEMBER_STORAGE_BACKEND": "postgres",
        "SECURITY_ENFORCED": "false",
        "require_database_url": True,
        "require_redis": False,
    },
    "local-full": {
        "APP_ENV": "development",
        "MEMBER_STORAGE_BACKEND": "postgres",
        "SECURITY_ENFORCED": "true",
        "require_database_url": True,
        "require_redis": True,
        "require_no_demo": True,
    },
    "local-pilot": {
        "APP_ENV": "production",
        "MEMBER_STORAGE_BACKEND": "postgres",
        "SECURITY_ENFORCED": "true",
        "require_database_url": True,
        "require_redis": False,
        "require_no_demo": True,
    },
    "test": {
        "APP_ENV": "test",
        "MEMBER_STORAGE_BACKEND": "json",
        "SECURITY_ENFORCED": "false",
        "require_database_url": False,
        "require_redis": False,
    },
    "ci": {
        "APP_ENV": "test",
        "MEMBER_STORAGE_BACKEND": "json",
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
        "APP_ENV": _env("APP_ENV", str(profile["APP_ENV"])),
        "MEMBER_STORAGE_BACKEND": _env("MEMBER_STORAGE_BACKEND", str(profile["MEMBER_STORAGE_BACKEND"])),
        "SECURITY_ENFORCED": _env("SECURITY_ENFORCED", str(profile["SECURITY_ENFORCED"])),
        "DATABASE_URL": _env("DATABASE_URL"),
        "REDIS_URL": _env("REDIS_URL"),
        "ENABLE_DEMO_ROUTES": _env(
            "ENABLE_DEMO_ROUTES",
            "true" if name == "local-dev" else "false",
        ),
        "ENABLE_TEST_ROUTES": _env(
            "ENABLE_TEST_ROUTES",
            "true" if name in {"local-dev", "test", "ci"} else "false",
        ),
        "ENABLE_DEBUG_ROUTES": _env("ENABLE_DEBUG_ROUTES", "false"),
        "APP_PROFILE": _env("APP_PROFILE", name),
        "PAYMENT_BACKEND": _env("PAYMENT_BACKEND", "manual"),
        "POS_BACKEND": _env("POS_BACKEND", "manual"),
        "OBJECT_STORAGE_BACKEND": _env("OBJECT_STORAGE_BACKEND", "local" if name != "local-dev" else "memory"),
    }
    # Environment overrides profile defaults already applied via _env second arg only when unset.
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
    print(f"INFO: MEMBER_STORAGE_BACKEND={resolved['MEMBER_STORAGE_BACKEND']}")
    print(f"INFO: SECURITY_ENFORCED={resolved['SECURITY_ENFORCED']}")

    if resolved["MEMBER_STORAGE_BACKEND"] not in {"json", "postgres"}:
        fail("MEMBER_STORAGE_BACKEND must be json or postgres")
    else:
        pass_("storage backend recognized")

    if profile.get("require_database_url"):
        if _token_configured(resolved["DATABASE_URL"]):
            pass_("DATABASE_URL configured")
        else:
            fail("DATABASE_URL required for this profile")
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
            fail("ENABLE_DEMO_ROUTES must be false for local-full")
        else:
            pass_("demo routes disabled")
        if resolved["ENABLE_DEBUG_ROUTES"].lower() in {"1", "true", "yes", "on"}:
            fail("ENABLE_DEBUG_ROUTES must be false for local-full")
        else:
            pass_("debug routes disabled")

    if resolved["MEMBER_STORAGE_BACKEND"] == "postgres" and not _token_configured(resolved["DATABASE_URL"]):
        fail("postgres backend without DATABASE_URL")

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
    args = parser.parse_args(argv)
    if args.list:
        for name, meta in PROFILES.items():
            print(f"{name}: storage={meta['MEMBER_STORAGE_BACKEND']} redis_required={meta.get('require_redis')}")
        return 0
    return validate(args.profile)


if __name__ == "__main__":
    raise SystemExit(main())
