from pathlib import Path

import pytest

pytestmark = [pytest.mark.architecture]
DOCKERFILE = Path(__file__).resolve().parents[2] / "docker/Dockerfile"
DOCKERFILE_IGNORE = DOCKERFILE.with_name("Dockerfile.dockerignore")


def test_ai_dependency_stage_is_source_independent():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    ai_base = dockerfile.split("FROM base AS ai-base", 1)[1].split("FROM ai-base AS ai-application", 1)[0]

    assert "COPY UI_API/requirements-ai.txt" in ai_base
    assert "COPY UI_API/ /app/UI_API/" not in ai_base
    assert dockerfile.index("FROM base AS ai-base") > dockerfile.index("FROM application AS runtime")


def test_application_stages_copy_the_same_source_and_frontend_runtime():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert dockerfile.count("COPY UI_API/ /app/UI_API/") == 2
    assert dockerfile.count("COPY --from=frontend-runtime-deps /frontend/node_modules") == 2


def test_dockerfile_ignore_does_not_hide_sources_copied_by_the_dockerfile():
    """Dockerfile-specific ignore rules must agree with its COPY sources."""
    ignored = {
        line.strip()
        for line in DOCKERFILE_IGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "docs" not in ignored
    assert (DOCKERFILE.parents[1] / "docs").is_dir()
