from services.rag_studio_workflow import build_workflow


def test_workflow_explains_missing_publication_job_and_recovery_action():
    workflow = build_workflow(
        publication={
            "total_items": 1,
            "published_items": 0,
            "index_health": "indexing",
            "counts": {"indexing": 1},
            "recent_publication_attempts": [
                {
                    "attempt_id": "pa_1",
                    "phase": "build",
                    "status": "in_progress",
                    "job_status": "missing",
                }
            ],
        },
        published_configuration=None,
        readiness_confirmation=None,
    )

    assert workflow["ready"] is False
    assert workflow["next_step"] == "publish"
    publish = next(step for step in workflow["steps"] if step["id"] == "publish")
    assert publish["state"] == "blocked"
    assert publish["reason"] == "publication_job_missing"
    assert publish["action"] == "resume-publication"
    assert publish["attempt_id"] == "pa_1"


def test_workflow_is_ready_only_after_formal_result_confirmation():
    workflow = build_workflow(
        publication={
            "total_items": 2,
            "published_items": 2,
            "index_health": "healthy",
            "counts": {"published": 2},
            "recent_publication_attempts": [],
        },
        published_configuration={"version": 3, "method": "hybrid_rrf"},
        readiness_confirmation={"check_id": "arc_1"},
    )

    assert workflow["ready"] is True
    assert workflow["next_step"] is None
    assert all(step["state"] == "complete" for step in workflow["steps"])
