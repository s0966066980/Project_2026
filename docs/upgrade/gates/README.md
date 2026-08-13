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

Admin and Kiosk generated-client consumer evidence, and the Pilot authority
items remain. PostgreSQL uniqueness, foreign keys, and rotation concurrency
are recorded below; the gate is not passed.

## UPGRADE-031 — Identity PostgreSQL uniqueness and foreign keys

Identity now has real PostgreSQL constraint evidence: a duplicate `key_id` is
rejected by the unique constraint, and a credential referencing an unknown
device is rejected by the composite foreign key. The existing lifecycle suite
continues to prove issue, session, rotation, revocation, expiry and safe audit
behavior.

```text
pytest tests/test_identity_credential_lifecycle.py \\
       tests/test_identity_postgres_constraints.py (PostgreSQL 18.4)  14 passed
full backend suite                                               468 passed, 49 skipped
docker/scripts/test.sh                                           passed
```

Generated-client consumer evidence and Pilot authority items remain open.

## UPGRADE-038 — Identity PostgreSQL rotation concurrency

The production PostgreSQL device-identity adapter now has executable evidence
for concurrent rotation: two administrators rotating the same active
credential produce one replacement and one controlled refusal, while the
rotation audit remains singular. A credential already in its rotation grace
window is no longer eligible for a second replacement.

```text
pytest tests/test_identity_postgres_concurrency.py (PostgreSQL 18.4)  1 passed
full backend suite                                               472 passed, 54 skipped
docker/scripts/test.sh                                           passed
```

Generated-client consumer evidence and Pilot authority items remain open.

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

The full touch and voice E2E needs the target Kiosk, and the Admin/Kiosk
generated-client consumer ledger is not written. Everything else this section
listed as open has since been evidenced: transactional confirmation atomicity
in UPGRADE-041, restart during confirmation in UPGRADE-042, outbox
retry/dead-letter in UPGRADE-022, and cart revision conflicts under PostgreSQL
concurrency in UPGRADE-023. The gate is still not passed, and what is left is
now hardware and consumer evidence rather than backend behaviour.

## UPGRADE-017 — Member capability gate

```text
pytest tests/test_member_capability_gate.py   11 passed   (PostgreSQL 18.4)
```

Registration and login including not-found and malformed numbers; the masked
form; a tenant-scoped lookup hash; key failure refusing rather than returning
something plausible; session binding, clearing and store isolation.

### The promise that outranks the rest — and the defect against it

Guest ordering is Core; Member is Operational. Breaking the member store and
walking a Guest through checkout found that it was not true:

```text
POST /api/v1/checkout/prepare
  -> CheckoutConfirmationModule.prepare
  -> runtime.ProductionPricing.price
  -> capabilities.member.get_session_member   RuntimeError
  -> checkout fails for a Guest
```

Pricing asked Member whether the session belonged to a member so it could apply
member pricing, and let the failure escape. An Operational dependency was
deciding whether anyone could buy anything, which inverts the criticality
declaration in `CONTEXT.md`.

Pricing now treats an unanswerable Member as "not a member" — the safe answer,
because it never grants a discount the customer has not proven — and counts
`checkout_member_lookup_degraded_total` so the degradation is visible instead
of silent. The metric had to be registered first: `increment_metric` refuses
unregistered names, which caught the omission immediately.

Mutation: letting the failure escape again failed exactly that test and left
the other ten passing.

### A Pilot finding, not a test failure

`members` stores the number in three columns — `phone`, `phone_encrypted`,
`phone_lookup_hash`. On this runtime:

```text
plaintext phone: 21    encrypted: 0    total rows: 21
```

`MEMBER_IDENTITY_READ_MODE` defaults to `legacy` and `MEMBER_IDENTITY_DUAL_WRITE`
to false, so the protection exists and is never taken. The test proves the
mechanism works when enabled — ciphertext written, decryptable, masked form
distinct — rather than flipping a deployment decision on the owner's behalf.

**Member PII protection is off in this runtime.** That is acceptable for a
development runtime and is not acceptable for Pilot, so it belongs on the Local
Pilot Admission list next to the Configuration Authority.

### Still open for this capability

PostgreSQL migration/backfill and the Admin/Kiosk consumer ledger remain. The
scoped integrity/concurrency proof is recorded below; the gate is not passed.

## UPGRADE-018 — Campaign & promotion capability gate

```text
pytest tests/test_campaign_capability_gate.py   24 passed   (PostgreSQL 18.4)
```

Lifecycle: `archived` is terminal; `draft` cannot reach `active` without
passing through review; every transition target is itself a declared state; a
live or scheduled campaign is not editable until it is paused, so nobody edits
the terms of an offer while customers are being sold under them.

Schedule: a date-only end is inclusive to the end of that day in the
**campaign's** timezone, not the server's — the same instant is inside an offer
ending on the 13th in UTC and outside it in Taipei, and the tests pin both
sides of that boundary. An unusable timezone string falls back rather than
taking pricing down; an authoring mistake is not an outage.

Pricing authority: an offer scoped to another store does not apply here; an
inactive one does not price; an offer outside its window does not price; an
offer may not price an item at zero or below, and may not raise the price above
the catalog price. Two offers never stack — the cheaper one wins.

