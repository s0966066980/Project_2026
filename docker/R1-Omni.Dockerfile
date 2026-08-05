# syntax=docker/dockerfile:1.7

FROM python:3.10-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/cache/huggingface \
    TRANSFORMERS_OFFLINE=1 \
    R1_OMNI_MODEL_ROOT=/models \
    R1_OMNI_ALLOWED_VIDEO_DIR=/tmp/project-2026-media

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg git libgl1 libglib2.0-0 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/r1-omni

COPY R1-Omni/requirements-docker.txt /tmp/requirements-r1-docker.txt

RUN mkdir -p /models /cache/huggingface /tmp/project-2026-media

FROM base AS cpu

RUN python -m pip install \
        filelock fsspec jinja2 "networkx>=3.2,<4" "numpy<2" pillow \
        "sympy==1.13.1" typing-extensions
RUN python -m pip install --no-deps \
        torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
        --index-url https://download.pytorch.org/whl/cpu
RUN python -m pip install --requirement /tmp/requirements-r1-docker.txt

COPY R1-Omni/ /opt/r1-omni/

ENV R1_OMNI_DEVICE=cpu

EXPOSE 7890

HEALTHCHECK --interval=30s --timeout=10s --start-period=15m --retries=20 \
    CMD python -c "import json, urllib.request; payload=json.load(urllib.request.urlopen('http://127.0.0.1:7890/health', timeout=8)); raise SystemExit(0 if payload.get('status') == 'ok' and payload.get('model_loaded') else 1)"

CMD ["python", "r1_omni_server.py", "--host", "0.0.0.0", "--port", "7890"]

FROM base AS gpu

RUN python -m pip install \
        filelock fsspec jinja2 "networkx>=3.2,<4" "numpy<2" pillow \
        "sympy==1.13.1" typing-extensions
RUN python -m pip install --no-deps \
        torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
        --index-url https://download.pytorch.org/whl/cu124
RUN python -m pip install --requirement /tmp/requirements-r1-docker.txt

COPY R1-Omni/ /opt/r1-omni/

ENV R1_OMNI_DEVICE=cuda

EXPOSE 7890

HEALTHCHECK --interval=30s --timeout=10s --start-period=10m --retries=20 \
    CMD python -c "import json, urllib.request; payload=json.load(urllib.request.urlopen('http://127.0.0.1:7890/health', timeout=8)); raise SystemExit(0 if payload.get('status') == 'ok' and payload.get('model_loaded') and payload.get('device') == 'cuda' else 1)"

CMD ["python", "r1_omni_server.py", "--host", "0.0.0.0", "--port", "7890"]
