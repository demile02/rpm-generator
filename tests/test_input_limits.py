#!/usr/bin/env python3
"""Batch 2 §2: server-side input validation (HTTP 4xx, tanpa andalkan UI)."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

VALID_CONTEXT = {
    'education_system': 'KEMENAG',
    'institution_type': 'MTs',
    'grade': 'MTs_7',
    'subject': 'Akidah Akhlak',
    'phase': 'D',
    'element': 'Pemahaman Konsep',
    'topic': 'Taubat',
}


@pytest.fixture
def api_pipeline(test_db):
    import app as app_module
    from module_generation_pipeline import ModuleGenerationPipeline
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    app_module._generation_pipeline = pipe
    yield pipe
    app_module._generation_pipeline = None
    pipe.curriculum_validator.close()


def _ctx(flask_client):
    resp = flask_client.post('/api/context/generate', json=dict(VALID_CONTEXT))
    assert resp.status_code == 200, resp.get_data(as_text=True)


class TestContextInputLimits:
    def test_empty_body_400(self, flask_client):
        assert flask_client.post(
            '/api/context/generate', json={}).status_code == 400

    def test_bad_system_400(self, flask_client):
        bad = dict(VALID_CONTEXT, education_system='KEMENDIKBUD')
        assert flask_client.post(
            '/api/context/generate', json=bad).status_code == 400

    def test_bad_institution_400(self, flask_client):
        bad = dict(VALID_CONTEXT, institution_type='SMA')
        assert flask_client.post(
            '/api/context/generate', json=bad).status_code == 400

    def test_unknown_grade_400(self, flask_client):
        bad = dict(VALID_CONTEXT, grade='MTs_99')
        assert flask_client.post(
            '/api/context/generate', json=bad).status_code == 400

    def test_phase_mismatch_400(self, flask_client):
        bad = dict(VALID_CONTEXT, phase='E')
        resp = flask_client.post('/api/context/generate', json=bad)
        assert resp.status_code == 400

    def test_oversized_topic_400(self, flask_client):
        bad = dict(VALID_CONTEXT, topic='x' * 201)
        assert flask_client.post(
            '/api/context/generate', json=bad).status_code == 400

    def test_nonstring_subject_400(self, flask_client):
        bad = dict(VALID_CONTEXT, subject=123)
        assert flask_client.post(
            '/api/context/generate', json=bad).status_code == 400

    def test_valid_context_200(self, flask_client):
        assert flask_client.post(
            '/api/context/generate', json=dict(VALID_CONTEXT)).status_code == 200


class TestGenerateInputLimits:
    def test_oversized_topic_400(self, flask_client, api_pipeline):
        _ctx(flask_client)
        resp = flask_client.post('/api/module/generate',
                                 json=dict(VALID_CONTEXT,
                                           topic='x' * 201))
        assert resp.status_code == 400

    def test_oversized_penyusun_400(self, flask_client, api_pipeline):
        _ctx(flask_client)
        resp = flask_client.post('/api/module/generate',
                                 json=dict(VALID_CONTEXT,
                                           penyusun='x' * 101))
        assert resp.status_code == 400

    def test_oversized_readiness_400(self, flask_client, api_pipeline):
        _ctx(flask_client)
        resp = flask_client.post('/api/module/generate',
                                 json=dict(VALID_CONTEXT,
                                           student_readiness='x' * 2001))
        assert resp.status_code == 400

    def test_null_byte_400(self, flask_client, api_pipeline):
        _ctx(flask_client)
        resp = flask_client.post('/api/module/generate',
                                 json=dict(VALID_CONTEXT,
                                           topic='Taubat\x00'))
        assert resp.status_code == 400

    def test_too_many_meetings_400(self, flask_client, api_pipeline):
        _ctx(flask_client)
        resp = flask_client.post('/api/module/generate',
                                 json=dict(VALID_CONTEXT,
                                           jumlah_pertemuan=17,
                                           jp_per_pertemuan=2))
        assert resp.status_code == 400

    def test_too_many_jp_400(self, flask_client, api_pipeline):
        _ctx(flask_client)
        resp = flask_client.post('/api/module/generate',
                                 json=dict(VALID_CONTEXT,
                                           jumlah_pertemuan=2,
                                           jp_per_pertemuan=11))
        assert resp.status_code == 400

    def test_max_meetings_boundary_passes_input(
            self, flask_client, api_pipeline):
        """16x10 lolos validasi input (AI di-mock agar tanpa gateway)."""
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        _ctx(flask_client)
        with patch_pipeline_ai(api_pipeline, fake_router_response):
            resp = flask_client.post(
                '/api/module/generate',
                json=dict(VALID_CONTEXT,
                          jumlah_pertemuan=16, jp_per_pertemuan=10))
        # Lolos gate input: boleh 200 (sukses) atau 422 (gagal validasi
        # isi, BUKAN 400 input). 400 berarti gate salah menolak.
        assert resp.status_code in (200, 422), resp.get_data(as_text=True)

    def test_total_cap_unit(self):
        import app as app_module
        errors = []
        with patch('module_generation_pipeline.resolve_jp_menit',
                   return_value=(60, None)):
            app_module._check_meeting_caps(
                {'jumlah_pertemuan': 16, 'jp_per_pertemuan': 10},
                dict(VALID_CONTEXT), errors)
        assert any('Total alokasi' in e['message'] for e in errors)

    def test_client_context_bad_identifier_400(
            self, flask_client, api_pipeline):
        resp = flask_client.post('/api/module/generate', json=dict(
            VALID_CONTEXT, institution_type='XXX'))
        assert resp.status_code == 400

    def test_oversized_body_413(self, flask_client, api_pipeline):
        _ctx(flask_client)
        big = 'x' * (2 * 1024 * 1024 + 100)
        resp = flask_client.post('/api/module/generate',
                                 json=dict(VALID_CONTEXT, topic=big))
        assert resp.status_code == 413
