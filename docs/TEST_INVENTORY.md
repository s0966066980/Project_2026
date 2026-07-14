# Test Inventory

- Backend test files: **72**
- Backend test functions: **352**
- Frontend test files: **4**
- Frontend test cases (approx): **12**
- TDD evidence docs: **28**

## Classification (backend functions)

| Class | Count |
| --- | ---: |
| KEEP_CORE | 238 |
| KEEP_INTEGRATION | 70 |
| MOVE_EXTENDED | 33 |
| REMOVE_REDUNDANT | 11 |

## Estimated tier

| Tier | Count |
| --- | ---: |
| 1 | 37 |
| 2 | 201 |
| 3 | 70 |
| 4 | 44 |

Duplicate test names: 1
Similar-body groups (body ≥5 lines): 0
Docker references scanned: 41
Deploy artifacts: 7

## Notes

- Classifications are inventory heuristics for L0; L4 performs actual removal/merge with TEST_REMOVAL_LOG.
- KEEP_CORE / KEEP_INTEGRATION are protected from blind deletion.
- Docker is inventoried for L1 relocation/archive; not required for local runtime.

