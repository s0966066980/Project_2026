from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .profile import PersistenceProfile, load_profile

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def load_environment_files(repository_root: Path | None = None) -> None:
    """Load supported local deployment files without overriding process env."""

    root = Path(repository_root or REPOSITORY_ROOT)
    external_file = str(os.getenv("PROJECT_2026_ENV_FILE", "") or "").strip()
    if external_file:
        external_path = Path(external_file).expanduser()
        if not external_path.is_file():
            raise RuntimeError(f"PROJECT_2026_ENV_FILE does not exist: {external_path}")
        load_dotenv(external_path, override=False)
    load_dotenv(root / "UI_API" / ".env", override=False)
    load_dotenv(root / ".env", override=False)


def current_profile(*, app_env: str | None = None) -> PersistenceProfile:
    load_environment_files()
    environment = dict(os.environ)
    if app_env is not None:
        environment["APP_ENV"] = str(app_env)
    return load_profile(environment, repository_root=REPOSITORY_ROOT)


def ensure_runtime_paths() -> dict[str, str]:
    profile = current_profile()
    profile.runtime_paths.ensure()
    return profile.runtime_paths.as_dict()


def sqlite_database_path() -> str:
    profile = current_profile()
    profile.runtime_paths.ensure()
    return str(profile.runtime_paths.sqlite_database)
