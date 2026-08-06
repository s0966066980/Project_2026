# Create project analysis snapshots only on explicit request

Status: accepted

The Project Core Brain scans its allowed evidence only when an administrator explicitly selects 「分析目前專案」 or 「重新分析」. Each run creates an immutable Project Analysis Snapshot containing its observation time, evidence revision, healthy, warning, and blocked findings, and a source reference for every claim.

Follow-up questions are answered only from the selected snapshot. Repository or runtime changes never silently mutate an existing snapshot; the administrator must explicitly create a replacement. The first release performs no background scan, schedule, continuous monitoring, or implicit test execution.
