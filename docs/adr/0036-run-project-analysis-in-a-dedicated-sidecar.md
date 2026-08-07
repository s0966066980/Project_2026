# Run project analysis in a dedicated sidecar

Status: accepted

Production project analysis runs in a dedicated `project-analyst` Docker sidecar rather than installing Codex, Claude, or Grok in the App or Worker image. The sidecar accepts only a sanitized Project Analysis Snapshot, invokes one allowlisted non-interactive adapter, and returns a common structured result. It runs as non-root with a read-only root filesystem, dropped capabilities, bounded resources and execution time, and automation-specific credentials supplied through Docker secrets.

The sidecar has no Docker socket, user-home, `.env`, database, raw-media, or whole-repository mount and cannot mutate project or runtime state. CLI versions are pinned and automatic updating, memory, write tools, and unapproved network tools are disabled. A host-installed CLI bridge may implement the same contract for development convenience, but it is never a production dependency or an automatic fallback.
