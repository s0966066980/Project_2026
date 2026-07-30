# Local Pilot Follow-up Workflow

This workflow moves Project_2026 from the accepted 60% baseline to **Local Pilot Readiness** on one local host. It is intentionally phase-gated: a phase may contain parallel implementation work, but the next phase cannot be declared complete until the current phase has satisfied its exit gate and recorded its evidence.

The target is the Local Single-Host PostgreSQL Runtime. Real Payment/POS automation, three-VM PostgreSQL high availability, multi-availability-zone failover, and off-host disaster recovery remain outside this workflow. Manual Payment/POS is acceptable only when the UI and records preserve `Payment Pending` instead of implying payment or POS completion.

## Operating rules

1. Every phase has entry conditions, scoped work, automated evidence, manual evidence, and an exit gate.
2. Code existence, an HTTP `200`, or a passing unit test alone is not completion. Full credit requires implementation, automated verification, and the required real-machine validation.
3. Each phase writes an evidence record beneath `docs/validation/local-pilot/` when execution begins. Evidence must identify the revision and runtime dependencies without recording secrets, raw customer media, or unnecessary personal data.
4. A failure may be deferred only when it is assigned to a named later phase. An unclassified failure blocks the current gate.
5. A dependency change invalidates the affected phase and its downstream evidence. Unrelated evidence remains valid.
6. Phase 7 may accept a P2 defect only with documented impact, mitigation, owner, and due date. P0, P1, and unclassified defects block Local Pilot Readiness.

## Evidence record

Each phase record contains:

- phase and gate status;
- Git revision and dirty-worktree disclosure;
- sanitized Runtime Persistence Profile and configuration fingerprint;
- database endpoint fingerprint, PostgreSQL major version, and migration head;
- emotion, voice, STT, TTS, LLM, embedding, and reranker provider/model versions when relevant;
- commands and summarized automated results;
- numbered real-machine scenarios with expected and observed outcomes;
- unresolved defects, severity, mitigation, owner, and due date;
- validator and approver identities and timestamps.

An evidence record never contains database credentials, API tokens, raw customer audio/video, full transcripts, or unredacted member data.

## Phase 1 — Establish a reproducible runtime baseline

### Entry

- The repository is available on the intended local-pilot host.
- The supported Conda `emotion_ui` Python runtime and frontend dependencies are installed.

### Work

- Remove legacy database selectors, especially `MEMBER_STORAGE_BACKEND`, from shell, Playwright, pytest, startup, and maintenance paths.
- Make UI_API, the reliable worker, maintenance commands, pytest, and Playwright load the same Runtime Persistence Profile and credential-source rules.
- Ensure credential files or injected values are discoverable by supported commands without placing secrets in the repository or evidence record.
- Keep the local PostgreSQL endpoint loopback-only and preserve the existing separated Runtime Data Root directories.
- Produce one complete failure inventory after every backend and frontend test command can run to completion.

### Required evidence

- The local-pilot environment validator passes without configuration failures.
- Runtime persistence status proves PostgreSQL 18 connection, primary role, complete adapter coverage, migration head, and a successful rollback-only write probe.
- UI_API and worker start from the supported scripts; `/live` and `/ready` pass.
- The selected emotion provider identifies itself, reports its model loaded, and declares the capability required by the requested test. Port reachability alone is not sufficient.
- Pytest, Vitest, TypeScript, syntax, build, and Playwright commands all start and reach a result rather than aborting because of environment drift.

### Exit gate

All runtime and test entry points are reproducible under the same profile rules. Remaining failures are listed and assigned to Phases 2–6; no environment-origin failure is unclassified.

## Phase 2 — Converge identity, authorization, and API contracts

### Entry

- Phase 1 evidence is current.
- The full backend failure inventory is available.

### Work

- Require a password-authenticated manager session and RBAC authorization for every Admin API, including local-pilot deployments.
- Make tests authenticate explicitly instead of relying on an anonymous local bypass.
- Keep the accepted RAG permission vocabulary: `rag.read`, `rag.write`, and `rag.publish`.
- Delete remaining `rag.review` permission and route references. Map retained operations to their actual read, draft-management, or publication responsibility; do not introduce an alias.
- Align v1 envelopes, legacy compatibility assertions that remain supported, member administration, and security expectations with the same authentication policy.

### Required evidence

- Anonymous Admin requests are denied consistently.
- Authenticated principals receive only the operations granted by the central permission catalog.
- Identity, RBAC, v1 contract, member administration, and security suites have zero failures.
- A full backend run has no unknown failure; non-Phase-2 failures are assigned to a later phase.

### Exit gate

The central permission catalog, route policy, API contract, and tests express one Admin authentication model. No superseded RAG review capability remains reachable or documented as active.

## Phase 3 — Converge frontend and API type contracts

### Entry

- Phase 2 identity and API evidence is current.
- The E2E process can start with the Phase 1 runtime profile.

### Work

