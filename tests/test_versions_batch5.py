#!/usr/bin/env python3
"""Batch 5 §15: editing, versioning, partial regen, validation, export.

Seluruh AI di-mock (fakta integrasi real dibuktikan E2E terpisah);
validator yang diuji adalah validator produksi yang sama.
"""
import copy
import json
import sys
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

NEW_ACTS = [
    {'name': 'Apersepsi baru', 'description': 'Siswa menyimak dalil baru '
     'tentang taubat lalu berbagi pengalaman dalam suasana aman.',
     'duration': 15, 'experience': 'memahami', 'tp_linked': 'TP-1',
     'stage': 'Pembuka', 'meeting': 1},
    {'name': 'Diskusi konsep baru', 'description': 'Kelompok menganalisis '
     'pengertian taubat melalui kartu informasi dan menyusun peta konsep.',
     'duration': 35, 'experience': 'memahami', 'tp_linked': 'TP-1',
     'stage': 'Inti', 'meeting': 1},
    {'name': 'Sortir baru', 'description': 'Siswa mengurutkan kartu tindakan '
     'dan mencocokkannya dengan langkah taubat nasuha yang benar.',
     'duration': 30, 'experience': 'mengaplikasi', 'tp_linked': 'TP-2',
     'stage': 'Inti', 'meeting': 1},
    {'name': 'Pembuka dua baru', 'description': 'Siswa mengikuti kuis cepat '
     'tentang langkah taubat sebelum masuk kegiatan inti kedua.',
     'duration': 15, 'experience': 'mengaplikasi', 'tp_linked': 'TP-2',
     'stage': 'Pembuka', 'meeting': 2},
    {'name': 'Simulasi baru', 'description': 'Kelompok memerankan kasus '
     'pelanggaran lalu menunjukkan proses taubat melalui dialog.',
     'duration': 35, 'experience': 'mengaplikasi', 'tp_linked': 'TP-3',
     'stage': 'Inti', 'meeting': 2},
    {'name': 'Refleksi baru', 'description': 'Siswa menulis refleksi pribadi '
     'dan menutup pembelajaran dengan doa bersama.',
     'duration': 30, 'experience': 'merefleksi', 'tp_linked': 'TP-3',
     'stage': 'Penutup', 'meeting': 2},
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


def _seed(flask_client, api_pipeline):
    """Generasi mock penuh + simpan; return generation_id."""
    import app as app_module
    from test_phase_c_module_generation import (
        fake_router_response, patch_pipeline_ai)
    from module_store import ModuleStore
    assert flask_client.post(
        '/api/context/generate', json=dict(VALID_CONTEXT)).status_code == 200

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


def _save(flask_client, gid, base, changes):
    return flask_client.post(f'/api/module/{gid}/versions',
                             json={'base_version': base, 'changes': changes})


class TestEditing:
    def test_edit_single_field_v2_validated(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        tp = [dict(t) for t in module['learning_objectives']]
        tp[0]['text'] = ('Menerapkan konsep taubat nasuha dalam kehidupan '
                         'sehari-hari dengan konsisten')
        resp = _save(flask_client, gid, 1,
                     {'tp': [{'id': t['id'], 'text': t['text']} for t in tp]})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert body['version_no'] == 2
        assert body['parent_version_no'] == 1
        assert body['status'] == 'validated'
        assert body['alignment_status'] == 'Aligned'
        assert body['changed_sections'] == ['tp']
        assert body['module']['learning_objectives'][0]['text'].startswith(
            'Menerapkan konsep taubat nasuha')

    def test_edit_multiple_fields(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        resp = _save(flask_client, gid, 1, {
            'meta': {'penyusun': 'Ibu Guru Baru'},
            'readiness': {'student_readiness': 'Hasil observasi: murid paham.'},
        })
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert sorted(body['changed_sections']) == ['meta', 'readiness']
        assert body['module']['penyusun'] == 'Ibu Guru Baru'

    def test_refresh_reads_latest_version(self, flask_client, api_pipeline):
        """Refresh harus membuka version terbaru, bukan baseline generate."""
        gid, _module = _seed(flask_client, api_pipeline)
        resp = _save(flask_client, gid, 1,
                     {'meta': {'penyusun': 'Perubahan tersimpan'}})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        latest = json.loads(resp.data)['version']
        opened = flask_client.get(f'/api/module/{gid}')
        assert opened.status_code == 200, opened.get_data(as_text=True)
        body = json.loads(opened.data)
        assert body['version_no'] == latest['version_no']
        assert body['module']['penyusun'] == 'Perubahan tersimpan'

    def test_protected_section_rejected_400(self, flask_client, api_pipeline):
        gid, _module = _seed(flask_client, api_pipeline)
        resp = _save(flask_client, gid, 1, {'cp': {'text': 'CP palsu'}})
        assert resp.status_code == 400
        resp2 = _save(flask_client, gid, 1,
                      {'curriculum_context': {'phase': 'F'}})
        assert resp2.status_code == 400

    def test_unknown_section_rejected_400(self, flask_client, api_pipeline):
        gid, _module = _seed(flask_client, api_pipeline)
        resp = _save(flask_client, gid, 1, {'judul': 'x'})
        assert resp.status_code == 400

    def test_tp_id_set_must_match(self, flask_client, api_pipeline):
        gid, _module = _seed(flask_client, api_pipeline)
        resp = _save(flask_client, gid, 1, {
            'tp': [{'id': 'TP-1', 'text': 'Menerapkan taubat setiap hari'}]})
        assert resp.status_code == 400

    def test_c1_tp_edit_rejected_422(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        tp = [dict(t) for t in module['learning_objectives']]
        tp[0]['text'] = 'Menyebutkan pengertian taubat'
        resp = _save(flask_client, gid, 1,
                     {'tp': [{'id': t['id'], 'text': t['text']} for t in tp]})
        assert resp.status_code == 422
        assert 'TP_LEVEL_INVALID' in resp.get_data(as_text=True)

    def test_stale_base_rejected_409_no_overwrite(
            self, flask_client, api_pipeline):
        from module_store import VersionStore
        gid, module = _seed(flask_client, api_pipeline)
        tp = [dict(t) for t in module['learning_objectives']]
        tp[0]['text'] = 'Menerapkan taubat dalam kehidupan sehari-hari'
        assert _save(flask_client, gid, 1, {
            'tp': [{'id': t['id'], 'text': t['text']} for t in tp]
        }).status_code == 200
        # Basis v1 kini basi (latest v2) -> 409, tanpa overwrite.
        tp[1]['text'] = 'Menganalisis taubat dalam kehidupan modern'
        resp = _save(flask_client, gid, 1, {
            'tp': [{'id': t['id'], 'text': t['text']} for t in tp]})
        assert resp.status_code == 409
        assert 'STALE_VERSION' in resp.get_data(as_text=True)
        hist = VersionStore(api_pipeline.db_path).history(gid)
        assert [h['version_no'] for h in hist] == [1, 2]
        latest = VersionStore(api_pipeline.db_path).latest(gid)
        assert latest['module']['learning_objectives'][1]['text'] != \
            'Menganalisis taubat dalam kehidupan modern'

    def test_needs_review_draft_on_misalignment(
            self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        # Hapus seluruh aktivitas mengaplikasi -> pengalaman kosong
        # (alignment), bukan struktural -> draft Needs-review.
        acts = [dict(a) for a in module['learning_activities']
                if a.get('experience') != 'mengaplikasi']
        assert acts, 'fixture membutuhkan aktivitas non-mengaplikasi'
        payload = []
        for i, a in enumerate(acts):
            payload.append({
                'id': a.get('id') or f'ACT-{i}', 'name': a['name'],
                'description': a['description'], 'duration': a['duration'],
                'tp_linked': a.get('tp_linked') or 'TP-1',
                'experience': a['experience'], 'stage': a['stage'],
                'meeting': a['meeting']})
        # Budget tetap valid: pertemuan 1 (satu aktivitas) -> 80 mnt,
        # pertemuan 2 (dua aktivitas) -> 40+40 mnt. Yang diuji hanya
        # misalignment pengalaman (soft), bukan budget (hard).
        for item in payload:
            if item['meeting'] == 1:
                item['duration'] = 80
            else:
                item['duration'] = 40
        resp = _save(flask_client, gid, 1, {'aktivitas': payload})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert body['status'] == 'draft'
        assert body['alignment_status'] == 'Needs review'

    def test_factuality_gate_active_on_edit(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        asm = copy.deepcopy(module['assessments'])
        asm['formative'][0]['question'] += ' Sesuai PP No. 99 Tahun 2099.'
        resp = _save(flask_client, gid, 1, {'asesmen': asm})
        assert resp.status_code == 422
        assert 'REGULATORY_CLAIM_UNVERIFIED' in resp.get_data(as_text=True)

    def test_time_budget_active_on_edit(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        acts = []
        for i, a in enumerate(module['learning_activities']):
            acts.append({
                'id': a.get('id') or f'ACT-{i}', 'name': a['name'],
                'description': a['description'],
                'duration': 5, 'tp_linked': a.get('tp_linked') or 'TP-1',
                'experience': a['experience'], 'stage': a['stage'],
                'meeting': a['meeting']})
        resp = _save(flask_client, gid, 1, {'aktivitas': acts})
        assert resp.status_code == 422
        assert 'TIME_BUDGET_INVALID' in resp.get_data(as_text=True)


class TestVersioning:
    def _chain(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        tp = [dict(t) for t in module['learning_objectives']]
        tp[0]['text'] = 'Menerapkan taubat dalam kehidupan sehari-hari'
        r2 = _save(flask_client, gid, 1, {
            'tp': [{'id': t['id'], 'text': t['text']} for t in tp]})
        assert r2.status_code == 200, r2.get_data(as_text=True)
        r3 = _save(flask_client, gid, 2, {'meta': {'penyusun': 'Guru B'}})
        assert r3.status_code == 200, r3.get_data(as_text=True)
        return gid

    def test_chain_parents_and_history(self, flask_client, api_pipeline):
        from module_store import VersionStore
        gid = self._chain(flask_client, api_pipeline)
        hist = VersionStore(api_pipeline.db_path).history(gid)
        assert [(h['version_no'], h['parent_version_no'], h['status'])
                for h in hist] == [(1, None, 'validated'),
                                   (2, 1, 'validated'),
                                   (3, 2, 'validated')]

    def test_old_versions_immutable(self, flask_client, api_pipeline):
        from module_store import VersionStore
        gid = self._chain(flask_client, api_pipeline)
        v1_before = VersionStore(api_pipeline.db_path).get(gid, 1)
        text_before = v1_before['module']['learning_objectives'][0]['text']
        assert 'Menerapkan taubat dalam kehidupan' not in text_before
        v1_after = VersionStore(api_pipeline.db_path).get(gid, 1)
        assert v1_after['module']['learning_objectives'][0]['text'] == \
            text_before

    def test_restore_creates_new_version(self, flask_client, api_pipeline):
        from module_store import VersionStore
        gid = self._chain(flask_client, api_pipeline)
        resp = flask_client.post(f'/api/module/{gid}/versions/1/restore')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert body['version_no'] == 4
        assert body['parent_version_no'] == 1
        assert [h['version_no'] for h in
                VersionStore(api_pipeline.db_path).history(gid)] == [1, 2, 3, 4]

    def test_restore_missing_404(self, flask_client, api_pipeline):
        gid, _module = _seed(flask_client, api_pipeline)
        assert flask_client.post(
            f'/api/module/{gid}/versions/99/restore').status_code == 404

    def test_finalize_flow(self, flask_client, api_pipeline):
        gid, _module = _seed(flask_client, api_pipeline)
        resp = flask_client.post(f'/api/module/{gid}/finalize')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert body['status'] == 'finalized'
        # Finalize ganda ditolak; edit setelah finalize -> version baru.
        assert flask_client.post(
            f'/api/module/{gid}/finalize').status_code == 422
        r = _save(flask_client, gid, body['version_no'] - 1,
                  {'meta': {'penyusun': 'Guru C'}})
        assert r.status_code == 409
        r2 = _save(flask_client, gid, body['version_no'],
                   {'meta': {'penyusun': 'Guru C'}})
        assert r2.status_code == 200
        assert json.loads(r2.data)['version']['status'] == 'validated'

    def test_finalize_draft_rejected(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        acts = [dict(a) for a in module['learning_activities']
                if a.get('experience') != 'mengaplikasi']
        payload = []
        for i, a in enumerate(acts):
            payload.append({
                'id': a.get('id') or f'ACT-{i}', 'name': a['name'],
                'description': a['description'],
                'duration': 80 if a['meeting'] == 1 else 40,
                'tp_linked': a.get('tp_linked') or 'TP-1',
                'experience': a['experience'], 'stage': a['stage'],
                'meeting': a['meeting']})
        r = _save(flask_client, gid, 1, {'aktivitas': payload})
        assert r.status_code == 200
        assert json.loads(r.data)['version']['status'] == 'draft'
        fin = flask_client.post(f'/api/module/{gid}/finalize')
        assert fin.status_code == 422
        assert 'FINALIZE_NOT_ALLOWED' in fin.get_data(as_text=True)


def _regen_mock(target):
    from test_phase_c_module_generation import (
        fake_router_response, mock_meeting_principles)

    def side_effect(prompt, system_instruction=None, **kwargs):
        if target == 'aktivitas' and '"activities"' in prompt:
            return {'activities': [dict(a, id=f'N{i}') for i, a in enumerate(NEW_ACTS)],
                    'meeting_principles': mock_meeting_principles(2)}
        if target == 'materi' and '"introduction"' in prompt:
            return {'introduction': 'Intro baru', 'main_content': 'Isi baru.',
                    'key_concepts': ['Taubat'],
                    'essential_understanding': {
                        'core_insight': 'Wawasan baru tentang taubat.',
                        'relationship': 'Hubungan baru.',
                        'application': 'Penerapan baru.',
                        'value': 'Nilai baru.'}}
        if target == 'tp' and 'tp_list' in prompt:
            return {'tp_list': [
                'Menerapkan taubat nasuha dalam kehidupan sehari-hari',
                'Menganalisis kaitan taubat dengan akhlak terpuji',
                'Mengevaluasi program perbaikan diri selama sepekan']}
        if target == 'praktik_pedagogis' and 'pedagogical_practices' in prompt:
            resp = fake_router_response(prompt, system_instruction, **kwargs)
            resp['pedagogical_practices'] = [
                'Inkuiri terbimbing berbasis pengamatan sumber utama.',
                'Diskusi kelompok untuk membandingkan temuan.',
                'Presentasi singkat dengan umpan balik terarah.']
            return resp
        if target == 'kktp' and 'criteria' in prompt:
            resp = fake_router_response(prompt, system_instruction, **kwargs)
            return resp
        if target in ('asesmen', 'rubrik') and 'diagnostic' in prompt:
            resp = fake_router_response(prompt, system_instruction, **kwargs)
            if target == 'rubrik':
                return dict(resp)
            return resp
        return fake_router_response(prompt, system_instruction, **kwargs)

    return side_effect


class TestPartialRegen:
    def _regen(self, flask_client, api_pipeline, target):
        from test_phase_c_module_generation import patch_pipeline_ai
        gid, _module = _seed(flask_client, api_pipeline)
        with patch_pipeline_ai(api_pipeline, _regen_mock(target)):
            resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                     json={'base_version': 1, 'target': target})
        return gid, resp

    def test_regen_aktivitas_preserves_tp(self, flask_client, api_pipeline):
        from module_store import VersionStore
        gid, module = _seed(flask_client, api_pipeline)
        old_tp = [t['text'] for t in module['learning_objectives']]
        gid, resp = self._regen(flask_client, api_pipeline, 'aktivitas')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert body['changed_sections'] == ['aktivitas']
        new_tp = [t['text'] for t in body['module']['learning_objectives']]
        assert new_tp == old_tp
        names = [a['name'] for a in body['module']['learning_activities']]
        assert 'Apersepsi baru' in names
        # KBC traceability dihitung ulang dan valid.
        kbc = body['module']['approach_principles']['kbc']
        assert kbc['enabled'] is True
        acts = {a['id'] for a in body['module']['learning_activities']}
        for ins in kbc.get('insertions') or []:
            assert set(ins.get('activity_ids') or []) <= acts

    def test_regen_praktik_pedagogis_preserves_tp(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import patch_pipeline_ai
        gid, module = _seed(flask_client, api_pipeline)
        old_tp = [t['text'] for t in module['learning_objectives']]
        with patch_pipeline_ai(api_pipeline, _regen_mock('praktik_pedagogis')):
            resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                     json={'base_version': 1,
                                           'target': 'praktik_pedagogis'})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert body['changed_sections'] == ['praktik_pedagogis']
        assert body['module']['pedagogical_practices']
        assert [t['text'] for t in body['module']['learning_objectives']] == old_tp

    def test_regen_materi_preserves_tp(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        old_tp = [t['text'] for t in module['learning_objectives']]
        gid, resp = self._regen(flask_client, api_pipeline, 'materi')
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert [t['text'] for t in body['module']['learning_objectives']] == old_tp
        assert body['module']['essential_understanding'][
            'core_insight'] == 'Wawasan baru tentang taubat.'

    def test_regen_invalid_no_new_version(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import patch_pipeline_ai
        from module_store import VersionStore
        gid, _module = _seed(flask_client, api_pipeline)

        def garbage(prompt, system_instruction=None, **kwargs):
            if '"activities"' in prompt:
                return {'activities': 'bukan-list'}
            from test_phase_c_module_generation import fake_router_response
            return fake_router_response(prompt, system_instruction, **kwargs)

        with patch_pipeline_ai(api_pipeline, garbage):
            resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                     json={'base_version': 1,
                                           'target': 'aktivitas'})
        assert resp.status_code == 422
        assert [h['version_no'] for h in
                VersionStore(api_pipeline.db_path).history(gid)] == [1]

    def test_regen_unknown_target_400(self, flask_client, api_pipeline):
        gid, _module = _seed(flask_client, api_pipeline)
        resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                 json={'base_version': 1, 'target': 'judul'})
        assert resp.status_code == 400

    def test_regen_stale_409(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import patch_pipeline_ai
        gid, module = _seed(flask_client, api_pipeline)
        tp = [dict(t) for t in module['learning_objectives']]
        tp[0]['text'] = 'Menerapkan taubat dalam kehidupan sehari-hari'
        assert _save(flask_client, gid, 1, {
            'tp': [{'id': t['id'], 'text': t['text']} for t in tp]
        }).status_code == 200
        # Basis v1 kini basi (latest v2) -> regen pun 409.
        with patch_pipeline_ai(api_pipeline, _regen_mock('materi')):
            resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                     json={'base_version': 1,
                                           'target': 'materi'})
        assert resp.status_code == 409

    def test_regen_after_teacher_edit_keeps_edit(
            self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        tp = [dict(t) for t in module['learning_objectives']]
        tp[0]['text'] = ('Menerapkan taubat nasuha hasil edit guru dalam '
                         'kehidupan sehari-hari')
        assert _save(flask_client, gid, 1, {
            'tp': [{'id': t['id'], 'text': t['text']} for t in tp]
        }).status_code == 200
        from test_phase_c_module_generation import patch_pipeline_ai
        with patch_pipeline_ai(api_pipeline, _regen_mock('materi')):
            resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                     json={'base_version': 2,
                                           'target': 'materi'})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert body['module']['learning_objectives'][0]['text'].startswith(
            'Menerapkan taubat nasuha hasil edit guru')

    def _regen_with(self, flask_client, api_pipeline, target, mock):
        from test_phase_c_module_generation import patch_pipeline_ai
        gid, _module = _seed(flask_client, api_pipeline)
        with patch_pipeline_ai(api_pipeline, mock):
            resp = flask_client.post(f'/api/module/{gid}/regenerate',
                                     json={'base_version': 1,
                                           'target': target})
        return gid, resp

    def test_regen_tp_changes_only_tp(self, flask_client, api_pipeline):
        from test_phase_c_module_generation import fake_router_response

        def mock(prompt, system_instruction=None, **kwargs):
            if 'tp_list' in prompt:
                return {'tp_list': [
                    'Menerapkan taubat nasuha dalam kehidupan sehari-hari',
                    'Menganalisis kaitan taubat dengan akhlak terpuji',
                    'Mengevaluasi program perbaikan diri selama sepekan']}
            return fake_router_response(prompt, system_instruction, **kwargs)

        gid, module = _seed(flask_client, api_pipeline)
        old_acts = [a['name'] for a in module['learning_activities']]
        gid, resp = self._regen_with(flask_client, api_pipeline, 'tp', mock)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert body['changed_sections'] == ['tp']
        assert [t['text'] for t in
                body['module']['learning_objectives']][0].startswith(
                    'Menerapkan taubat nasuha dalam kehidupan')
        assert [a['name'] for a in
                body['module']['learning_activities']] == old_acts

    def test_regen_kktp_preserves_activities(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import fake_router_response

        def mock(prompt, system_instruction=None, **kwargs):
            if 'criteria' in prompt:
                return {'criteria': ['Menerapkan langkah taubat dengan benar '
                                     'dan konsisten',
                                     'Menganalisis contoh kasus taubat harian'],
                        'level': 'C6'}
            return fake_router_response(prompt, system_instruction, **kwargs)

        gid, module = _seed(flask_client, api_pipeline)
        old_acts = [a['name'] for a in module['learning_activities']]
        gid, resp = self._regen_with(flask_client, api_pipeline, 'kktp', mock)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert all(k['cognitive_level'] == 'C6'
                   for k in body['module']['success_criteria'])
        assert [a['name'] for a in
                body['module']['learning_activities']] == old_acts

    def test_regen_asesmen_changes_only_assessments(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import fake_router_response

        def mock(prompt, system_instruction=None, **kwargs):
            resp = fake_router_response(prompt, system_instruction, **kwargs)
            if 'diagnostic' in prompt and isinstance(resp, dict):
                resp = dict(resp)
                items = [dict(it) for it in resp.get('formative') or []]
                if items:
                    items[0] = dict(
                        items[0],
                        question=items[0]['question'] + ' (regen)')
                resp['formative'] = items
            return resp

        gid, module = _seed(flask_client, api_pipeline)
        old_tp = [t['text'] for t in module['learning_objectives']]
        gid, resp = self._regen_with(
            flask_client, api_pipeline, 'asesmen', mock)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert [t['text'] for t in
                body['module']['learning_objectives']] == old_tp
        assert body['module']['assessments']['formative'][0][
            'question'].endswith('(regen)')

    def test_regen_rubrik_updates_descriptors(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import fake_router_response

        def mock(prompt, system_instruction=None, **kwargs):
            resp = fake_router_response(prompt, system_instruction, **kwargs)
            if 'diagnostic' in prompt and isinstance(resp, dict):
                resp = dict(resp)
                desc = dict(resp.get('rubric_descriptors') or {})
                desc['KKTP-1'] = [
                    'Belum dapat menerapkan langkah taubat (regen)',
                    'Menerapkan sebagian langkah dengan bimbingan (regen)',
                    'Menerapkan seluruh langkah secara mandiri (regen)',
                    'Menerapkan dan menjelaskan hikmahnya (regen)',
                ]
                resp['rubric_descriptors'] = desc
            return resp

        gid, resp = self._regen_with(flask_client, api_pipeline, 'rubrik', mock)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        rows = {r['kktp_id']: r
                for r in body['module']['rubric']['kktp_rubric']}
        assert rows['KKTP-1']['descriptors'][0].endswith('(regen)')

    def test_regen_refleksi_preserves_kbc(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import fake_router_response

        def mock(prompt, system_instruction=None, **kwargs):
            resp = fake_router_response(prompt, system_instruction, **kwargs)
            if 'triggering_questions' in prompt and isinstance(resp, dict):
                resp = dict(resp)
                resp['student_reflection'] = [
                    'Apa langkah taubat yang saya praktikkan hari ini? (regen)']
            return resp

        gid, module = _seed(flask_client, api_pipeline)
        old_themes = list((module['approach_principles']['kbc'] or {}).get(
            'themes') or [])
        gid, resp = self._regen_with(
            flask_client, api_pipeline, 'refleksi', mock)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        refl = {r['role']: r['questions']
                for r in body['module']['reflection']}
        assert refl['student'] == [
            'Apa langkah taubat yang saya praktikkan hari ini? (regen)']
        assert list((body['module']['approach_principles']['kbc'] or {}).get(
            'themes') or []) == old_themes

    def _regen_aktivitas_mock(self, n_meetings):
        from test_phase_c_module_generation import mock_meeting_principles

        def mock(prompt, system_instruction=None, **kwargs):
            if '"activities"' not in prompt:
                from test_phase_c_module_generation import (
                    fake_router_response)
                return fake_router_response(
                    prompt, system_instruction, **kwargs)
            # Aktivitas valid untuk n pertemuan: tiap pertemuan
            # 2 JP x 40 mnt = 80 mnt (10+25+20+15+10). Tiap pertemuan
            # memuat 3 mengaplikasi (syarat >= jumlah TP terpenuhi
            # untuk n berapa pun) dan mencakup TP-1..TP-3.
            acts = []
            for mtg in range(1, n_meetings + 1):
                base = (mtg - 1) % 3
                tp = [f'TP-{(base + i) % 3 + 1}' for i in range(3)]
                acts.append({
                    'name': f'Apersepsi P{mtg}',
                    'description': 'Siswa menyimak pemantik dan berbagi '
                                   f'pengalaman awal pada pertemuan {mtg}.',
                    'duration': 10, 'experience': 'memahami',
                    'tp_linked': tp[0], 'stage': 'Pembuka',
                    'meeting': mtg})
                acts.append({
                    'name': f'Inti A P{mtg}',
                    'description': 'Kelompok menganalisis bahan dan '
                                   f'menyusun hasil pada pertemuan {mtg}.',
                    'duration': 25, 'experience': 'mengaplikasi',
                    'tp_linked': tp[0], 'stage': 'Inti', 'meeting': mtg})
                acts.append({
                    'name': f'Inti B P{mtg}',
                    'description': 'Siswa mengurutkan kartu tindakan dan '
                                   'mencocokkannya dengan langkah yang benar '
                                   f'pada pertemuan {mtg}.',
                    'duration': 20, 'experience': 'mengaplikasi',
                    'tp_linked': tp[1], 'stage': 'Inti', 'meeting': mtg})
                acts.append({
                    'name': f'Inti C P{mtg}',
                    'description': 'Kelompok memerankan kasus lalu '
                                   'menunjukkan proses yang tepat melalui '
                                   f'dialog pada pertemuan {mtg}.',
                    'duration': 15, 'experience': 'mengaplikasi',
                    'tp_linked': tp[2], 'stage': 'Inti', 'meeting': mtg})
                acts.append({
                    'name': f'Tutup P{mtg}',
                    'description': 'Siswa menulis refleksi dan menutup '
                                   f'pembelajaran pertemuan {mtg} dengan doa.',
                    'duration': 10, 'experience': 'merefleksi',
                    'tp_linked': tp[2], 'stage': 'Penutup', 'meeting': mtg})
            return {'activities': acts,
                    'meeting_principles': mock_meeting_principles(
                        n_meetings)}

        return mock

    def test_regen_aktivitas_n_meetings_tambah_pecah(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import patch_pipeline_ai
        gid, module = _seed(flask_client, api_pipeline)
        assert len(module['meetings']) == 2
        with patch_pipeline_ai(
                api_pipeline, self._regen_aktivitas_mock(3)):
            resp = flask_client.post(
                f'/api/module/{gid}/regenerate',
                json={'base_version': 1, 'target': 'aktivitas',
                      'n_meetings': 3})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = json.loads(resp.data)['version']
        assert body['changed_sections'] == ['aktivitas']
        mod = body['module']
        assert [m['index'] for m in mod['meetings']] == [1, 2, 3]
        assert {a['meeting'] for a in mod['learning_activities']} == \
            {1, 2, 3}
        pakai = {}
        for a in mod['learning_activities']:
            pakai[a['meeting']] = pakai.get(a['meeting'], 0) + a['duration']
        for m in mod['meetings']:
            assert pakai.get(m['index'], 0) == m['minutes'] == 80

    def test_regen_aktivitas_n_meetings_kurang_gabung(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import patch_pipeline_ai
        gid, _module = _seed(flask_client, api_pipeline)
        with patch_pipeline_ai(
                api_pipeline, self._regen_aktivitas_mock(1)):
            resp = flask_client.post(
                f'/api/module/{gid}/regenerate',
                json={'base_version': 1, 'target': 'aktivitas',
                      'n_meetings': 1})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        mod = json.loads(resp.data)['version']['module']
        assert [m['index'] for m in mod['meetings']] == [1]
        assert {a['meeting'] for a in mod['learning_activities']} == {1}
        assert sum(a['duration']
                   for a in mod['learning_activities']) == 80

    def test_regen_aktivitas_n_meetings_sama_tetap_jalan(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import patch_pipeline_ai
        gid, _module = _seed(flask_client, api_pipeline)
        with patch_pipeline_ai(
                api_pipeline, self._regen_aktivitas_mock(2)):
            resp = flask_client.post(
                f'/api/module/{gid}/regenerate',
                json={'base_version': 1, 'target': 'aktivitas',
                      'n_meetings': 2})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        mod = json.loads(resp.data)['version']['module']
        assert [m['index'] for m in mod['meetings']] == [1, 2]

    def test_regen_aktivitas_antislop_murid_informal(
            self, flask_client, api_pipeline):
        from test_phase_c_module_generation import patch_pipeline_ai

        def mock(prompt, system_instruction=None, **kwargs):
            if '"activities"' not in prompt:
                from test_phase_c_module_generation import (
                    fake_router_response)
                return fake_router_response(
                    prompt, system_instruction, **kwargs)
            return {
                'activities': [{
                    'name': 'Inti kasar',
                    'description': 'Peserta didik membaca tafsir, '
                                   'Peta Struktur, dan lain-lain.',
                    'duration': 40, 'experience': 'memahami',
                    'tp_linked': 'TP-1', 'stage': 'Pembuka',
                    'meeting': 1},
                    {'name': 'Inti inti',
                     'description': 'Siswa berdiskusi makna, dll.',
                     'duration': 20, 'experience': 'mengaplikasi',
                     'tp_linked': 'TP-1', 'stage': 'Inti',
                     'meeting': 1},
                    {'name': 'Inti lanjut',
                     'description': 'Siswa mempraktikkan hafalan, dst.',
                     'duration': 20, 'experience': 'mengaplikasi',
                     'tp_linked': 'TP-2', 'stage': 'Inti',
                     'meeting': 1},
                    {'name': 'Tutup',
                     'description': 'Murid menulis refleksi.',
                     'duration': 40, 'experience': 'merefleksi',
                     'tp_linked': 'TP-1', 'stage': 'Penutup',
                     'meeting': 2},
                    {'name': 'Tambah',
                     'description': 'Murid mengulang hafalan.',
                     'duration': 40, 'experience': 'mengaplikasi',
                     'tp_linked': 'TP-3', 'stage': 'Inti',
                     'meeting': 2}],
                'meeting_principles': [
                    {'meeting': 1,
                     'berkesadaran': 'Murid menyadari tujuan ... 1a',
                     'bermakna': 'Murid mengaitkan materi ... 1b',
                     'menggembirakan': 'Murid gembira berdiskusi ... 1c'},
                    {'meeting': 2,
                     'berkesadaran': 'Murid menyadari tujuan ... 2a',
                     'bermakna': 'Murid mengaitkan materi ... 2b',
                     'menggembirakan': 'Murid gembira berlatih ... 2c'}]}
        gid, _module = _seed(flask_client, api_pipeline)
        with patch_pipeline_ai(api_pipeline, mock):
            resp = flask_client.post(
                f'/api/module/{gid}/regenerate',
                json={'base_version': 1, 'target': 'aktivitas'})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        mod = json.loads(resp.data)['version']['module']
        descs = [a['description']
                 for a in mod['learning_activities']]
        assert descs
        for teks in descs:
            assert 'lain-lain' not in teks.lower()
            assert 'peserta didik' not in teks.lower()
            assert 'siswa' not in teks.lower()
        assert any('murid' in t.lower() for t in descs)

    @pytest.mark.parametrize('n', [0, 17, 'x', None, True])
    def test_regen_aktivitas_n_meetings_invalid_400(
            self, flask_client, api_pipeline, n):
        gid, _module = _seed(flask_client, api_pipeline)
        resp = flask_client.post(
            f'/api/module/{gid}/regenerate',
            json={'base_version': 1, 'target': 'aktivitas',
                  'n_meetings': n})
        assert resp.status_code == 400, resp.get_data(as_text=True)

    def test_regen_bukan_aktivitas_n_meetings_400(
            self, flask_client, api_pipeline):
        gid, _module = _seed(flask_client, api_pipeline)
        resp = flask_client.post(
            f'/api/module/{gid}/regenerate',
            json={'base_version': 1, 'target': 'materi',
                  'n_meetings': 3})
        assert resp.status_code == 400, resp.get_data(as_text=True)


class TestVersionExport:
    def test_export_serves_edited_v2(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        tp = [dict(t) for t in module['learning_objectives']]
        tp[0]['text'] = 'Menerapkan taubat versi dua dalam kehidupan'
        assert _save(flask_client, gid, 1, {
            'tp': [{'id': t['id'], 'text': t['text']} for t in tp]
        }).status_code == 200
        resp = flask_client.get(f'/api/module/{gid}/export-docx')
        assert resp.status_code == 200
        old = flask_client.get(f'/api/module/{gid}/export-docx?version=1')
        assert old.status_code == 200
        assert old.data != resp.data

    def test_export_unknown_version_404(self, flask_client, api_pipeline):
        gid, _module = _seed(flask_client, api_pipeline)
        assert flask_client.get(
            f'/api/module/{gid}/export-docx?version=99').status_code == 404

    def test_export_draft_422(self, flask_client, api_pipeline):
        gid, module = _seed(flask_client, api_pipeline)
        acts = [dict(a) for a in module['learning_activities']
                if a.get('experience') != 'mengaplikasi']
        payload = []
        for i, a in enumerate(acts):
            payload.append({
                'id': a.get('id') or f'ACT-{i}', 'name': a['name'],
                'description': a['description'],
                'duration': 80 if a['meeting'] == 1 else 40,
                'tp_linked': a.get('tp_linked') or 'TP-1',
                'experience': a['experience'], 'stage': a['stage'],
                'meeting': a['meeting']})
        r = _save(flask_client, gid, 1, {'aktivitas': payload})
        assert r.status_code == 200
        assert json.loads(r.data)['version']['status'] == 'draft'
        assert flask_client.get(
            f'/api/module/{gid}/export-docx').status_code == 422
