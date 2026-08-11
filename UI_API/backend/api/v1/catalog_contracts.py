"""Published DTOs for the catalog capability's `/api/v1` transport.

The stored row carries twenty-three keys, most of them import-compatibility or
storage detail: `image_ref`, `image_source`, `image_storage`,
`official_image_url`, `official_name`, `source_category`, `source_url`,
`rag_metadata` and `extra`. None of those are what a Store Menu Item *is*, and
a published contract that exposes them makes every one of them a promise.

This DTO publishes the domain fields — the ones CONTEXT.md names, plus what an
operator needs to act on availability — and nothing else. Adding a field to a
versioned contract later is compatible; removing one is not, so the direction
that costs least when wrong is to start narrow.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: Catalog Availability: the operational sellability overlay on an item.
AvailabilityStatus = Literal["normal", "low_stock", "sold_out", "disabled"]


class CatalogItemDTO(BaseModel):
    id: str
    name: str
    category: str = ""
    price: int = 0
    description: str = ""
    #: Served image reference: an uploaded object or an external http(s) URL.
    image: str = ""
    prep_time_minutes: int = 0
    nutrition: str = ""
    price_note: str = ""
    availability_note: str = ""
    aliases: list[str] = Field(default_factory=list)
    retired: bool = False


class CatalogItemListDTO(BaseModel):
    items: list[CatalogItemDTO]
    #: Distinct category labels of the items in this response. Categories are
    #: not a managed entity — they are whatever the live items say they are.
    categories: list[str]


class CatalogItemWriteDTO(BaseModel):
    """Authoring fields. Everything else about an item is derived or stored."""

    name: str | None = None
    category: str | None = None
    price: int | None = None
    description: str | None = None
    image: str | None = None
    prep_time_minutes: int | None = None
    nutrition: str | None = None
    price_note: str | None = None
    availability_note: str | None = None
    aliases: list[str] | None = None


class CatalogAvailabilityRowDTO(BaseModel):
    id: str
    name: str = ""
    category: str = ""
    status: AvailabilityStatus = "normal"
    #: Set by the store's service-period rules rather than by an operator.
    time_unavailable: bool = False


class ServicePeriodWindowDTO(BaseModel):
    start: str = ""
    end: str = ""


class CatalogAvailabilityDTO(BaseModel):
    #: The period currently in force, resolved from the windows below.
    service_period: str = ""
    #: `auto` resolves by clock; naming a period pins it until changed.
    configured_service_period: str = "auto"
    service_periods: dict[str, ServicePeriodWindowDTO] = Field(default_factory=dict)
    items: list[CatalogAvailabilityRowDTO]


class CatalogAvailabilityCommandDTO(BaseModel):
    """The operator's intent. Unknown item ids are dropped, not rejected.

    Availability is an overlay on a catalog that changes underneath it; a stale
    id in a saved selection is expected rather than an error worth refusing the
    whole change over.
    """

    service_period: str | None = None
    service_periods: dict[str, ServicePeriodWindowDTO] | None = None
    sold_out_item_ids: list[str] = Field(default_factory=list)
    low_stock_item_ids: list[str] = Field(default_factory=list)
    disabled_item_ids: list[str] = Field(default_factory=list)


def catalog_item_dto(row: dict) -> CatalogItemDTO:
    """Project one stored catalog row onto the published contract."""

    return CatalogItemDTO(
        id=str(row.get("id") or ""),
        name=str(row.get("name") or ""),
        category=str(row.get("category") or ""),
        price=int(row.get("price") or 0),
        description=str(row.get("description") or ""),
        image=str(row.get("image") or ""),
        prep_time_minutes=int(row.get("prep_time_minutes") or 0),
        nutrition=str(row.get("nutrition") or ""),
        price_note=str(row.get("price_note") or ""),
        availability_note=str(row.get("availability_note") or ""),
        aliases=[str(alias) for alias in (row.get("aliases") or []) if str(alias)],
        retired=bool(row.get("retired") or False),
    )


def catalog_availability_dto(state: dict) -> CatalogAvailabilityDTO:
    rows = [
        CatalogAvailabilityRowDTO(
            id=str(row.get("id") or ""),
            name=str(row.get("name") or ""),
            category=str(row.get("category") or ""),
            status=str(row.get("status") or "normal"),
            time_unavailable=bool(row.get("time_unavailable") or False),
        )
        for row in (state.get("items") or [])
        if str(row.get("id") or "")
    ]
    periods = {
        name: ServicePeriodWindowDTO(
            start=str((window or {}).get("start") or ""),
            end=str((window or {}).get("end") or ""),
        )
        for name, window in (state.get("service_periods") or {}).items()
    }
    return CatalogAvailabilityDTO(
        service_period=str(state.get("service_period") or ""),
        configured_service_period=str(state.get("configured_service_period") or "auto"),
        service_periods=periods,
        items=rows,
    )
