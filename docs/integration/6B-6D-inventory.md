# Milestones 6B–6D Inventory — Control Plane Durable Persistence

## 6B Recommendation / Promotion

| Artifact | Durable table |
| --- | --- |
| Strategy versions | `recommendation_strategy_versions` |
| Durable experiment assignment | `recommendation_assignments` (+ JSON mirror) |
| Governance events | `recommendation_governance_events` |
| Promotion rule versions | `promotion_rule_versions` |

Production callers keep existing service API; assignment is stable per experiment+session.

## 6C Fleet

| Artifact | Durable table / cache |
| --- | --- |
| Device last-known state | `fleet_device_state` |
| Commands | `fleet_commands` (allowlisted) |
| Config versions | `fleet_config_versions` |
| Rollouts | `fleet_rollouts` |
| Online presence | Redis ephemeral key `fleet:presence:{tenant}:{device}` (not SoT) |

JSON `fleet_devices.json` remains compatibility.

## 6D Analytics

| Artifact | Path |
| --- | --- |
| Event log | `analytics_event_log` via `PostgresAnalyticsSink` |
| Checkpoints | `analytics_checkpoints` |
| Recursive PII reject | nested phone/email/password/token/card/address/raw_media |
| Compatibility | JSON + InMemory sink for tests/dev |

Outbox analytics sink continues to use analytics_pipeline_service publish path (ACK after sink write).
