import asyncio

import pytest

from services import project_brain_service


def test_analysis_uses_only_the_explicit_ready_model_and_saves_latest(monkeypatch):
    saved = []
    monkeypatch.setattr(project_brain_service, "ready_models", lambda: [{"id": "qwen:test", "ready": True}])

    async def snapshot(run_tests):
        return {"generated_at": "2026-08-11T00:00:00+00:00", "allowlisted_tests": {"ran": run_tests}}

    monkeypatch.setattr(project_brain_service, "_snapshot", snapshot)
    monkeypatch.setattr(project_brain_service, "_generate", lambda **kwargs: f"由 {kwargs['model']} 分析")
    monkeypatch.setattr(project_brain_service, "_save_report", lambda report: saved.append(report))

    result = asyncio.run(project_brain_service.analyze("qwen:test", run_tests=True))

    assert result["model"] == "qwen:test"
    assert result["analysis"] == "由 qwen:test 分析"
    assert saved == [result]


def test_project_brain_has_no_silent_model_fallback(monkeypatch):
    monkeypatch.setattr(project_brain_service, "ready_models", lambda: [{"id": "ready:model", "ready": True}])
    with pytest.raises(ValueError, match="selected_model_not_ready"):
        asyncio.run(project_brain_service.analyze("missing:model"))


def test_extension_output_is_a_non_applying_isolated_proposal(monkeypatch):
    monkeypatch.setattr(project_brain_service, "ready_models", lambda: [{"id": "qwen:test", "ready": True}])
    monkeypatch.setattr(project_brain_service, "_generate", lambda **_kwargs: "# 隔離提案")

    result = asyncio.run(project_brain_service.propose(
        "qwen:test", kind="extension", request="新增獨立排隊顯示功能"
    ))

    assert result["status"] == "proposal_only"
    assert result["proposed_path"].startswith("extensions/proposals/")
    assert result["applied"] is False
