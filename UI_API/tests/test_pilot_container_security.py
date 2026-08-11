"""The Pilot runtime contract, asserted on the overlay that defines it.

Container hardening is not something a comment can hold. `docker/compose.pilot.yaml`
is the only file that turns the development stack into a Pilot, so the properties
that make it a Pilot — no writable root filesystem, no Linux capabilities, no
root, no privilege escalation, no development configuration authority — are
asserted here rather than left to whoever last edited the overlay.

These tests read the overlay as written, including its YAML merge keys, so a
service that quietly stops inheriting the hardening anchor fails immediately.
"""

from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PILOT_OVERLAY = REPOSITORY_ROOT / "docker" / "compose.pilot.yaml"
BASE_COMPOSE = REPOSITORY_ROOT / "docker" / "compose.yaml"

# The application containers. postgres, ollama and r1-omni keep their upstream
# runtime contract and are deliberately out of this overlay's scope.
HARDENED_SERVICES = ("migrate", "app", "worker")

RUNTIME_UID = "10001"

REQUIRED_SECRETS = ("pilot_env", "database_url", "migration_database_url")


@pytest.fixture(scope="module")
def overlay() -> dict:
    return yaml.safe_load(PILOT_OVERLAY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def base_compose() -> dict:
    return yaml.safe_load(BASE_COMPOSE.read_text(encoding="utf-8"))


def test_the_pilot_overlay_exists_and_covers_every_application_service(overlay):
    services = overlay["services"]
    assert set(HARDENED_SERVICES) <= set(services), (
        "Every application container must be hardened by the Pilot overlay; "
        f"missing: {sorted(set(HARDENED_SERVICES) - set(services))}"
    )


@pytest.mark.parametrize("service", HARDENED_SERVICES)
def test_pilot_services_run_with_a_read_only_root_filesystem(overlay, service):
    assert overlay["services"][service]["read_only"] is True


@pytest.mark.parametrize("service", HARDENED_SERVICES)
def test_pilot_services_drop_every_linux_capability(overlay, service):
    definition = overlay["services"][service]
    assert definition["cap_drop"] == ["ALL"]
    # A capability may only come back with observed runtime evidence behind it.
    # Granting one here without that evidence is the failure this test names.
    assert "cap_add" not in definition


@pytest.mark.parametrize("service", HARDENED_SERVICES)
def test_pilot_services_forbid_privilege_escalation(overlay, service):
    assert "no-new-privileges:true" in overlay["services"][service]["security_opt"]


@pytest.mark.parametrize("service", HARDENED_SERVICES)
def test_pilot_services_run_as_the_non_root_runtime_principal(overlay, service):
    user = str(overlay["services"][service]["user"])
    assert user.split(":")[0] == RUNTIME_UID
    assert not user.startswith("0")
    assert "root" not in user


@pytest.mark.parametrize("service", HARDENED_SERVICES)
def test_pilot_services_open_only_the_declared_writable_tmpfs(overlay, service):
    mounts = overlay["services"][service]["tmpfs"]
    assert [mount.split(":")[0] for mount in mounts] == ["/tmp"], (
        "The root filesystem stays read-only; only /tmp is granted back, and any "
        "further writable path needs its own justification and evidence."
    )
    options = mounts[0].split(":", 1)[1]
    assert "nosuid" in options
    assert "nodev" in options


@pytest.mark.parametrize("service", HARDENED_SERVICES)
def test_pilot_services_read_configuration_from_host_external_secrets(overlay, service):
    declared = overlay["services"][service]["secrets"]
    assert set(REQUIRED_SECRETS) <= set(declared)


def test_the_pilot_configuration_authority_is_required_and_host_external(overlay):
    secrets = overlay["secrets"]
    assert set(REQUIRED_SECRETS) == set(secrets)
    for name in REQUIRED_SECRETS:
        source = secrets[name]["file"]
        # `${VAR:?message}` makes `docker compose config` fail before a Pilot can
        # boot on development defaults. A plain `${VAR}` or a repository-relative
        # path would let an unconfigured Pilot start and look healthy.
        assert source.startswith("${") and ":?" in source, (
            f"Pilot secret '{name}' must come from a required host-external variable"
        )
        assert ".env" not in source
        assert not source.lstrip("${").startswith((".", "/"))


@pytest.mark.parametrize("service", HARDENED_SERVICES)
def test_pilot_services_declare_the_commercial_fail_closed_environment(overlay, service):
    environment = overlay["services"][service]["environment"]
    assert environment["APP_ENV"] == "pilot"
    assert environment["SECURITY_ENFORCED"] == "true"
    for disabled in (
        "ENABLE_NGROK",
        "ENABLE_DEMO_ROUTES",
        "ENABLE_DIAGNOSTIC_ROUTES",
        "ENABLE_DEBUG_ROUTES",
        "ENABLE_LEGACY_KIOSK_TOKEN",
        "ALLOW_UNSAFE_PRODUCTION_ROUTES",
        "ALLOW_POSTGRES_JSON_FALLBACK",
    ):
        assert environment[disabled] == "false", f"{disabled} must be false in the Pilot profile"
    assert environment["STRUCTURED_LOGGING_ENABLED"] == "true"


@pytest.mark.parametrize("service", HARDENED_SERVICES)
def test_pilot_database_credentials_come_only_from_secret_files(overlay, service):
    environment = overlay["services"][service]["environment"]
    # The development URLs in compose.yaml carry an inline password. The Pilot
    # clears them so the persistence profile reads the secret files instead;
    # it refuses a value and a file for the same name.
    assert environment["DATABASE_URL"] == ""
    assert environment["MIGRATION_DATABASE_URL"] == ""
    assert environment["DATABASE_URL_FILE"].startswith("/run/secrets/")
    assert environment["MIGRATION_DATABASE_URL_FILE"].startswith("/run/secrets/")
    assert environment["PROJECT_2026_ENV_FILE"].startswith("/run/secrets/")


def test_the_development_stack_is_not_a_pilot_configuration_authority(base_compose):
    """compose.yaml must stay visibly a development stack.

    The Local Pilot evidence recorded before this overlay existed was collected
    on the development environment block. Nothing stops that from happening
    again except this file declaring itself development.
    """

    app_environment = base_compose["services"]["app"]["environment"]
    assert app_environment["APP_ENV"] == "development"
    assert app_environment["SECURITY_ENFORCED"] == "false"
    assert "secrets" not in base_compose["services"]["app"]
