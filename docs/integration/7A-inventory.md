# Milestone 7A Inventory — API v1 Write Contracts

## New write surfaces

| Method | Path | Permission |
| --- | --- | --- |
| PATCH | `/api/v1/settings` | settings.write |
| PUT | `/api/v1/availability/{item_id}` | catalog.availability.write |
| POST | `/api/v1/promotions` | rag.write |
| POST | `/api/v1/rag/documents` | rag.write |
| POST | `/api/v1/rag/documents/{id}/review` | rag.review |
| POST | `/api/v1/rag/documents/{id}/publish` | rag.publish |
| POST | `/api/v1/rag/documents/{id}/rollback` | rag.rollback |
| POST | `/api/v1/fleet/devices/{id}/commands` | device_identity.manage |
| POST | `/api/v1/orders/{id}/transition` | operations.write |

Legacy `/api/*` write routes remain for compatibility. No unversioned new public writes.
