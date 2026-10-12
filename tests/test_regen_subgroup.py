#!/usr/bin/env python3
"""Regen sub-bucket asesmen: diagnostik/formatif/sumatif terpisah.

AI di-mock; validator + versioning + merge adalah kode produksi.
Hanya bucket diminta yang diganti; bucket lain dipertahankan.
"""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from test_versions_batch5 import _seed, api_pipeline  # noqa: F401,E402


def _subgroup_mock(bucket, mark):
    """Mock AI: hanya bucket target yang ditandai, sisanya fake normal."""
    from test_phase_c_module_generation import (
        fake_router_response, patch_pipeline_ai  # noqa: F401
    )

    def side_effect(prompt, system_instruction=None, **kwargs):
        resp = fake_router_response(prompt, system_instruction, **kwargs)
        if '"diagnostic"' in prompt and isinstance(resp, dict):
            resp = copy.deepcopy(resp)
            items = resp.get(bucket)
            if isinstance(items, dict):
                items = items.get('items')
            if isinstance(items, list) and items:
                first = dict(items[0])
                first['question'] = first.get('question', '') + mark
                items[0] = first
                if isinstance(resp.get(bucket), dict):
                    resp[bucket] = dict(resp[bucket], items=items)
                else:
                    resp[bucket] = items
            return resp
        return resp

    return side_effect


def _regen(flask_client, api_pipeline, target, mock):
    from test_phase_c_module_generation import patch_pipeline_ai
    gid, _module = _seed(flask_client, api_pipeline)
    with patch_pipeline_ai(api_pipeline, mock):
        resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                 json={'base_version': 1, 'target': target})
    return gid, resp


def _assessments_of(flask_client, gid):
    resp = flask_client.get(f'/api/module/{gid}')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return json.loads(resp.data)['module']['assessments']


class TestSubgroupRegen:
    @pytest.mark.parametrize('target,bucket', [
        ('diagnostik', 'diagnostic'),
        ('formatif', 'formative'),
        ('sumatif', 'summative'),
    ])
    def test_subgroup_mengganti_hanya_bucketnya(
            self, flask_client, api_pipeline, target, bucket):
        from test_phase_c_module_generation import patch_pipeline_ai  # noqa
        gid, _module = _seed(flask_client, api_pipeline)
        old = _assessments_of(flask_client, gid)

        def _old_items(key):
            val = old.get(key)
            if isinstance(val, dict):
                return val.get('items')
            return val

        with patch_pipeline_ai(
                api_pipeline, _subgroup_mock(bucket, ' (regen-%s)' % target)):
            resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                     json={'base_version': 1,
                                           'target': target})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert body['changed_sections'] == [target]
        new_asm = body['module']['assessments']

        def _new_items(key):
            val = new_asm.get(key)
            if isinstance(val, dict):
                return val.get('items')
            return val

        # Bucket target berubah (bertanda), jumlah sama.
        assert len(_new_items(bucket)) == len(_old_items(bucket))
        assert '(regen-%s)' % target in _new_items(bucket)[0]['question']
        # Bucket lain utuh.
        for key in ('diagnostic', 'formative', 'summative'):
            if key != bucket:
                assert _new_items(key) == _old_items(key), key

    def test_diagnostik_invalid_tanpa_version_baru(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)
        from module_store import VersionStore
        from module_store import VersionStore
        gid, _module = _seed(flask_client, api_pipeline)

        def garbage(prompt, system_instruction=None, **kwargs):
            if '"diagnostic"' in prompt:
                resp = fake_router_response(
                    prompt, system_instruction, **kwargs)
                resp = copy.deepcopy(resp)
                bad = dict(resp['diagnostic'][0])
                bad.pop('options', None)
                bad.pop('correct_answer', None)
                resp['diagnostic'][0] = bad
                return resp
            return fake_router_response(
                prompt, system_instruction, **kwargs)

        with patch_pipeline_ai(api_pipeline, garbage):
            resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                     json={'base_version': 1,
                                           'target': 'diagnostik'})
        assert resp.status_code == 422, resp.get_data(as_text=True)
        assert [h['version_no'] for h in
                VersionStore(api_pipeline.db_path).history(gid)] == [1]

    def test_counts_override_jumlah_bucket(self, flask_client,
                                           api_pipeline):
        from test_phase_c_module_generation import patch_pipeline_ai
        gid, _module = _seed(flask_client, api_pipeline)
        old = _assessments_of(flask_client, gid)
        with patch_pipeline_ai(
                api_pipeline,
                _subgroup_mock('diagnostic', ' (regen-count)')):
            resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                     json={'base_version': 1,
                                           'target': 'diagnostik',
                                           'counts': {'diagnostik': 3}})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        new_asm = json.loads(resp.data)['version']['module']['assessments']
        assert len(new_asm['diagnostic']) == 3
        assert '(regen-count)' in new_asm['diagnostic'][0]['question']
        assert new_asm['formative'] == old['formative']
        assert new_asm['summative'] == old['summative']

    @pytest.mark.parametrize('counts', [
        {'diagnostik': 0},
        {'diagnostik': 31},
        {'diagnostik': 'banyak'},
        {'formatif': True},
        {'salah': 5},
        ['diagnostik'],
    ])
    def test_counts_invalid_400(self, flask_client, api_pipeline,
                               counts):
        gid, _module = _seed(flask_client, api_pipeline)
        resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                 json={'base_version': 1,
                                       'target': 'diagnostik',
                                       'counts': counts})
        assert resp.status_code == 400, resp.get_data(as_text=True)
