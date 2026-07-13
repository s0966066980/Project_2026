# Architecture Decision Records

ADR 用來保存長期、跨模組且難以回復的架構決策。ADR 是決策歷史，不是待辦清單。

## 索引

| 編號 | 決策 | 狀態 | 日期 |
| --- | --- | --- | --- |
| [0001](0001-modular-monolith-first.md) | Modular Monolith First | Accepted | 2026-07-13 |
| [0002](0002-independent-frontend-deployment-boundaries.md) | Kiosk 與 Admin 為獨立前端部署邊界 | Accepted | 2026-07-13 |
| [0003](0003-ai-provider-port-adapter.md) | AI Provider 使用 Port / Adapter | Accepted | 2026-07-13 |

## 狀態

- `Proposed`：提案中，尚未成為約束。
- `Accepted`：目前有效。
- `Superseded`：已被新 ADR 取代，保留歷史。
- `Deprecated`：不再建議，但可能仍存在相容路徑。
- `Rejected`：已評估但未採用。

## 新增規則

1. 使用四位數遞增編號：`0004-short-title.md`。
2. 一份 ADR 只回答一個核心決策。
3. 至少包含：Context、Decision、Consequences、Alternatives。
4. Accepted ADR 不直接重寫決策；需要改變時新增 ADR，並將舊 ADR 標為 `Superseded by ADR-xxxx`。
5. 一般 refactor、rename、依賴升級與小型 UI 調整不需要 ADR。

## Template

```markdown
# ADR-000X：決策標題

- 狀態：Proposed
- 日期：YYYY-MM-DD
- Owner：模組或角色

## Context

問題、限制與需要決策的原因。

## Decision

採用的方案與適用範圍。

## Consequences

正面影響、代價、風險與後續責任。

## Alternatives

評估但未採用的方案與原因。
```