### What the gate clarified about where price comes from

`quote_promotion` reads `promo_price`, the promoted price itself. It never
reads `discount_type`/`discount_value`, which are campaign-authoring fields.
An offer carrying only those two prices nothing, and the gate now says so out
loud, because inferring a live price from an authoring field would let an
unreviewed edit move what a customer pays.

### The client's preference is a tie-break, not an override

`select_promotion_quote` takes a `preferred_ref` — the offer the browser says
it wants. It may break a tie between offers the server itself found eligible;
it may not introduce one, and it may not beat a cheaper offer. Both directions
are checked, because this is the field a tampered client would reach for.

### A scheduled campaign is projected as "active"

`project_legacy` writes `status: "active"` into `promotion_records` for a
campaign that is merely `scheduled`. Anything trusting that field alone would
show — and price — an offer before it starts. What actually holds the line is
`start_at` on the projected record, so the gate reads the record the Kiosk
reads and prices against it on both sides of the start:

```text
publish starting 2026-08-20, quote on 08-13   not eligible  promotion_not_started
publish starting 2026-08-20, quote on 08-21   eligible      50
```

The behaviour is correct as long as every reader evaluates the window. It is
recorded here rather than changed, because the flag is what the Admin console
lists on and narrowing it is a product decision, not a test's.

### Publication

A campaign starting later is published as `scheduled`, not forced live —
publishing is a request to go on air, not an instruction to go on air now. A
payload the authoring rules refuse leaves nothing behind: the campaign list is
identical before and after the rejection, so an operator never has half a
campaign they cannot see.

### Mutation

```text
the client's preference outranks the price
  FAILED test_a_preference_cannot_beat_a_cheaper_offer            (23 passed)
an offer may raise the price above the catalog price
  FAILED test_an_offer_that_raises_the_price_is_not_honoured      (23 passed)
the last day ends at midnight instead of end of day
  FAILED test_the_last_day_of_an_offer_lasts_until_the_end_of_that_day
  FAILED test_the_boundary_is_read_in_the_offers_timezone_not_the_servers
                                                                  (22 passed)
revert
  24 passed
```

Each mutation failed exactly the rule it broke and left the rest passing.

### Still open for this capability

The external notification surface, content edits under concurrent publication,
and the Admin and Kiosk generated-client consumer ledger remain. The durable
publish race is recorded below, as is the local notification-copy batch
worker contract; the gate is not passed.

## UPGRADE-034 — Campaign notification-copy batch worker

The notification-copy batch worker now has executable evidence for its local
processing contract: one failed item does not abort the remaining items, a
partial batch succeeds with per-item failures recorded, and a batch is marked
failed only when every item fails.

```text
pytest tests/test_push_copy_batch_worker.py                     2 passed
full backend suite                                               472 passed, 50 skipped
docker/scripts/test.sh                                           passed
```

Provider delivery, the live notification surface, and Admin/Kiosk consumer
evidence remain open.

## UPGRADE-037 — Campaign PostgreSQL publish race

The production PostgreSQL campaign repository now has executable evidence for
the publish race: two publishers forced to observe the same draft version
produce exactly one winner and one `campaign_version_conflict`, leaving one
durable current version rather than silently overwriting each other.

```text
pytest tests/test_campaign_postgres_publish_race.py (PostgreSQL 18.4)  1 passed
full backend suite                                               472 passed, 53 skipped
docker/scripts/test.sh                                           passed
```

External notification delivery, the live notification surface, and the
Admin/Kiosk generated-client consumer ledger remain open.

## UPGRADE-019 — Knowledge/RAG capability gate

```text
pytest tests/test_knowledge_rag_capability_gate.py   20 passed
```

Retrieval is exercised against a fake provider on purpose. The question this
gate asks is what the capability does with what a provider returns — drop a
weak hit, fall back, refuse — and a real embedded index would answer a
different question (whether Chroma works) while making every assertion
non-deterministic. The publication store is faked for the same reason: the
rule under test is what reaches the index, not how rows are stored.

What counts as an answer: a hit below the policy threshold is not returned at
all, a hit exactly at it is; an unscored row is dropped rather than ranked
first, because a row that cannot be compared cannot be trusted; `strict`
admits less than `balanced`; an empty index answers empty instead of failing.
An unsupported method, `top_k` or policy is refused by name **before** the
provider is called.

Degradation: a failing strategy falls back down its chain and the answer says
both what was asked for and what actually ran, so a worse answer is never
mistaken for a good one. A caller that opts out of fallback gets the failure
and exactly one attempt. When every strategy in the chain fails, retrieval
raises — an unavailable provider must not become a confident empty answer.

The published index: a publication reaches the querying process chunk for
chunk, carrying tenant, store and attempt id; repairing the same publication
twice indexes it once. An artifact that does not match its item is refused and
nothing is partially applied. The dangerous case of the three is not the
unparseable one — it is valid JSON of the right shape and one document short,
which would answer from a document belonging to a different chunk.

