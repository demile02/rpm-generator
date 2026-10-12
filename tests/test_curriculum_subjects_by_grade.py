"""Regression tests for the grade-filtered subject dropdown flow."""


def test_curriculum_subjects_requires_grade_context(flask_client):
    response = flask_client.get("/api/curriculum/subjects")
    assert response.status_code == 400
    assert response.get_json()["code"] == "CURRICULUM_SUBJECTS_INPUT_REQUIRED"


def test_curriculum_subjects_filters_by_grade_phase(flask_client):
    response = flask_client.get(
        "/api/curriculum/subjects"
        "?education_system=KEMENAG&institution_type=MTs&grade=MTs_7"
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["phase"] == "D"
    assert isinstance(data["subjects"], list)
    assert data["subjects"]
    assert data["subjects"] == sorted(data["subjects"], key=str.upper)
    assert [item.upper() for item in data["subjects"]] == sorted(
        item.upper() for item in data["subjects"]
    )
    assert "AKIDAH AKHLAK" in [item.upper() for item in data["subjects"]]
    assert "ILMU KALAM" not in [item.upper() for item in data["subjects"]]


def test_curriculum_subjects_uppercase_matches_lookup(flask_client):
    picked = flask_client.get(
        "/api/curriculum/subjects"
        "?education_system=KEMENAG&institution_type=MTs&grade=MTs_7"
    ).get_json()["subjects"][0]
    elements = flask_client.get(
        "/api/curriculum/elements",
        query_string={
            "subject": picked,
            "phase": "D",
            "education_system": "KEMENAG",
            "institution_type": "MTs",
        },
    )
    assert elements.status_code == 200
    assert elements.get_json()["elements"]
