"""Promotion rules exposed through one small application interface."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from modules.promotion.contracts import (
    CampaignPreview,
    CampaignSnapshot,
    CampaignStateError,
    EligibilityResult,
    PriceProjection,
    PromotionContext,
    PromotionQuote,
)

ACTIVE_STATUSES = {"", "active", "published", "enabled"}
DEFAULT_TIMEZONE = "Asia/Taipei"


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y", "enabled", "active"}


def _as_values(value: Any) -> frozenset[str]:
    if value in (None, ""):
        return frozenset()
    values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
    return frozenset(str(item or "").strip() for item in values if str(item or "").strip())


def _timezone(promotion: dict) -> ZoneInfo:
    name = str(promotion.get("timezone") or DEFAULT_TIMEZONE).strip()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _datetime(value: Any, *, timezone: ZoneInfo, end_of_day: bool = False) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 10:
        try:
            parsed_date = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None
        return datetime.combine(parsed_date, time.max if end_of_day else time.min, tzinfo=timezone)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone)


def _scope_matches(promotion: dict, context: PromotionContext) -> bool:
    expected_tenant = str(promotion.get("tenant_id") or "").strip()
    expected_store = str(promotion.get("store_id") or "").strip()
    if not expected_tenant and not expected_store:
        return True
    if context.scope is None:
        return False
    return (not expected_tenant or expected_tenant == str(context.scope.tenant_id)) and (
        not expected_store or expected_store == str(context.scope.store_id)
    )


def evaluate_promotion(promotion: dict, context: PromotionContext) -> EligibilityResult:
    metadata = promotion.get("metadata") if isinstance(promotion.get("metadata"), dict) else {}
    status = str(promotion.get("status") or metadata.get("status") or "").strip().lower()
    if status not in ACTIVE_STATUSES:
        return EligibilityResult(False, "promotion_not_active")
    if "enabled" in promotion and not _as_bool(promotion.get("enabled")):
        return EligibilityResult(False, "promotion_disabled")
    if not _scope_matches(promotion, context):
        return EligibilityResult(False, "scope_mismatch")

    timezone = _timezone(promotion)
    now = context.now if context.now.tzinfo is not None else context.now.replace(tzinfo=timezone)
    starts_at = _datetime(
        promotion.get("start_at") or promotion.get("starts_at") or promotion.get("valid_from"),
        timezone=timezone,
    )
    ends_at = _datetime(
        promotion.get("end_at") or promotion.get("ends_at") or promotion.get("valid_until"),
        timezone=timezone,
        end_of_day=True,
    )
    if starts_at and now < starts_at:
        return EligibilityResult(False, "promotion_not_started")
    if ends_at and now > ends_at:
        return EligibilityResult(False, "promotion_expired")
    if promotion.get("member_only") and context.is_member is False:
        return EligibilityResult(False, "member_required")

    placements = _as_values(promotion.get("placements") or promotion.get("surface"))
    if placements and context.placement and context.placement not in placements:
        return EligibilityResult(False, "placement_mismatch")

    required = _as_values(promotion.get("required_cart_item_ids") or promotion.get("required_items"))
    if required and context.cart_item_ids is not None and not required.issubset(context.cart_item_ids):
        return EligibilityResult(False, "requirements_not_met")

    item_ids = _as_values(promotion.get("item_ids") or promotion.get("items"))
    categories = _as_values(promotion.get("categories") or promotion.get("category"))
    target_type = str(promotion.get("target_type") or "").strip()
    target_value = str(promotion.get("target_value") or "").strip()
    matches_item = bool(context.item_id and context.item_id in item_ids)
    matches_category = bool(context.category and context.category in categories)
    matches_legacy_target = (target_type == "item" and target_value == context.item_id) or (
        target_type == "category" and target_value == context.category
    )
    if (context.item_id or context.category) and (item_ids or categories or target_value):
        if not (matches_item or matches_category or matches_legacy_target):
            return EligibilityResult(False, "target_mismatch")
    return EligibilityResult(True, "eligible")


def quote_promotion(
    promotion: dict,
    context: PromotionContext,
    *,
    base_price: int,
) -> PromotionQuote:
    result = evaluate_promotion(promotion, context)
    reference = str(promotion.get("offer_id") or promotion.get("id") or "").strip()
    title = str(promotion.get("title") or reference).strip()
    if not result.eligible:
        return PromotionQuote(False, result.code, base_price, base_price, 0, reference, title)
    pricing = promotion.get("pricing") if isinstance(promotion.get("pricing"), dict) else {}
    raw_price = promotion.get("promo_price") or promotion.get("promotion_price") or pricing.get("promotion_price")
    try:
        effective_price = int(float(raw_price))
    except (TypeError, ValueError):
        return PromotionQuote(False, "promotion_price_invalid", base_price, base_price, 0, reference, title)
    if effective_price <= 0 or effective_price > base_price:
        return PromotionQuote(False, "promotion_price_invalid", base_price, base_price, 0, reference, title)
    return PromotionQuote(
        True,
        "eligible",
        base_price,
        effective_price,
        base_price - effective_price,
        reference,
        title,
    )


def select_promotion_quote(
    promotions: list[dict],
    context: PromotionContext,
    *,
    base_price: int,
    preferred_ref: str = "",
) -> PromotionQuote:
    candidates: list[tuple[int, int, int, str, PromotionQuote]] = []
    for promotion in promotions:
        quote = quote_promotion(promotion, context, base_price=base_price)
        if not quote.eligible:
            continue
        try:
            priority = int(promotion.get("priority") or 0)
        except (TypeError, ValueError):
            priority = 0
        candidates.append(
            (
                quote.effective_price,
                -priority,
                0 if preferred_ref and quote.promotion_ref == preferred_ref else 1,
                quote.promotion_ref,
                quote,
            )
        )
    if not candidates:
        return PromotionQuote(False, "no_applicable_promotion", base_price, base_price, 0)
    return min(candidates, key=lambda candidate: candidate[:4])[4]


def project_item_price(
    promotions: list[dict],
    context: PromotionContext,
    *,
    base_price: int,
) -> PriceProjection:
    selected = select_promotion_quote(promotions, context, base_price=base_price)
    if selected.eligible:
        return PriceProjection(
            base_price=base_price,
            effective_price=selected.effective_price,
            discount=selected.discount,
            promotion_ref=selected.promotion_ref,
            promotion_title=selected.promotion_title,
        )

    without_cart = replace(context, cart_item_ids=None)
    conditional_candidates: list[tuple[int, str, PromotionQuote, tuple[str, ...]]] = []
    for promotion in promotions:
        required = tuple(sorted(_as_values(promotion.get("required_cart_item_ids") or promotion.get("required_items"))))
        if not required:
            continue
        quote = quote_promotion(promotion, without_cart, base_price=base_price)
        if quote.eligible:
            conditional_candidates.append((quote.effective_price, quote.promotion_ref, quote, required))
    if not conditional_candidates:
        return PriceProjection(base_price, base_price, 0)
    _, _, quote, required = min(conditional_candidates, key=lambda candidate: candidate[:2])
    return PriceProjection(
        base_price=base_price,
        effective_price=base_price,
        discount=0,
        promotion_ref=quote.promotion_ref,
        promotion_title=quote.promotion_title,
        conditional=True,
        conditional_price=quote.effective_price,
        required_cart_item_ids=required,
    )


CAMPAIGN_STATUSES = {"draft", "review", "scheduled", "active", "paused", "ended", "archived"}
CAMPAIGN_TRANSITIONS = {
    "draft": {"review", "archived"},
    "review": {"draft", "scheduled", "active", "archived"},
    "scheduled": {"active", "paused", "ended"},
    "active": {"paused", "ended"},
    "paused": {"active", "ended", "archived", "draft"},
    "ended": {"archived", "draft"},
    "archived": set(),
}
CAMPAIGN_EDITABLE_STATUSES = {"draft", "review", "paused", "ended"}
CAMPAIGN_PUBLISHABLE_STATUSES = {"draft", "review"}
ALLOWED_PLACEMENTS = {
    "menu_card",
    "item_detail",
    "pos_home_banner",
    "kiosk_cart_banner",
    "recommendation",
    "voice",
}


def _campaign_repository(repository=None):
    if repository is not None:
        return repository
    from repositories.campaign_repository import default_campaign_repository

    return default_campaign_repository


def preview_campaign(
    payload: dict,
    scope,
    *,
    repository=None,
    exclude_campaign_id: str = "",
    catalog_items: list[dict] | None = None,
) -> CampaignPreview:
    raw = dict(payload or {})
    errors: list[dict[str, str]] = []
    name = str(raw.get("name") or "").strip()
    if not name:
        errors.append({"path": "name", "code": "required", "message": "請輸入活動名稱。"})
    objective = str(raw.get("objective") or "promote_item").strip()
    if objective not in {"promote_item", "increase_add_on", "increase_order_value", "member_return", "clear_inventory"}:
        errors.append({"path": "objective", "code": "unsupported", "message": "請重新選擇活動目標。"})
    audience = str(raw.get("audience") or "all").strip()
    if audience not in {"all", "member"}:
        errors.append({"path": "audience", "code": "unsupported", "message": "請重新選擇適用顧客。"})
    schedule = dict(raw.get("schedule") or {})
    starts_at = str(schedule.get("starts_at") or "").strip()
    ends_at = str(schedule.get("ends_at") or "").strip()
    if not starts_at:
        errors.append({"path": "schedule.starts_at", "code": "required", "message": "請輸入活動開始時間。"})
    if starts_at and ends_at and starts_at > ends_at:
        errors.append({"path": "schedule.ends_at", "code": "before_start", "message": "結束時間必須晚於開始時間。"})
    placements = tuple(
        dict.fromkeys(str(value or "").strip() for value in raw.get("placements") or [] if str(value or "").strip())
    )
    unknown = [value for value in placements if value not in ALLOWED_PLACEMENTS]
    if unknown:
        errors.append({"path": "placements", "code": "unsupported", "message": "包含目前不支援的顯示位置。"})
    if not placements:
        errors.append({"path": "placements", "code": "required", "message": "請至少選擇一個顯示位置。"})
    rules = raw.get("promotion_rules") or []
    if not isinstance(rules, list) or len(rules) != 1:
        errors.append(
            {"path": "promotion_rules", "code": "single_rule_required", "message": "第一階段每個活動請設定一種優惠。"}
        )
        rules = []
    catalog = {str(item.get("id") or ""): item for item in (catalog_items or [])}
    price_previews = []
    for index, rule in enumerate(rules):
        rule = dict(rule or {})
        if rule.get("type") not in {"fixed_item_price", "add_on_fixed_price"}:
            errors.append(
                {
                    "path": f"promotion_rules.{index}.type",
                    "code": "unsupported",
                    "message": "請選擇指定餐點特價或搭配加購價。",
                }
            )
        if not rule.get("item_ids"):
            errors.append(
                {"path": f"promotion_rules.{index}.item_ids", "code": "required", "message": "請選擇優惠餐點。"}
            )
        try:
            price = int(rule.get("promotion_price"))
        except (TypeError, ValueError):
            price = 0
        if price <= 0:
            errors.append(
                {
                    "path": f"promotion_rules.{index}.promotion_price",
                    "code": "invalid_price",
                    "message": "優惠價必須大於 0 元。",
                }
            )
        if rule.get("type") == "add_on_fixed_price" and not rule.get("required_cart_item_ids"):
            errors.append(
                {
                    "path": f"promotion_rules.{index}.required_cart_item_ids",
                    "code": "required",
                    "message": "請選擇顧客需要先購買的餐點。",
                }
            )
        for item_id in rule.get("item_ids") or []:
            item = catalog.get(str(item_id))
            if catalog_items is not None and item is None:
                errors.append(
                    {
                        "path": f"promotion_rules.{index}.item_ids",
                        "code": "item_not_found",
                        "message": "選取的優惠餐點已不存在，請重新選擇。",
                    }
                )
                continue
            if item is None:
                continue
            try:
                base_price = int(float(item.get("price") or 0))
            except (TypeError, ValueError):
                base_price = 0
            if price > base_price > 0:
                errors.append(
                    {
                        "path": f"promotion_rules.{index}.promotion_price",
                        "code": "price_above_base",
                        "message": "優惠價不可高於餐點原價。",
                    }
                )
            price_previews.append(
                {
                    "item_id": str(item_id),
                    "item_name": str(item.get("name") or item_id),
                    "base_price": base_price,
                    "effective_price": price,
                    "savings": max(0, base_price - price),
                    "conditional": rule.get("type") == "add_on_fixed_price",
                }
            )

    conflicts = []
    repo = _campaign_repository(repository)
    item_ids = set(str(value) for rule in rules for value in (rule.get("item_ids") or []))
    for existing in repo.list(scope):
        if existing.campaign_id == exclude_campaign_id or existing.status not in {"review", "scheduled", "active"}:
            continue
        existing_schedule = dict(existing.payload.get("schedule") or {})
        existing_start = str(existing_schedule.get("starts_at") or "")
        existing_end = str(existing_schedule.get("ends_at") or "")
        overlaps_time = (not ends_at or not existing_start or ends_at >= existing_start) and (
            not existing_end or not starts_at or existing_end >= starts_at
        )
        existing_items = {
            str(value)
            for rule in existing.payload.get("promotion_rules") or []
            for value in (rule.get("item_ids") or [])
        }
        if overlaps_time and item_ids & existing_items:
            conflicts.append(
                {
                    "campaign_id": existing.campaign_id,
                    "code": "overlapping_item_price",
                    "message": f"與「{existing.payload.get('name') or '另一個活動'}」的餐點與期間重疊，發布時會由系統選擇顧客最優惠價格。",
                }
            )
    summary = f"適用於{'會員' if audience == 'member' else '所有顧客'}，會影響 {len(placements)} 個顧客畫面。"
    return CampaignPreview(not errors, tuple(errors), tuple(conflicts), len(placements), summary, tuple(price_previews))


def create_campaign_draft(
    payload: dict, scope, *, actor_id: str, repository=None, catalog_items: list[dict] | None = None
) -> CampaignSnapshot:
    repo = _campaign_repository(repository)
    campaign_id = f"cmp_{uuid4().hex}"
    preview = preview_campaign(payload, scope, repository=repo, catalog_items=catalog_items)
    if not preview.valid:
        raise ValueError(preview.field_errors)
    canonical = dict(payload)
    canonical.update({"campaign_id": campaign_id, "status": "draft", "version": 1, "updated_by": actor_id})
    snapshot = repo.append_version(scope, campaign_id, canonical, "draft", expected_version=0, actor_id=actor_id)
    repo.audit(scope, actor_id=actor_id, action="campaign_draft_created", snapshot=snapshot)
    return snapshot


def list_campaigns(scope, *, repository=None) -> list[CampaignSnapshot]:
    return _campaign_repository(repository).list(scope)


def get_campaign(campaign_id: str, scope, *, repository=None) -> CampaignSnapshot | None:
    return _campaign_repository(repository).get(scope, str(campaign_id or "").strip())


def revise_campaign_draft(
    campaign_id: str,
    payload: dict,
    scope,
    *,
    expected_version: int,
    actor_id: str,
    repository=None,
    catalog_items: list[dict] | None = None,
) -> CampaignSnapshot:
    repo = _campaign_repository(repository)
    current = repo.get(scope, campaign_id)
    if current is None:
        raise LookupError("campaign_not_found")
    if current.status == "archived":
        raise CampaignStateError("archived_campaign_is_immutable")
    if current.status not in CAMPAIGN_EDITABLE_STATUSES:
        raise CampaignStateError("campaign_must_be_paused_or_ended_before_edit")
    preview = preview_campaign(
        payload, scope, repository=repo, exclude_campaign_id=campaign_id, catalog_items=catalog_items
    )
    if not preview.valid:
        raise ValueError(preview.field_errors)
    # Revising content never moves the campaign through its lifecycle; a paused campaign stays
    # paused so that saving edits can never take a campaign off air or put one on air.
    canonical = dict(payload)
    canonical.update(
        {"campaign_id": campaign_id, "status": current.status, "version": expected_version + 1, "updated_by": actor_id}
    )
    snapshot = repo.append_version(
        scope, campaign_id, canonical, current.status, expected_version=expected_version, actor_id=actor_id
    )
    repo.audit(scope, actor_id=actor_id, action="campaign_draft_revised", snapshot=snapshot)
    return snapshot


def publish_campaign(
    payload: dict,
    scope,
    *,
    campaign_id: str = "",
    expected_version: int = 0,
    actor_id: str,
    repository=None,
    catalog_items: list[dict] | None = None,
    now: datetime | None = None,
) -> CampaignSnapshot:
    """Validate, store and put a campaign on air in one call.

    The whole chain runs here so a caller never has to hold or replay intermediate versions.
    Optimistic concurrency stays strict: `expected_version` is the version the operator's form
    was based on, and a mismatch fails closed rather than overwriting somebody else's edit.
    """
    repo = _campaign_repository(repository)
    campaign_id = str(campaign_id or "").strip()
    if campaign_id:
        current = repo.get(scope, campaign_id)
        if current is None:
            raise LookupError("campaign_not_found")
        if current.status not in CAMPAIGN_PUBLISHABLE_STATUSES:
            raise CampaignStateError("campaign_is_already_published")
        content_status = current.status
    else:
        campaign_id = f"cmp_{uuid4().hex}"
        expected_version = 0
        content_status = "draft"

    preview = preview_campaign(
        payload, scope, repository=repo, exclude_campaign_id=campaign_id, catalog_items=catalog_items
    )
    if not preview.valid:
        raise ValueError(preview.field_errors)

    canonical = dict(payload)
    canonical.update(
        {
            "campaign_id": campaign_id,
            "status": content_status,
            "version": expected_version + 1,
            "updated_by": actor_id,
        }
    )
    snapshot = repo.append_version(
        scope, campaign_id, canonical, content_status, expected_version=expected_version, actor_id=actor_id
    )
    repo.audit(scope, actor_id=actor_id, action="campaign_publish_requested", snapshot=snapshot)

    if snapshot.status == "draft":
        snapshot = transition_campaign(
            campaign_id, "review", scope, expected_version=snapshot.version, actor_id=actor_id, repository=repo
        )
    target = _publication_target(dict(payload.get("schedule") or {}), now=now)
    return transition_campaign(
        campaign_id, target, scope, expected_version=snapshot.version, actor_id=actor_id, repository=repo
    )


def _publication_target(schedule: dict, *, now: datetime | None = None) -> str:
    """A campaign starting later is scheduled; one already due goes on air immediately."""
    timezone = ZoneInfo(DEFAULT_TIMEZONE)
    starts_at = _datetime(schedule.get("starts_at"), timezone=timezone)
    reference = now or datetime.now(timezone)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone)
    return "scheduled" if starts_at and starts_at > reference else "active"


def transition_campaign(
    campaign_id: str,
    target_status: str,
    scope,
    *,
    expected_version: int,
    actor_id: str,
    repository=None,
) -> CampaignSnapshot:
    repo = _campaign_repository(repository)
    current = repo.get(scope, campaign_id)
    if current is None:
        raise LookupError("campaign_not_found")
    target = str(target_status or "").strip().lower()
    if target not in CAMPAIGN_TRANSITIONS.get(current.status, set()):
        raise CampaignStateError(f"campaign_transition_not_allowed:{current.status}:{target}")
    payload = dict(current.payload)
    payload.update({"status": target, "version": expected_version + 1, "updated_by": actor_id})
    snapshot = repo.append_version(
        scope, campaign_id, payload, target, expected_version=expected_version, actor_id=actor_id
    )
    if target in {"scheduled", "active", "paused", "ended", "archived"}:
        repo.project_legacy(scope, snapshot)
    repo.audit(scope, actor_id=actor_id, action=f"campaign_{target}", snapshot=snapshot)
    return snapshot