The prohibition: **RAG may not write ordering.** Every import in
`modules/knowledge_publication`, `modules/retrieval_check`,
`modules/retrieval_configuration` and `capabilities/knowledge_rag` is parsed
and checked against the ordering roots at any nesting depth. A second rule
asserts those roots still exist — ordering was reorganised once already in
this project, and a guard naming the old layout would keep passing while
checking nothing. That rule earned itself immediately: it rejected three
module names from the first draft of this list.

### Mutation

```text
present a hit below the threshold as an answer
  FAILED …below_the_relevance_threshold_is_not_an_answer
  FAILED …with_no_score_is_dropped_rather_than_ranked_first
  FAILED …a_stricter_policy_admits_less                      (17 passed)
fall back without recording that it happened
  FAILED …falls_back_and_says_that_it_did                    (19 passed)
index an artifact that does not match its item
  FAILED …does_not_match_its_item_is_refused[not-a-list]
  FAILED …does_not_match_its_item_is_refused[wrong-length]   (18 passed)
turn an unavailable provider into an empty answer
  FAILED …a_caller_that_refuses_fallback_gets_the_failure
  FAILED …raises_rather_than_inventing_an_answer             (18 passed)
revert
  20 passed
```

### Still open for this capability

Index rebuild, governance and the malicious-document path, and end-to-end
retrieval against a real index on the target hardware remain. PostgreSQL
duplicate-document handling, artifact cleanup, and retirement state are
recorded below; the gate is not passed.

## UPGRADE-032 — Knowledge PostgreSQL duplicate-document handling

The production PostgreSQL publication store now has executable evidence for
the duplicate-document policy: a near duplicate is refused unless the editor
explicitly overrides the warning, while an exact duplicate remains refused
even with that override.

```text
pytest tests/test_knowledge_postgres_duplicates.py (PostgreSQL 18.4)  1 passed
full backend suite                                               468 passed, 50 skipped
docker/scripts/test.sh                                           passed
```

Index rebuild, retirement cleanup, governance, malicious-document handling,
and real-index retrieval on target hardware remain open; retirement evidence
is recorded below.

## UPGRADE-033 — Knowledge publication artifact cleanup

The publication artifact adapter now has deterministic contract evidence for
the runtime portion of rebuild/cleanup: every chunk receives scoped metadata,
successful artifacts can be cleaned completely, and a partial build removes
the already-registered chunk ids in reverse order before surfacing a transient
failure.

```text
pytest tests/test_knowledge_artifacts.py                         2 passed
full backend suite                                               470 passed, 50 skipped
docker/scripts/test.sh                                           passed
```

The live index provider, store-level retirement state transitions, and target
hardware retrieval remain open; the PostgreSQL retirement transition is
recorded below.

## UPGRADE-036 — Knowledge PostgreSQL retirement cleanup

The production PostgreSQL publication store now has executable evidence for
retirement: the published pointer is removed, the knowledge version becomes
retired, the artifact cleanup is completed exactly once, and the retirement
and cleanup audit events remain durable. Resuming an already completed cleanup
does not delete the artifact a second time.

```text
pytest tests/test_knowledge_postgres_retirement.py (PostgreSQL 18.4)  1 passed
full backend suite                                               472 passed, 52 skipped
docker/scripts/test.sh                                           passed
```

Index rebuild, governance, malicious-document handling, and real-index
retrieval on target hardware remain open.

## UPGRADE-020 — Recommendation capability gate

```text
pytest tests/test_recommendation_capability_gate.py   13 passed
```

Recommendation is declared an enhancement in `CONTEXT.md`, not a transaction
authority, so every check here asks the same question: when this capability
has a bad day, does the customer still get a menu and a price?

The engine having a bad day: a provider failure, a provider timeout and an
empty result all fall back to a deterministic list rather than a blank
surface, and the answer says `fallback_status: engine_fallback` so an operator
can tell a degraded decision from a healthy one. An engine failure with an
empty menu returns an empty list and a decision id — not an exception.

What may be recommended: an excluded item is never returned (this is how
sold-out and unavailable items are kept off the surface), an item with no id
is dropped because nobody could order it, no more items come back than were
asked for, and every item carries the decision id and rank that make a later
touch attributable. An offer is recommended **by reference and version**, not
by restating its terms — the projected `offer_versions` carry `offer_id` and
`version` and nothing else, so a price cannot travel inside a suggestion.

The prohibition is checked as an import rule, since that is the only way to
state it once and have it hold for every future caller: `modules/cart`,
`modules/checkout_confirmation`, `modules/ordering_entry` and
`modules/promotion` may not reach `modules.recommendation`,
`modules.analytics` or the capability surface at any nesting depth. A second
rule asserts every tree it names still exists.

### A defect the gate found

Analytics is downstream of a decision. It was also, in practice, a
precondition for one:

```text
decide(..., scope=...)
  -> record_touch
  -> analytics_pipeline_service.publish
  -> sink.write   RuntimeError
  -> no recommendation is shown
```

An unavailable analytics sink raised straight out of `decide`, so an Optional
capability could blank an enhancement surface on the Kiosk. The same shape as
the Member defect in UPGRADE-017, in a different capability.

