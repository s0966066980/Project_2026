# Milestone 1A PostgreSQL Migration Foundation — TDD Evidence

## Source and User Journeys

Source：使用者指定進行 Milestone 1A，驗收範圍由 `docs/FUTURE_MODULES.md` 的 migration foundation 完成條件衍生，沒有外部 `*.plan.md`。

- Maintainer 需要在 apply 前查看 migration status 並驗證 source/database drift。
- Release process 需要 checksum mismatch、來源遺失與版本不連續時阻斷部署。
- 多 instance deployment 需要 migration lock，避免同時套用同一版本。
- CI 需要在 disposable PostgreSQL 驗證首次 apply 與重複 apply 的 idempotency。
- Operations 需要明確 backup、restore 與 roll-forward runbook。
- Security reviewer 需要 migration command 不輸出 `DATABASE_URL` 或 credential。

## RED / GREEN Evidence

- Initial RED：`.venv/bin/pytest -q tests/test_postgres_migration_foundation.py tests/test_commercial_foundation.py`
  - 結果：9 failed, 6 passed。
  - 缺口：migration plan API、checksum/sequence validation、advisory lock、PostgreSQL CI job 與 recovery 文件。
  - Checkpoint：`fb8b515 test: define milestone 1a migration foundation`。
- Initial GREEN：migration/foundation/documentation 目標 tests 18 passed。
  - Checkpoint：`a156a96 feat: establish PostgreSQL migration foundation`。
- Boundary RED：migration source 全部缺失與 invalid status diagnostic 共 2 個預期失敗。
- Boundary GREEN：目標 tests 20 passed。
  - Checkpoint：`13e0810 fix: close migration foundation validation gaps`。
- Security/Coverage GREEN：連線錯誤遮罩、CLI、pending apply 與 clean validation unit tests 通過。
  - Checkpoint：`130da32 test: harden migration coverage and error safety`。

## Test Specification

| # | 保證 | 測試或命令 | 類型 | 結果 |
| --- | --- | --- | --- | --- |
| 1 | Migration 檔名為連續四位版本，缺檔或跳號會失敗 | `test_postgres_migration_foundation.py` | Unit | PASS |
| 2 | Applied、pending、checksum mismatch 與 missing source 可被辨識 | `test_postgres_migration_foundation.py` | Unit | PASS |
| 3 | Apply 前取得 parameterized transaction advisory lock | `test_migration_lock_uses_parameterized_transaction_advisory_lock` | Unit | PASS |
| 4 | 已套用且 checksum 相同的 migration 重複 init 不重新執行 | `test_init_schema_locks_before_validation_and_skips_applied_migration` | Unit | PASS |
| 5 | Pending migration 套用 SQL 並記錄 version/checksum | `test_init_schema_applies_pending_migration` | Unit | PASS |
| 6 | CLI status/validate/apply 回傳 machine-readable plan，錯誤不洩漏 URL | CLI unit tests | Unit | PASS |
| 7 | 新 PostgreSQL 16 DB 可 apply，第二次 apply 無副作用，最後 clean | `tests/postgres_migration_integration.py` | Integration | PASS |
| 8 | CI workflow 包含 disposable PostgreSQL、status/validate/apply gate | `test_ci_runs_postgres_migration_integration_without_external_services` | Regression | PASS |
| 9 | 第一方文件連結與 backup/recovery runbook 完整 | `test_documentation_integrity.py`、foundation tests | Regression | PASS |

## Verification and Coverage

- Migration unit/legacy target：26 passed。
- Disposable PostgreSQL 16 integration：1 passed。
- Full JSON backend suite：178 passed, 1 third-party deprecation warning。
- Coverage：兩個新增/修改 migration modules 合計 93% branch-aware coverage。
- Ruff、Ruff format、mypy、application import、Frontend type/syntax 與 Shell syntax：PASS。
- GitHub-hosted workflow：NOT RUN；本機已使用 unprivileged disposable PostgreSQL 16 重現相同 status → validate → apply twice → clean validate 流程。

## Known Gaps

- Backup/restore scripts 已有 syntax validation 與 runbook，本次未對 production-sized dump 執行 restore drill。
- 現行 runner 使用單一 transaction，不支援 `CREATE INDEX CONCURRENTLY`；需要時先新增 explicit non-transactional migration contract。
- Tenant/Store/Device 與 Member UUID/PII migration 不屬於 Milestone 1A，未開始實作。
