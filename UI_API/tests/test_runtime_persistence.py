from __future__ import annotations

import os
from pathlib import Path

import pytest
from modules.runtime_persistence.database import PostgresConnectionPool
from modules.runtime_persistence.profile import PersistenceConfigurationError, load_profile
from modules.runtime_persistence.runtime import load_environment_files


def _environment(tmp_path: Path, **overrides: str) -> dict[str, str]:
    values = {
        "APP_ENV": "development",
        "DATABASE_BACKEND": "postgresql",
        "DATABASE_TOPOLOGY": "single",
        "DATABASE_URL": "postgresql://runtime@127.0.0.1:5432/project_2026",
        "RUNTIME_DATA_ROOT": str(tmp_path / "runtime"),
    }
    values.update(overrides)
    return values


def test_supported_environment_files_share_one_non_overriding_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    ui_api = repository / "UI_API"
    ui_api.mkdir(parents=True)
    (ui_api / ".env").write_text("DATABASE_URL_FILE=/private/runtime-url\n", encoding="utf-8")
    (repository / ".env").write_text(
        "DATABASE_URL_FILE=/must-not-override\nDATABASE_TOPOLOGY=single\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
    monkeypatch.delenv("DATABASE_TOPOLOGY", raising=False)

    load_environment_files(repository)

    assert os.environ["DATABASE_URL_FILE"] == "/private/runtime-url"
    assert os.environ["DATABASE_TOPOLOGY"] == "single"


def test_external_deployment_environment_precedes_repository_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    ui_api = repository / "UI_API"
    ui_api.mkdir(parents=True)
    external = tmp_path / "private" / "pilot.env"
    external.parent.mkdir()
    external.write_text("APP_ENV=pilot\nDATABASE_TOPOLOGY=single\n", encoding="utf-8")
    external.chmod(0o600)
    (ui_api / ".env").write_text("APP_ENV=development\n", encoding="utf-8")
    monkeypatch.setenv("PROJECT_2026_ENV_FILE", str(external))
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DATABASE_TOPOLOGY", raising=False)

    load_environment_files(repository)

    assert os.environ["APP_ENV"] == "pilot"
    assert os.environ["DATABASE_TOPOLOGY"] == "single"


def test_single_host_profile_uses_distinct_private_runtime_directories(tmp_path: Path) -> None:
    profile = load_profile(_environment(tmp_path), repository_root=tmp_path / "repository")

    profile.runtime_paths.ensure(provision_database_paths=True)
    paths = profile.runtime_paths.as_dict()
    leaf_paths = [Path(value) for name, value in paths.items() if name != "root"]

    assert profile.topology == "single"
    assert len(leaf_paths) == len(set(leaf_paths))
    assert all(path.is_dir() for path in leaf_paths)
    assert all(path.stat().st_mode & 0o777 == 0o700 for path in leaf_paths)
    assert profile.runtime_paths.postgres_data != profile.runtime_paths.objects
    assert profile.runtime_paths.objects != profile.runtime_paths.rag_indexes


def test_application_startup_does_not_chmod_postgres_owned_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = load_profile(_environment(tmp_path), repository_root=tmp_path / "repository")
    paths = profile.runtime_paths
    paths.ensure()
    database_paths = {paths.postgres_data, paths.postgres_wal_archive}
    real_chmod = Path.chmod

    def guarded_chmod(path: Path, mode: int, *args, **kwargs) -> None:
        if path in database_paths:
            raise PermissionError(f"application attempted database chmod: {path}")
        real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "chmod", guarded_chmod)

    paths.ensure()


def test_production_reserves_ha_topology_contract(tmp_path: Path) -> None:
    with pytest.raises(PersistenceConfigurationError, match="DATABASE_TOPOLOGY=ha"):
        load_profile(
            _environment(tmp_path, APP_ENV="production", DATABASE_TOPOLOGY="single"),
            repository_root=tmp_path / "repository",
        )

    profile = load_profile(
        _environment(tmp_path, APP_ENV="production", DATABASE_TOPOLOGY="ha"),
        repository_root=tmp_path / "repository",
    )
    assert profile.topology == "ha"


def test_runtime_root_cannot_be_inside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    with pytest.raises(PersistenceConfigurationError, match="outside the Git repository"):
        load_profile(
            _environment(tmp_path, RUNTIME_DATA_ROOT=str(repository / "runtime")),
            repository_root=repository,
        )


def test_database_secret_file_must_be_private(tmp_path: Path) -> None:
    secret = tmp_path / "database-url"
    secret.write_text("postgresql://runtime@127.0.0.1/project_2026", encoding="utf-8")
    secret.chmod(0o644)
    values = _environment(tmp_path, DATABASE_URL="", DATABASE_URL_FILE=str(secret))

    with pytest.raises(PersistenceConfigurationError, match="0600"):
        load_profile(values, repository_root=tmp_path / "repository")


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def test_pool_close_rolls_back_before_reuse(monkeypatch) -> None:
    connection = _FakeConnection()
    monkeypatch.setattr(PostgresConnectionPool, "_open", staticmethod(lambda _url: connection))
    pool = PostgresConnectionPool(url="postgresql://example/project", maximum_size=1)

    lease = pool.acquire()
    lease.close()
    next_lease = pool.acquire()

    assert connection.rollbacks == 1
    assert next_lease._connection is connection
    next_lease.close()
    pool.close()


def test_postgres_container_mounts_only_database_owned_directories() -> None:
    compose = Path(__file__).resolve().parents[1] / "deploy" / "postgres" / "compose.yaml"
    text = compose.read_text(encoding="utf-8")
    postgres_service = text.split("secrets:\n", 1)[0]

    assert "/postgres/pgdata:" in postgres_service
    assert "/postgres/wal-archive:" in postgres_service
    assert "127.0.0.1:55432:5432" in postgres_service
    assert "entrypoint: /project-entrypoint.sh" in postgres_service
    assert "./project-entrypoint.sh:/project-entrypoint.sh:ro" in postgres_service
    for application_directory in ("/objects:", "/rag/indexes:", "/logs:", "/exports:", "/imports:"):
        assert application_directory not in postgres_service


def test_runtime_code_never_applies_schema_migrations() -> None:
    backend = Path(__file__).resolve().parents[1] / "backend"
    offenders: list[str] = []
    for path in backend.rglob("*.py"):
        if path == backend / "repositories" / "postgres_utils.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "postgres_utils.init_schema(" in source:
            offenders.append(str(path.relative_to(backend)))

    assert offenders == []


def test_schema_maintenance_has_one_explicit_module_interface() -> None:
    from modules.runtime_persistence import migrations

    assert callable(migrations.inspect_schema)
    assert callable(migrations.require_schema_head)
    assert callable(migrations.migrate_to_head)


def test_postgres_domain_stores_do_not_require_sqlite_paths() -> None:
    from modules.cart.postgres_store import PostgresCartStore
    from modules.checkout_confirmation.postgres_store import PostgresCheckoutStore
    from modules.knowledge_publication.postgres_store import PostgresPublicationStore
    from modules.ordering_entry.postgres_store import PostgresEntryFlowStore
    from modules.voice_turn.postgres_store import PostgresVoiceTurnStore

    stores = (
        PostgresCartStore(),
        PostgresCheckoutStore(),
        PostgresPublicationStore(),
        PostgresEntryFlowStore(),
        PostgresVoiceTurnStore(),
    )

    assert len(stores) == 5