The touch is now recorded in a way that cannot stop the decision, and the loss
is counted as `recommendation_touch_record_degraded_total` so the attribution
gap is visible rather than silent. The metric had to be registered first —
`increment_metric` refuses unregistered names.

### Mutation

```text
let the analytics outage escape again
  FAILED …an_analytics_outage_does_not_take_recommendations_down   (12 passed)
degrade silently, without counting it
  FAILED …an_analytics_outage_does_not_take_recommendations_down   (12 passed)
do not mark an engine failure as a fallback
  FAILED …a_provider_failure_still_returns_something_to_show
  FAILED …an_empty_recommendation_falls_back_rather_than_showing_a_blank
  FAILED …the_fallback_is_marked_as_a_fallback                     (10 passed)
recommend an item the caller excluded
  FAILED …an_item_the_caller_excluded_is_never_recommended         (12 passed)
revert
  13 passed
```

The first two mutations are the same test failing for the two different
reasons it exists: the recommendation must survive, and the loss must be
counted.

### Still open for this capability

Runtime interaction and intervention pipeline publication, the effectiveness
report against real touch data in PostgreSQL, and the Kiosk consumer ledger
remain open. PostgreSQL interaction storage, replay idempotency, and Kiosk
route publication are recorded below; the capability gate is not passed.

## UPGRADE-035 — Recommendation PostgreSQL interaction storage

The production PostgreSQL interaction adapter now has executable evidence for
scoped storage and replay: an event is readable only within its commercial
scope, replaying the same opaque `event_id` updates the existing row instead
of creating a second row, and privacy projection removes secret metadata.

```text
pytest tests/test_recommendation_postgres_interactions.py (PostgreSQL 18.4)  1 passed
full backend suite                                               472 passed, 51 skipped
docker/scripts/test.sh                                           passed
```

Runtime publication/intervention, effectiveness against real touch data, and
the Kiosk consumer ledger remain open.

## UPGRADE-039 — Recommendation PostgreSQL interaction route publication

The Kiosk interaction route now has executable PostgreSQL evidence: a request
passes through the versioned route, resolves the default commercial scope,
normalizes and persists one interaction event, and privacy projection removes
secret metadata.

```text
pytest tests/test_recommendation_postgres_interaction_route.py (PostgreSQL 18.4)  1 passed
full backend suite                                                   472 passed, 55 skipped
docker/scripts/test.sh                                               passed
```

Runtime recommendation/intervention publication, effectiveness against real
touch data, and the Kiosk consumer ledger remain open.

## UPGRADE-040 — Recommendation PostgreSQL intervention route publication

The Kiosk intervention routes now have executable PostgreSQL evidence: a
barrier-state request creates one scoped intervention outcome, and a following
intervention-result request updates that same outcome with customer feedback
and scenario enrichment. The route also exposed and now uses the missing
Operations statistics capability wrappers instead of failing at runtime.

```text
pytest tests/test_recommendation_postgres_intervention_route.py (PostgreSQL 18.4)  1 passed
full backend suite                                                              472 passed, 56 skipped
docker/scripts/test.sh                                                          passed
```

Effectiveness against real touch data, runtime recommendation quality, and the
Kiosk consumer ledger remain open.

## UPGRADE-021 — Reliable worker and order outbox delivery

The worker's durable job and outbox contracts now have executable evidence for
retry with bounded backoff, visibility-timeout reclaim after a worker crash,
dead-lettering after the attempt budget, and idempotent outbox acknowledgement.

```text
pytest tests/test_worker_reliability.py   4 passed
full backend suite                         453 passed, 44 skipped
docker/scripts/test.sh                     passed
```

The test uses one injected clock for enqueue, claim, retry, and reclaim, so a
host-clock-dependent event cannot make the evidence pass by accident.
Production outbox seeding still defaults to the current UTC time; the optional
`available_at` is a deterministic adapter/test boundary.

## UPGRADE-022 — Reliable Checkout confirmation outbox delivery

The active `checkout_outbox` path used by Checkout confirmation now claims
events with a lease, retries transient consumer failures with bounded backoff,
and dead-letters events after their attempt budget. Published events clear the
lease and are not delivered again. SQLite keeps the compatibility bootstrap;
PostgreSQL uses row locking with `SKIP LOCKED`, and migration `0029` adds the
durability fields and claim index.

```text
pytest tests/test_checkout_outbox_reliability.py tests/test_checkout_contract.py  5 passed
full backend suite                                                               456 passed, 44 skipped
docker/scripts/test.sh                                                           passed
```

## UPGRADE-023 — PostgreSQL cart revision concurrency

PostgreSQL cart replacement now locks the existing cart row with `FOR UPDATE`.
First-writer creation uses `ON CONFLICT DO NOTHING` before the same locked read,
so two requests carrying the same stale revision cannot overwrite one another.
The integration test runs two threads against PostgreSQL and requires exactly
one commit plus one `cart_revision_conflict`; it then verifies revision 1 and
the committed lines.

```text
pytest tests/test_cart_revision_concurrency.py (PostgreSQL 18.4)  1 passed
full backend suite                                             456 passed, 45 skipped
docker/scripts/test.sh                                         passed
```

## UPGRADE-024 — PostgreSQL Checkout outbox claim state

