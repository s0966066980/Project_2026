# ADR-0010：High Availability / Multi-region Evidence-based Evaluation

- 狀態：Accepted (Evaluation Only)
- 日期：2026-07-13
- Owner：Platform / Operations

## Context

Roadmap Milestone 4E requires an evidence-based evaluation of multi-region / HA options. Project_2026 remains a Modular Monolith with PostgreSQL as commercial source of truth, Redis for ephemeral coordination, and separate API/Worker/AI gateway processes.

Current operational evidence available in-repo:

| Signal | Evidence status |
| --- | --- |
| Production traffic / concurrency | Not measured (pilot not certified) |
| DB / Redis / Worker / AI load | Contracts and metrics names exist; no durable production time-series |
| Latency / availability SLOs | Pilot targets documented; attainment not claimed |
| Incident history / RTO / RPO | Runbooks exist; no production incident corpus |
| Multi-region demand | No regional traffic split data |

## Decision

**Defer multi-region active-active and microservice split.**

Implement only when measured evidence shows need:

1. Continue vertical scale and multi-process (API + Worker) on a single primary region.
2. Prefer managed PostgreSQL HA (primary + synchronous/asynchronous standby) and Redis managed HA for pilot maturity.
3. Keep read replicas optional after query-load evidence exists.
4. Reject for now:
   - Microservice split of the commercial core
   - Active-active multi-region writes
   - Multiple writable databases
   - Eventual consistency for checkout/order truth

## Alternatives considered

| Option | Cost / complexity | RTO/RPO | Consistency | Maturity fit |
| --- | --- | --- | --- | --- |
| Vertical scale + multi-process | Low | Host restart minutes | Strong | Current |
| Managed DB HA + Redis HA | Medium | Minutes | Strong | Next when pilot traffic exists |
| Active-passive multi-region | High | Tens of minutes | Strong with failover | Deferred |
| Active-active multi-region | Very high | Low RTO, complex RPO | Often eventual | Rejected without evidence |

## Consequences

- No premature architecture change in this milestone.
- Observability, restore drills, worker reliability, and deployment contracts remain the priority.
- Revisit this ADR when pilot has: sustained concurrency metrics, DB CPU/IO saturation, RTO/RPO requirements from business, and completed restore drills with measured durations.

## Evidence collection checklist (future)

- [ ] 7-day p95/p99 latency by endpoint
- [ ] Peak concurrent Kiosk sessions
- [ ] PostgreSQL connections, slow queries, disk growth
- [ ] Worker queue depth / oldest age
- [ ] Redis memory and fail-closed incidents
- [ ] AI gateway timeout rate without checkout impact
- [ ] Restore drill duration and verified row counts
