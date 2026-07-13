# Pilot Release Checklist — NOT Production Certified

This checklist is a pilot release gate and is **NOT Production Certified** evidence.

- [ ] Change/ADR/TDD evidence reviewed; release SHA and rollback owner recorded.
- [ ] Python 3.10/3.12 backend, PostgreSQL integration, frontend and shell CI PASS.
- [ ] PostgreSQL backup exists; restore was recently exercised in isolation.
- [ ] `migration validate --require-clean`, scope validator and Member identity verifier PASS.
- [ ] `/live` is live and `/ready` is ready on the candidate deployment.
- [ ] Default tenant/store/device are active and owned correctly.
- [ ] Checkout server pricing, duplicate key replay, conflict, rollback and outbox smoke PASS.
- [ ] Admin/device auth, legacy token flags, CORS/TLS and rate limit evidence reviewed.
- [ ] Log redaction, retention, disk capacity, alerts and incident contacts verified.
- [ ] AI degraded exercise confirms basic checkout readiness remains available.
- [ ] Known limitations, legal/privacy approval and go/no-go decision recorded.
