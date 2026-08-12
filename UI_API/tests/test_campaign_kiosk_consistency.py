from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from services import promotion_banner_service


def _banner(campaign_id: str, *, title: str) -> dict:
    return {
        "id": campaign_id,
        "offer_id": campaign_id,
        "status": "active",
        "enabled": True,
        "surface": "pos_home_banner",
        "title": title,
        "start_at": "2026-01-01T00:00:00+08:00",
        "end_at": "2026-12-31T23:59:59+08:00",
    }


def test_kiosk_ignores_active_legacy_promotions_without_an_active_campaign(monkeypatch):
    monkeypatch.setattr(
        promotion_banner_service.promotion_repository,
        "list_promotions_scoped",
        lambda _scope: [_banner("savor-test-sharebox", title="孤兒測試活動"), _banner("cmp-live", title="正式活動")],
    )
    monkeypatch.setattr(
        promotion_banner_service.campaign_repository.default_campaign_repository,
        "list",
        lambda _scope: [SimpleNamespace(campaign_id="cmp-live", status="active")],
    )

    result = promotion_banner_service.get_active_pos_banners(
        now=datetime(2026, 8, 4, 12, 0, tzinfo=ZoneInfo("Asia/Taipei")),
        scope=LEGACY_DEFAULT_SCOPE,
    )

    assert [item["id"] for item in result] == ["cmp-live"]
