# Pilot Alert Policy

Alert 必須帶 `request_id`/`trace_id` 或安全 aggregate ID，不帶 Phone、Token、DATABASE_URL 或模型敏感輸入。

| Signal | Suggested trigger | Severity | First action |
| --- | --- | --- | --- |
| Database unavailable | `/ready` database failed 2 minutes | Critical | [DB / Migration runbook](RUNBOOK.md#database--migration) |
| Migration drift | checksum/pending failure once during release | Critical | Stop rollout; do not edit applied migration |
| Scope violation | validator count > 0 | Critical | Disable affected writer and preserve evidence |
| Checkout failure spike | > 2% server failures for 5 minutes | High | Inspect transaction/error code and idempotency metrics |
| Auth spike | failure rate > baseline threshold for 5 minutes | High | Check source, rate limit and credential revoke |
| Outbox backlog | oldest pending > 5 minutes after Worker 2E | High | Pause downstream assumptions; replay idempotently |
| Disk / storage | free capacity < 20% or backup failure | High | Protect DB/log integrity; expand or clean by policy |
| AI degraded | provider failure/fallback threshold 10 minutes | Medium | Keep checkout available; activate degraded mode |

Thresholds are initial pilot values and require traffic-informed tuning. Missing telemetry is itself an alert, not evidence of zero failures.
