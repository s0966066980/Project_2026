"""Compatibility shim — remove after callers cut over to modules.identity."""

from __future__ import annotations

import sys

from modules.identity import _admin_authorization_service as _impl

sys.modules[__name__] = _impl
