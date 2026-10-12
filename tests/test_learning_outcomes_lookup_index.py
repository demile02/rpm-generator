"""Regression coverage for indexed learning_outcomes CP lookup."""

import sqlite3

import pytest

from db_initialization import DatabaseInitializer


LOOKUP_INDEX = "idx_learning_outcomes_subject_phase_status"
LOOKUP_SQL = """
    SELECT *
    FROM learning_outcomes
    WHERE subject = ? AND phase = ? AND status = ?
    ORDER BY source_page, id
"""
LOOKUP_ARGS = ("Akidah Akhlak", "D", "active")


def _all_learning_outcomes(connection):
    return connection.execute(
        "SELECT * FROM learning_outcomes ORDER BY id"
    ).fetchall()


def _lookup_rows(connection):
    return connection.execute(LOOKUP_SQL, LOOKUP_ARGS).fetchall()


@pytest.mark.database
def test_learning_outcomes_lookup_migration_is_indexed_and_preserves_rows(test_db):
    """Add lookup index on copied DB without changing CP data or results."""
    with sqlite3.connect(test_db) as connection:
        before_rows = _all_learning_outcomes(connection)
        before_lookup = _lookup_rows(connection)

    initializer = DatabaseInitializer(str(test_db))
    initializer.connect()
    initializer.create_simplified_schema()
    initializer.close()

    with sqlite3.connect(test_db) as connection:
        index_names = {
            row[1]
            for row in connection.execute(
                "PRAGMA index_list(learning_outcomes)"
            ).fetchall()
        }
        assert LOOKUP_INDEX in index_names

        plan = connection.execute(
            "EXPLAIN QUERY PLAN " + LOOKUP_SQL,
            LOOKUP_ARGS,
        ).fetchall()
        details = " ".join(row[3] for row in plan)
        assert LOOKUP_INDEX in details, details

        assert _all_learning_outcomes(connection) == before_rows
        assert _lookup_rows(connection) == before_lookup


@pytest.mark.database
def test_learning_outcomes_lookup_index_migration_is_idempotent(test_db):
    """Re-running additive schema migration keeps one lookup index."""
    for _ in range(2):
        initializer = DatabaseInitializer(str(test_db))
        initializer.connect()
        initializer.create_simplified_schema()
        initializer.close()

    with sqlite3.connect(test_db) as connection:
        matching_indexes = [
            row[1]
            for row in connection.execute(
                "PRAGMA index_list(learning_outcomes)"
            ).fetchall()
            if row[1] == LOOKUP_INDEX
        ]
        assert matching_indexes == [LOOKUP_INDEX]
