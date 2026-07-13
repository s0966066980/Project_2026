# Milestones 4A–4E TDD Evidence

## Scope

- 4A Payment/POS fake adapter, webhook HMAC, reconciliation
- 4B Object storage isolation, size/type, signed URL
- 4C Fleet heartbeat, allowlisted commands, expiry
- 4D Analytics envelope, idempotent publish/replay, quality
- 4E HA evaluation ADR (defer multi-region / active-active)

## External blockers

- Real payment merchant credentials / certification: BLOCKED (fake/sandbox only)
- Production S3/object-storage account wiring: BLOCKED (contract + local adapter)
- Multi-region demand evidence: not present; architecture deferred