The PostgreSQL Checkout outbox adapter now returns the row after its claim
update, so the consumer sees the incremented `attempt_count` and current
`max_attempts` just like the SQLite adapter. The real PostgreSQL integration
test inserts a uniquely identified event, claims it through the adapter, and
asserts `attempt_count == 1`; the event is removed after the assertion.

```text
pytest tests/test_postgres_checkout_outbox_claim.py (PostgreSQL 18.4)  1 passed
full backend suite                                               456 passed, 46 skipped
docker/scripts/test.sh                                           passed
```

## UPGRADE-025 — Operations health timeout and operator retry

The Admin Operations health panel now has executable evidence for both sides
of its bounded failure contract: a service-health request that never answers
fails after 5 seconds, and a subsequent operator retry performs a fresh read
and returns the panel to a healthy state when the service recovers. The panel
continues to use the shared versioned Operations client with retries disabled,
so the retry remains an explicit operator action.

```text
npm test -- --run tests/unit/health-admin.test.ts          14 passed
frontend full unit suite                                  131 passed
frontend typecheck + syntax                               passed
full backend suite                                        456 passed, 46 skipped
docker/scripts/test.sh                                    passed
```

## UPGRADE-028 — Campaign authored push-copy resolution

Campaign evidence now covers the authored push-copy path: campaign wording is
served only while its referenced offer is live, expired wording falls back to
the base copy, missing authored copy falls back to the menu description, and
member-only offers are excluded from guest push-copy resolution.

```text
pytest tests/test_campaign_capability_gate.py -k push_copy   3 passed
```

The pytest line here previously named the intervention-route test, which has
nothing to do with push copy; the authored-copy checks live in the Campaign
gate suite.

## UPGRADE-041 — PostgreSQL Checkout confirmation atomicity

Checkout confirmation now has executable PostgreSQL evidence for its all-or-
nothing write boundary: when a later order item violates a database constraint,
the order, its items, and its confirmation outbox event are all rolled back.

```text
pytest tests/test_ordering_postgres_transaction_atomicity.py (PostgreSQL 18.4)  1 passed
```

Mutation: committing the order before its items are written — the exact
regression this claims to catch — failed the check, and reverting returned it
to green.

One caveat on the evidence as written. The outbox half of the assertion joins
`order_outbox` to `orders`, and `order_outbox_aggregate_id_fkey` cascades from
`orders(id)`. With no order row surviving, no outbox row can survive either, so
that second assertion is guaranteed by the schema rather than by the code under
test. The rollback of the order is proven; "the outbox event rolled back too"
rests on the foreign key, which is the stronger guarantee but a different one.

## UPGRADE-042 — PostgreSQL Checkout outbox restart recovery

The Checkout confirmation outbox now has PostgreSQL recovery evidence across a
dispatcher restart: a claimed event records its attempt, a failed delivery
clears the lease and becomes available again, and a fresh store instance can
claim and publish it exactly once.

```text
pytest tests/test_postgres_checkout_outbox_reliability.py (PostgreSQL 18.4)  1 passed
```

## UPGRADE-043 — Recommendation PostgreSQL effectiveness facts

Recommendation effectiveness now has an executable PostgreSQL data-path gate:
real touch events are written through the analytics sink, real order
attribution is written through the scoped PostgreSQL adapter, and the report
reads both durable sources to produce the deduplicated funnel and revenue.

```text
pytest tests/test_recommendation_postgres_effectiveness.py (PostgreSQL 18.4)  1 passed
```

## UPGRADE-044 — Campaign PostgreSQL edit/publish race

Campaign authoring now has PostgreSQL evidence for an editor revising a draft
while another operator publishes that same draft: exactly one optimistic
concurrency winner is retained, the other receives `campaign_version_conflict`,
and the durable campaign remains on a single version path.

```text
pytest tests/test_campaign_postgres_edit_publish_race.py (PostgreSQL 18.4)  1 passed
```

## UPGRADE-029 — Recommendation interaction and analytics contracts

Recommendation now has repository-level evidence for the remaining pure
interaction and analytics contracts: experiment assignment stays disabled
until both switches are ready and is deterministic when enabled; interaction
metrics are normalized and clamped while UI context is preserved; repeated
payment failures produce a high-level staff intervention that disables
promotion; and effectiveness reporting scopes events, deduplicates touch and
purchase ids, preserves provisional attributions, and reports sample-size
warnings and variant comparisons.

```text
pytest tests/test_recommendation_analytics_capability.py       6 passed
full backend suite                                            468 passed, 46 skipped
docker/scripts/test.sh                                        passed
```

This does not yet prove the live interaction/intervention pipeline against
PostgreSQL touch data or the Admin/Kiosk consumer ledger; those remain open.

## UPGRADE-030 — Member PostgreSQL scoped registration integrity

Member registration now has a real PostgreSQL concurrency check: two
simultaneous registrations for the same phone and tenant both complete without
an integrity error, leave exactly one scoped member row, preserve the optional
consent flags, and leave exactly one member-preferences row.

```text
pytest tests/test_member_postgres_integrity.py (PostgreSQL 18.4)       1 passed
full backend suite                                                   468 passed, 47 skipped
docker/scripts/test.sh                                               passed
```

