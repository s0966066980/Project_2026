from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.promotion import (
    CampaignConflictError,
    CampaignSnapshot,
    CampaignStateError,
    create_campaign_draft,
    preview_campaign,
    publish_campaign,
    revise_campaign_draft,
    transition_campaign,
)

TAIPEI = ZoneInfo("Asia/Taipei")


class MemoryCampaignRepository:
    def __init__(self):
        self.rows = {}
        self.audits = []
        self.projections = []

    def get(self, _scope, campaign_id):
        return self.rows.get(campaign_id)

    def list(self, _scope):
        return list(self.rows.values())

    def append_version(self, _scope, campaign_id, payload, status, *, expected_version, actor_id):
        current = self.rows.get(campaign_id)
        if (current.version if current else 0) != expected_version:
            raise CampaignConflictError("campaign_version_conflict")
        snapshot = CampaignSnapshot(campaign_id, expected_version + 1, status, dict(payload))
        self.rows[campaign_id] = snapshot
        return snapshot

    def project_legacy(self, _scope, snapshot):
        self.projections.append(snapshot)

    def audit(self, _scope, *, actor_id, action, snapshot):
        self.audits.append((actor_id, action, snapshot.version))


def campaign_payload(name="夏日薯條優惠"):
    return {
        "name": name,
        "objective": "increase_add_on",
        "audience": "all",
        "schedule": {"starts_at": "2026-07-15T08:00", "ends_at": "2026-07-31T22:00"},
        "promotion_rules": [{
            "type": "add_on_fixed_price",
            "item_ids": ["fries"],
            "required_cart_item_ids": ["meal"],
            "promotion_price": 30,
        }],
        "placements": ["menu_card", "item_detail", "kiosk_cart_banner"],
        "creatives": {"badge": "現省 20 元", "description": "搭配主餐更優惠"},
    }


def test_campaign_versions_are_append_only_and_audited():
    repository = MemoryCampaignRepository()
    draft = create_campaign_draft(campaign_payload(), LEGACY_DEFAULT_SCOPE, actor_id="staff-1", repository=repository)
    review = transition_campaign(draft.campaign_id, "review", LEGACY_DEFAULT_SCOPE, expected_version=1, actor_id="staff-1", repository=repository)
    active = transition_campaign(draft.campaign_id, "active", LEGACY_DEFAULT_SCOPE, expected_version=2, actor_id="manager-1", repository=repository)

    assert (draft.version, review.version, active.version) == (1, 2, 3)
    assert len(repository.audits) == 3
    assert repository.projections[-1].status == "active"


def test_campaign_optimistic_concurrency_fails_closed():
    repository = MemoryCampaignRepository()
    draft = create_campaign_draft(campaign_payload(), LEGACY_DEFAULT_SCOPE, actor_id="staff", repository=repository)

    with pytest.raises(CampaignConflictError):
        revise_campaign_draft(draft.campaign_id, campaign_payload("新名稱"), LEGACY_DEFAULT_SCOPE, expected_version=0, actor_id="staff", repository=repository)


def test_published_campaign_must_be_paused_before_revision():
    repository = MemoryCampaignRepository()
    draft = create_campaign_draft(campaign_payload(), LEGACY_DEFAULT_SCOPE, actor_id="staff", repository=repository)
    review = transition_campaign(draft.campaign_id, "review", LEGACY_DEFAULT_SCOPE, expected_version=1, actor_id="staff", repository=repository)
    active = transition_campaign(review.campaign_id, "active", LEGACY_DEFAULT_SCOPE, expected_version=2, actor_id="manager", repository=repository)

    with pytest.raises(CampaignStateError, match="campaign_must_be_paused_or_ended_before_edit"):
        revise_campaign_draft(
            active.campaign_id,
            campaign_payload("新版草稿"),
            LEGACY_DEFAULT_SCOPE,
            expected_version=3,
            actor_id="staff",
            repository=repository,
        )

    assert repository.rows[active.campaign_id].status == "active"
    assert repository.projections[-1].status == "active"


def test_archived_campaign_cannot_be_reopened_or_deleted_in_place():
    repository = MemoryCampaignRepository()
    draft = create_campaign_draft(campaign_payload(), LEGACY_DEFAULT_SCOPE, actor_id="staff", repository=repository)
    archived = transition_campaign(draft.campaign_id, "archived", LEGACY_DEFAULT_SCOPE, expected_version=1, actor_id="staff", repository=repository)

    with pytest.raises(CampaignStateError):
        transition_campaign(archived.campaign_id, "draft", LEGACY_DEFAULT_SCOPE, expected_version=2, actor_id="staff", repository=repository)


