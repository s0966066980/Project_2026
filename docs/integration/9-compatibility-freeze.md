# Phase 9 Compatibility Freeze

## Active compatibility paths (do not expand)

| Path | Flag / control | Production default |
| --- | --- | --- |
| Member phone PK/column | `MEMBER_IDENTITY_READ_MODE` | Prefer uuid_preferred/uuid_only after evidence |
| Legacy admin token | `ENABLE_LEGACY_ADMIN_TOKEN` | false in commercial runtime |
| Legacy kiosk token | `ENABLE_LEGACY_KIOSK_TOKEN` | false in commercial runtime |
| WebSocket query token | realtime routes compatibility | Migrate to device session cookie |
| JSON storage | `MEMBER_STORAGE_BACKEND=json` | forbidden in commercial runtime |
| Legacy `/api/*` write | allowlist + no new endpoints | v1 write is required for new surface |

## Removal gates (not executed in this program)

Contract removal requires:

1. Production metrics showing zero legacy callers
2. Forward migration (never rewrite 0001–0011)
3. Explicit pilot/production change window
4. Rollback application path via feature flags

## Classification

COMPATIBILITY_FREEZE_PASS for inventory and non-expansion.
CONTRACT_REMOVE remains future gated work — not claimed complete.
