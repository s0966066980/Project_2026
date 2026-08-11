# P2 Emotion Legacy Purge Manifest

This is the exact, non-wildcard manifest required by ADR-0057 before the
legacy emotion evidence cutover. It is intentionally limited to the named
emotion-intervention artifacts; authoritative ordering, member, campaign,
recommendation, and operational data are out of scope.

## Exact targets

| Target | Action | Replacement / proof |
| --- | --- | --- |
| `UI_API/learning_data/emotion_intervention_logs.json` | Permanently unlink if present; no backup | `emotion_analysis_records.json` stores only the P2 eight-field advisory record |
| `UI_API/backend/repositories/emotion_log_repository._LEGACY_PATH` | Remove the legacy path and purge helper after cutover | Repository has one writer and one 30-day TTL record path |
| `EMOTION_ENABLED` setting key | Remove from settings contract, defaults, public projection, and environment override | `EMOTION_CAPTURE_MODE` is the only `off` / `periodic_ordering` / `voice_only` authority |
| Legacy `voice` / `periodic` emotion mode values | Forward-map once to canonical mode, then persist without the old key/value | Settings migration is deterministic and idempotent |

## Safety boundary

No wildcard, workspace-root, home-directory, recursive, database, volume,
backup, or customer-data deletion is authorized by this manifest. A missing
exact file is a successful no-op. The migration is forward-only; the new
record path is independently rebuildable from its canonical record store.
