# 62. Serve one versioned HTTP prefix

The application publishes exactly one external HTTP contract prefix, `/api/v1`.
The unversioned `/api/*` compatibility surface — 67 paths still being served on
2026-08-12 — is withdrawn, and a request to any of them now answers 404.

Sixty of those paths were never a second implementation. `v1_emotion_routes.py`
and its siblings are nine-line modules that call the unversioned module's
`create_router` with a versioned prefix, so the same handler answered on both,
and removing the second registration removed a published prefix rather than any
behaviour. Seven paths were not duplicates and were given a versioned home
before the withdrawal: the five Optimization Lab paths, and the Admin health
report with its two incident actions.

The health report is not the service-health view. `/api/v1/operations/service-health`
answers "can a customer order right now", one row per service; the report is
built from the Admin audit trail and carries the incidents an operator
acknowledges or escalates. Treating the two as the same surface would have
dropped the incident capability while a name-based mapping made the change look
complete, so the report moved to `/api/v1/admin/health` on its own.

`/api/admin/auth/me` was the one genuine duplicate implementation: it answered
with `{"principal": …, "access": …}` while `/api/v1/auth/me` answered with the
`{"data": …}` envelope, and Admin only ever called the versioned one. Its
transport module is deleted rather than adapted.

## Why now, and what it costs

The execution plan's zero-use inventory recorded that the compatibility surface
had no static consumers, which was true: the frontend allowlist is empty and
every browser call goes through `shared/api/v1Client`. That is not the same
claim as the surface being gone, and the two had been reading as one sentence.
Sixty-seven unversioned paths remained reachable by anything that could open a
socket to the host, each one a second published contract for a capability that
already had an authoritative one — the state `CONTEXT.md` defines an
Authoritative Capability Contract to forbid.

The cost is paid by any consumer outside this repository that was calling an
unversioned path. There is no such consumer we can observe, and the alternative
— keeping both prefixes until runtime telemetry proves zero calls — was the
plan of record and had produced no movement, because nothing generates that
telemetry today.

One behavioural difference survives the move. Errors raised from `/api/v1` pass
through the versioned error envelope, so a refusal that used to arrive as
`{"detail": {"code": …}}` now arrives as `{"error": {"code": …}, "meta": …}`.
The code itself is preserved.

## What this does not settle

Module Independence is untouched. Eight capability interfaces still read from
`services/` and `repositories/`, tracked in `CAPABILITIES_STILL_ON_LEGACY_LAYERS`,
and collapsing a transport prefix says nothing about who owns the data behind
it. The count of capabilities that have passed the gate is unchanged.

`/api/demo/*` and `/api/debug/*` remain unversioned. They are development
routes behind explicit flags that answer 404 in a commercial runtime, not
contracts, and versioning them would imply a stability they must not have.
