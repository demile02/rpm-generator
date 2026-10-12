"""Regression tests for curriculum-options response caching."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_curriculum_options_reuses_payload_until_database_changes(
        flask_app, test_db, monkeypatch):
    import app as app_module

    previous_db = app_module.DB_PATH
    app_module.DB_PATH = test_db
    app_module._CURRICULUM_OPTIONS_CACHE.clear()
    calls = 0
    original_get_db = app_module.get_db

    def counted_get_db():
        nonlocal calls
        calls += 1
        return original_get_db()

    monkeypatch.setattr(app_module, "get_db", counted_get_db)
    try:
        client = flask_app.test_client()
        first = client.get("/api/curriculum/options")
        second = client.get("/api/curriculum/options")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.get_json() == second.get_json()
        assert calls == 1

        stat = test_db.stat()
        os.utime(test_db, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        third = client.get("/api/curriculum/options")
        assert third.status_code == 200
        assert calls == 2
    finally:
        app_module.DB_PATH = previous_db
        app_module._CURRICULUM_OPTIONS_CACHE.clear()
