#!/usr/bin/env python3
"""Batch 4A: DELETE /api/modules/<generation_id> — bulk delete riwayat.

Hapus beneran di persistence (generated_modules + module_versions),
tanpa ubah schema. Log generasi (audit) dipertahankan.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from test_versions_batch5 import _save, _seed, api_pipeline  # noqa: F401,E402


def _hapus(flask_client, gid):
    return flask_client.delete('/api/modules/%s' % gid)


def _daftar(flask_client):
    resp = flask_client.get('/api/modules')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return json.loads(resp.data)['modules']


class TestBulkDelete:
    def test_hapus_sukses_hilang_dari_riwayat(self, flask_client,
                                              api_pipeline):
        gid, _ = _seed(flask_client, api_pipeline)
        resp = _hapus(flask_client, gid)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['status'] == 'success'
        assert body['deleted'] is True
        gids = [m['generation_id'] for m in _daftar(flask_client)]
        assert gid not in gids

    def test_hapus_juga_menghapus_versions(self, flask_client,
                                           api_pipeline):
        gid, _ = _seed(flask_client, api_pipeline)
        resp = _save(flask_client, gid, 1, {'topic': 'Topik edit guru'})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        resp = _hapus(flask_client, gid)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        # Modul dan versinya tidak lagi dapat dibuka.
        assert flask_client.get(
            '/api/module/%s' % gid).status_code == 404
        assert flask_client.get(
            '/api/module/%s/versions' % gid).status_code == 404

    def test_hapus_tidak_ada_404(self, flask_client, api_pipeline):
        resp = _hapus(flask_client, '00000000-0000-4000-8000-000000000000')
        assert resp.status_code == 404, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['status'] == 'error'

    def test_hapus_id_malformed_400(self, flask_client, api_pipeline):
        resp = _hapus(flask_client, 'x' * 200)
        assert resp.status_code == 400, resp.get_data(as_text=True)

    def test_hapus_satu_lainnya_bertahan(self, flask_client,
                                         api_pipeline):
        gid1, _ = _seed(flask_client, api_pipeline)
        gid2, _ = _seed(flask_client, api_pipeline)
        assert _hapus(flask_client, gid1).status_code == 200
        gids = [m['generation_id'] for m in _daftar(flask_client)]
        assert gid1 not in gids
        assert gid2 in gids

    def test_hapus_tidak_mengubah_schema(self, flask_client,
                                         api_pipeline):
        import sqlite3
        conn = sqlite3.connect(api_pipeline.db_path)
        try:
            tabel = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        assert 'generated_modules' in tabel
        assert 'module_versions' in tabel
