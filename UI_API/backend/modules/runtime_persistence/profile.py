from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import unquote, urlsplit


class PersistenceConfigurationError(RuntimeError):
    pass


_LEGACY_SELECTION_KEYS = ("MEMBER_STORAGE_BACKEND", "DATABASE_PORT")
_BACKENDS = {"postgresql", "sqlite"}
_TOPOLOGIES = {"single", "ha"}
_COMMERCIAL_ENVS = {"staging", "pilot", "production"}
_DIRECTORY_NAMES = {
    "postgres_data": ("postgres", "pgdata"),
    "postgres_wal_archive": ("postgres", "wal-archive"),
    "postgres_backups": ("backups", "postgres"),
    "sqlite": ("sqlite",),
    "objects": ("objects",),
    "rag_indexes": ("rag", "indexes"),
    "logs": ("logs",),
    "exports": ("exports",),
    "imports": ("imports",),
    "tmp": ("tmp",),
}
_DATABASE_OWNED_DIRECTORIES = frozenset({"postgres_data", "postgres_wal_archive"})


def _clean(value: object) -> str:
    return str(value or "").strip()


def _secret_value(environment: Mapping[str, str], name: str) -> str:
    direct = _clean(environment.get(name))
    file_name = _clean(environment.get(f"{name}_FILE"))
    if direct and file_name:
        raise PersistenceConfigurationError(f"Configure only one of {name} or {name}_FILE")
    if direct:
        return direct
    if not file_name:
        return ""
    path = Path(file_name).expanduser()
    if not path.is_file() or path.is_symlink():
        raise PersistenceConfigurationError(f"{name}_FILE must reference a regular, non-symlink file")
    if path.stat().st_mode & 0o077:
        raise PersistenceConfigurationError(f"{name}_FILE permissions must be 0600 or stricter")
    return path.read_text(encoding="utf-8").strip()


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.exists() and current.is_symlink():
            return True
    return False


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    postgres_data: Path
    postgres_wal_archive: Path
    postgres_backups: Path
    sqlite: Path
    objects: Path
    rag_indexes: Path
    logs: Path
    exports: Path
    imports: Path
    tmp: Path

    @property
    def sqlite_database(self) -> Path:
        return self.sqlite / "runtime.sqlite3"

    def as_dict(self) -> dict[str, str]:
        return {
            key: str(getattr(self, key))
            for key in (
                "root",
                "postgres_data",
                "postgres_wal_archive",
                "postgres_backups",
                "sqlite",
                "objects",
                "rag_indexes",
                "logs",
                "exports",
                "imports",
                "tmp",
            )
        }

    def ensure(self, *, provision_database_paths: bool = False) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        for name in _DIRECTORY_NAMES:
            path = getattr(self, name)
            if name in _DATABASE_OWNED_DIRECTORIES and not provision_database_paths:
                if not path.exists():
                    continue
                if not path.is_dir() or path.is_symlink():
                    raise PersistenceConfigurationError(
                        f"Database-owned runtime path must be a real directory: {path}"
                    )
                if path.stat().st_mode & 0o077:
                    raise PersistenceConfigurationError(
                        f"Database-owned runtime path must not be group/world accessible: {path}"
                    )
                continue
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.chmod(0o700)


@dataclass(frozen=True)
class PersistenceProfile:
    app_env: str
    backend: str
    topology: str
    runtime_paths: RuntimePaths
    database_url: str
    migration_database_url: str
    postgres_required_major: int = 18

    @property
    def is_postgresql(self) -> bool:
        return self.backend == "postgresql"

    @property
    def is_commercial(self) -> bool:
        return self.app_env in _COMMERCIAL_ENVS

    def endpoint_summary(self) -> dict[str, object]:
        if not self.is_postgresql or not self.database_url:
            return {"configured": False, "fingerprint": ""}
        parsed = urlsplit(self.database_url)
        host = parsed.hostname or ""
        port = parsed.port or 5432
        database = unquote(parsed.path.lstrip("/"))
        identity = f"{host.lower()}:{port}/{database}"
        query = parsed.query.lower()
        return {
            "configured": True,
            "host_alias": host,
            "port": port,
            "database": database,
            "tls_requested": "sslmode=" in query and "sslmode=disable" not in query,
            "fingerprint": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
        }


