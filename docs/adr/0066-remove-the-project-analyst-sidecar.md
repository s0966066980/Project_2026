# ADR-0066: Remove the Project Analyst Sidecar

- Status: Accepted
- Date: 2026-08-14
- Supersedes the implementation of ADR-0036, ADR-0037, ADR-0039, ADR-0040 and
  ADR-0047. Those records stay: they explain why the sidecar was shaped the way
  it was, and this decision is only legible next to them.

## Context

The Project Analyst Sidecar read the project's own files — never customer or
store data — and returned a structured report about them. It ran in an isolated
container with no repository mount, no database, no user home and no Docker
socket, and it carried a proposal generator that could produce a patch it was
structurally unable to apply.

Three things were true at once when this was decided:

**Nothing could run it.** The three profiles are CLI-shaped: a pinned binary
plus a mounted vendor credential. On this deployment all three report
`cli_not_installed`, so the Admin selector was empty and the analysis was
unreachable. A local `ollama` profile was added on 2026-08-13 and did work,
which is what made the next point visible rather than theoretical.

**The model cannot do the job at project scale.** The real snapshot is about
186,000 characters. Asked to read it in one pass, qwen3.5:4b returns something
that is not the result contract at all; reading one file at a time it answers
correctly but can never see a relationship between two files. A report that
cannot compare `CONTEXT.md` against the code it describes is not the report
this capability existed to produce.

**It is not what the owner needs.** The stated goal — "read today's voice
conversations, check whether RAG already answers them, propose new knowledge if
not" — is the Daily Diagnostic Workbench, a different capability over
operational data that already implements that whole chain. The Project Analyst
reads source code and has nothing to say about a voice conversation.

## Decision

Remove the Project Analyst Sidecar entirely: `project_analyst/`,
`UI_API/backend/project_analysis/`, the `project_brain_service`, the
`/api/v1/project-brain/*` routes, the Admin panel, the compose overlay and
Dockerfile, and the three test suites.

Removed rather than left in place behind a hidden panel. This project has just
spent a week finding read models that were empty because their writers had no
callers — `record_final_checkout`, `build_order_attributions`, the Voice
Evidence projection. Unreachable code that still looks present is the specific
failure mode being paid for elsewhere, and a subsystem nobody can run is the
same thing at a larger scale.

## Consequences

The confinement work is the real loss: a disposable clone at an explicit
revision, a read-only source mount, additions restricted to `docs/proposals/`
and `extensions/<name>/`, a refusal to modify any existing file, and a patch
that is never applied. That was the hard part and it worked. It is recoverable
from git history if the capability returns; it is not recoverable from memory,
which is why ADR-0039 and ADR-0040 are being kept rather than deleted with the
code.

`extensions/` never existed as a directory and no loader ever imported one, so
nothing downstream depended on the proposal target.

The Daily Diagnostic Workbench is unaffected. It has its own analyzer profiles,
including its own `ollama` entry, and reads operational evidence rather than
source files.

If a project-analysis capability is wanted again, the two things to settle
first are the ones that ended this one: a model that can hold the whole
snapshot, and a stated purpose that is not already served by the diagnostic
workbench.
