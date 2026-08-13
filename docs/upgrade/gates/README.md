# Gate evidence

One entry per completed upgrade item: what was claimed, how it was verified,
and what the verification would have looked like had it failed. A gate recorded
without the second half is a claim, not evidence.

Baseline for all of these: [`../baseline.md`](../baseline.md), `c3592c1`.

## UPGRADE-001 — Test infrastructure

**Gate 1.1**: no unknown-marker warning; unit and integration selectable
separately; hardware excludable; CI can split jobs.

Before: fourteen markers declared in `pyproject.toml`, none applied.
`pytest -m unit` and `pytest -m integration` each answered
`no tests collected (356 deselected)`.

After, measured in the test image:

```text
pytest -m unit           66/370
pytest -m contract       65/370
pytest -m architecture  101/370
pytest -m security       31/370
pytest -m integration    16/370
pytest -m postgres        5/370
pytest -m redis           9/370
pytest -m slow           97/370
pytest -m "not hardware" 370/370
PytestUnknownMarkWarning  0
```

`hardware` is declared with no tests behind it on purpose; everything else is
enforced non-empty by `tests/test_test_taxonomy.py`, which also fails on an
unmarked test file and on an applied-but-undeclared marker. The CI redis job
now selects `-m redis` instead of naming a path.

## UPGRADE-002 — Unversioned surface stays withdrawn

Mutation-verified. Registering `GET /api/mutation_probe` on `core_routes`:

```text
FAILED test_no_unversioned_api_path_is_published
FAILED test_every_published_path_is_versioned_or_explicitly_exempt
```

Removing it returned all four rules to green. A rule that has never been seen
to fail is not known to work.

## UPGRADE-003 — Contract snapshot

118 operations and 77 models captured. Mutation-verified against each of the
three changes the roadmap names as unabsorbable by a consumer:

| Mutation | Result |
| --- | --- |
| rename `auth_method` to `auth_mechanism` | FAILED |
| make `session_id` required | FAILED |
| unregister `v1_promotion_banner_routes` | FAILED |
| revert all three | passed |

## UPGRADE-004 — Build metadata

`GET /api/v1/operations/build`, verified on the live stack after a stamped
rebuild:

```json
{"version": "9.0", "git_sha": "cf84941",
 "build_time": "2026-08-12T09:52:33Z",
 "schema_version": "0028_optimization_lab",
 "deployment_profile": "development"}
```

`schema_version` is the migration head the build carries, read from disk, not
the head the database is at. The two differ exactly when a deployment is
half-applied.

## UPGRADE-005 — Model registry

`config/models/manifest.yaml` declares five models. Verified on the host, where
the weights live:

```text
present  emotion/R1-Omni-0.5B          R1-Omni/models/R1-Omni-0.5B
present  emotion/bert-base-uncased     R1-Omni/models/bert-base-uncased
present  emotion/siglip-base-patch16-224
present  emotion/whisper-large-v3
verified llm/qwen3.5:4b                2a654d98e6fba55d…
model registry verified: 5 declared
```

Negative cases: a manifest digest of all zeroes produced
`mismatch llm/qwen3.5:4b: manifest 0000000000000000… host 2a654d98e6fba55d…`;
pointing the emotion entry at a non-existent directory produced a `missing`
failure; doing the same to the optional RAG entry produced a note, not a
failure, because ordering continues without it.

`--local` must run where the weights are. The application image never carries
model weights, so it reports all four missing — true of that container, and
meaningless as a statement about the deployment. The validator says so in its
failure message.

## UPGRADE-006 — Upgrade from the previous release

Applying every migration to an empty database only proves a fresh install
works. Rehearsed against a temporary PostgreSQL database on the running
18.4 instance:

```text
apply --through 0027_remove_pre_pilot_rag_history   27 applied, 1 pending
apply                                                28 applied, 0 pending
validate --require-clean                             exit 0
apply --through 9999_does_not_exist                  unknown migration: rejected
```