- Correct the data shapes and event protocols in RAG Admin, Voice Turn, the shared API client, and related tests.
- Add precise TypeScript/JSDoc types for JavaScript modules; do not weaken strictness or suppress contract errors to make the command green.
- Consolidate shared API calls and authentication fixtures without coupling Kiosk business state to Admin business state.
- Establish a reliable Playwright server lifecycle and an authenticated Admin login smoke path.

### Required evidence

- TypeScript typecheck, JavaScript syntax checks, all frontend unit tests, and the production build pass.
- Playwright starts reliably and the Kiosk boot plus Admin login/navigation smoke scenarios pass.
- Domain E2E scenarios are assigned to Phase 4 or the appropriate Phase 5 sub-gate rather than silently skipped.

### Exit gate

Frontend compilation, type contracts, test infrastructure, and shared transport contracts are green without lowering validation standards.

## Phase 4 — Close the core transaction loop

### Entry

- Phases 1–3 are current.
- Menu, store availability, member, Cart, Checkout Confirmation, worker, and outbox dependencies are available on the pilot host.

### Work and scenarios

Validate both guest and member paths from `Ordering Entry Flow` through Menu Ready, server-authoritative Cart, Checkout Quote, Order Confirmation, Payment Pending, and outbox dispatch.

The gate includes at least these recovery scenarios:

- Member Found, Member Not Found, and Member Login Service Failure remain distinct.
- Registration failure preserves input and consent choices; guest fallback is explicit.
- Menu Initialization Failure retries without a page reload and preserves valid entry state.
- Cart and Checkout Quote values are server-authored.
- stale and expired Quotes are rejected safely;
- unavailable fulfillment items create no partial Order;
- Confirmation Outcome Unknown reuses the same Quote and idempotency key;
- repeated confirmation returns the existing Order and never creates a duplicate;
- manual payment remains Payment Pending until an explicit result exists.

### Required evidence

- Module, integration, route, and browser scenarios cover the success and recovery paths.
- A human operator completes both guest and member orders on the target host and verifies the resulting Admin/order state.
- Order, immutable pricing lines, Confirmation Attempt, session closure, and outbox records agree.

### Exit gate

Both entry paths complete without client-authored commercial values, duplicate orders, hidden uncertainty, or false payment success. Every required recovery path has automated and real-machine evidence.

## Phase 5 — Close intelligent-capability loops

Phase 5 has three ordered sub-gates. Completing one sub-gate does not permit the later sub-gates to borrow its evidence.

### Phase 5A — RAG Readiness

#### Work and evidence

- Author store-scoped Knowledge Items as Drafts.
- Publish through the durable Draft → Indexing → Published lifecycle and prove the reliable worker sees the same durable job.
- Exercise phase-aware resume for a missing or interrupted publication job without creating a new version or rolling back successful work.
- Publish one Retrieval Configuration.
- Run an eligible Ad Hoc Retrieval Check against the Published index without fallback and confirm the immutable result as RAG Readiness evidence.
- Verify that changing the Published index or configuration invalidates the confirmation.
- Verify the Admin workflow explains blocked and empty-result states and offers the correct recovery action.

#### Exit gate

The store has Published knowledge, a Published Retrieval Configuration, a healthy index, and a current RAG Readiness Confirmation. Evaluation Readiness and its twenty-case benchmark remain a later quality improvement, not a local-pilot blocker.

### Phase 5B — Voice Turn readiness

#### Work and evidence

- Validate one stable `voice_turn_id`, adaptive capture, automatic submission after silence, cancellation, no-speech, reconnect/replay, and exactly one visible terminal outcome.
- Prove progressive validated text appears independently of TTS completion.
- Prove a Voice Order Draft never mutates the Cart until the customer explicitly confirms selected items.
- Validate microphone-only Voice Media Degradation, transcription failure, assistant failure, and Voice Playback Degradation.
- Prove asynchronous Voice Emotion Observation never delays or changes its originating Voice Turn.
- After Voice Model Warm State is established, measure thirty fixed Voice Turns on the pilot host, split evenly between short conversational and ordering utterances. Voice Response Wait P95 must be at most three seconds.

#### Exit gate

All lifecycle and degradation scenarios pass, no duplicate assistant or draft execution occurs, and the recorded thirty-turn performance sample meets the P95 target.

### Phase 5C — Emotion diagnostic readiness

#### Work and evidence

- Select exactly one provider through the Emotion Runtime Profile. A readiness or inference failure disables the affected diagnostic with a reason and never selects another provider.
- Replace direct generic-LLM text classification with Text-to-Speech Emotion Simulation: fixed neutral TTS produces audio, and the selected provider analyzes that audio through a validated audio-only contract.
- Implement Live Admin Emotion Test as one adaptive capture. With speech, STT uses audio from that same capture; STT failure records `transcript_unavailable` and never accepts replacement text.
- Keep Emotion Model Observation separate from Emotion Observation Explanation. The downstream LLM receives only the authoritative classification and provider-authored analysis, cannot inspect raw media/transcript, and cannot change the classification.
- Retain only the bounded Admin Emotion Diagnostic Record; discard temporary raw media and transcript content after inference.
- Normalize authoritative classification to Neutral, Happy, Frustrated, Anxious, Confused, or Angry. An unclassifiable result is explicit rather than guessed.
- Run the versioned sixty-sample Emotion Diagnostic Acceptance Set: five samples per label in audio-only mode and five per label in live-media mode. Audio-only samples include semantic/prosody controlled pairs.

