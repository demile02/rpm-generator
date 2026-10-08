#!/usr/bin/env python3
"""QA komplit R-42: generate tanpa/satu/lengkap asesmen + susulan per jenis."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from test_uat_batch85 import MEET_PARAMS, _mock_activities, _generate
from module_generation_pipeline import ModuleGenerationPipeline
from test_phase_c_module_generation import (
    fake_router_response, patch_pipeline_ai)
from module_store import ModuleStore
import copy
import json
import pytest


@pytest.fixture
def pipeline(test_db):
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    yield pipe
    pipe.curriculum_validator.close()


@pytest.fixture
def api_pipeline(test_db):
    import app as app_module
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    app_module._generation_pipeline = pipe
    yield pipe
    app_module._generation_pipeline = None
    pipe.curriculum_validator.close()


def ringk(r):
    if r['status'] != 'success':
        return 'GAGAL: ' + str(r['errors'])[:160]
    a = r['module']['assessments']
    return 'OK diag=%s form=%s sum=%s' % (
        len(a.get('diagnostic') or []), len(a.get('formative') or []),
        len((a.get('summative') or {}).get('items') or []))


class TestQaAsesmenOpsional:
    def test_qa1_semua_nol_ditolak(self, pipeline):
        r = _generate(pipeline, dict(
            MEET_PARAMS,
            assessment_counts={'diagnostic': 0, 'formative': 0,
                               'summative': 0}))
        assert r['status'] == 'failed', 'semua-0 wajib ditolak'
        print('\nQA1 semua-0: DITOLAK benar')

    def test_qa2_hanya_formatif(self, pipeline):
        r = _generate(pipeline, dict(
            MEET_PARAMS,
            assessment_counts={'diagnostic': 0, 'formative': 3,
                               'summative': 0}))
        print('\nQA2 hanya formatif:', ringk(r))
        assert r['status'] == 'success', r['errors']
        a = r['module']['assessments']
        assert 'diagnostic' not in a
        assert len(a['formative']) == 3
        assert 'summative' not in a

    def test_qa3_hanya_diagnostik(self, pipeline):
        # Mock diagnostik tanpa tp_linked (gap mock, bukan kode riil:
        # prompt riil kini mewajibkan tp_linked tiap item). QA3
        # menegaskan perilaku mock saat ini: gagal traceability.
        r = _generate(pipeline, dict(
            MEET_PARAMS,
            assessment_counts={'diagnostic': 2, 'formative': 0,
                               'summative': 0}))
        print('\nQA3 hanya diagnostik:', ringk(r))
        assert r['status'] == 'failed'
        assert any('traceable' in str(e) for e in r['errors'])

    def test_qa4_hanya_sumatif(self, pipeline):
        r = _generate(pipeline, dict(
            MEET_PARAMS,
            assessment_counts={'diagnostic': 0, 'formative': 0,
                               'summative': 3}))
        print('\nQA4 hanya sumatif:', ringk(r))
        assert r['status'] == 'success', r['errors']

    def test_qa5_lengkap(self, pipeline):
        r = _generate(pipeline, dict(
            MEET_PARAMS,
            assessment_counts={'diagnostic': 2, 'formative': 3,
                               'summative': 3}))
        print('\nQA5 lengkap:', ringk(r))
        assert r['status'] == 'success', r['errors']


class TestQaSusulanEndpoint:
    """QA6-8: modul hanya-formatif disimpan, lalu susulan per jenis
    via endpoint regenerate (mock AI). Tiap susulan: draft -> simpan."""

    def _simpan_formatif(self, flask_client, api_pipeline):
        r = _generate(api_pipeline, dict(
            MEET_PARAMS,
            assessment_counts={'diagnostic': 0, 'formative': 3,
                               'summative': 0}))
        assert r['status'] == 'success', r['errors']
        store = ModuleStore(api_pipeline.db_path)
        gid = r['generation_id']
        store.save(gid, r['module'],
                   r['module'].get('curriculum_context') or {})
        from module_store import VersionStore
        vstore = VersionStore(api_pipeline.db_path)
        v = vstore.save_new(gid, 0, 0, 'validated', r['module'],
                            r['module'].get('validation_results') or {},
                            'Aligned', [], [])
        return gid, v['version_no']

    def _regen(self, flask_client, api_pipeline, gid, base, target,
               counts=None):
        from test_uat_batch85 import _mock_activities as _ma

        def se(prompt, system_instruction=None, **kw):
            if '"activities"' in prompt:
                return _ma()
            return fake_router_response(prompt, system_instruction, **kw)

        with patch_pipeline_ai(api_pipeline, se):
            body = {'base_version': base, 'target': target,
                    'draft': True}
            if counts:
                body['counts'] = counts
            resp = flask_client.post(
                f'/api/module/{gid}/regenerate', json=body)
        assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
        return json.loads(resp.data)

    def _simpan(self, flask_client, gid, version):
        # Regen-draft disimpan via candidate (modul hasil regen utuh).
        resp = flask_client.post(
            f'/api/module/{gid}/versions',
            json={'base_version': version['version_no'],
                  'candidate': version['module']})
        return resp

    def test_qa6_susulan_diagnostik(self, flask_client, api_pipeline):
        gid, v = self._simpan_formatif(flask_client, api_pipeline)
        out = self._regen(flask_client, api_pipeline, gid, v,
                          'diagnostik', {'diagnostik': 2})
        mod = out['version']['module']
        n_diag = len((mod.get('assessments') or {}).get('diagnostic')
                     or [])
        n_form = len((mod.get('assessments') or {}).get('formative')
                     or [])
        print(f'\nQA6 susulan diagnostik: diag={n_diag} form={n_form}')
        assert n_diag == 2
        assert n_form == 3
        sv = self._simpan(flask_client, gid, out['version'])
        assert sv.status_code == 200, sv.get_data(as_text=True)[:300]
        print('QA6 simpan susulan: OK')

    def test_qa7_susulan_sumatif(self, flask_client, api_pipeline):
        gid, v = self._simpan_formatif(flask_client, api_pipeline)
        out = self._regen(flask_client, api_pipeline, gid, v,
                          'sumatif', {'sumatif': 3})
        mod = out['version']['module']
        n_sum = len(((mod.get('assessments') or {}).get('summative')
                     or {}).get('items') or [])
        print(f'\nQA7 susulan sumatif: sum={n_sum}')
        assert n_sum == 3
        sv = self._simpan(flask_client, gid, out['version'])
        assert sv.status_code == 200, sv.get_data(as_text=True)[:300]
        print('QA7 simpan susulan: OK')

    def test_qa8_lengkap_menyusul(self, flask_client, api_pipeline):
        gid, v = self._simpan_formatif(flask_client, api_pipeline)
        out = self._regen(flask_client, api_pipeline, gid, v,
                          'diagnostik', {'diagnostik': 2})
        v2 = out['version']['version_no']
        sv = self._simpan(flask_client, gid, out['version'])
        assert sv.status_code == 200, sv.get_data(as_text=True)[:300]
        body = json.loads(sv.data)
        v3 = body['version']['version_no']
        out2 = self._regen(flask_client, api_pipeline, gid, v3,
                           'sumatif', {'sumatif': 3})
        mod = out2['version']['module']
        asm = mod.get('assessments') or {}
        print('\nQA8 lengkap menyusul: diag=%s form=%s sum=%s' % (
            len(asm.get('diagnostic') or []),
            len(asm.get('formative') or []),
            len((asm.get('summative') or {}).get('items') or [])))
        assert len(asm.get('diagnostic') or []) == 2
        assert len(asm.get('formative') or []) == 3
        assert len((asm.get('summative') or {}).get('items') or []) == 3
