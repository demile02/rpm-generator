#!/usr/bin/env python3
"""Relevansi topik<->elemen: elements list, /api/topic/relevance, soft gate.

- validate_generate_body menerima elements[] + element tunggal lama.
- _generation_params_from_request membawa elements list + element primer.
- POST /api/topic/relevance: advisory, fail open saat AI down.
- /api/module/generate (sync+async): tanpa skip flag -> 422
  RELEVANCE_WARNING bila perlu_warning; dengan skip flag -> generate.
- Perilaku lama (element tunggal, tanpa elements) tidak berubah.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

VALID_BODY = {
    'education_system': 'KEMENAG',
    'institution_type': 'MTs',
    'grade': 'MTs_7',
    'subject': 'Akidah Akhlak',
    'phase': 'D',
    'element': 'Pemahaman Konsep',
    'topic': 'Taubat',
}

REL_OK = {
    "relevansi": [{"elemen": "Pemahaman Konsep", "nilai": "RELEVAN",
                   "alasan": "Topik taubat adalah inti akidah."}],
    "saran": "",
    "perlu_warning": False,
}
REL_WARN = {
    "relevansi": [{"elemen": "Pemahaman Konsep",
                   "nilai": "KURANG_RELEVAN",
                   "alasan": "Topik lebih cocok ke fikih ibadah."}],
    "saran": "Ibadah",
    "perlu_warning": True,
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


def _wrap(fake, canned):
    """Relevance prompt -> canned; selain itu delegasi ke fake repo.

    Marker = kalimat khas prompt relevansi (kata 'relevansi' saja terlalu
    umum — muncul juga di prompt stage lain).
    """
    def side_effect(prompt, system_instruction=None, **kwargs):
        if 'Nilai relevansi topik di atas' in prompt:
            return canned
        return fake(prompt, system_instruction, **kwargs)
    return side_effect


class TestElementsValidation:
    def test_elements_absent_valid(self):
        import app as app_module
        errors = []
        app_module._validate_elements_field({}, errors)
        assert errors == []

    def test_elements_list_valid(self):
        import app as app_module
        errors = []
        app_module._validate_elements_field(
            {'elements': ['Aqidah', 'Akhlak']}, errors)
        assert errors == []

    def test_elements_nonlist_400_shape(self):
        import app as app_module
        errors = []
        app_module._validate_elements_field(
            {'elements': 'bukan-list'}, errors)
        assert errors and errors[0]['code'] == 'INVALID_PARAMS'

    def test_elements_item_too_long(self):
        import app as app_module
        errors = []
        app_module._validate_elements_field(
            {'elements': ['x' * 101]}, errors)
        assert errors

    def test_elements_nonstring_item(self):
        import app as app_module
        errors = []
        app_module._validate_elements_field(
            {'elements': ['ok', 123]}, errors)
        assert errors

    def test_elements_blank_item(self):
        import app as app_module
        errors = []
        app_module._validate_elements_field({'elements': ['  ']}, errors)
        assert errors

    def test_elements_over_count(self):
        import app as app_module
        errors = []
        app_module._validate_elements_field(
            {'elements': ['a'] * 11}, errors)
        assert errors

    def test_normalize_primary_first_dedup(self):
        import app as app_module
        assert app_module._normalize_elements(
            {'element': 'P', 'elements': ['P', 'Q']}) == ['P', 'Q']
        assert app_module._normalize_elements(
            {'elements': ['Q', 'R']}) == ['Q', 'R']
        assert app_module._normalize_elements({'element': 'P'}) == ['P']
        assert app_module._normalize_elements({}) == []

    def test_params_carry_elements_and_primary(self):
        import app as app_module
        p = app_module._generation_params_from_request(
            {'element': 'P', 'elements': ['P', 'Q'], 'topic': ' T '})
        assert p['element'] == 'P'
        assert p['elements'] == ['P', 'Q']
        assert p['topic'] == 'T'
        p = app_module._generation_params_from_request({'elements': ['Q']})
        assert p['element'] == 'Q' and p['elements'] == ['Q']
        p = app_module._generation_params_from_request({})
        assert p['element'] is None and p['elements'] == []

    def test_generate_body_accepts_elements(self):
        import app as app_module
        body = dict(VALID_BODY, elements=['Pemahaman Konsep'])
        assert app_module.validate_generate_body(body, body) == []

    def test_generate_body_rejects_bad_elements(self):
        import app as app_module
        body = dict(VALID_BODY, elements='bukan-list')
        errors = app_module.validate_generate_body(body, body)
        assert any(e['code'] == 'INVALID_PARAMS' for e in errors)


class TestTopicRelevanceEndpoint:
    def test_all_relevant_200(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        with patch_pipeline_ai(
                api_pipeline, _wrap(fake_router_response, REL_OK)):
            resp = flask_client.post('/api/topic/relevance',
                                     json=dict(VALID_BODY))
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['status'] == 'success'
        assert body['perlu_warning'] is False
        assert len(body['relevansi']) == 1
        assert body['relevansi'][0]['nilai'] == 'RELEVAN'

    def test_warn_returns_saran_200(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        with patch_pipeline_ai(
                api_pipeline, _wrap(fake_router_response, REL_WARN)):
            resp = flask_client.post(
                '/api/topic/relevance',
                json=dict(VALID_BODY, elements=['Pemahaman Konsep']))
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['perlu_warning'] is True
        assert body['saran'] == 'Ibadah'

    def test_ai_down_fail_open_200(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)

        def ai_down(prompt, system_instruction=None, **kwargs):
            if 'Nilai relevansi topik di atas' in prompt:
                raise ConnectionError('gateway down')
            return fake_router_response(prompt, system_instruction, **kwargs)

        with patch_pipeline_ai(api_pipeline, ai_down):
            resp = flask_client.post('/api/topic/relevance',
                                     json=dict(VALID_BODY))
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['perlu_warning'] is False
        assert body.get('fail_open') is True

    def test_skip_flag_skips_ai(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        calls = []

        def counting(prompt, system_instruction=None, **kwargs):
            calls.append(prompt)
            return _wrap(fake_router_response, REL_OK)(
                prompt, system_instruction, **kwargs)

        with patch_pipeline_ai(api_pipeline, counting):
            resp = flask_client.post(
                '/api/topic/relevance',
                json=dict(VALID_BODY, skip_relevance_check=True))
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert json.loads(resp.data).get('skipped') is True
        assert calls == []

    def test_invalid_elements_400(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        with patch_pipeline_ai(
                api_pipeline, _wrap(fake_router_response, REL_OK)):
            resp = flask_client.post(
                '/api/topic/relevance',
                json=dict(VALID_BODY, elements='bukan-list'))
        assert resp.status_code == 400


class TestGenerateSoftGate:
    def test_warn_returns_422_without_pipeline(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        gen_calls = []
        real_generate = api_pipeline.generate

        def spy(params):
            gen_calls.append(params)
            return real_generate(params)

        with patch_pipeline_ai(
                api_pipeline, _wrap(fake_router_response, REL_WARN)), \
                patch.object(api_pipeline, 'generate', side_effect=spy):
            resp = flask_client.post('/api/module/generate',
                                     json=dict(VALID_BODY))
        assert resp.status_code == 422, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body.get('code') == 'RELEVANCE_WARNING'
        assert body['perlu_warning'] is True
        assert body['relevansi'] and body['saran'] == 'Ibadah'
        assert gen_calls == []

    def test_skip_flag_reaches_pipeline(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        gen_calls = []

        def canned(params):
            gen_calls.append(params)
            return {'status': 'failed', 'generation_id': 'g1',
                    'module': None, 'validation': {}, 'errors': ['boom']}

        with patch_pipeline_ai(
                api_pipeline, _wrap(fake_router_response, REL_WARN)), \
                patch.object(api_pipeline, 'generate', side_effect=canned):
            resp = flask_client.post(
                '/api/module/generate',
                json=dict(VALID_BODY, skip_relevance_check=True))
        assert resp.status_code == 422, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body.get('code') != 'RELEVANCE_WARNING'
        assert len(gen_calls) == 1

    def test_legacy_single_element_unaffected(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        with patch_pipeline_ai(
                api_pipeline, _wrap(fake_router_response, REL_OK)):
            resp = flask_client.post('/api/module/generate',
                                     json=dict(VALID_BODY))
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert json.loads(resp.data)['status'] == 'success'

    def test_elements_list_generates_via_primary(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        body = dict(VALID_BODY)
        del body['element']
        body['elements'] = ['Pemahaman Konsep']
        with patch_pipeline_ai(
                api_pipeline, _wrap(fake_router_response, REL_OK)):
            resp = flask_client.post('/api/module/generate', json=body)
        assert resp.status_code == 200, resp.get_data(as_text=True)

    def test_async_gate_and_skip(self, flask_client, api_pipeline):
        import threading
        import app as app_module
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        app_module.generation_jobs.clear()
        with patch_pipeline_ai(
                api_pipeline, _wrap(fake_router_response, REL_WARN)):
            resp = flask_client.post('/api/module/generate',
                                     json=dict(VALID_BODY, **{'async': True}))
            assert resp.status_code == 202, resp.get_data(as_text=True)
            job_id = json.loads(resp.data)['job_id']
            for _ in range(200):
                job = app_module.generation_jobs.get(job_id)
                if job and job['status'] != 'running':
                    break
                threading.Event().wait(0.05)
            warning = flask_client.get('/api/generation/status/' + job_id)
            assert warning.status_code == 200
            warning_body = json.loads(warning.data)
            assert warning_body['status'] == 'warning'
            assert warning_body['code'] == 'RELEVANCE_WARNING'
            assert warning_body['perlu_warning'] is True
            warning_timing = warning_body.get('timing') or {}
            assert {'request_validation_ms', 'queue_wait_ms',
                    'relevance_duration_ms', 'worker_total_ms'} <= set(
                        warning_timing)

            resp = flask_client.post(
                '/api/module/generate',
                json=dict(VALID_BODY, **{'async': True,
                                         'skip_relevance_check': True}))
            assert resp.status_code == 202, resp.get_data(as_text=True)
            job_id = json.loads(resp.data)['job_id']
            for _ in range(200):
                job = app_module.generation_jobs.get(job_id)
                if job and job['status'] != 'running':
                    break
                threading.Event().wait(0.05)
        job = app_module.generation_jobs.get(job_id)
        assert job is not None and job['status'] == 'success', \
            (job or {}).get('result')
        success_timing = (job or {}).get('timing') or {}
        assert {'request_validation_ms', 'queue_wait_ms', 'lock_wait_ms',
                'pipeline_worker_ms', 'pipeline_duration_ms',
                'ai_duration_ms', 'final_duration_ms',
                'persistence_duration_ms', 'worker_total_ms'} <= set(
                    success_timing)
        app_module.generation_jobs.clear()
