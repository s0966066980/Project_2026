# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim AS frontend-runtime-deps

WORKDIR /frontend
COPY UI_API/frontend/package.json UI_API/frontend/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts

FROM python:3.10-slim-bookworm AS base

# The revision this image is, recorded once at build time. The runtime image has
# no Git and no repository, so asking at runtime can only ever answer "unknown";
# for a digest-pinned artifact the revision is a property of the image anyway.
ARG APP_GIT_REVISION=unknown
ENV APP_GIT_REVISION=${APP_GIT_REVISION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/project2026

RUN groupadd --gid 10001 project2026 \
    && useradd --uid 10001 --gid project2026 --create-home --home-dir /home/project2026 project2026

WORKDIR /app/UI_API

COPY UI_API/requirements-docker.txt /tmp/requirements-docker.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement /tmp/requirements-docker.txt

COPY UI_API/ /app/UI_API/
COPY --from=frontend-runtime-deps /frontend/node_modules /app/UI_API/frontend/node_modules

RUN mkdir -p /var/lib/project-2026 \
    && chown -R project2026:project2026 /app/UI_API /var/lib/project-2026

FROM base AS test

USER root
RUN python -m pip install --requirement requirements-ci.txt
# The proposal-workflow tests build a real Git repository and assert the source
# tree is byte-identical afterwards. Mocking the clone would prove the code
# calls git, which is not the claim. Without git those thirteen tests skip —
# and the ones that skip are precisely the ones that prove the isolation.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
# The contract-drift gate regenerates the published TypeScript from the running
# schema, so the generator has to be in the image. A gate that skips when its
# tool is missing is a gate that reports green without checking anything.
COPY tools/ /app/tools/
# Same reason for the Pilot container-security gate: it asserts the contract
# written in docker/compose.pilot.yaml, so the overlay has to be in the image.
# Without it the gate errors out inside docker/scripts/test.sh while still
# passing in CI, where pytest runs against a checkout.
COPY docker/ /app/docker/
USER project2026

FROM base AS ai-base

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY UI_API/requirements-ai.txt /tmp/requirements-ai.txt
RUN python -m pip install --requirement /tmp/requirements-ai.txt

RUN mkdir -p /home/project2026/.cache /tmp/project-2026-media \
    && chown -R project2026:project2026 /home/project2026/.cache /tmp/project-2026-media

FROM ai-base AS ai-runtime

USER project2026

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=5m --retries=20 \
    CMD python -c "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4); payload = json.load(response); raise SystemExit(0 if response.status == 200 and payload.get('ready') else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

FROM base AS runtime

USER project2026

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=12 \
    CMD python -c "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4); payload = json.load(response); raise SystemExit(0 if response.status == 200 and payload.get('ready') else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
