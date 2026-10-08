#!/usr/bin/env python3
"""Hapus permanen: audit log generate + satu riwayat versi.

Keputusan user:
- Hapus log = hanya baris audit generation_logs (modul riwayat tetap).
- Hapus versi = per-baris di modul terbuka; versi terakhir dilindungi.
- Keduanya lewat dialog konfirmasi (di UI) + popup hasil.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from module_store import GenerationLogStore  # noqa: E402
from test_log_generations import _rec, _seed_logs  # noqa: E402,F401
from test_versions_batch5 import _save, _seed, api_pipeline  # noqa: F401,E402


class TestDeleteLog:
    def test_hapus_satu_hilang_dari_daftar(
            self, flask_client, api_pipeline):
        _seed_logs(api_pipeline)
        resp = flask_client.delete('/api/generations/g-fail')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['deleted'] is True
        rows = {g['generation_id']: g
                for g in json.loads(
                    flask_client.get('/api/generations').data
                )['generations']}
        assert 'g-fail' not in rows
        assert 'g-ok' in rows

    def test_hapus_tidak_ada_404(self, flask_client, api_pipeline):
        resp = flask_client.delete('/api/generations/nope')
        assert resp.status_code == 404

    def test_hapus_malformed_400(self, flask_client, api_pipeline):
        assert flask_client.delete('/api/generations/..').status_code \
            == 400

    def test_hapus_log_modul_tetap(self, flask_client, api_pipeline):
        gid, _ = _seed(flask_client, api_pipeline)
        GenerationLogStore(api_pipeline.db_path).save_records([
            _rec(gid, 'tp', 'success'), _rec(gid, 'final', 'success')])
        assert flask_client.delete(
            f'/api/generations/{gid}').status_code == 200
        # Modul riwayat tetap bisa dibuka.
        assert flask_client.get(f'/api/module/{gid}').status_code == 200

    def test_hapus_bulk(self, flask_client, api_pipeline):
        _seed_logs(api_pipeline)
        resp = flask_client.delete(
            '/api/generations',
            json={'generation_ids': ['g-ok', 'g-fail', 'hilang']})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert sorted(body['deleted']) == ['g-fail', 'g-ok']
        assert body['missing'] == ['hilang']
        rows = {g['generation_id']: g
                for g in json.loads(
                    flask_client.get('/api/generations').data
                )['generations']}
        assert 'g-ok' not in rows
        assert 'g-fail' not in rows
        # Baris audit lain (dari DB produksi bawaan fixture) tak ikut
        # terhapus: hanya target yang hilang.
        assert GenerationLogStore(
            api_pipeline.db_path).fetch('g-ok') == []
        assert GenerationLogStore(
            api_pipeline.db_path).fetch('g-fail') == []

    def test_hapus_bulk_kosong_400(self, flask_client, api_pipeline):
        assert flask_client.delete(
            '/api/generations',
            json={'generation_ids': []}).status_code == 400


class TestDeleteVersion:
    def _dua_versi(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        tp = [dict(t) for t in module['learning_objectives']]
        tp[0]['text'] = ('Menerapkan konsep taubat nasuha dalam '
                         'kehidupan sehari-hari dengan konsisten')
        resp = _save(flask_client, gid, 1, {
            'tp': [{'id': t['id'], 'text': t['text']} for t in tp]})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        return gid

    def test_hapus_satu_versi(self, flask_client, api_pipeline):
        gid = self._dua_versi(flask_client, api_pipeline)
        resp = flask_client.delete(f'/api/module/{gid}/versions/1')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)
        assert body['deleted_version'] == 1
        assert body['latest_version'] == 2
        # v1 tak lagi bisa dibuka, v2 masih bisa.
        assert flask_client.get(
            f'/api/module/{gid}/versions/1').status_code == 404
        assert flask_client.get(
            f'/api/module/{gid}/versions/2').status_code == 200

    def test_versi_terakhir_dilindungi(self, flask_client, api_pipeline):
        gid = self._dua_versi(flask_client, api_pipeline)
        # Hapus v1 dulu -> sisa v2 satu-satunya -> hapus v2 ditolak.
        assert flask_client.delete(
            f'/api/module/{gid}/versions/1').status_code == 200
        resp = flask_client.delete(f'/api/module/{gid}/versions/2')
        assert resp.status_code == 422, resp.get_data(as_text=True)
        assert json.loads(resp.data)['errors'][0]['code'] == \
            'LAST_VERSION_PROTECTED'
        # Modul tetap utuh.
        assert flask_client.get(f'/api/module/{gid}').status_code == 200

    def test_versi_tak_ada_404(self, flask_client, api_pipeline):
        gid = self._dua_versi(flask_client, api_pipeline)
        assert flask_client.delete(
            f'/api/module/{gid}/versions/9').status_code == 404

    def test_hapus_dua_sisa_satu_lalu_tolak(
            self, flask_client, api_pipeline):
        gid = self._dua_versi(flask_client, api_pipeline)
        assert flask_client.delete(
            f'/api/module/{gid}/versions/1').status_code == 200
        resp = flask_client.delete(f'/api/module/{gid}/versions/2')
        assert resp.status_code == 422
