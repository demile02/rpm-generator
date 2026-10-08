#!/usr/bin/env python3
"""Regresi: regen async aktivitas + n_meetings harus hasilkan draft.

Bug nyata (Okt 2026): frontend kirim {async, draft, n_meetings} dan
polling menunjukkan success, tapi hasil tidak pernah tampil — loading
tertutup dengan status basi. Penyebab: worker async tidak memakai
	flag draft (hasil jalan jalur sync_save tanpa draft_only), dan
frontend tidak guard payload tanpa version.module.
"""
import copy
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from test_versions_batch5 import (  # noqa: F401,E402
    _seed, api_pipeline, VALID_CONTEXT, ROWS_D, NEW_ACTS,
)


def _acts_merged(meetings_n):
    from test_phase_c_module_generation import mock_meeting_principles
    acts = []
    for i, row in enumerate(NEW_ACTS):
        a = dict(row)
        a['meeting'] = min(row['meeting'], meetings_n)
        acts.append(a)
    return {'activities': acts,
            'meeting_principles': mock_meeting_principles(meetings_n)}


class TestAsyncRegenDraft:
    def _async_regen(self, flask_client, api_pipeline, gid, base,
                     target, extra):
        from test_phase_c_module_generation import (
            fake_router_response, patch_pipeline_ai)

        def side_effect(prompt, system_instruction=None, **kwargs):
            if '"activities"' in prompt:
                return _acts_merged(extra.get('n_meetings', 2))
            return fake_router_response(
                prompt, system_instruction, **kwargs)

        with patch_pipeline_ai(api_pipeline, side_effect):
            resp = flask_client.post(
                f'/api/module/{gid}/regenerate',
                json=dict({'base_version': base, 'target': target,
                           'async': True, 'draft': True}, **extra))
        assert resp.status_code == 202, resp.get_data(as_text=True)
        job_id = json.loads(resp.data)['job_id']
        deadline = time.time() + 120
        while time.time() < deadline:
            poll = flask_client.get(f'/api/generation/status/{job_id}')
            body = json.loads(poll.data)
            if body.get('status') != 'running':
                return body
            time.sleep(1)
        pytest.fail('worker regen tidak selesai dalam 120 detik')

    def test_async_aktivitas_1_pertemuan_jadi_draft(
            self, flask_client, api_pipeline):
        gid, _module = _seed(flask_client, api_pipeline)
        body = self._async_regen(flask_client, api_pipeline, gid, 1,
                                 'aktivitas', {'n_meetings': 1})
        assert body['status'] == 'success', body
        assert body.get('draft') is True
        version = body.get('version') or {}
        module = version.get('module') or {}
        assert len(module.get('meetings') or []) == 1
        # Draft-only: tidak ada version baru tersimpan.
        hist = flask_client.get(f'/api/module/{gid}/versions')
        versions = json.loads(hist.data)['versions']
        assert [v['version_no'] for v in versions] == [1]
