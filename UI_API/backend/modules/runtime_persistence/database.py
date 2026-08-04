from __future__ import annotations

import threading
from contextlib import suppress
from queue import Empty, Full, LifoQueue
from typing import Any


class PersistenceConnectionError(RuntimeError):
    pass


class _ConnectionLease:
    def __init__(self, pool: "PostgresConnectionPool", connection: Any):
        self._pool = pool
        self._connection = connection
        self._released = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        broken = exc_type is not None
        try:
            if broken:
                self._connection.rollback()
            else:
                self._connection.commit()
        except Exception:
            broken = True
            raise
        finally:
            self._release(broken=broken)
        return False

    def __getattr__(self, name: str):
        return getattr(self._connection, name)

    def close(self) -> None:
        if self._released:
            return
        broken = False
        try:
            # `close()` must never return an open transaction to the pool.
            # Domain adapters commit explicitly; rollback is harmless after a
            # commit and protects the next borrower after an early return.
            self._connection.rollback()
        except Exception:
            broken = True
        self._release(broken=broken)

    def _release(self, *, broken: bool) -> None:
        if self._released:
            return
        self._released = True
        self._pool.release(self._connection, broken=broken)


class PostgresConnectionPool:
    def __init__(self, *, url: str, minimum_size: int = 1, maximum_size: int = 10, timeout_seconds: float = 5.0):
        self.url = str(url or "").strip()
        if not self.url:
            raise PersistenceConnectionError("PostgreSQL connection URL is required")
        self.minimum_size = max(0, int(minimum_size))
        self.maximum_size = max(1, int(maximum_size))
        if self.minimum_size > self.maximum_size:
            raise PersistenceConnectionError("Database pool minimum cannot exceed maximum")
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self._available: LifoQueue[Any] = LifoQueue(maxsize=self.maximum_size)
        self._created = 0
        self._lock = threading.Lock()
        self._closed = False

    @staticmethod
    def _open(url: str):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except Exception as exc:
            raise PersistenceConnectionError("psycopg is required for PostgreSQL storage") from exc
        try:
            return psycopg.connect(url, row_factory=dict_row)
        except Exception as exc:
            raise PersistenceConnectionError("Unable to connect to PostgreSQL") from exc

    def warm(self) -> None:
        while self._created < self.minimum_size:
            connection = self._create_if_allowed()
            if connection is None:
                break
            self.release(connection, broken=False)

    def _create_if_allowed(self):
        with self._lock:
            if self._closed:
                raise PersistenceConnectionError("Database connection pool is closed")
            if self._created >= self.maximum_size:
                return None
            self._created += 1
        try:
            return self._open(self.url)
        except Exception:
            with self._lock:
                self._created -= 1
            raise

    def acquire(self) -> _ConnectionLease:
        if self._closed:
            raise PersistenceConnectionError("Database connection pool is closed")
        try:
            connection = self._available.get_nowait()
        except Empty:
            connection = self._create_if_allowed()
            if connection is None:
                try:
                    connection = self._available.get(timeout=self.timeout_seconds)
                except Empty as exc:
                    raise PersistenceConnectionError("Timed out waiting for a PostgreSQL connection") from exc
        if getattr(connection, "closed", False):
            self.release(connection, broken=True)
            return self.acquire()
        return _ConnectionLease(self, connection)

    def release(self, connection: Any, *, broken: bool) -> None:
        if broken or self._closed or getattr(connection, "closed", False):
            with suppress(Exception):
                connection.close()
            with self._lock:
                self._created = max(0, self._created - 1)
            return
        try:
            self._available.put_nowait(connection)
        except Full:
            with suppress(Exception):
                connection.close()
            with self._lock:
                self._created = max(0, self._created - 1)

    def close(self) -> None:
        with self._lock:
            self._closed = True
        while True:
            try:
                connection = self._available.get_nowait()
            except Empty:
                break
            with suppress(Exception):
                connection.close()
            with self._lock:
                self._created = max(0, self._created - 1)


_RUNTIME_POOL: PostgresConnectionPool | None = None
_RUNTIME_POOL_KEY: tuple[str, int, int, float] | None = None
_POOL_LOCK = threading.Lock()


def pooled_connection(
    *,
    url: str,
    minimum_size: int = 1,
    maximum_size: int = 10,
    timeout_seconds: float = 5.0,
):
    global _RUNTIME_POOL, _RUNTIME_POOL_KEY
    key = (url, int(minimum_size), int(maximum_size), float(timeout_seconds))
    with _POOL_LOCK:
        if _RUNTIME_POOL is None or _RUNTIME_POOL_KEY != key:
            if _RUNTIME_POOL is not None:
                _RUNTIME_POOL.close()
            _RUNTIME_POOL = PostgresConnectionPool(
                url=url,
                minimum_size=minimum_size,
                maximum_size=maximum_size,
                timeout_seconds=timeout_seconds,
            )
            _RUNTIME_POOL_KEY = key
        pool = _RUNTIME_POOL
    return pool.acquire()


def direct_connection(*, url: str):
    return PostgresConnectionPool._open(url)


def reset_pool_for_tests() -> None:
    global _RUNTIME_POOL, _RUNTIME_POOL_KEY
    with _POOL_LOCK:
        if _RUNTIME_POOL is not None:
            _RUNTIME_POOL.close()
        _RUNTIME_POOL = None
        _RUNTIME_POOL_KEY = None
