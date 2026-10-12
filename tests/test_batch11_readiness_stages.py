#!/usr/bin/env python3
"""Batch 11: student_readiness diteruskan ke stage Aktivitas & Asesmen.

Readiness = konteks pedagogis (scaffolding/bantuan/contoh/
kompleksitas), bukan target. Tanpa readiness: prompt generik, hasil
tetap valid. Tanpa real AI (mock dispatch + validator produksi).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from module_generation_pipeline import (  # noqa: E402
    KKTPEntry, ModuleGenerationPipeline, _readiness_stage_block,
)

READINESS = ('Sebagian besar murid sudah memahami konsep dasar materi, '
             'tetapi masih mengalami kesulitan ketika harus menerapkan '
             'konsep tersebut pada situasi atau contoh yang baru.')


@pytest.fixture
def pipeline(test_db):
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    yield pipe
    pipe.curriculum_validator.close()


def _ctx():
    return SimpleNamespace(subject='Akidah Akhlak', phase='D',
                           topic='Taubat')


def _acts_response():
    return {'activities': [
        {'name': 'Apersepsi', 'description': 'Siswa mengingat konsep',
         'duration': 15, 'experience': 'memahami', 'tp_linked': 'TP-1'},
        {'name': 'Diskusi', 'description': 'Siswa menerapkan konsep',
         'duration': 45, 'experience': 'mengaplikasi', 'tp_linked': 'TP-1'},
        {'name': 'Refleksi', 'description': 'Siswa merefleksikan',
         'duration': 15, 'experience': 'merefleksi', 'tp_linked': 'TP-1'},
    ]}


def _asm_response():
    mc = {'question': 'Apa itu taubat?', 'type': 'multiple_choice',
          'options': [{'label': 'A', 'text': 'Xa'},
                      {'label': 'B', 'text': 'Xb'},
                      {'label': 'C', 'text': 'Xc'},
                      {'label': 'D', 'text': 'Xd'}],
          'correct_answer': 'B', 'tp_linked': 'TP-1',
          'kktp_linked': 'KKTP-1'}
    short = {'question': 'Jelaskan taubat.', 'type': 'short_answer',
             'tp_linked': 'TP-1', 'kktp_linked': 'KKTP-1'}
    essay = {'question': 'Analisis taubat.', 'type': 'essay',
             'tp_linked': 'TP-1', 'kktp_linked': 'KKTP-1'}
    return {'diagnostic': [dict(mc)], 'formative': [dict(short)],
            'summative': {'items': [dict(essay)], 'rubric': 'R'},
            'rubric_descriptors': {}}


def _kktp():
    return [KKTPEntry(id='KKTP-1', tp_id='TP-1', criteria=['c1'],
                      cognitive_level='C3')]


class TestReadinessBlock:
    def test_empty_yields_empty(self):
        assert _readiness_stage_block('') == ''
        assert _readiness_stage_block(None) == ''
        assert _readiness_stage_block('   ') == ''

    def test_filled_carries_fact_and_guardrails(self):
        block = _readiness_stage_block(READINESS)
        assert READINESS in block
        assert 'CP/TP/KKTP' in block or 'TP/KKTP' in block
        assert 'DILARANG' in block


class TestStagePrompts:
    def _capture(self, pipeline, stage_fn, readiness):
        from test_phase_c_module_generation import patch_pipeline_ai
        seen = {}

        def fx(prompt, system_instruction=None, **kwargs):
            seen['prompt'] = prompt + '\n' + (system_instruction or '')
            if stage_fn == 'activities':
                return _acts_response()
            return _asm_response()

        with patch_pipeline_ai(pipeline, fx):
            if stage_fn == 'activities':
                out = pipeline._generate_activities(
                    ['TP-1 text'], _ctx(), None, None, readiness)
            else:
                out = pipeline._generate_assessments(
                    ['TP-1 text'], _kktp(), _ctx(),
                    {'diagnostic': 1, 'formative': 1, 'summative': 1},
                    None, readiness)
        return out, seen['prompt']

    def test_activities_prompt_carries_readiness(self, pipeline):
        _, prompt = self._capture(pipeline, 'activities', READINESS)
        assert READINESS[:40] in prompt

    def test_activities_prompt_has_generic_anti_slop_rules(self, pipeline):
        _, prompt = self._capture(pipeline, 'activities', '')
        assert 'JANGAN mengarang nama khusus' in prompt
        assert 'tindakan nyata' in prompt
        assert 'Tindakan + objek + output' in prompt or 'tindakan + objek + output' in prompt
        assert 'Jigsaw Sumber' in prompt
        assert 'model/metode yang tidak diminta' in prompt

    def test_assessments_prompt_has_generic_anti_slop_rules(self, pipeline):
        _, prompt = self._capture(pipeline, 'assessments', '')
        assert 'JANGAN mengarang nama khusus' in prompt
        assert 'istilah bahasa Inggris' in prompt
        assert 'Jika pengguna atau sumber memang meminta model/metode' in prompt

    def test_requested_method_remains_allowed_by_instruction(self, pipeline):
        _, prompt = self._capture(pipeline, 'activities', '')
        assert 'Jika pengguna atau sumber memang meminta model/metode, pertahankan nama resminya' in prompt
        assert 'tanpa membuat kombinasi baru' in prompt

    def test_no_narrow_blacklist_only(self, pipeline):
        _, prompt = self._capture(pipeline, 'activities', '')
        assert 'atau istilah bahasa Inggris' in prompt
        assert 'nama permainan' in prompt
        assert 'label kreatif' in prompt

    def test_activities_prompt_empty_without(self, pipeline):
        _, prompt = self._capture(pipeline, 'activities', '')
        assert 'Kesiapan murid menurut observasi' not in prompt

    def test_assessments_prompt_carries_readiness(self, pipeline):
        _, prompt = self._capture(pipeline, 'assessments', READINESS)
        assert READINESS[:40] in prompt

    def test_assessments_prompt_empty_without(self, pipeline):
        _, prompt = self._capture(pipeline, 'assessments', '')
        assert 'Kesiapan murid menurut observasi' not in prompt

    def test_empty_readiness_still_valid(self, pipeline):
        out, _ = self._capture(pipeline, 'activities', '')
        assert len(out) == 3
        out, _ = self._capture(pipeline, 'assessments', '')
        assert len(out['diagnostic']) == 1


class TestFrozenPipelineAB:
    """A/B terkontrol: outline + aktivitas + asesmen mock bervariasi
    menurut readiness; target beku. Final harus sukses, kontrol
    identik, D/E beradaptasi dan tetap TP-aligned."""

    def _mock(self, readiness_on):
        from test_phase_c_module_generation import (
            fake_router_response, mock_meeting_principles)
        import test_meetings_rpm as tmr

        def fx(prompt, system_instruction=None, **kwargs):
            if '"activities"' in prompt:
                suffix = ' bertahap dengan kartu bantuan' \
                    if readiness_on else ''
                return {
                    'activities': [
                        {'name': f"A{i + 1}",
                         'description': f"Deskripsi A{i + 1}{suffix}",
                         'duration': dur, 'experience': exp,
                         'tp_linked': tp, 'stage': stage,
                         'meeting': meeting}
                        for i, (meeting, stage, dur, tp, exp)
                        in enumerate(tmr.ROWS_D)],
                    'meeting_principles': mock_meeting_principles(2)}
            if 'diagnostic' in prompt:
                base = fake_router_response(
                    prompt, system_instruction, **kwargs)
                if readiness_on:
                    base = dict(base)
                    base['diagnostic'] = [
                        dict(it, question=it['question'] +
                             ' (konteks situasi baru)')
                        for it in base['diagnostic']]
                return base
            return fake_router_response(
                prompt, system_instruction, **kwargs)
        return fx

    def _run(self, pipeline, readiness):
        from test_phase_c_module_generation import patch_pipeline_ai
        import test_meetings_rpm as tmr
        params = dict(tmr.MEET_PARAMS)
        if readiness:
            params['student_readiness'] = readiness
        elif 'student_readiness' in params:
            del params['student_readiness']
        with patch_pipeline_ai(pipeline, self._mock(bool(readiness))):
            return pipeline.generate(params)

    def test_ab_final(self, pipeline):
        ra = self._run(pipeline, '')
        assert ra['status'] == 'success', ra['errors']
        rb = self._run(pipeline, READINESS)
        assert rb['status'] == 'success', rb['errors']
        ma, mb = ra['module'], rb['module']
        # Kontrol identik.
        assert ma['master_outline']['design']['cp'] == \
            mb['master_outline']['design']['cp']
        assert [(t['id'], t['text']) for t in
                ma['master_outline']['design']['tp']] == \
            [(t['id'], t['text']) for t in
             mb['master_outline']['design']['tp']]
        assert ma.get('topic') == mb.get('topic')
        # D beradaptasi, tetap TP-aligned.
        tp_ids = {t['id'] for t in mb['learning_objectives']}
        descs_b = [a.get('description', '')
                   for a in mb['learning_activities']]
        assert any('bertahap dengan kartu bantuan' in d
                   for d in descs_b)
        descs_a = [a.get('description', '')
                   for a in ma['learning_activities']]
        assert not any('bertahap dengan kartu bantuan' in d
                       for d in descs_a)
        for a in mb['learning_activities']:
            assert a.get('tp_linked') in tp_ids
        # E beradaptasi (konteks situasi baru), MC tetap kontraktual.
        diag_b = mb['master_outline']['assessment']['awal']
        items_b = diag_b if isinstance(diag_b, list) else \
            diag_b.get('items', [])
        assert any('(konteks situasi baru)' in (it.get('question') or '')
                   for it in items_b)
        for it in items_b:
            if str(it.get('type') or '').lower() == 'multiple_choice':
                assert len(it.get('options') or []) >= 4
                assert it.get('correct_answer') in [
                    o.get('label') for o in it['options']]
        # A tanpa readiness tetap valid.
        assert ra['validation']['final']['passed'] is True
        # B: tidak ada diagnosis murid yang dikarang AI.
        lr = mb['master_outline']['identification']['learner_readiness']
        assert lr.get('aspects') == []
