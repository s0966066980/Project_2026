# Select only ready project analyst profiles

Status: accepted

The Project Analyst Sidecar exposes Codex, Claude, and Grok only as server-discovered Project Analyst Profiles. A profile is ready only when its CLI version satisfies the pinned range, its automation credential is valid, non-interactive execution works, read-only and tool restrictions are enforced, and a contract probe returns the common JSON Schema.

Admin may configure one ready profile as the default and explicitly choose another ready profile before an analysis. A profile that fails readiness is not selectable and reports its bounded failure reason. If the selected profile becomes unavailable during a run, that run fails visibly and the system never switches to another provider or model automatically.
