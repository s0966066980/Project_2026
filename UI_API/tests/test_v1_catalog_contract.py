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
        assert INTERNAL_KEYS.isdisjoint(item), (
            f"published contract leaked internals: {sorted(INTERNAL_KEYS & set(item))}"
        )
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


def _created(client, **overrides):
    payload = {"name": "契約測試品項", "category": "測試", "price": 100, **overrides}
    return client.post("/api/v1/catalog/items", json=payload)


def test_an_item_can_be_authored_and_read_back():
    with TestClient(app) as client:
        created = _created(client)
        assert created.status_code == 201, created.text
        item = created.json()["data"]
        assert item["name"] == "契約測試品項"
        assert item["price"] == 100

        fetched = client.get(f"/api/v1/catalog/items/{item['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == item["id"]


def test_a_partial_change_leaves_the_untouched_fields_alone():
    with TestClient(app) as client:
        item = _created(client, name="改價前").json()["data"]

        updated = client.patch(f"/api/v1/catalog/items/{item['id']}", json={"price": 250})

    assert updated.status_code == 200
    body = updated.json()["data"]
    assert body["price"] == 250
    assert body["name"] == "改價前"


def test_retirement_hides_an_item_from_the_sellable_catalog_and_can_be_undone():
    with TestClient(app) as client:
        item = _created(client, name="退役測試").json()["data"]

        retired = client.post(f"/api/v1/catalog/items/{item['id']}/retirement")
        assert retired.status_code == 200
        assert retired.json()["data"]["retired"] is True

        sellable = client.get("/api/v1/catalog/items").json()["data"]["items"]
        assert item["id"] not in {row["id"] for row in sellable}

        # Retired is not deleted: it stays addressable for recovery.
        with_retired = client.get("/api/v1/catalog/items?include_retired=true").json()["data"]["items"]
        assert item["id"] in {row["id"] for row in with_retired}

        restored = client.delete(f"/api/v1/catalog/items/{item['id']}/retirement")

    assert restored.status_code == 200
    assert restored.json()["data"]["retired"] is False


def test_authoring_refusals_name_the_field_rather_than_failing_generically():
    with TestClient(app) as client:
        missing_name = client.post("/api/v1/catalog/items", json={"category": "測試", "price": 10})
        bad_price = _created(client, price=-5)

    assert missing_name.status_code == 422
    assert missing_name.json()["error"]["code"] in {"name_required", "validation_error"}
    assert bad_price.status_code == 422


def test_changing_an_item_that_is_not_there_is_a_not_found():
    with TestClient(app) as client:
        response = client.patch("/api/v1/catalog/items/no-such-item", json={"price": 1})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "item_not_found"


def test_an_unreadable_upload_is_refused_by_type_rather_than_stored():
    with TestClient(app) as client:
        item = _created(client, name="圖片測試").json()["data"]
        response = client.put(
            f"/api/v1/catalog/items/{item['id']}/image",
            files={"file": ("note.txt", b"not an image", "text/plain")},
        )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "image_type_not_allowed"


def test_availability_publishes_the_four_statuses_and_the_service_period():
    with TestClient(app) as client:
        state = client.get("/api/v1/catalog/availability")

    assert state.status_code == 200
    data = state.json()["data"]
    assert isinstance(data["service_period"], str)
    assert {row["status"] for row in data["items"]} <= {"normal", "low_stock", "sold_out", "disabled"}


def test_an_operator_can_mark_an_item_sold_out():
    with TestClient(app) as client:
        item = _created(client, name="售完測試").json()["data"]

        saved = client.put(
            "/api/v1/catalog/availability",
            json={"sold_out_item_ids": [item["id"]], "low_stock_item_ids": [], "disabled_item_ids": []},
        )

    assert saved.status_code == 200
    rows = {row["id"]: row for row in saved.json()["data"]["items"]}
    assert rows[item["id"]]["status"] == "sold_out"


def test_a_stale_item_id_is_dropped_rather_than_refusing_the_whole_change():
    with TestClient(app) as client:
        saved = client.put(
            "/api/v1/catalog/availability",
            json={"sold_out_item_ids": ["gone-yesterday"], "low_stock_item_ids": [], "disabled_item_ids": []},
        )

    assert saved.status_code == 200
    assert all(row["status"] != "sold_out" for row in saved.json()["data"]["items"])


def test_legacy_catalog_routes_are_absent_after_consumer_migration():
    with TestClient(app) as client:
        responses = (
            client.get("/api/menu"),
            client.get("/api/menu/items"),
            client.post("/api/availability", json={}),
        )

    assert {response.status_code for response in responses} == {404}


def test_supported_catalog_flow_leaves_the_legacy_counter_at_zero():
    from services import observability_service

    def counted() -> float:
        snapshot = observability_service.metrics_snapshot()
        return sum(snapshot.get("legacy_catalog_requests_total", {}).values())

    observability_service.reset_metrics_for_tests()
    with TestClient(app) as client:
        before = counted()
        items = client.get("/api/v1/catalog/items")
        availability = client.get("/api/v1/catalog/availability")
        after = counted()

    assert items.status_code == 200
    assert availability.status_code == 200
    assert before == after == 0


def test_promotion_banner_transport_survives_catalog_legacy_removal():
    assert "/api/promotions/pos-banner" in {route.path for route in app.routes}