The CI job derives the previous migration from the directory listing rather
than naming it, so the step does not rot the next time a migration lands, and
asserts exactly one migration remains before applying it — otherwise the step
would pass while rehearsing nothing.

## UPGRADE-015 — Identity credential lifecycle

The Module Independence Gate for Identity asks for issue, rotate, revoke and
expiry; store isolation; wrong-device and wrong-store refusal; session replay
and expiry; and an audit trail that is complete without carrying the secret.

None of it is provable on SQLite. `authenticate_device_session` returns `None`
outright when PostgreSQL is not in use, so every negative case would have
passed for the wrong reason. The twelve checks skip unless the run is really on
PostgreSQL, and they remove the rows they create.

Run against the live PostgreSQL 18.4:

```text
pytest tests/test_identity_credential_lifecycle.py   12 passed
```

Covered: a session opens and names its device; a wrong secret is refused; an
unknown key and a wrong secret are refused in the same words, so the refusal
does not say which half was wrong; an expired credential stops opening
sessions; rotation issues a new secret and closes the old one past its grace
window; revocation ends the credential and the sessions it had already opened;
a manager from another store cannot issue, and cannot revoke; a device outside
the scope is refused; the stored credential is a hash; the audit trail records
the events without the raw credential.

### A defect the gate found

Revoking an already-revoked credential returned `True` and wrote another
`device_credential_revoked` event every time. Three clicks produced three
revocation records for one revocation — a security trail describing actions
nobody took.

```text
before   revoke x3 -> True, True, True   audit: device_credential_revoked x3
after    revoke x3 -> True, True, True   audit: device_credential_revoked x1
```

The adapter now transitions only a credential that is still active, and the
event is recorded only on that transition. The API answer stays `True` because
the credential is revoked, which is what the caller asked for; returning
`False` would have made the route answer 404 "not found" for a credential that
exists and is revoked.

### Still open for this capability

PostgreSQL unique/foreign-key/concurrency evidence, Admin and Kiosk
generated-client consumer evidence, and the Pilot authority items. The gate is
not passed.

## UPGRADE-016 — Ordering transaction authority

The roadmap states the invariants Ordering may never break. Each is checked
through the published API against the database that actually stores orders — a
fake store cannot answer "did this produce two rows", which is the question.

Run against the live PostgreSQL 18.4:

```text
pytest tests/test_ordering_transaction_authority.py   8 passed
```

| Invariant | How it holds |
| --- | --- |
| client price ≠ trusted price | The cart stores intentions, not an invoice: `unit_price`, `price` and `total` sent by the browser are dropped before pricing sees them, and the quote's subtotal is the published catalog price |
| promotion is server validated | A total below the subtotal has to name the offer on a line; the observed discount carried `applied_offer_id` |
| duplicate checkout ≠ duplicate order | Same key replays; **a different key on the same quote still returns the same order**, and `confirmed_orders` holds one row. The quote is the anchor, not the header |
| payment pending ≠ paid | A confirmed order is `payment_pending`; HTTP 200 from checkout is not money received |
| the answer can be lost | `GET /api/v1/checkout/outcome/{quote_id}` returns the same order after the reply is dropped |

The one-order guarantee is not application logic that could drift — the
database enforces it:

```text
confirmed_orders_tenant_id_store_id_quote_id_key  UNIQUE (tenant_id, store_id, quote_id)
```

That constraint is the evidence, and it is stronger than a mutation would be.
Dropping a unique constraint from a live orders table to watch a test go red is
not a trade worth making.

### Mutation

The dangerous direction is a system claiming money it has not received, so that
is the one that was broken on purpose:

```text
order status 'payment_pending' -> 'paid'
  FAILED test_a_confirmed_order_is_pending_payment_and_never_paid
  7 passed  (the other invariants correctly unaffected)
revert
  8 passed
```

### Still open for this capability

Transactional outbox atomicity, retry and dead-letter evidence; restart during
confirmation; cart revision conflicts under concurrency; and the full touch and
voice E2E, which needs the target Kiosk. The gate is not passed.
