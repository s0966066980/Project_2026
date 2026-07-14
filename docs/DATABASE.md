# Database — Single-Store Local Pilot

PostgreSQL is the **only commercial Source of Truth** for `local-pilot`.

Migrations `0001`–`0011` are immutable. New schema uses forward versions only (`0012+`).

## Ownership Matrix (core)

| Domain | Tables (representative) | Owner Module | Scope | PII | SoT |
| --- | --- | --- | --- | --- | --- |
| Tenant/Store/Device | tenants, stores, devices | identity / device | tenant/store/device | no | postgres |
| Admin identity | admin_users, admin_roles, admin_sessions, … | identity | tenant/store | login id | postgres |
| Device identity | device_credentials, device_sessions | device | device | hashes only | postgres |
| Member | members, member_sessions, preferences | member | tenant | phone encrypted | postgres |
| Catalog | menu via app + store_availability | catalog | store | no | postgres (+ seed import) |
| Settings | commercial_settings_versions | catalog / core | tenant/store | no | postgres |
| Promotion | promotion_records, promotion_rule_versions | promotion | store | no | postgres |
| Order | orders, order_items, checkout_idempotency, order_outbox | ordering | store/device | minimal | postgres |
| Interaction | interaction_events, intervention_outcomes | intervention | device | limited | postgres |
| RAG | rag_documents, rag_document_versions, rag_publications | rag | tenant/store | no | postgres (+ object binary) |
| Recommendation | recommendation_* tables | recommendation | store | opaque refs | postgres |
| Worker | background_jobs, order_outbox delivery cols | worker | tenant | no | postgres |
| Fleet | fleet_device_state, fleet_commands, … | fleet | device | no | postgres |
| Analytics | analytics_event_log | analytics | tenant/store | no phone | postgres |
| Object metadata | object_storage_metadata | object_storage | tenant | no | postgres |

## Local filesystem only

- RAG source binaries (via object storage)
- Images / audio / video temp
- Model weights
- Logs / PIDs / runtime temp

## Forbidden in local-pilot

- JSON repository as commercial SoT
- Silent PostgreSQL → JSON fallback
- Tests writing tracked `learning_data/*.json`
