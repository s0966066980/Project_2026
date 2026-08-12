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
