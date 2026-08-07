"""Compatibility shim — remove after callers cut over to modules.identity.adapters.postgres."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from modules.identity.adapters import postgres as _impl

if TYPE_CHECKING:
    # The runtime swap below is invisible to static analysis, so the names are
    # re-exported here for type checking only.
    from modules.identity.adapters.postgres import *  # noqa: F403

sys.modules[__name__] = _impl
