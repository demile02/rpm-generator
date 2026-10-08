#!/usr/bin/env python3
"""Log generate: GET /api/generations + detail per generation.

Read-only atas generation_logs (audit trail AI): daftar ringkasan
per generation_id terbaru dulu (termasuk generate gagal), dan detail
record stage-attempt satu generate. Tanpa raw prompt/response (memang
tidak disimpan), tanpa API key/secret.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from module_store import GenerationLogStore  # noqa: E402
from test_versions_batch5 import api_pipeline  # noqa: F401,E402


def _rec(gid, stage, status, attempt=1, err=None):
    return {'generation_id': gid, 'stage': stage, 'attempt': attempt,
            'prompt_version': '1.0', 'prompt_hash': 'h', 'model': 'rpm',
            'provider': '9router', 'status': status,
            'error_category': err, 'error': err or '',
            'duration_ms': 1.0, 'response_chars': 10, 'empty_flag': 0,
            'truncated_flag': 0, 'output_tokens': 5, 'is_retry': 0}


def _seed_logs(api_pipeline):
    store = GenerationLogStore(api_pipeline.db_path)
    store.save_records([
        _rec('g-ok', 'tp', 'success'),
        _rec('g-ok', 'final', 'success'),
        _rec('g-fail', 'tp', 'success'),
        _rec('g-fail', 'activities', 'failed', attempt=2,
             err='validation'),
    ])
    return store


class TestGenerationsList:
    def test_sukses_dan_gagal_terdaftar(self, flask_client, api_pipeline):
        _seed_logs(api_pipeline)
        resp = flask_client.get('/api/generations')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['status'] == 'success'
        rows = {g['generation_id']: g for g in body['generations']}
        assert rows['g-ok']['status'] == 'success'
        assert rows['g-fail']['status'] == 'partial'
        assert rows['g-fail']['error_categories'] == ['validation']
        assert 'tp' in rows['g-fail']['stages']
        assert rows['g-fail']['attempts'] == 2

    def test_gagal_total_status_failed(self, flask_client, api_pipeline):
        GenerationLogStore(api_pipeline.db_path).save_records([
            _rec('g-dead', 'tp', 'failed', err='transport')])
        resp = flask_client.get('/api/generations')
        rows = {g['generation_id']: g
                for g in json.loads(resp.data)['generations']}
        assert rows['g-dead']['status'] == 'failed'

    def test_shape_ringkas(self, flask_client, api_pipeline):
        _seed_logs(api_pipeline)
        body = json.loads(flask_client.get('/api/generations').data)
        for row in body['generations']:
            for key in ('generation_id', 'status', 'stages', 'attempts',
                        'error_categories', 'started_at', 'updated_at'):
                assert key in row, key

    def test_kosong_tetap_sukses(self, flask_client, api_pipeline):
        import sqlite3
        conn = sqlite3.connect(api_pipeline.db_path)
        conn.execute('DELETE FROM generation_logs')
        conn.commit()
        conn.close()
        resp = flask_client.get('/api/generations')
        assert resp.status_code == 200
        assert json.loads(resp.data)['generations'] == []


class TestGenerationDetail:
    def test_detail_urut_waktu(self, flask_client, api_pipeline):
        _seed_logs(api_pipeline)
        resp = flask_client.get('/api/generations/g-fail')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['generation_id'] == 'g-fail'
        assert [r['stage'] for r in body['records']] == [
            'tp', 'activities']
        assert body['records'][1]['error_category'] == 'validation'

    def test_unknown_404(self, flask_client, api_pipeline):
        resp = flask_client.get('/api/generations/tidak-ada')
        assert resp.status_code == 404

    def test_malformed_400(self, flask_client, api_pipeline):
        assert flask_client.get('/api/generations/..').status_code == 400
