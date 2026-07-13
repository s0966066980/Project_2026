# Pilot SLO Targets

以下皆為 pilot target，not historical attainment；正式達成率必須由實際 metrics window 計算，不得從測試結果推論。

| SLI | Pilot target | Window | Exclusions |
| --- | --- | --- | --- |
| Checkout confirmed availability | ≥ 99.5% | rolling 7 days | 明確 client validation rejection |
| Checkout server latency p95 | ≤ 2 seconds | rolling 24 hours | payment provider 尚未整合 |
| `/ready` availability | ≥ 99.9% | rolling 24 hours | 已公告 maintenance |
| Authenticated HTTP 5xx rate | < 0.5% | rolling 1 hour | approved fault exercise |
| Outbox oldest pending age | < 5 minutes | rolling 15 minutes | Worker 2E 上線前只觀測 backlog |

Error budget、burn rate 與達成報告只有在 metrics backend、clock、scrape interval 與 traffic eligibility 經驗證後啟用。AI/Emotion degraded 不計入基本 checkout readiness，但需獨立呈現 availability 與 fallback rate。