The remaining Member gate work is migration/backfill authority and the
Admin/Kiosk consumer ledger.

## UPGRADE-027 — Member consent policy

Member registration now keeps necessary terms separate from the two optional
consents. Without order-history consent, detailed history is neither stored
for completed or abandoned orders nor projected to the customer; without
personalization consent, preference aggregates, usuals, and push context are
not updated or projected. Each optional consent can still be enabled
independently.

```text
pytest tests/test_member_consent_policy.py                 3 passed
full backend suite                                        459 passed, 46 skipped
docker/scripts/test.sh                                    passed
```

## UPGRADE-026 — Kiosk checkout projection seam

The first Kiosk frontend decomposition step extracts the checkout projection
rules from `kiosk/app.js` into `kiosk/checkout.js`. Its small interface owns
server-quote totals, server-issued order identity, and the final completion
item projection; DOM event wiring and transport remain in the app adapter.
The characterization tests cover server-pricing preference and the safe local
fallback for incomplete response payloads.

```text
npm test -- --run tests/unit/checkout-contract.test.ts tests/unit/cart-contract.test.ts  5 passed
frontend full unit suite                                                               134 passed
frontend typecheck + syntax                                                            passed
full backend suite                                                                      456 passed, 46 skipped
docker/scripts/test.sh                                                                  passed
```

## Verification pass — 2026-08-13

The whole suite, re-run at `2f10774` plus the lint repair below.

```text
pytest -q                              472 passed,  60 skipped   (SQLite)
pytest -q  (DATABASE_BACKEND=postgresql) 523 passed,   9 skipped   (PostgreSQL 18.4)
mypy                                   no issues in 63 source files
ruff check . && ruff format --check .  clean, after the repair below
```

The nine remaining skips on PostgreSQL are all `tests/test_redis_shared_integration.py`,
which needs `REDIS_URL`.

Three things this pass corrected rather than reported as passing:

**Lint was not clean.** `ruff check .` reported 12 findings (10 unsorted import
blocks, one unused import, one lambda assignment) and `ruff format --check`
wanted 14 files reformatted — all of them newly added test files. CI runs both
over the whole tree, so this would have failed on push. Fixed; the lambda
became a `def` rather than being auto-fixed away.

**The running stack was not healthy.** `app` was `unhealthy` and `/ready`
returned 503 with `database: failed, migration: failed`. The cause was not a
defect in the code: migration `0029_checkout_outbox_reliability` had been
applied to the database while the running container still carried an image
built before it existed, so the app correctly refused to call itself ready
against a schema ahead of its own source. Rebuilding `app` and `worker` cleared
it — `ready: true`, all four required checks ok, `schema_version` now
`0029_checkout_outbox_reliability`. Worth keeping: the readiness check caught a
real half-applied deployment, which is exactly what it is for.

**Most new entries carry no mutation.** Of the 36 entries in this file, 7
record a mutation. The 21 added in the most recent batch record only "N
passed". A check that has never been seen to fail is not known to work, and
that is this project's own standard — UPGRADE-002 says so in as many words.
UPGRADE-041 has since been mutation-verified (above) and the vacuous half of
its assertion recorded. The rest still need the same treatment before they
count as evidence.

## Mutation pass — 2026-08-13

The verification pass above found that 21 of the entries in this file recorded
only "N passed". Every one of those rules has now been broken on purpose. What
follows is the result for each, and the four gaps the exercise exposed.

Mutations were run against a live-mounted source tree (`docker run -v
$PWD/UI_API:/app/UI_API project-2026:test`) rather than a rebuilt image, so a
mutate/run/revert cycle costs about a second instead of a minute. The driver
refuses to run when its anchor text is missing or ambiguous — a mutation that
silently failed to apply would "prove" a rule that was never exercised.

### Caught

| Rule | Mutation | Result |
| --- | --- | --- |
| 001 layer markers | remove a file's `pytestmark`; add an undeclared marker | both FAILED |
| 015 revocation | leave the credential's sessions alive; audit every repeat revoke | both FAILED |
| 021 worker retry | retry past the attempt budget; retry with no backoff | both FAILED |
| 022 checkout outbox | never dead-letter; keep the lease after a failed delivery | both FAILED |
| 023 cart revision | accept a stale expected revision | FAILED |
| 024 outbox claim | claim without counting the attempt | FAILED |
| 027 member consent | register without the necessary terms; project history and usuals without their consents | all three FAILED |
| 028 push copy | serve campaign wording after its offer ends; show a member-only offer to a guest | both FAILED |
| 029 recommendation contracts | keep negative dwell/counts; enable an experiment on one switch; stop escalating repeated payment failures; intervene on a normal session | all five FAILED |
| 030 member integrity | drop the conflict target on the member row, then on the preference row | both FAILED |
| 032 knowledge duplicates | publish a near-duplicate without the override; accept an exact duplicate | both FAILED |
| 033 artifacts | keep the chunks a partial build already wrote | FAILED |
| 034 push-copy batch | fail the whole batch for one failed item | FAILED |
| 035 interactions | store client metadata verbatim; store a replayed event twice | both FAILED |
| 036 retirement | leave the published pointer; skip the row-revision bump | both FAILED |
| 037/044 campaign race | accept a stale expected version; read the definition without a lock | both FAILED |
| 038 rotation | rotate an already-rotated credential | FAILED |
| 040 intervention route | drop the result write-back; read the outcome without its device scope | both FAILED |
| 041 checkout atomicity | commit the order before its items | FAILED |
| 042 outbox restart | keep the lease after failure; keep the lock after publishing | both FAILED |
| 043 effectiveness | count a repeated impression twice; count a repeated purchase twice | both FAILED |
| 025 admin health (frontend) | retry behind the operator's back; unbound the read; drop the failure label | all three FAILED |
| 026 kiosk checkout seam (frontend) | prefer local cart data over the server quote; read subtotal as total | both FAILED |

