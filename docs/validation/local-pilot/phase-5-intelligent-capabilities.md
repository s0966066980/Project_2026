# Phase 5 — Intelligent Capability Evidence

- Evidence date: 2026-07-28 (Asia/Taipei)
- Status: **5A passed, 5B passed, 5C functional contract passed / quality gate pending**
- Revision: `723f87c` on `main`
- Worktree: dirty; evidence applies to the tested working tree
- Runtime profile: `local-pilot`
- Database fingerprint: `e2343247250475d8`
- Migration head: `0022_checkout_pickup_number`

No raw audio, video, transcript, knowledge text, credential, or member data is
stored in this evidence record.

## 5A — RAG Readiness: passed

The Store Knowledge Base publication module owns store-scoped PostgreSQL records
for the Knowledge Version lifecycle, Publication Batch item results, phase-aware
resume, atomic swap, audit, and cleanup. Retrieval Configuration and Retrieval
Check remain separate modules with their own rules.

The live Admin RAG Studio currently reports:

- readiness: **4/4**;
- Published knowledge: present;
- Published Retrieval Configuration: version 1;
- index: healthy, identity `37a3bd1b20beea63e20342efc179fff9844f83f8d584ee595d5707e64827ce36`;
- method/effective method: `hybrid_reranker` / `hybrid_reranker`;
- current confirmation: `arc_1e1d208ee7b546c680da681b1176a7e9`;
- result count: 1;
- fallback: none.

An observed failure was fixed in the retrieval policy: a primary method that
returned candidates but lost every row after relevance filtering incorrectly
stopped instead of trying its configured fallback. The balanced reranker cutoff
was also calibrated from 0.35 to 0.30 so the relevant store answer scoring
0.323735 is not discarded. Two regression tests preserve both behaviors.

Focused RAG/publication verification finished with **36 passed**. Changes to the
Published index identity or Retrieval Configuration invalidate the confirmation.

## 5B — Voice Turn readiness: passed

Three runtime defects were found through the real PostgreSQL path and fixed:

1. `voice_turn_events.terminal` received a SQLite-style integer instead of a
   database-portable boolean.
2. The HTTP stream waited for the complete TTS terminal path before replaying
   durable events, so validated assistant text was not progressive.
3. The assistant inherited the global 220-token limit and could emit an unbounded
   list of menu IDs, producing long latency outliers.
4. Durable effects called asynchronous emotion scheduling from a worker thread
   without a running event loop, leaving an un-awaited coroutine warning and
   losing that optional observation.

The route now polls and streams durable events while execution continues, keeps
accepted work alive after a subscriber disconnects, and lets replay return the
single durable terminal outcome. The production assistant uses a 96-token task
limit, a concise answer contract, and at most five transcript/answer-grounded menu
IDs. Emotion scheduling now supports both an existing event loop and the durable
worker-thread path, with temporary-media cleanup on every exit. Tests verify
PostgreSQL-safe booleans, progressive text before TTS completion, bounded
order-draft output, and warning-free worker-thread scheduling.

The repeatable validator uses a real device session, real upload/STT,
`qwen3.5:4b`, TTS, and the PostgreSQL durable store. After warm-up, thirty fixed
turns (15 conversational and 15 ordering) produced:

| Metric | Observed |
| --- | ---: |
| Minimum | 1857.32 ms |
| Median | 2130.59 ms |
| P95 | **2428.17 ms** |
| Maximum | 2693.31 ms |

All 30 turns had exactly `accepted → transcribing → transcript → assistant_result
→ completed`, monotonic sequences, one terminal event, and available playback.
The P95 is below the 3000 ms gate. The first diagnostic run had exposed the real
performance problem (P95 9304.04 ms), so it is retained here as failure-to-fix
evidence rather than omitted.

Focused Voice module/runtime/stream verification finished with **14 passed**. A
post-restart two-turn real smoke run also preserved the exact protocol, available
playback, and a P95 of 2375.81 ms without the coroutine warning.

## 5C — Emotion diagnostic readiness: quality gate pending

The selected provider is `r1_omni`. Live health and the authenticated Admin
capability endpoint report:

- provider status: ready;
- model loaded: true;
- capabilities: `audio_only`, `video_audio`;
- capture: `single_adaptive`, up to 8 seconds;
- live STT and emotion inference use the same captured media;
- text simulation: neutral TTS followed by provider `audio_only` inference;
- live diagnostic: provider `video_audio` inference;
- provider failures disable the affected diagnostic and do not select a fallback.

The authoritative provider classification is separate from the downstream LLM
explanation. The explanation receives structured provider output, not raw media
or transcript, and cannot replace the classification. Temporary raw media and
transcript content are discarded after inference; only the bounded diagnostic
record remains. Backend emotion verification finished with **14 passed**, the
Admin emotion Playwright scenario passed, and both provider server files pass
Python compilation.

The required, versioned 60-sample acceptance corpus is not present in the
repository or the protected runtime data root. Consequently no honest per-mode
macro-F1, per-label recall, or explanation-change measurement can be reported.
The implementation/output contract is complete, but Phase 5C remains a release
gate until the designated evaluator supplies and labels 30 audio-only plus 30
live-media samples and records the required metrics.

## Gate conclusion

RAG and Voice are ready for the local pilot. Emotion diagnostics are operational,
but the quantitative quality gate is deliberately not marked passed without its
real labelled acceptance set.
