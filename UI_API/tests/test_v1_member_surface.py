"""The Admin member service owns one versioned browser surface."""

from fastapi.testclient import TestClient

from main import app


def test_member_list_and_missing_detail_use_the_versioned_envelope():
    with TestClient(app) as client:
        listing = client.get("/api/v1/members")
        missing = client.get("/api/v1/members/not-a-real-member")

    assert listing.status_code == 200
    body = listing.json()
    assert isinstance(body["data"], list)
    assert body["pagination"]["page"] == 1
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "member_not_found"


def test_member_export_is_a_masked_csv_from_the_versioned_surface():
    with TestClient(app) as client:
        response = client.get("/api/v1/members/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "members_export.csv" in response.headers["content-disposition"]