In every case the mutation failed the rule it broke and left the rest of the
suite passing.

### The four gaps it exposed

**A cart race that never raced (UPGRADE-023).** Both writers were creating a
cart that did not exist yet, so what serialized them was the unique index
behind `INSERT ... ON CONFLICT DO NOTHING`. Removing `SELECT ... FOR UPDATE`
left the test green. The case where the lock matters — two writers against a
cart that already exists, which is where a lost update actually happens — was
not covered. It is now, and it catches the missing lock 3/3.

**A rotation race that never raced (UPGRADE-038).** `executor.map` with no
barrier ran the two rotations back to back. Adding a barrier was not enough
either: the two `SELECT`s still land about 5ms apart, so the loser reliably
reads the committed grace window. Sixteen simultaneous rotators put several
readers inside the same window — stable 6/6 with the lock, caught 6/6 without
it. The two-caller test keeps its narrower claim and now states what it does
not prove.

**A cleanup failure nobody checked (UPGRADE-033).** `delete_document`
returning False means the index still holds the chunk. Swallowing that marks
an item retired while its content stays answerable, which is the one outcome
retirement exists to prevent — and it passed. Covered now, with the
unparseable-artifact-reference case beside it.

**A dedup claim with no duplicates (UPGRADE-043).** The fixture had one of
everything, so "deduplicated funnel" held whatever the code did. The report is
now also asked for a replayed impression and a twice-attributed order item.

**A pickup number the kitchen never issued (UPGRADE-026).** The seam's own
comment says only the server can provide a pickup number, but inventing one
locally passed. A made-up number sends a customer to wait for an order nobody
called. Covered now.

### Rules that cannot fail while their neighbour holds

Three checks are unreachable defence rather than live rules, and are recorded
as such instead of being counted as evidence:

- the campaign compare-and-set `rowcount` check, unreachable while the
  definition row is locked and the version compared;
- the device clause on the intervention-outcome `UPDATE`, unreachable because
  the scoped `SELECT ... FOR UPDATE` already returned nothing;
- the outbox half of UPGRADE-041, guaranteed by `ON DELETE CASCADE`.

Each is worth keeping — they are the second line if the first is ever changed
— but none of them is something a test observed working.

### One thing the pass broke and fixed

The knowledge duplicates test recorded ids at the call site, so a draft
created inside a `pytest.raises` that unexpectedly succeeded was left in
PostgreSQL, and then failed the same test on its next run for a reason
unrelated to the code. That is not hypothetical: it happened here and cost a
diagnosis. Drafts now register themselves as they are created.

## Incident — local LLM unusable, 2026-08-13

Reported as two symptoms: the Admin LLM test failed against local Ollama, and
the AI paths that depend on it did not work. Three separate causes, one
environmental and two in the code.

### The GPU was granted and then silently lost

Ollama's scheduler reported a healthy CUDA device with 23 GiB free, while the
inference process behind it said something else:

```text
sched.go   msg="gpu memory" id=0 library=CUDA available="23.0 GiB"
ggml_cuda_init: failed to initialize CUDA: no CUDA-capable device is detected
common_param: system_info: n_threads = 4 (n_threads_batch = 4) / 20
```

The container had been created with `gpus: all`, `NVIDIA_VISIBLE_DEVICES=all`
and the device nodes were present inside it, but CUDA initialisation failed
anyway — the cgroup device access had been revoked from the running container
after it started, which typically follows a `systemctl daemon-reload` or a
driver update. Ollama fell back to CPU on 4 of 20 threads without saying so,
and a 4B model behind a 6,000-character prompt could not finish inside two
minutes.

Recreating the container restored it (`offloaded 34/34 layers to GPU`):

| Path | Before | After |
| --- | --- | --- |
| `POST /api/v1/diagnostics/ask` | 120s, timed out | 1.9s cold, 1.0s warm |
| `connectivity_test` (both providers) | 7.6s local probe | 1.5s, `all_ok` |

This is worth remembering as a diagnostic: **Ollama reporting GPU memory is
not evidence that it is using the GPU.** Only `ggml_cuda_init` and the
`offloaded N/N layers` line say that. A GPU that disappears from a running
container is invisible from the outside and shows up only as slowness.

### The local adapter discarded the caller's timeout

