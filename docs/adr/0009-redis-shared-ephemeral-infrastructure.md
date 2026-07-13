# ADR-0009：Redis Shared Ephemeral Infrastructure

- 狀態：Accepted
- 日期：2026-07-13
- Owner：Backend / Platform

## Context

單 process rate limit、cache 與 coordination 無法跨 API instance 一致運作，但 Redis 不應成為 Order、Member、Identity 或其他商業資料的真相來源。

## Decision

採用 `CachePort`、`RateLimitPort`、`DistributedLockPort` 隔離 Redis adapter。Key 固定為 `project2026:v1:<tenant>:<store>:<kind>:<resource-sha256>`，resource 只保存雜湊，不含 phone、credential 或完整 PII。

- Security rate limit：staging/production Redis unavailable 時 fail closed；development 可明確回到 process-local compatibility limiter。
- Noncritical cache：有界 TTL，unavailable 時 degrade/cache miss。
- Distributed lock：資料正確性 use case 使用 `required=True` fail closed；owner token + atomic compare-delete 防止其他 instance 解鎖。
- Redis 只保存短期 cache、counter、lock、presence/hot idempotency hint；PostgreSQL 仍是 idempotency 與商業資料 Source of Truth。

## TTL 與 Failure Policy

Cache TTL 最長 24 小時；rate limit 使用 use-case window；lock 使用 bounded lease。Caller 必須依 correctness 指定 lock failure policy，不允許 service 直接 import Redis client。

## Security Boundary

Namespace 一律含 tenant/store。Redis URL 只能由 environment/secret injection 提供，不輸出至 log/error/readiness；production shared rate limit 啟用但缺少 URL 時 startup fail fast。

## Consequences

多 instance 共享 counter/cache/lock，並可分別測試 adapter 與 failure policy。代價是 production 增加 Redis availability dependency，且 lock lease expiry 仍要求 caller operation 有 timeout/idempotency。

## Alternatives

- Process memory：無法跨 instance，僅保留 development compatibility。
- PostgreSQL 實作全部 transient counter/cache：可行但增加 transaction contention，不作預設 hot-path。
- Redis 作 Order/idempotency 真相：拒絕，會建立資料正確性與 recovery 風險。
