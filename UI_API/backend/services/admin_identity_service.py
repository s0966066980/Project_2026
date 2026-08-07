"""Compatibility shim — remove after callers cut over to modules.identity."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from modules.identity import _admin_identity_service as _impl

if TYPE_CHECKING:
    # The runtime swap below is invisible to static analysis, so the names are
    # re-exported here for type checking only.
    from modules.identity._admin_identity_service import *  # noqa: F403

# Preserve monkeypatch surface used by existing tests and routes.
sys.modules[__name__] = _impl
