#!/usr/bin/env python3
"""Batch 2 §3: audit access-control (model capability-URL, tanpa auth
multi-user — didokumentasikan di app.py). Unknown ID -> 404 tanpa bocor;
malformed ID -> 400; secret tidak pernah terekspos."""
import json
import sys
import uuid
from pathlib import Path

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

ROWS_D = [
    (1, 'Pembuka', 15, 'TP-1', 'memahami'),
    (1, 'Inti', 35, 'TP-1', 'mengaplikasi'),
    (1, 'Inti', 30, 'TP-2', 'mengaplikasi'),
    (2, 'Pembuka', 15, 'TP-2', 'memahami'),
    (2, 'Inti', 35, 'TP-3', 'mengaplikasi'),
    (2, 'Penutup', 30, 'TP-3', 'merefleksi'),
]


@pytest.fixture
def api_pipeline(test_db):
    import app as app_module
    from module_generation_pipeline import ModuleGenerationPipeline
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    app_module._generation_pipeline = pipe
    yield pipe
    app_module._generation_pipeline = None
    pipe.curriculum_validator.close()


def _act(name, duration, tp, exp, stage, meeting):
    return {'name': name, 'description': 'Deskripsi ' + name,
            'duration': duration, 'experience': exp, 'tp_linked': tp,
            'stage': stage, 'meeting': meeting}


def _generate_stored(flask_client, api_pipeline):
    """Generasi mock + simpan; return (generation_id, module)."""
    import app as app_module
    from test_phase_c_module_generation import (
        fake_router_response, patch_pipeline_ai)
    from module_store import ModuleStore
    ctx = flask_client.post('/api/context/generate', json=dict(VALID_CONTEXT))
    assert ctx.status_code == 200

    def side_effect(prompt, system_instruction=None, **kwargs):
        if '"activities"' in prompt:
            from test_phase_c_module_generation import (
                mock_meeting_principles)
            return {'activities': [
                _act(f'A{i + 1}', dur, tp, exp, stage, meeting)
                for i, (meeting, stage, dur, tp, exp) in enumerate(ROWS_D)],
                'meeting_principles': mock_meeting_principles(2)}
        return fake_router_response(prompt, system_instruction, **kwargs)

    with patch_pipeline_ai(api_pipeline, side_effect):
        resp = flask_client.post('/api/module/generate', json={
            'education_system': 'KEMENAG', 'institution_type': 'MTs',
            'grade': 'MTs_7', 'subject': 'Akidah Akhlak',
            'element': 'Pemahaman Konsep', 'phase': 'D',
            'topic': 'Taubat',
            'jumlah_pertemuan': 2, 'jp_per_pertemuan': 2})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = json.loads(resp.data)
    ModuleStore(api_pipeline.db_path).save(
        body['generation_id'], body['module'],
        body['module'].get('curriculum_context') or {})
    return body['generation_id'], body['module']


class TestUnknownIdsStaySilent:
    def test_get_unknown_uuid_404(self, flask_client, api_pipeline):
        resp = flask_client.get(f'/api/module/{uuid.uuid4()}')
        assert resp.status_code == 404
        assert 'Taubat' not in resp.get_data(as_text=True)

    def test_put_unknown_uuid_404(self, flask_client, api_pipeline):
        resp = flask_client.put(f'/api/module/{uuid.uuid4()}',
                                json={'module': {'title': 'x'}})
        assert resp.status_code == 404

    def test_export_unknown_uuid_404(self, flask_client, api_pipeline):
        resp = flask_client.get(
            f'/api/module/{uuid.uuid4()}/export-docx')
        assert resp.status_code == 404

    def test_status_unknown_job_404(self, flask_client, api_pipeline):
        resp = flask_client.get(f'/api/generation/status/{uuid.uuid4()}')
        assert resp.status_code == 404

    def test_malformed_ids_400(self, flask_client, api_pipeline):
        assert flask_client.get('/api/module/...x').status_code == 400
        assert flask_client.put(
            '/api/module/...x', json={'module': {}}).status_code == 400
        assert flask_client.get(
            '/api/module/...x/export-docx').status_code == 400
        long_id = 'a' * 129
        assert flask_client.get(
            f'/api/module/{long_id}').status_code == 400


class TestGenerationIsolation:
    def test_other_generation_unreachable_without_id(
            self, flask_client, api_pipeline):
        gid, module = _generate_stored(flask_client, api_pipeline)
        other = str(uuid.uuid4())
        assert other != gid
        resp = flask_client.get(f'/api/module/{other}')
        assert resp.status_code == 404
        body = resp.get_data(as_text=True)
        assert module['title'] not in body
        assert 'Taubat' not in body

    def test_own_generation_reachable_with_id(
            self, flask_client, api_pipeline):
        gid, module = _generate_stored(flask_client, api_pipeline)
        resp = flask_client.get(f'/api/module/{gid}')
        assert resp.status_code == 200
        assert json.loads(resp.data)['module']['id'] == module['id']

    def test_export_other_without_id_404(
            self, flask_client, api_pipeline):
        gid, _module = _generate_stored(flask_client, api_pipeline)
        assert str(uuid.uuid4()) != gid
        resp = flask_client.get(
            f'/api/module/{uuid.uuid4()}/export-docx')
        assert resp.status_code == 404


class TestSecretHygiene:
    def test_api_key_never_in_error_responses(
            self, flask_client, api_pipeline, monkeypatch):
        monkeypatch.setenv('NINE_ROUTER_API_KEY', 'SECRET-XYZ-123')
        for resp in (
            flask_client.post('/api/context/generate', json={}),
            flask_client.post('/api/module/generate',
                              json={'topic': 'x' * 5000}),
            flask_client.get('/api/module/invalid..id'),
            flask_client.get(f'/api/module/{uuid.uuid4()}'),
        ):
            assert 'SECRET-XYZ-123' not in resp.get_data(as_text=True)

    def test_generation_logs_contain_no_raw_or_secret(
            self, flask_client, api_pipeline, monkeypatch):
        import app as app_module
        from module_store import GenerationLogStore
        monkeypatch.setenv('NINE_ROUTER_API_KEY', 'SECRET-XYZ-123')
        app_module.get_generation_pipeline().ai_client.config.api_key = \
            'SECRET-XYZ-123'
        gid, _module = _generate_stored(flask_client, api_pipeline)
        records = GenerationLogStore(
            api_pipeline.db_path).fetch(gid)
        assert records, 'expected audit rows'
        blob = json.dumps(records, ensure_ascii=False, default=str)
        assert 'SECRET-XYZ-123' not in blob
        assert 'Pengenalan materi taubat' not in blob
        assert 'Authorization' not in blob
        for record in records:
            assert 'prompt_version' in record
            assert 'error_category' in record or record['status'] == 'success'
