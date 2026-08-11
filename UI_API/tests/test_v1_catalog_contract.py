"""The `/api/v1/catalog` contract.

The stored row carries import-compatibility and storage keys that are not part
of what a Store Menu Item is. A published contract that leaked them would make
every one of them a promise the capability has to keep.
"""

from fastapi.testclient import TestClient

from main import app

INTERNAL_KEYS = {
    "image_ref",
    "image_source",
    "image_storage",
    "official_image_url",
    "official_name",
    "source_category",
    "source_url",
    "rag_metadata",
    "extra",
    "available_categories",
    "retired_at",
}


def test_sellable_catalog_is_readable_by_a_kiosk_device():
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/items")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["request_id"].startswith("req_")
    assert isinstance(body["data"]["items"], list)
    assert isinstance(body["data"]["categories"], list)


def test_published_item_contract_excludes_storage_and_import_detail():
    with TestClient(app) as client:
        items = client.get("/api/v1/catalog/items").json()["data"]["items"]

    assert items, "expected a seeded catalog"
    for item in items:
        assert INTERNAL_KEYS.isdisjoint(item), f"published contract leaked internals: {sorted(INTERNAL_KEYS & set(item))}"
        assert set(item) == {
            "id",
            "name",
            "category",
            "price",
            "description",
            "image",
            "prep_time_minutes",
            "nutrition",
            "price_note",
            "availability_note",
            "aliases",
            "retired",
        }


def test_categories_are_the_distinct_labels_of_the_returned_items():
    with TestClient(app) as client:
        data = client.get("/api/v1/catalog/items").json()["data"]

    assert data["categories"] == sorted({item["category"] for item in data["items"] if item["category"]})


def test_a_missing_item_is_a_named_not_found():
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/items/no-such-item")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "item_not_found"


def test_one_item_can_be_read_by_id():
    with TestClient(app) as client:
        items = client.get("/api/v1/catalog/items").json()["data"]["items"]
        first = items[0]
        response = client.get(f"/api/v1/catalog/items/{first['id']}")

    assert response.status_code == 200
    assert response.json()["data"] == first
