# Retain only the latest project analysis report

Status: accepted

Each project retains only its latest successful structured Project Analysis Snapshot report: observation time, Git revision, selected Project Analyst Profile, healthy, warning, and blocked findings, and evidence references. Sanitized source input, CLI event streams, model reasoning, and follow-up conversation are never persisted; input and raw output are discarded after the report is produced, and conversation remains browser-session state only.

A successful explicit rescan atomically replaces and permanently deletes the previous report. A failed rescan leaves the previous report available but marks it stale and records only a safe failure reason. This preserves a usable last-known result without building project-source, model-output, or conversation history.
