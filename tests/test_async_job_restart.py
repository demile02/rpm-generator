"""Regression tests for restart-safe asynchronous jobs."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def api_pipeline(test_db):
    import app as app_module
    from module_generation_pipeline import ModuleGenerationPipeline

    pipeline = ModuleGenerationPipeline(db_path=str(test_db))
    app_module._generation_pipeline = pipeline
    yield pipeline
    app_module._generation_pipeline = None
    pipeline.curriculum_validator.close()


@pytest.fixture
def flask_client(api_pipeline, flask_app):
    return flask_app.test_client()


def test_async_job_store_survives_process_state_loss(tmp_path):
    from module_store import AsyncJobStore

    db_path = tmp_path / "async.db"
    first = AsyncJobStore(str(db_path))
    first.create(
        "job-restart-1",
        "generate",
        {"params": {"topic": "Taubat"}, "gate_data": {"topic": "Taubat"}},
        status="running",
        timing={"accepted_at": "2026-10-11T00:00:00Z"},
    )

    reopened = AsyncJobStore(str(db_path))
    row = reopened.get("job-restart-1")
    assert row is not None
    assert row["status"] == "running"
    assert row["kind"] == "generate"
    assert row["payload"]["params"]["topic"] == "Taubat"

    reopened.update(
        "job-restart-1",
        status="success",
        result={"generation_id": "generation-1"},
        progress=100,
    )
    assert AsyncJobStore(str(db_path)).get("job-restart-1")["status"] == "success"


def test_generation_status_reads_persisted_job_after_memory_loss(
        flask_client, api_pipeline):
    from module_store import AsyncJobStore
    import app as app_module

    job_id = "job-restart-status-1"
    AsyncJobStore(api_pipeline.db_path).create(
        job_id,
        "generate",
        {"params": {}, "gate_data": {}},
        status="running",
    )
    app_module.generation_jobs.clear()

    response = flask_client.get(f"/api/generation/status/{job_id}")
    assert response.status_code == 200
    assert response.get_json()["status"] == "running"


def test_recovery_requeues_unfinished_generation(monkeypatch, api_pipeline):
    from module_store import AsyncJobStore
    import app as app_module

    job_id = "job-restart-requeue-1"
    AsyncJobStore(api_pipeline.db_path).create(
        job_id,
        "generate",
        {"params": {"topic": "Taubat"}, "gate_data": {"topic": "Taubat"}},
        status="running",
    )
    app_module.generation_jobs.clear()
    submitted = []

    def fake_submit(fn, *args):
        submitted.append((fn, args))
        return True

    monkeypatch.setattr(app_module, "_submit_background_job", fake_submit)
    app_module._recover_persisted_jobs(str(api_pipeline.db_path))

    assert len(submitted) == 1
    assert submitted[0][0] is app_module._run_generation_job
    assert submitted[0][1][0] == job_id
    assert submitted[0][1][1] == {"topic": "Taubat"}
    assert app_module.generation_jobs.get(job_id)["status"] == "running"
    app_module.generation_jobs.clear()
