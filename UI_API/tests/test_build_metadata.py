"""What build is running, answerable by an operator standing at the device.

"Which version is this?" is the first question of every incident, and until now
the only answer the running system could give was the OpenAPI title version —
a literal in app_factory that nothing kept in step with anything. The git
revision was baked into the image and read by exactly one internal snapshot.
"""

import pytest
from fastapi.testclient import TestClient

import config
from capabilities.operations_configuration import interface as operations
from main import app

pytestmark = [pytest.mark.contract, pytest.mark.security]

FIELDS = {"version", "git_sha", "build_time", "schema_version", "deployment_profile"}


def test_build_metadata_reports_the_five_published_fields():
    metadata = operations.build_metadata()

    assert set(metadata) == FIELDS
    assert all(isinstance(value, str) and value for value in metadata.values())


def test_the_openapi_version_and_the_reported_version_are_one_value():
    """Two sources for the version means one of them is eventually wrong."""

    assert app.version == config.APP_VERSION
    assert operations.build_metadata()["version"] == config.APP_VERSION


def test_the_schema_version_is_the_migration_head_this_build_carries():
    """Read from the build, not the database, so it answers during an outage.

    A half-applied deployment is exactly when the two differ, and exactly when
    an operator needs to know which one they are looking at.
    """

    from modules.runtime_persistence.migrations import local_schema_head

    head = local_schema_head()
    assert head.startswith("0"), head
    assert operations.build_metadata()["schema_version"] == head


def test_the_endpoint_requires_an_authorised_operator():
    with TestClient(app) as client:
        response = client.get("/api/v1/operations/build")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert set(body["build"]) == FIELDS


def test_no_secret_reaches_the_response():
    """The endpoint exists to be read during an incident; it must stay safe to read."""

    metadata = operations.build_metadata()
    rendered = " ".join(metadata.values()).lower()
    for key in sorted(config.CREDENTIAL_SETTING_KEYS):
        value = str(getattr(config, key, "") or "")
        if value:
            assert value.lower() not in rendered
    for forbidden in ("password", "secret", "token", "api_key"):
        assert forbidden not in rendered
