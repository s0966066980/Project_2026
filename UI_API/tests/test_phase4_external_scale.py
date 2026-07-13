"""Milestones 4A–4E external integration and scale evaluation contracts."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

TENANT = UUID("00000000-0000-4000-8000-000000000001")
STORE = UUID("00000000-0000-4000-8000-000000000002")
DEVICE = UUID("00000000-0000-4000-8000-000000000003")


def test_payment_fake_adapter_webhook_and_reconciliation() -> None:
    import hashlib
    import hmac

    from models.payment import PaymentRequest, PaymentStatus
    from services import payment_gateway_service

    payment_gateway_service.reset_for_tests()
    order_id = uuid4()
    authorized = payment_gateway_service.authorize(
        PaymentRequest(
            order_id=order_id,
            amount=220,
            currency="TWD",
            provider_token="tok_sandbox_abc",
            idempotency_key="pay-1",
            tenant_id=TENANT,
            store_id=STORE,
        )
    )
    assert authorized.status is PaymentStatus.AUTHORIZED
    replay = payment_gateway_service.authorize(
        PaymentRequest(
            order_id=order_id,
            amount=220,
            currency="TWD",
            provider_token="tok_sandbox_abc",
            idempotency_key="pay-1",
            tenant_id=TENANT,
            store_id=STORE,
        )
    )
    assert replay.provider_reference == authorized.provider_reference
    with pytest.raises(payment_gateway_service.PaymentGatewayError):
        payment_gateway_service.authorize(
            PaymentRequest(
                order_id=order_id,
                amount=1,
                currency="TWD",
                provider_token="card_number=4111",
                idempotency_key="bad",
                tenant_id=TENANT,
                store_id=STORE,
            )
        )
    payload = b'{"ok":true}'
    secret = "whsec_test"
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    event = payment_gateway_service.verify_webhook(
        payload=payload,
        signature_header=signature,
        shared_secret=secret,
        event_id="wh_1",
        amount=220,
        currency="TWD",
        provider_reference=authorized.provider_reference,
        status=PaymentStatus.CAPTURED,
        expected_amount=220,
        expected_currency="TWD",
    )
    assert event.signature_valid is True
    # replay
    again = payment_gateway_service.verify_webhook(
        payload=payload,
        signature_header=signature,
        shared_secret=secret,
        event_id="wh_1",
        amount=220,
        currency="TWD",
        provider_reference=authorized.provider_reference,
        status=PaymentStatus.CAPTURED,
        expected_amount=220,
        expected_currency="TWD",
    )
    assert again.event_id == "wh_1"
    report = payment_gateway_service.reconcile(
        [{"provider_reference": authorized.provider_reference, "amount": 220, "currency": "TWD"}],
        [{"provider_reference": authorized.provider_reference, "amount": 221, "currency": "TWD"}],
    )
    assert authorized.provider_reference in report["amount_mismatch"]


def test_object_storage_isolation_size_and_signed_url() -> None:
    from services import object_storage_service

    object_storage_service.reset_for_tests()
    store = object_storage_service.storage()
    meta = store.put(
        tenant_id=TENANT,
        store_id=STORE,
        owner="admin",
        content_type="text/plain",
        data=b"hello",
        filename="../secret.txt",
    )
    assert ".." not in meta.object_id
    assert store.get(meta.object_id, tenant_id=TENANT) == b"hello"
    other = UUID("00000000-0000-4000-8000-000000000099")
    with pytest.raises(object_storage_service.ObjectStorageError):
        store.get(meta.object_id, tenant_id=other)
    url = store.signed_url(meta.object_id, tenant_id=TENANT, ttl_seconds=60)
    assert "expires=" in url
    assert store.delete(meta.object_id, tenant_id=TENANT) is True
    with pytest.raises(object_storage_service.ObjectStorageError):
        store.get(meta.object_id, tenant_id=TENANT)


def test_fleet_commands_are_allowlisted_scoped_and_expiring(tmp_path, monkeypatch) -> None:
    from services import fleet_management_service

    monkeypatch.setattr(fleet_management_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    fleet_management_service.heartbeat(
        device_id=DEVICE,
        tenant_id=TENANT,
        store_id=STORE,
        app_version="1.2.3",
        config_version="cfg-9",
    )
    with pytest.raises(fleet_management_service.FleetError):
        fleet_management_service.issue_command(
            device_id=DEVICE,
            tenant_id=TENANT,
            command="rm -rf /",
            actor="admin",
            expires_at="2099-01-01T00:00:00+00:00",
        )
    cmd = fleet_management_service.issue_command(
        device_id=DEVICE,
        tenant_id=TENANT,
        command="refresh_config",
        actor="admin",
        expires_at="2099-01-01T00:00:00+00:00",
        command_id="cmd-1",
    )
    again = fleet_management_service.issue_command(
        device_id=DEVICE,
        tenant_id=TENANT,
        command="refresh_config",
        actor="admin",
        expires_at="2099-01-01T00:00:00+00:00",
        command_id="cmd-1",
    )
    assert cmd["command_id"] == again["command_id"]
    with pytest.raises(fleet_management_service.FleetError):
        fleet_management_service.consume_command("cmd-1", now="2100-01-01T00:00:00+00:00")


def test_analytics_envelope_replay_and_quality(tmp_path, monkeypatch) -> None:
    from services import analytics_pipeline_service

    monkeypatch.setattr(analytics_pipeline_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    sink = analytics_pipeline_service.InMemoryAnalyticsSink()
    envelope = analytics_pipeline_service.build_envelope(
        event_type="checkout_completed",
        payload={"total": 220},
        tenant_id=TENANT,
        store_id=STORE,
        session_ref="s1",
        order_ref="o1",
        member_ref="m-opaque",
        event_id="ae-1",
    )
    assert analytics_pipeline_service.publish(envelope, sink=sink) is True
    assert analytics_pipeline_service.publish(envelope, sink=sink) is False
    with pytest.raises(analytics_pipeline_service.AnalyticsError):
        analytics_pipeline_service.build_envelope(
            event_type="bad",
            payload={"phone": "0912345678"},
            tenant_id=TENANT,
        )
    count = analytics_pipeline_service.replay(tenant_id=TENANT, sink=analytics_pipeline_service.InMemoryAnalyticsSink())
    assert count == 1
    quality = analytics_pipeline_service.data_quality([envelope, envelope])
    assert quality["duplicates"] == 1


def test_ha_evaluation_adr_defers_multi_region() -> None:
    from pathlib import Path

    text = Path(__file__).resolve().parents[2].joinpath("docs/adr/0010-high-availability-evidence-evaluation.md").read_text(
        encoding="utf-8"
    )
    assert "Defer multi-region" in text
    assert "Microservice split" in text
    assert "No premature architecture change" in text
