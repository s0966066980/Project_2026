"""Prepare separated local runtime directories and PostgreSQL secret files."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from modules.runtime_persistence.profile import configured_runtime_paths  # noqa: E402

DEFAULT_RUNTIME_ROOT = Path("/home/oliver/.local/share/project-2026")
DEFAULT_SECRET_ROOT = Path("/home/oliver/.config/project-2026/secrets")


def _write_secret(path: Path, value: str, *, replace: bool = False) -> bool:
    if path.exists():
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"Secret path is not a regular file: {path}")
        if replace:
            path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return replace
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)
    return True


def prepare(
    *,
    runtime_root: Path,
    secret_root: Path,
    host_port: int = 55432,
    refresh_database_urls: bool = False,
) -> dict[str, object]:
    repository_root = Path(__file__).resolve().parents[3]
    paths = configured_runtime_paths(
        {"RUNTIME_DATA_ROOT": str(runtime_root)},
        repository_root=repository_root,
    )
    paths.ensure(provision_database_paths=True)
    secret_root = secret_root.expanduser().resolve(strict=False)
    if secret_root == Path.home().resolve() or repository_root.resolve() in secret_root.parents:
        raise RuntimeError("Secret root must be outside the repository and narrower than the home directory")
    secret_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    secret_root.chmod(0o700)

    migration_password_path = secret_root / "postgres_migration_password"
    runtime_password_path = secret_root / "postgres_runtime_password"
    created = {
        "postgres_migration_password": _write_secret(migration_password_path, secrets.token_urlsafe(32)),
        "postgres_runtime_password": _write_secret(runtime_password_path, secrets.token_urlsafe(32)),
    }
    migration_password = migration_password_path.read_text(encoding="utf-8").strip()
    runtime_password = runtime_password_path.read_text(encoding="utf-8").strip()
    created["migration_database_url"] = _write_secret(
        secret_root / "migration_database_url",
        f"postgresql://project_migrator:{quote(migration_password, safe='')}@127.0.0.1:{host_port}/project_2026",
        replace=refresh_database_urls,
    )
    created["database_url"] = _write_secret(
        secret_root / "database_url",
        f"postgresql://project_runtime:{quote(runtime_password, safe='')}@127.0.0.1:{host_port}/project_2026",
        replace=refresh_database_urls,
    )
    return {
        "runtime_paths": paths.as_dict(),
        "secret_root": str(secret_root),
        "created": created,
        "secret_values_exposed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--secret-root", type=Path, default=DEFAULT_SECRET_ROOT)
    parser.add_argument("--host-port", type=int, default=55432)
    parser.add_argument(
        "--refresh-database-urls",
        action="store_true",
        help="Rewrite only database URL files; preserve PostgreSQL passwords.",
    )
    args = parser.parse_args()
    if not 1 <= args.host_port <= 65535:
        raise SystemExit("host port must be between 1 and 65535")
    print(
        json.dumps(
            prepare(
                runtime_root=args.runtime_root,
                secret_root=args.secret_root,
                host_port=args.host_port,
                refresh_database_urls=args.refresh_database_urls,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
