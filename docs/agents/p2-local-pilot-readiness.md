# P2 Local Pilot Readiness

## Status

`READY_FOR_HUMAN` — not declared. The Docker artifact and all repository-verifiable admission checks below are recorded; target Kiosk admission and physical AV acceptance remain external gates.

This evidence is for commit `f5967a6` and was collected on 2026-08-11. Any later application, image, migration, or external-configuration change makes this record `EVIDENCE_STALE`.

## Candidate artifact

| Item | Evidence |
| --- | --- |
| app and worker image | `project-2026:ai`, `sha256:064453313b190b4314e653d6cd45d5b8cbb4771dedb67ca9afaa2963f134c49c` |
| R1-Omni image | `project-2026-r1-omni:gpu`, `sha256:0cfd93d4549aee379e7c7c687dc3c92167b3b0c0a834811d0f2cc618eee9fe4f` |
| Ollama image | `ollama/ollama@sha256:4dea9fb511947e24a84237bb636b0203abcb2ff0d3fbc7b4ff865deb91362131` |
| PostgreSQL image | `postgres:18.4-bookworm`, `sha256:1961f96e6029a02c3812d7cb329a3b03a3ac2bb067058dec17b0f5596aca9296` |
| external compose fingerprint | `11a7b823d5c5477120c620d60a95ebb69eeef914dbd09389526a2728343a8de7` |
| migration head | `0027_remove_pre_pilot_rag_history` |
| migration state | 27 applied, 0 pending, checksums valid |

The application and worker were started through `docker/compose.yaml` plus the AI and GPU overrides. The Ollama tag was resolved to the digest above for this run. Existing PostgreSQL data and volumes were retained.

## Passed checks

- Docker Compose app, worker, PostgreSQL, Ollama, and R1-Omni were healthy.
- `/ready` reported database, migration, and commercial-scope checks valid; AI warm-up reached STT, RAG, and Voice LLM ready with no degraded optional dependency.
- R1-Omni profile reported ready with CUDA and audio/video-audio capability.
- Edge TTS synthesis returned 11,376 bytes for a Traditional Chinese probe.
- Docker Compose backend matrix: 131 passed, 2 dependency warnings.
- Dockerized Playwright against the running Compose stack: 5 passed, including Kiosk reachability and recommendation failure/placeholder behavior.
- PostgreSQL custom-format backup was restored into an explicitly named temporary database and verified at 27 migration rows; the temporary database and exact temporary dump path were removed afterward.
- App/worker restart followed by readiness check passed.
- P2 legacy source/bundle checks found no old guest bypass copy, passive keyword recorder, or passive-recorder settings in supported surfaces. The exact emotion purge target is recorded in [`p2-emotion-legacy-purge-manifest.md`](p2-emotion-legacy-purge-manifest.md).
- The passive keyword recorder file was deleted in PR #42 and has a Docker negative test.

## Not yet admissible

The following cannot be proven by this repository and host alone:

1. Admission of the target Kiosk device, including its actual microphone, camera, browser permissions, AudioWorklet, bundled Silero VAD v5, 250 ms speech / 1.2 s silence behavior, 30-second cap, echo cooldown, and noisy-store acceptance.
2. Physical-device touch ordering, voice ordering, checkout outcome-unknown recovery, and payment-pending handoff on the target Kiosk.
3. Live Admin AV Test and voice-aligned audiovisual Emotion evidence on the target camera/microphone. Host `/dev/video*`, `/dev/snd`, and an available NVIDIA GPU are not evidence for the target device.

These are `ready-for-human` gates, not failures converted to pass. No P3 work may start until Local Pilot Admission is declared for this same artifact.

## Recovery and security notes

- No PostgreSQL volume, backup, secret, customer record, or authoritative business data was deleted.
- The temporary restore database and dump had exact names and were removed after verification.
- The app and worker run as the non-root `project2026` user. Their root filesystem is not read-only and no capability drop is currently configured; this is a remaining pilot security hardening item, not a passed claim. It is tracked as a corrective issue in [#44](https://github.com/s0966066980/Project_2026/issues/44), which is a precondition of [#20](https://github.com/s0966066980/Project_2026/issues/20). Landing #44 changes the runtime contract and the images, so this whole record becomes `EVIDENCE_STALE` at that point and the admission below must be re-run against the new digest-pinned candidate.
- The host-only Playwright browser smoke test is supplementary; it does not replace target-device AV evidence.
