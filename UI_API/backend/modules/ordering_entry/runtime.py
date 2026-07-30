from threading import Lock

from modules.checkout_confirmation import runtime as checkout_runtime
from modules.runtime_persistence.runtime import sqlite_database_path

from repositories import menu_repository, postgres_utils

from .module import OrderingEntryFlowModule
from .postgres_store import PostgresEntryFlowStore
from .sqlite_store import SQLiteEntryFlowStore

_DEFAULT = None
_KEY = ""
_LOCK = Lock()


class ProductionMenuBootstrap:
    def initialize(self, *, scope, session_id):
        if not session_id:
            raise RuntimeError("ordering_session_missing")
        if not any(row.get("available", True) is not False for row in menu_repository.get_menu()):
            raise RuntimeError("available_menu_snapshot_missing")
        checkout_runtime.default_cart().get(scope=scope, session_id=session_id)

    def abandon(self, *, scope, session_id):
        checkout_runtime.default_cart().close(scope=scope, session_id=session_id, abandoned=True)


def default_module():
    global _DEFAULT, _KEY
    path = sqlite_database_path()
    with _LOCK:
        if _DEFAULT is None or _KEY != path:
            _DEFAULT = OrderingEntryFlowModule(
                PostgresEntryFlowStore() if postgres_utils.use_postgres() else SQLiteEntryFlowStore(path),
                ProductionMenuBootstrap(),
            )
            _KEY = path
    return _DEFAULT


def reset_default_for_tests():
    global _DEFAULT, _KEY
    with _LOCK:
        _DEFAULT = None
        _KEY = ""
