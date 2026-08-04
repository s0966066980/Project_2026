"""Architecture: track compatibility shims for removal."""

from __future__ import annotations

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"

# Temporary allowlist — must shrink to empty.
COMPAT_SHIMS = {
    "services/admin_identity_service.py",
    "services/admin_authorization_service.py",
    "services/admin_access_service.py",
    "repositories/admin_identity_repository.py",
}


def test_compatibility_shims_are_explicitly_listed() -> None:
    found: set[str] = set()
    for rel in COMPAT_SHIMS:
        path = BACKEND / rel
        if path.is_file() and "Compatibility shim" in path.read_text(encoding="utf-8"):
            found.add(rel)
    # All listed shims currently exist during cutover.
    assert found == COMPAT_SHIMS
