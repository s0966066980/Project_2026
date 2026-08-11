# syntax=docker/dockerfile:1.7
#
# The Project Analyst Sidecar image.
#
# Provider CLIs live here and nowhere else. Installing Codex, Claude or Grok
# into the App or Worker image would give a provider the same process,
# filesystem and network reach as the ordering system (ADR-0036).
#
# The build context is the repository root, but only project_analyst/ is copied
# in. The sidecar must not be able to read the project even by accident — every
# file it analyses arrives in a request body.

FROM python:3.10-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/analyst \
    PROJECT_ANALYST_HOME=/tmp/project-analyst

RUN groupadd --gid 10002 analyst \
    && useradd --uid 10002 --gid analyst --create-home --home-dir /home/analyst analyst

WORKDIR /srv

COPY project_analyst/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement /tmp/requirements.txt

# Provider CLIs are pinned by profiles.py and installed by an operator into a
# derived image. The base image ships without them on purpose: an absent CLI
# reports `cli_not_installed` and the profile is simply not selectable, which
# is the correct closed state for a sidecar with no credentials mounted.

COPY project_analyst/ /srv/project_analyst/

FROM base AS analyst

# No Git here on purpose. The analyst sidecar receives a snapshot in a request
# body and has no repository to read; a version-control client would be a tool
# with nothing legitimate to do and a great deal of illegitimate reach.

USER analyst

EXPOSE 7900

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request; raise SystemExit(0 if urllib.request.urlopen('http://127.0.0.1:7900/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "project_analyst.service:app", "--host", "0.0.0.0", "--port", "7900"]

FROM base AS proposer

# The proposal workflow clones the source at an explicit revision into a
# disposable directory, so this role — and only this role — needs Git.
USER root
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

USER analyst

CMD ["python", "-c", "import project_analyst.proposer as p; print('proposal workflow module loaded', p.DOCUMENT_ROOT, p.EXTENSION_ROOT)"]
