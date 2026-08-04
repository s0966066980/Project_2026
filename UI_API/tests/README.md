# Backend contract tests

These tests exercise the supported public seams: the R1-Omni evidence gateway, typed settings,
checkout application module, and diagnostic route registration. Provider calls are replaced only
at the adapter boundary; checkout and settings tests do not inspect implementation details.

Run locally with `pytest -q tests` from `UI_API`. Integration suites for Postgres, Redis, and
object storage belong in a separately provisioned environment and are not silently replaced by
in-memory fakes.
