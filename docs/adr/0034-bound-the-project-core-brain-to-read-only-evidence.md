# Bound the Project Core Brain to read-only project evidence

Status: accepted

The first Project Core Brain release is an evidence-backed project analysis capability, not an autonomous development agent. It may read Git-tracked source code, tests, documentation, and non-secret configuration inside this repository; code-architecture facts; Git status and diffs; Docker and capability-API readiness; and results from tests explicitly triggered by an administrator.

The capability cannot read `.env` files, credentials, customer database records, raw media, home-directory content, or paths outside the project. It cannot execute arbitrary shell commands, edit files, mutate Git, change runtime configuration, or operate business data. Future creation of non-core documents or features requires a separately authorized workflow with its own permissions and review boundary.
