#!/usr/bin/env python3
"""Ubah jumlah pertemuan via kunci 'pertemuan' (versions-POST).

Tambah = kloning deterministik pertemuan terakhir (tanpa AI);
kurang = buang dari belakang. Budget waktu + prinsip overlap
tervalidasi battery produksi.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from test_versions_batch5 import _seed, api_pipeline  # noqa: F401,E402


def _simpan(flask_client, gid, base, changes):
    return flask_client.post(f'/api/module/{gid}/versions',
                             json={'base_version': base, 'changes': changes})


def _budget_ok(module):
    pakai = {}
    for a in module['learning_activities']:
        pakai[a['meeting']] = pakai.get(a['meeting'], 0) + a['duration']
    for m in module['meetings']:
        assert pakai.get(m['index'], 0) == m['minutes'], m['index']
    return pakai


class TestPertemuanCount:
    def test_tambah_kloning_terakhir(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        n0 = len(module['meetings'])
        last_acts = [a for a in module['learning_activities']
                     if a['meeting'] == n0]
        assert last_acts
        resp = _simpan(flask_client, gid, 1, {'pertemuan': {'n': n0 + 1}})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert body['changed_sections'] == ['aktivitas']
        mod = body['module']
        assert [m['index'] for m in mod['meetings']] == list(
            range(1, n0 + 2))
        baru = [a for a in mod['learning_activities']
                if a['meeting'] == n0 + 1]
        assert len(baru) == len(last_acts)
        assert len({a['id'] for a in mod['learning_activities']}) == len(
            mod['learning_activities'])
        _budget_ok(mod)
        # Prinsip pertemuan lama terbawa, baru kosong.
        assert mod['meetings'][0].get('principles')
        assert not mod['meetings'][-1].get('principles')

    def test_kurang_buang_belakang(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        n0 = len(module['meetings'])
        assert n0 >= 2
        resp = _simpan(flask_client, gid, 1, {'pertemuan': {'n': n0 - 1}})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        mod = json.loads(resp.data)['version']['module']
        assert [m['index'] for m in mod['meetings']] == list(
            range(1, n0))
        assert all(a['meeting'] <= n0 - 1
                   for a in mod['learning_activities'])
        _budget_ok(mod)

    @pytest.mark.parametrize('n', [0, 17, 'x', None, True])
    def test_n_invalid_400(self, flask_client, api_pipeline, n):
        gid, _module = _seed(flask_client, api_pipeline)
        resp = _simpan(flask_client, gid, 1, {'pertemuan': {'n': n}})
        assert resp.status_code == 400, resp.get_data(as_text=True)

    def test_n_sama_400(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        n0 = len(module['meetings'])
        resp = _simpan(flask_client, gid, 1, {'pertemuan': {'n': n0}})
        assert resp.status_code == 400, resp.get_data(as_text=True)

    def test_bukan_object_400(self, flask_client, api_pipeline):
        gid, _module = _seed(flask_client, api_pipeline)
        resp = _simpan(flask_client, gid, 1, {'pertemuan': 3})
        assert resp.status_code == 400, resp.get_data(as_text=True)
