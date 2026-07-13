# Milestone 2F — Deployment / Operations Hardening TDD Evidence

## Source

`CODEX_AUTONOMOUS_ROADMAP.txt` Milestone 2F.

## Initial RED

`pytest -q tests/test_deployment_operations.py` fails until deployment docs, Dockerfiles, env templates, pre/post deploy scripts and commercial fail-fast for staging/pilot exist.

## GREEN

Contract tests cover process/image boundaries (no GPU trees in API/Worker images), environment separation, production/staging/pilot fail-fast, restore drill template fields and release scripts.

Local verification:

- `pytest -q tests/test_deployment_operations.py` — **PASS (8)**
- Full JSON backend — **PASS (286)**
- Shell `bash -n` on pre/post deploy and restore drill scripts — **PASS**
- Restore drill dry-run record written under `docs/operations/restore-drills/`
- Staging-like compose image build — **NOT RUN locally** (Docker unavailable)