#### Exit gate

For audio-only and live-media modes independently:

- capability identity and output contracts pass 100%;
- macro-F1 is at least 0.70;
- each label's recall is at least 0.50;
- Emotion Observation Explanation changes the provider classification zero times.

Both Admin diagnostics must be usable. A blank-video audio wrapper, direct LLM classification, or disabled audio-only function does not satisfy this gate.

## Phase 6 — Prove local operational recovery

### Entry

- Phases 1–5 are current.
- A safe isolated restore target and explicit backup destination are available.

### Work and scenarios

- Restart UI_API, reliable worker, PostgreSQL, Ollama/LLM, and the selected emotion provider independently and in documented order.
- Interrupt durable publication, Voice Turn, Checkout/outbox, and other resumable jobs at controlled phases; prove restart continues from the last verified successful phase without replaying completed effects.
- Create a PostgreSQL backup and restore it into an isolated validation database. Never overwrite the active database during the test.
- Verify restored migration head, commercial scope, representative member/order/RAG records, constraints, and a rollback-only write probe.
- Run Voice Turn, Knowledge artifact, job/outbox, diagnostic-record, and temporary-artifact retention cleanup using their configured stores and paths.
- Verify health, structured logs, audit records, safe error messages, and data-path permissions before and after recovery.
- Confirm that same-host backups are described as local recovery evidence, not disaster recovery.

### Exit gate

The system survives the required process interruptions, resumes durable work correctly, restores an isolated database successfully, cleans bounded data safely, and retains consistent authoritative records and audit evidence.

## Phase 7 — Sign off Local Pilot Readiness

### Entry

- Every previous phase has a current evidence record.
- The tested revision, configuration fingerprints, database migration head, and model versions match the intended pilot release.

### Work

- Apply the evidence invalidation rules below and rerun every affected gate and downstream gate.
- Run the complete backend, frontend, browser, operational, and real-machine acceptance set.
- Triage every remaining defect. P0/P1 defects must be closed. Each accepted P2 requires impact, mitigation, owner, and due date. Unclassified failures are prohibited.
- Record the final completion score and explicit exclusions for real Payment/POS, HA, and off-host disaster recovery.

### Exit gate

All required gates are current, P0/P1 count is zero, every P2 exception is controlled, and the designated operator accepts the evidence record. Only then may the single-host target be reported as **100% Local Pilot Readiness**.

## Evidence invalidation

Use dependency impact rather than invalidating every phase for every change:

| Changed input | Minimum evidence to reopen |
| --- | --- |
| Runtime profile, credentials source, Python/runtime dependencies, PostgreSQL major/topology, migration head | Phase 1 and every downstream phase |
| Identity, permission catalog, Admin authentication, v1 envelope | Phase 2 and downstream dependent scenarios |
| Shared API client, event protocol, frontend build/type configuration, E2E fixture | Phase 3 and every affected domain scenario |
| Ordering Entry, Member, Cart, pricing, promotion, availability, Checkout Confirmation, Order/outbox | Phase 4 and affected Voice/operations/final gates |
| Published knowledge, index identity, retrieval algorithm, Retrieval Configuration | Phase 5A and Phase 7 |
| STT, voice LLM, TTS, Voice Turn protocol, Voice Order Draft | Phase 5B, affected Phase 5C integrations, Phase 6, and Phase 7 |
| Emotion provider/model, emotion labels, TTS audio contract, live-capture/STT alignment, explanation prompt | Phase 5C, affected Phase 6 scenarios, and Phase 7 |
| Worker delivery, retention, backup/restore, audit, health/readiness | Phase 6 and Phase 7 |
| Documentation or presentation-only change with no runtime or acceptance effect | Review the document; retain unrelated execution evidence |

Every invalidation decision is written into the next evidence record with its changed dependency and affected gates. Manual discretion may widen the retest scope but may not retain evidence whose recorded dependency no longer matches.

## Initial baseline

The accepted starting point on 2026-07-28 is **60% Local Pilot Readiness** under the weighted assessment: Core Transaction 40%, Admin and Data 20%, AI/RAG 25%, and Operational Safety 15%.

Known initial evidence includes a healthy PostgreSQL 18 single-host connection, migration head `0021_rag_readiness_confirmation`, complete registered persistence-adapter coverage, a successful write probe, healthy `/live` and `/ready`, an R1-Omni health response, passing frontend unit tests and production build, and working RAG retrieval after publication recovery.

Known blockers include backend contract/security failures, inconsistent Admin authentication tests, a residual `rag.review` permission reference, TypeScript contract failures, Playwright startup failure caused by the prohibited legacy database selector, absence of a recorded end-to-end real-machine acceptance run, and emotion diagnostics that do not yet implement the accepted provider-first audio/live workflow.
