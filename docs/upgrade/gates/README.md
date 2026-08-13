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

Transactional confirmation atomicity and restart during confirmation remain;
the full touch and voice E2E also needs the target Kiosk. Checkout outbox
retry/dead-letter evidence is recorded in UPGRADE-022, and cart revision
conflicts under PostgreSQL concurrency are recorded in UPGRADE-023. The gate is
not passed.

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

Consent version and retention, history-consent behaviour, PostgreSQL
migration/backfill/integrity/concurrency, and the Admin/Kiosk consumer ledger.
The gate is not passed.

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

Push copy resolution and the notification surface; content edits under
concurrent publication (the version conflict is proven, the publish race is
not); the Admin and Kiosk generated-client consumer ledger. The gate is not
passed.

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

Ingestion and duplicate-document handling at the store level, index rebuild
and retirement cleanup, governance and the malicious-document path, and
end-to-end retrieval against a real index on the target hardware. The gate is
not passed.

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

Interaction and intervention pipelines, experiment assignment, the
effectiveness report against real touch data in PostgreSQL, and the Kiosk
consumer ledger. The gate is not passed.

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
