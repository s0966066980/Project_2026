# TDD — Milestones 6B–6D Control Plane Durable Persistence

## RED

1. Migration 0011 defines strategy/assignment/event, fleet, and analytics tables.
2. Experiment assignment remains stable when variant order changes.
3. Fleet commands remain allowlisted.
4. Analytics rejects nested forbidden keys and is idempotent on event_id.

## GREEN

- `tests/test_control_plane_durable.py`
- Service dual-path hooks for assignment, heartbeat, analytics sink

## Classification

PRODUCTION_PATH_PASS (internal durable contracts). PostgreSQL apply retained in CI when DATABASE_URL available.