def test_publish_takes_a_new_campaign_on_air_in_one_call():
    repository = MemoryCampaignRepository()

    published = publish_campaign(
        campaign_payload(),
        LEGACY_DEFAULT_SCOPE,
        actor_id="manager",
        repository=repository,
        now=datetime(2026, 7, 20, 12, 0, tzinfo=TAIPEI),
    )

    assert (published.status, published.version) == ("active", 3)
    assert repository.projections[-1].status == "active"
    assert [action for _, action, _ in repository.audits][0] == "campaign_publish_requested"


def test_publish_schedules_a_campaign_that_has_not_started():
    repository = MemoryCampaignRepository()

    published = publish_campaign(
        campaign_payload(),
        LEGACY_DEFAULT_SCOPE,
        actor_id="manager",
        repository=repository,
        now=datetime(2026, 7, 1, 12, 0, tzinfo=TAIPEI),
    )

    assert published.status == "scheduled"


def test_publish_refuses_a_campaign_that_is_already_on_air():
    repository = MemoryCampaignRepository()
    published = publish_campaign(
        campaign_payload(), LEGACY_DEFAULT_SCOPE, actor_id="manager", repository=repository,
        now=datetime(2026, 7, 20, 12, 0, tzinfo=TAIPEI),
    )

    with pytest.raises(CampaignStateError, match="campaign_is_already_published"):
        publish_campaign(
            campaign_payload(),
            LEGACY_DEFAULT_SCOPE,
            campaign_id=published.campaign_id,
            expected_version=published.version,
            actor_id="manager",
            repository=repository,
        )

    assert repository.rows[published.campaign_id].status == "active"


def test_publish_fails_closed_when_the_form_was_based_on_an_older_version():
    repository = MemoryCampaignRepository()
    draft = create_campaign_draft(campaign_payload(), LEGACY_DEFAULT_SCOPE, actor_id="staff", repository=repository)
    revise_campaign_draft(
        draft.campaign_id, campaign_payload("別人改的名稱"), LEGACY_DEFAULT_SCOPE,
        expected_version=1, actor_id="other", repository=repository,
    )

    with pytest.raises(CampaignConflictError):
        publish_campaign(
            campaign_payload(),
            LEGACY_DEFAULT_SCOPE,
            campaign_id=draft.campaign_id,
            expected_version=1,
            actor_id="staff",
            repository=repository,
        )

    assert repository.rows[draft.campaign_id].status == "draft"


def test_revising_a_paused_campaign_keeps_it_paused():
    repository = MemoryCampaignRepository()
    published = publish_campaign(
        campaign_payload(), LEGACY_DEFAULT_SCOPE, actor_id="manager", repository=repository,
        now=datetime(2026, 7, 20, 12, 0, tzinfo=TAIPEI),
    )
    paused = transition_campaign(
        published.campaign_id, "paused", LEGACY_DEFAULT_SCOPE,
        expected_version=published.version, actor_id="manager", repository=repository,
    )

    revised = revise_campaign_draft(
        paused.campaign_id, campaign_payload("改過的名稱"), LEGACY_DEFAULT_SCOPE,
        expected_version=paused.version, actor_id="staff", repository=repository,
    )

    assert revised.status == "paused"
    assert revised.payload["name"] == "改過的名稱"


def test_campaign_without_a_start_time_is_rejected():
    repository = MemoryCampaignRepository()
    payload = campaign_payload()
    payload["schedule"] = {"starts_at": "", "ends_at": "2026-07-31T22:00"}

    preview = preview_campaign(payload, LEGACY_DEFAULT_SCOPE, repository=repository)

    assert preview.valid is False
    assert {"schedule.starts_at"} == {error["path"] for error in preview.field_errors}


def test_campaign_preview_reports_overlap_in_chinese():
    repository = MemoryCampaignRepository()
    existing = create_campaign_draft(campaign_payload("既有活動"), LEGACY_DEFAULT_SCOPE, actor_id="staff", repository=repository)
    repository.rows[existing.campaign_id] = replace(existing, status="active")

    preview = preview_campaign(campaign_payload("新活動"), LEGACY_DEFAULT_SCOPE, repository=repository)

    assert preview.valid is True
    assert preview.impact_count == 3
    assert preview.conflicts[0]["code"] == "overlapping_item_price"
    assert "既有活動" in preview.conflicts[0]["message"]
