"""一鍵產生推薦詞：路由順序、批次進度與單項失敗不中斷整批。"""

import importlib

import pytest


def test_batch_routes_are_declared_before_the_item_id_route():
    """具名路由必須排在 /{item_id} 之前，否則 "batch" 會被當成品項 ID 而走進儲存端點。

    FastAPI 依宣告順序比對，因此直接檢查原始碼裡的順序，不必啟動整個應用程式。
    """

    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "backend" / "routes" / "push_copy_routes.py").read_text(
        encoding="utf-8"
    )

    batch_at = source.index('@router.post("/batch")')
    item_at = source.index('@router.post("/{item_id}")')
    assert batch_at < item_at, "POST /batch 必須宣告在 POST /{item_id} 之前"

    batch_get_at = source.index('@router.get("/batch")')
    assert batch_get_at < item_at


@pytest.fixture
def batch_repo(monkeypatch, tmp_path):
    from repositories import push_copy_batch_repository as repo
    importlib.reload(repo)
    monkeypatch.setattr(repo, "BATCHES_PATH", str(tmp_path / "batches.json"))
    monkeypatch.setattr(repo.postgres_utils, "use_postgres", lambda: False)
    return repo


def _scope():
    from models.commercial_scope import LEGACY_DEFAULT_SCOPE

    return LEGACY_DEFAULT_SCOPE


def test_progress_counts_each_item_as_it_finishes(batch_repo):
    scope = _scope()
    batch = batch_repo.create_batch(scope, mode="fill_missing", item_ids=["A", "B", "C", "D"])
    assert batch["total"] == 4
    assert batch["percent"] == 0

    batch_repo.record_item_result(scope, batch["batch_id"], ok=True)
    batch_repo.record_item_result(scope, batch["batch_id"], ok=True)
    batch_repo.record_item_result(scope, batch["batch_id"], ok=False, error="模型逾時")

    current = batch_repo.get_batch(scope, batch["batch_id"])
    assert (current["succeeded"], current["failed"], current["processed"]) == (2, 1, 3)
    assert current["percent"] == 75
    assert current["last_error"] == "模型逾時"


def test_regenerate_mode_is_kept_distinct_from_fill_missing(batch_repo):
    """兩者對既有文案的處置不同（覆寫 vs 不覆寫），進度紀錄必須分得出來。"""

    scope = _scope()
    fill = batch_repo.create_batch(scope, mode="fill_missing", item_ids=["A"])
    regen = batch_repo.create_batch(scope, mode="regenerate", item_ids=["A"])

    assert batch_repo.get_batch(scope, fill["batch_id"])["mode"] == "fill_missing"
    assert batch_repo.get_batch(scope, regen["batch_id"])["mode"] == "regenerate"


def test_unknown_mode_falls_back_to_the_non_destructive_one(batch_repo):
    """看不懂的模式必須退回不覆寫的那一種，猜錯方向會毀掉人工寫好的文案。"""

    scope = _scope()
    batch = batch_repo.create_batch(scope, mode="nonsense", item_ids=["A"])

    assert batch["mode"] == "fill_missing"


def test_latest_batch_lets_the_page_resume_progress_after_reload(batch_repo):
    scope = _scope()
    batch_repo.create_batch(scope, mode="fill_missing", item_ids=["A"])
    second = batch_repo.create_batch(scope, mode="regenerate", item_ids=["B", "C"])

    assert batch_repo.latest_batch(scope)["batch_id"] == second["batch_id"]


def test_one_failed_item_does_not_discard_the_rest(batch_repo, monkeypatch):
    """單一品項失敗不該讓其餘一百多項的成果作廢。"""

    from models.worker_jobs import BackgroundJob
    from services import worker_handlers

    scope = _scope()
    menu = [{"id": "A", "name": "甲"}, {"id": "B", "name": "乙"}, {"id": "C", "name": "丙"}]
    batch = batch_repo.create_batch(scope, mode="fill_missing", item_ids=["A", "B", "C"])

    saved: dict[str, str] = {}

    def fake_draft(item, *, slot="base", offer=None):
        if item["id"] == "B":
            return "", "模型回應被截斷。", []
        return f"{item['name']}的推薦詞", "", []

    monkeypatch.setattr("repositories.menu_repository.get_menu", lambda: menu)
    monkeypatch.setattr("repositories.push_copy_repository.list_copy_scoped", lambda _s: {})
    monkeypatch.setattr(
        "repositories.push_copy_repository.save_copy_scoped",
        lambda item_id, entry, _s, actor_id="": saved.update({item_id: entry["base_copy"]}),
    )
    monkeypatch.setattr("services.push_copy_authoring_service.draft_copy", fake_draft)
    monkeypatch.setattr("repositories.push_copy_batch_repository.get_batch", batch_repo.get_batch)
    monkeypatch.setattr("repositories.push_copy_batch_repository.mark_running", batch_repo.mark_running)
    monkeypatch.setattr(
        "repositories.push_copy_batch_repository.record_item_result", batch_repo.record_item_result
    )
    monkeypatch.setattr("repositories.push_copy_batch_repository.finish_batch", batch_repo.finish_batch)

    job = BackgroundJob(
        job_id="j", tenant_id=scope.tenant_id, store_id=scope.store_id,
        job_type="ai.background",
        payload_ref={"kind": "push_copy_batch", "batch_id": batch["batch_id"]},
        idempotency_key="k", status="running", attempt_count=1, max_attempts=1,
        scheduled_at=None, available_at=None, visibility_timeout_seconds=60,
    )
    result = worker_handlers.handle_ai_background(job)

    assert result.success is True
    assert saved == {"A": "甲的推薦詞", "C": "丙的推薦詞"}
    final = batch_repo.get_batch(scope, batch["batch_id"])
    assert (final["succeeded"], final["failed"]) == (2, 1)
    assert final["status"] == "succeeded"