`NvidiaNimAdapter` passed `request.timeout_seconds` to `requests`.
`OllamaAdapter` never did: `ask_ollama` and `ask_ollama_raw_text` always used
`OLLAMA_TIMEOUT` (120s). So the connectivity probe asking for 15s and the
Admin diagnostic asking for 60s both waited two minutes, while the browser's
own 15s client bound had already given up — the operator saw a failure with no
reason, and the server finished long afterwards and returned HTTP 200 to
nobody.

Both entry points now take the caller's bound, floored at one second so a
zero cannot become an instant abort, and fall back to the deployment default
only when no bound is stated. `tests/test_llm_local_adapter_bounds.py`, four
checks, mutation-verified four ways:

```text
discard the bound on the JSON path         FAILED (2)
discard the bound on the free-text path    FAILED (1)
ignore a stated bound entirely             FAILED (3)
pass a zero bound straight through         FAILED (1)
revert                                     4 passed
```

The warm-up and streaming calls keep the deployment default: neither has a
caller-declared bound to honour.

### An Admin button that could only produce a 422

`POST /api/v1/project-brain/analyze` was returning 422 on every click. The
route was right to refuse: no Project Analyst profile is ready on this runtime
(all report `cli_not_installed`), so the profile selector renders empty and
the page posted `{"profile": ""}`.

The defect was the surface. The button stayed enabled with nothing to select,
and the operator got a bare validation error instead of the reason the status
line beside it already displayed. The button is now disabled while no profile
is ready, and clicking with an empty selection reports the blocking reason
rather than sending a request that cannot succeed.

### Verification

```text
pytest -q                                478 passed,  63 skipped   (SQLite)
pytest -q (DATABASE_BACKEND=postgresql)  532 passed,   9 skipped   (PostgreSQL)
frontend vitest                          135 passed
mypy, ruff check, ruff format            clean
```

## UPGRADE-045 — A local profile for the project brain, and GPU as a requirement

Two requests, one root: the project brain had never been connected to Ollama,
and the AI services were only optionally on the GPU.

### The brain was not "disconnected from Ollama" — it never had a local profile

`project_analyst/profiles.py` knew three providers, all CLI-shaped: a pinned
binary, a version range, and a mounted vendor credential. On this runtime all
three report `cli_not_installed`, so the Admin selector was empty and the
analysis was unreachable. There was no Ollama profile to be disconnected from.

A local model is the one provider that can be ready without reaching outside
the appliance, which is what Local-First is supposed to mean, so it is now a
first-class profile rather than a fallback the CLI profiles degrade into:

```text
codex    ready=False  reason='cli_not_installed'
claude   ready=False  reason='cli_not_installed'
grok     ready=False  reason='cli_not_installed'
ollama   ready=True   version='qwen3.5:4b 0.32.5'
```

Readiness is "the host answers and carries the model", not "a credential is
mounted" — there is nothing to mount. The reason code names the missing model
(`local_llm_model_missing:qwen3.5:4b`) because `local_llm_model_missing` alone
leaves an operator guessing which one to pull.

Everything else the sidecar guarantees is unchanged, and the local provider
gets no more trust than a vendor CLI: the response must be the common result
shape, every cited path must have been in the snapshot, an unready profile is
refused rather than substituted, and a refusal never describes the host. A
real end-to-end run against the running Ollama:

```text
POST /analyze {profile: ollama}   2.1s
  [warning] Debug mode enabled in production-like configuration
  [warning] Security enforcement disabled
  evidence: UI_API/backend/config.py
```

The sidecar reaches Ollama by compose service name, so it still has no route
to anything outside the appliance. It gained no volume, no database and no
credential. Twelve checks in `tests/test_project_analyst_sidecar.py`, which is
44 passing.

`format: json` and a token budget are not incidental. `_findings_from` refuses
anything that is not the common result, and a small local model asked for free
text reliably wraps its JSON in prose; without a budget it loops on its own
output. Both are asserted, not assumed.

### GPU is now required, not preferred

`compose.ai-gpu.yaml` was an optional overlay. It is deleted; `gpus: all` and
`R1_OMNI_DEVICE: cuda` live in `compose.ai.yaml`, and every command that named
the overlay has been updated. `setup.sh --cpu` now refuses instead of quietly
producing a GPU stack under a CPU flag.

The important half is the healthcheck. Ollama does not fail when its GPU
disappears — it reports the CUDA device it saw at boot and falls back to CPU
inside llama-server, which is exactly the incident above. The healthcheck now
asserts device access on every interval:

```text
test: nvidia-smi -L >/dev/null 2>&1 && ollama list >/dev/null 2>&1

with the GPU (the running container)   exit 0
without it (same image, no device)     exit 127
```

`ollama list` says the daemon answers; `nvidia-smi` says the container can
still reach the GPU it was granted. Device access can be revoked from a
running container after a driver update or a `systemctl daemon-reload`, and
nothing else in the stack reports it.

### Verification

```text
pytest -q                                487 passed,  63 skipped   (SQLite)
pytest -q (DATABASE_BACKEND=postgresql)  541 passed,   9 skipped   (PostgreSQL)
mypy, ruff check, ruff format            clean
six services                             healthy
```