def _runtime_paths(root: Path, *, repository_root: Path | None) -> RuntimePaths:
    resolved = root.expanduser().resolve(strict=False)
    home = Path.home().resolve()
    forbidden = {Path("/").resolve(), home}
    if repository_root is not None:
        repository = repository_root.resolve()
        forbidden.update({repository, repository / "UI_API"})
        if resolved == repository or repository in resolved.parents:
            raise PersistenceConfigurationError("RUNTIME_DATA_ROOT must be outside the Git repository")
    if resolved in forbidden:
        raise PersistenceConfigurationError("RUNTIME_DATA_ROOT is too broad")
    if _has_symlink_component(resolved):
        raise PersistenceConfigurationError("RUNTIME_DATA_ROOT must not traverse symbolic links")
    values = {name: resolved.joinpath(*parts) for name, parts in _DIRECTORY_NAMES.items()}
    paths = list(values.values())
    if len({path.resolve(strict=False) for path in paths}) != len(paths):
        raise PersistenceConfigurationError("Runtime data directories must not overlap")
    return RuntimePaths(root=resolved, **values)


def load_profile(
    environment: Mapping[str, str] | None = None,
    *,
    repository_root: Path | None = None,
) -> PersistenceProfile:
    values = environment if environment is not None else os.environ
    legacy = [name for name in _LEGACY_SELECTION_KEYS if _clean(values.get(name))]
    if legacy:
        raise PersistenceConfigurationError(
            "Legacy database selection is not supported; remove " + ", ".join(sorted(legacy))
        )
    if _clean(values.get("ALLOW_POSTGRES_JSON_FALLBACK")).lower() in {"1", "true", "yes", "on"}:
        raise PersistenceConfigurationError("ALLOW_POSTGRES_JSON_FALLBACK is no longer supported")
    backend = _clean(values.get("DATABASE_BACKEND") or "postgresql").lower()
    if backend == "postgres":
        raise PersistenceConfigurationError("DATABASE_BACKEND must be 'postgresql', not 'postgres'")
    if backend not in _BACKENDS:
        raise PersistenceConfigurationError("DATABASE_BACKEND must be one of: postgresql, sqlite")
    topology = _clean(values.get("DATABASE_TOPOLOGY") or "single").lower()
    if topology not in _TOPOLOGIES:
        raise PersistenceConfigurationError("DATABASE_TOPOLOGY must be one of: single, ha")
    app_env = _clean(values.get("APP_ENV") or "development").lower()
    if app_env == "production" and topology != "ha":
        raise PersistenceConfigurationError("production requires DATABASE_TOPOLOGY=ha")
    if app_env in _COMMERCIAL_ENVS and backend != "postgresql":
        raise PersistenceConfigurationError(f"{app_env} requires DATABASE_BACKEND=postgresql")

    paths = configured_runtime_paths(values, repository_root=repository_root)
    database_url = _secret_value(values, "DATABASE_URL")
    migration_url = _secret_value(values, "MIGRATION_DATABASE_URL")
    if backend == "postgresql" and not database_url:
        raise PersistenceConfigurationError("DATABASE_URL or DATABASE_URL_FILE is required for PostgreSQL")
    return PersistenceProfile(
        app_env=app_env,
        backend=backend,
        topology=topology,
        runtime_paths=paths,
        database_url=database_url,
        migration_database_url=migration_url,
    )


def configured_runtime_paths(
    environment: Mapping[str, str] | None = None,
    *,
    repository_root: Path | None = None,
) -> RuntimePaths:
    values = environment if environment is not None else os.environ
    root_value = _clean(values.get("RUNTIME_DATA_ROOT"))
    root = Path(root_value) if root_value else Path.home() / ".local" / "share" / "project-2026"
    return _runtime_paths(root, repository_root=repository_root)
