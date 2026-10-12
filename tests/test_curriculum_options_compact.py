"""Regression tests for the compact curriculum-options flow."""


def test_compact_options_omits_lazy_elements(flask_client):
    response = flask_client.get("/api/curriculum/options?compact=1")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert "systems" in data
    assert "elements_by_subject" not in data
    system = data["systems"]["KEMENAG"]
    assert system["subjects"]
    madrasah = system["institutions"]["MTs"]
    assert madrasah["grades"]
    assert madrasah["grade_phase"]
    assert "grade_labels" not in madrasah
    assert "phases" not in madrasah
    assert "subjects" not in madrasah
    assert len(response.data) < 50000


def test_curriculum_elements_returns_filtered_active_elements(flask_client):
    response = flask_client.get(
        "/api/curriculum/elements?subject=Akidah%20Akhlak&phase=D"
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert isinstance(data["elements"], list)
    assert data["elements"]
    assert all(isinstance(item, str) and item for item in data["elements"])


def test_curriculum_elements_accepts_institution_unit_code(flask_client):
    response = flask_client.get(
        "/api/curriculum/elements?subject=Akidah%20Akhlak&phase=D"
        "&education_system=KEMENAG&institution_type=MTs"
    )
    assert response.status_code == 200
    assert response.get_json()["elements"]


def test_curriculum_elements_requires_subject_and_phase(flask_client):
    response = flask_client.get("/api/curriculum/elements?subject=Akidah%20Akhlak")
    assert response.status_code == 400
    assert response.get_json()["code"] == "CURRICULUM_ELEMENTS_INPUT_REQUIRED"
