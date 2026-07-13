# Milestone 0.5 Commercial Foundation Stabilization — TDD Evidence

## Source and User Journeys

Source plan：本次工作直接來自 Milestone 0.5 任務說明，沒有外部 `*.plan.md`。

- Repository maintainer 需要 foundation regression test 對應目前有效文件，避免文件重整後基線失效。
- Reviewer 需要不存在的第一方 Markdown local link 被測試阻擋。
- Maintainer 需要 Python 3.10/3.12 CI 相容性清楚，且 static checks 不重複執行。
- Data owner 需要 ADR-0004 決策歷史保留，同時明確標示實作延後。
- Roadmap reader 需要區分既有 migration framework 與下一階段 PostgreSQL integration 工作。

## RED / GREEN Evidence

- RED：`.venv/bin/pytest -q tests/test_commercial_foundation.py tests/test_documentation_integrity.py`
  - 結果：5 failed, 5 passed。
  - 預期失敗：ADR-0004 缺失、CI matrix 缺失、Roadmap 敘述未更新、broken local link 未被回報。
  - Checkpoint：`7fa9a51 test: add milestone 0.5 foundation regressions`。
- GREEN：相同目標測試完成後為 11 passed。
  - Checkpoint：`42c4048 fix: stabilize milestone 0.5 commercial foundation`。
- 完整回歸：`MEMBER_STORAGE_BACKEND=json DATABASE_URL= .venv/bin/pytest -q tests`
  - 結果：161 passed, 1 third-party deprecation warning。

## Test Specification

| # | 保證 | 測試或命令 | 類型 | 結果 |
| --- | --- | --- | --- | --- |
| 1 | Foundation test 只要求目前有效的一方文件與 lockfile | `test_commercial_foundation_documents_exist` | Regression | PASS |
| 2 | ADR-0004 保留 Accepted 決策並標示 Deferred | `test_member_identity_adr_preserves_the_accepted_deferred_decision` | Regression | PASS |
| 3 | Python 3.10/3.12 都執行 import 與 pytest，static checks 只在 3.10 執行 | `test_backend_ci_covers_supported_python_versions_without_duplicate_static_checks` | Regression | PASS |
| 4 | Roadmap 將 migration framework 描述為既有能力的完成與強化 | `test_roadmap_describes_hardening_the_existing_migration_framework` | Regression | PASS |
| 5 | 指定第一方 Markdown 的有效 local links 通過 | `test_first_party_documentation_links_are_valid` | Integration | PASS |
| 6 | 不存在的相對 Markdown link（含 anchor）會被回報 | `test_nonexistent_local_markdown_link_is_reported` | Unit | PASS |
| 7 | HTTP/HTTPS、mailto、純 anchor 與存在檔案的 fragment link 正確處理 | `test_external_anchor_and_existing_fragment_links_are_ignored` | Unit | PASS |

## Coverage and Known Gaps

- Coverage：NOT RUN。此次沒有修改 production application code；驗證以新增 regression tests、完整 pytest、Ruff、mypy、Frontend 與 Shell checks 為準。
- Python 3.10/3.12 雙版本執行由 GitHub Actions matrix 驗證；本機虛擬環境是 Python 3.12。
- PostgreSQL integration CI、migration status/validate/lock 與 backup/recovery 強化保留給 Milestone 1A。
