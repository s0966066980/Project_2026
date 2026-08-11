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

from pydantic import BaseModel, Field


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
