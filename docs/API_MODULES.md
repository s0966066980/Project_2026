# API Modules

Public HTTP surface prefers **`/api/v1/*`**.

## Composition

```text
Frontend v1Client
  → FastAPI /api/v1
    → Module api.py (router only)
      → Module application.py (public API)
        → Domain / Ports
          → Adapters (postgres, local storage, providers)
```

## Module routers (target)

| Module | Router module | Notes |
| --- | --- | --- |
| identity | `modules/identity/api.py` | login, me, admin session |
| device | `modules/device/api.py` | device credentials/sessions |
| catalog | `modules/catalog/api.py` | menu, availability, settings |
| member | `modules/member/api.py` | member lookup (masked) |
| ordering | `modules/ordering/api.py` | orders, transitions |
| promotion | `modules/promotion/api.py` | promotions |
| recommendation | `modules/recommendation/api.py` | events/strategies |
| rag | `modules/rag/api.py` | documents lifecycle |
| intervention | `modules/intervention/api.py` | interaction / voice assist surfaces |
| fleet | `modules/fleet/api.py` | device commands |
| analytics | `modules/analytics/api.py` | internal publish (if exposed) |

`routes/v1_routes.py` may only `include_router` module routers — no business logic.

## Common contracts

`api/v1/contracts.py` holds envelope types only (`ApiResponse`, `ApiMeta`, pagination, common errors).
Domain DTOs live in `modules/<name>/schemas.py`.
