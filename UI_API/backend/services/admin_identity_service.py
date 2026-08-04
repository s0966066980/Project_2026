"""Compatibility shim — remove after callers cut over to modules.identity."""

from __future__ import annotations

import sys

from modules.identity import _admin_identity_service as _impl

# Preserve monkeypatch surface used by existing tests and routes.
sys.modules[__name__] = _impl
