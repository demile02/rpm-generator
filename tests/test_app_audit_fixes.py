"""Focused regression tests for app.py audit fixes."""
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def isolated_feedback(monkeypatch, tmp_path):
    import app as app_module
    path = tmp_path / "feedback.json"
    monkeypatch.setattr(app_module, "FEEDBACK_FILE", path)
    return app_module


def test_upload_limit_is_request_local_and_does_not_mutate_app_config(flask_app):
    from flask import request

    assert flask_app.config["MAX_CONTENT_LENGTH"] == 2 * 1024 * 1024
    with flask_app.test_request_context("/api/modules/import", method="POST"):
        flask_app.preprocess_request()
        assert request.max_content_length == 10 * 1024 * 1024
        assert flask_app.config["MAX_CONTENT_LENGTH"] == 2 * 1024 * 1024
    with flask_app.test_request_context("/api/module/generate", method="POST"):
        flask_app.preprocess_request()
        assert request.max_content_length == 2 * 1024 * 1024


def test_feedback_rejects_non_string_user_fields(flask_client, isolated_feedback):
    response = flask_client.post("/api/feedback", json={
        "comment": "valid",
        "timestamp": {"bad": "type"},
        "page_url": ["bad"],
    })
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


def test_feedback_view_escapes_timestamp_and_all_rendered_fields(
        flask_client, isolated_feedback):
    response = flask_client.post("/api/feedback", json={
        "comment": "<script>alert(1)</script>",
        "timestamp": "<img src=x onerror=alert(1)>",
        "page_url": "<b>url</b>",
        "selector": "<i>selector</i>",
        "viewport": "<u>viewport</u>",
    })
    assert response.status_code == 200
    html = flask_client.get("/feedback").get_data(as_text=True)
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "&lt;b&gt;url&lt;/b&gt;" in html
    assert "&lt;i&gt;selector&lt;/i&gt;" in html
    assert "&lt;u&gt;viewport&lt;/u&gt;" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_concurrent_feedback_posts_do_not_lose_entries(
        flask_app, isolated_feedback):
    barrier = threading.Barrier(8)
    results = []
    lock = threading.Lock()

    def post_one(index):
        client = flask_app.test_client()
        barrier.wait()
        response = client.post("/api/feedback", json={
            "comment": f"comment-{index}",
            "timestamp": f"2026-10-11T00:00:{index:02d}Z",
        })
        with lock:
            results.append(response.status_code)

    threads = [threading.Thread(target=post_one, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [200] * 8
    payload = flask_app.test_client().get("/api/feedback").get_json()
    assert payload["count"] == 8


def test_subjects_and_options_follow_authoritative_institution_mapping(
        flask_client):
    import app as app_module
    subjects = flask_client.get("/api/subjects/KEMENDIKDASMEN").get_json()
    assert "MATEMATIKA" in subjects["subjects"]
    assert "Pendidikan Agama dan Budi Pekerti" in subjects["subjects"]

    options = flask_client.get("/api/curriculum/options").get_json()
    assert options["systems"]["KEMENAG"]["institutions"]["MI"]["subjects"]
    assert "Akidah Akhlak" in options["systems"]["KEMENAG"]["institutions"]["MI"]["subjects"]
    assert "MATEMATIKA" in options["systems"]["KEMENDIKDASMEN"]["institutions"]["SMP"]["subjects"]
    assert "Akidah Akhlak" not in options["systems"]["KEMENDIKDASMEN"]["institutions"]["SMP"]["subjects"]


def test_download_requested_module_comes_from_store_after_memory_clear(
        flask_app, test_db, monkeypatch, tmp_path):
    import app as app_module
    from module_store import ModuleStore

    module = {"id": "module-1", "generation_id": "gid-requested",
              "title": "stored module"}
    ModuleStore(str(test_db)).save("gid-requested", module, {"phase": "D"})
    class Pipeline:
        db_path = str(test_db)
    monkeypatch.setattr(app_module, "get_generation_pipeline", lambda: Pipeline())
    app_module.generation_context.clear()
    response = flask_app.test_client().get(
        "/api/module/download?generation_id=gid-requested")
    assert response.status_code == 200
    assert json.loads(response.data)["generation_id"] == "gid-requested"


def test_lazy_pipeline_initialization_is_singleton_under_race(monkeypatch):
    import app as app_module

    created = []
    class FakePipeline:
        def __init__(self, db_path):
            created.append(db_path)
    monkeypatch.setattr(app_module, "ModuleGenerationPipeline", FakePipeline)
    monkeypatch.setattr(app_module, "_generation_pipeline", None)
    threads = [threading.Thread(target=app_module.get_generation_pipeline)
               for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(created) == 1
    app_module._generation_pipeline = None
