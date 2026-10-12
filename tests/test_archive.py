#!/usr/bin/env python3
"""Arsip RPM (R-38..R-40): flag DB, baris+versi+log utuh, auto-arsip upload.

- Arsip/kembalikan: hanya flag archived (modul tetap bisa dibuka).
- Hapus massal ikut hapus arsip.
- Upload judul sama: yang lama otomatis terarsip (tidak nabrak).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from test_versions_batch5 import _seed, api_pipeline  # noqa: F401,E402


def _daftar(flask_client):
    resp = flask_client.get('/api/modules')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return {m['generation_id']: m
            for m in json.loads(resp.data)['modules']}


class TestArchiveFlag:
    def test_arsip_lalu_kembalikan(self, flask_client, api_pipeline):
        gid, _ = _seed(flask_client, api_pipeline)
        assert _daftar(flask_client)[gid]['archived'] is False
        resp = flask_client.post(f'/api/modules/{gid}/archive')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert json.loads(resp.data)['archived'] is True
        assert _daftar(flask_client)[gid]['archived'] is True
        # Modul arsip tetap bisa dibuka.
        assert flask_client.get(f'/api/module/{gid}').status_code == 200
        resp = flask_client.post(f'/api/modules/{gid}/unarchive')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert _daftar(flask_client)[gid]['archived'] is False

    def test_arsip_tidak_ada_404(self, flask_client, api_pipeline):
        assert flask_client.post(
            '/api/modules/00000000-0000-4000-8000-'
            '000000000000/archive').status_code == 404

    def test_arsip_malformed_400(self, flask_client, api_pipeline):
        assert flask_client.post(
            '/api/modules/../archive').status_code == 400

    def test_hapus_ikut_hapus_arsip(self, flask_client, api_pipeline):
        gid, _ = _seed(flask_client, api_pipeline)
        assert flask_client.post(
            f'/api/modules/{gid}/archive').status_code == 200
        assert flask_client.delete(
            f'/api/modules/{gid}').status_code == 200
        assert gid not in _daftar(flask_client)


class TestAutoArchiveUpload:
    def test_judul_sama_otomatis_arsip(self, flask_client, api_pipeline):
        # Logika auto-arsip (find_active_by_title + set_archived):
        # dua modul judul sama, yang lama terarsip, yang baru aktif.
        from module_store import ModuleStore
        import copy
        gid1, mod1 = _seed(flask_client, api_pipeline)
        store = ModuleStore(api_pipeline.db_path)
        gid2 = '11111111-1111-4111-8111-111111111111'
        mod2 = copy.deepcopy(mod1)
        mod2['generation_id'] = gid2
        mod2['id'] = gid2
        store.save(gid2, mod2, mod2.get('curriculum_context') or {})
        assert store.find_active_by_title(
            mod2.get('title') or '', exclude_id=gid2) == [gid1]
        assert store.set_archived(gid1, True) is True
        rows = _daftar(flask_client)
        assert rows[gid1]['archived'] is True
        assert rows[gid2]['archived'] is False
