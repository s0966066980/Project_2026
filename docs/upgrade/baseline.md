# Upgrade Baseline

The frozen starting point for the Commercial V1 upgrade. Every later item is
measured against this, so that each change can answer whether it improved the
system without breaking the last verified state.

```text
BASELINE_COMMIT = c3592c1cad05a990b95aad795036b8bb0b0bd5a9
BRANCH          = main   (single-branch exception, see README.md)
DATE            = 2026-08-12
WORKING TREE    = clean
```

## Environment

| Component | Version |
| --- | --- |
| OS | Ubuntu 24.04.4 LTS, kernel 7.0.0-28-generic |
| CPU / RAM | 20 cores / 30 GB |
| GPU | NVIDIA GeForce RTX 4090, 24564 MiB |
| Python (test image) | 3.10.20 |
| Node | v24.18.1 |
| Docker Engine | 29.1.3 |
| Docker Compose | 2.40.3 |
| PostgreSQL (runtime) | 18.4-bookworm |
| PostgreSQL (CI migration job) | 16 |

The two PostgreSQL versions are a real gap, not a typo: the migration job in CI
proves migrations against a major version the product does not run on. It is
recorded here rather than fixed silently, because changing it belongs to item
15 (migration hardening).

## Baseline test results

All commands run against `c3592c1`.

| Gate | Command | Result |
| --- | --- | --- |
| Backend suite | `docker compose --profile test run --rm --no-deps test` | **356 passed** |
| Lint | `ruff check .` over the whole tree | **clean** |
| Format | `ruff format --check .` over the whole tree | **clean** |
| Types | `mypy` over its declared scope | **0 errors, 63 files** |
| Frontend syntax | `npm run syntax` | **pass** |
| Frontend types | `npm run typecheck` | **pass** |
| Frontend unit | `npm test` | **130 passed** |
| Frontend build | `npm run build` | **pass** |
| Docker core smoke | `bash docker/scripts/test.sh` | **Docker smoke test passed** |

Live stack at baseline: app, worker, postgres, ollama, r1-omni and
project-analyst all healthy; `/ready` true; R1-Omni reports `model_loaded` on
cuda with both audio_only and video_audio capabilities.

## Known gaps carried into the upgrade

These are true at baseline and are not regressions introduced by later items.

- **Markers are decorative.** Fourteen pytest markers are declared in
  `pyproject.toml`; no test uses any of them. Marker-based selection collects
  nothing. This is item 01.
- **No guard on the unversioned surface.** The compatibility `/api/*` paths were
  withdrawn earlier the same day, but no test fails if one returns. This is
  item 1.3.
- **Contract check covers one capability.** Only the catalog contract is
  compared against the published schema.
- **`UI_API/deploy/postgres/`** is unreferenced but deliberately left in place:
  removing it is scoped to P5.1 Issue #31 in the execution plan, and taking it
  early would consume part of a tracked work package.

## Known degraded or deferred providers

- Codex / Claude / Grok CLI: deferred by owner; the Project Analyst runs
  local-only.
- NVIDIA NIM cloud text provider: configured path exists, no credentials.
- Target Kiosk hardware, microphone, camera: unavailable. Every hardware item
  in the roadmap is blocked on this and may not be substituted with results
  from this workstation.
