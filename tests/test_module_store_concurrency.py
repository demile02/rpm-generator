"""Concurrency regression tests for atomic optimistic version saves."""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from module_store import StaleVersionError, VersionStore


def test_concurrent_save_new_accepts_one_and_rejects_other_as_stale(tmp_path):
    db_path = tmp_path / "versions.db"
    seed_store = VersionStore(str(db_path))
    seed_store.save_new(
        "generation-1",
        0,
        0,
        "validated",
        {"title": "original", "items": ["v1"]},
        {},
        "Aligned",
        [],
        [],
    )

    stores = [VersionStore(str(db_path)), VersionStore(str(db_path))]
    start = threading.Barrier(2)
    outcomes = []
    outcome_lock = threading.Lock()

    def save(store, payload):
        start.wait()
        try:
            result = store.save_new(
                "generation-1",
                1,
                1,
                "validated",
                payload,
                {},
                "Aligned",
                ["content"],
                [],
            )
            outcome = ("saved", result)
        except Exception as exc:  # assert exact exception below
            outcome = ("failed", exc)
        with outcome_lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=save, args=(stores[0], {"title": "writer-a"})),
        threading.Thread(target=save, args=(stores[1], {"title": "writer-b"})),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(outcomes) == 2
    saved = [value for kind, value in outcomes if kind == "saved"]
    failed = [value for kind, value in outcomes if kind == "failed"]
    assert len(saved) == 1
    assert len(failed) == 1
    assert isinstance(failed[0], StaleVersionError)
    assert not any(isinstance(value, Exception) and not isinstance(
        value, StaleVersionError) for value in failed)

    history = VersionStore(str(db_path)).history("generation-1")
    assert [entry["version_no"] for entry in history] == [1, 2]
    assert VersionStore(str(db_path)).get("generation-1", 1)["module"] == {
        "title": "original",
        "items": ["v1"],
    }
    assert VersionStore(str(db_path)).get("generation-1", 2)["module"] == saved[0]["module"]
