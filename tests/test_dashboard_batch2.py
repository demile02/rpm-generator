#!/usr/bin/env python3
"""Batch 2: GET /api/modules — riwayat RPM Beranda (read-only).

Hanya RPM tersimpan (sukses) yang tampil, terbaru dulu; generasi
gagal tidak pernah masuk history.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from test_versions_batch5 import _save, _seed, api_pipeline  # noqa: F401,E402


def _modules(flask_client):
    resp = flask_client.get('/api/modules')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = json.loads(resp.data)
    assert body['status'] == 'success'
    return body['modules']


class TestModulesList:
    def test_berhasil_masuk_history(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        modules = _modules(flask_client)
        rows = [m for m in modules if m['generation_id'] == gid]
        assert len(rows) == 1
        row = rows[0]
        assert row['title'] == module['title']
        assert row['subject'] == module['subject']
        assert row['updated_at']
        assert row['status'] in ('validated', 'finalized', 'draft')

    def test_terbaru_dulu_dan_tanpa_duplikat(self, flask_client,
                                             api_pipeline):
        gid1, _ = _seed(flask_client, api_pipeline)
        gid2, _ = _seed(flask_client, api_pipeline)
        modules = _modules(flask_client)
        gids = [m['generation_id'] for m in modules]
        assert gids[0] == gid2 and gid1 in gids
        assert len(set(gids)) == len(gids)
        # Save versi baru pada gid1: tetap satu card, status ikut versi.
        resp = _save(flask_client, gid1, 1, {'topic': 'Topik edit guru'})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        modules = _modules(flask_client)
        gids = [m['generation_id'] for m in modules]
        assert len(set(gids)) == len(gids)
        assert gids.count(gid1) == 1

    def test_gagal_tidak_masuk_history(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        from module_generation_pipeline import ModuleGenerationPipeline
        pipe = api_pipeline
        with patch_pipeline_ai(pipe, fake_router_response):
            bad = pipe.generate({'education_system': 'KEMENAG',
                                 'institution_type': 'MTs',
                                 'grade': 'MTs_99',
                                 'subject': 'Akidah Akhlak',
                                 'topic': 'Taubat'})
        assert bad['status'] == 'failed'
        modules = _modules(flask_client)
        assert all(m['generation_id'] != bad['generation_id']
                   for m in modules)

    def test_unknown_route_shape(self, flask_client, api_pipeline):
        resp = flask_client.get('/api/modules')
        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert isinstance(body['modules'], list)
        for row in body['modules']:
            for key in ('generation_id', 'title', 'subject', 'grade',
                        'phase', 'updated_at', 'status', 'latest_version'):
                assert key in row, key
