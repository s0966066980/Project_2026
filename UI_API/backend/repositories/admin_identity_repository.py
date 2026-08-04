"""Compatibility shim — remove after callers cut over to modules.identity.adapters.postgres."""

from __future__ import annotations

import sys

from modules.identity.adapters import postgres as _impl

sys.modules[__name__] = _impl
