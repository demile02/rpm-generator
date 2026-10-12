#!/usr/bin/env python3
"""Batch 1 — runtime enforcement of skills/antislop rules in the RPM
pipeline. Mock AI only (no real 9Router); production validators run.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from module_generation_pipeline import (  # noqa: E402
    ANTISLOP_SKILL_RULES,
    ANTISLOP_SKILL_VERSION,
    ActivityEntry,
    AntiSlopProcessor,
    KKTPEntry,
    Module,
    ModuleGenerationPipeline,
    SkillDrivenNormalizer,
    TPEntry,
)


@pytest.fixture
def pipeline(test_db):
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    yield pipe
    pipe.curriculum_validator.close()


def _slop_description():
    return ('Siswa mengamati tayangan \u2014 lalu berdiskusi. '
            'Semoga bermanfaat!')


def _bare_module(**overrides):
    """Minimal Module carrying every humanizable + protected field."""
    def act(i, description):
        return ActivityEntry(
            id=f'ACT-{i}', name=f'A{i}', description=description,
            duration=15, tp_linked='TP-1', type='Diskusi',
            experience='mengaplikasi', stage='Inti', meeting=1)

    fields = dict(
        id='m1', title='T', subject='Akidah Akhlak', grade='MTs_7',
        phase='D', curriculum_version='KMA-1503-2025',
        module_identity={}, facilities=[], target_students={},
        learning_model='', methods=[],
        learning_objectives=[TPEntry(
            id='TP-1', text='Menerapkan konsep taubat', cognitive_level='C3',
            cp_reference='CP-1')],
        success_criteria=[KKTPEntry(
            id='KKTP-1', tp_id='TP-1', criteria=['Kriteria satu'],
            cognitive_level='C3')],
        essential_understanding={}, guiding_questions=['Mengapa taubat?'],
        learning_activities=[act(1, _slop_description())],
        assessments={'diagnostic': [{
            'question': 'Apa itu taubat \u2014 menurut dalil?',
            'type': 'multiple_choice',
            'options': [{'label': 'A', 'text': 'Opsi A'},
                        {'label': 'B', 'text': 'Opsi B'},
                        {'label': 'C', 'text': 'Opsi C'},
                        {'label': 'D', 'text': 'Opsi D'}],
            'correct_answer': 'B', 'points': 10, 'tp_linked': 'TP-1'}]},
        reflection=[{'role': 'student', 'questions': ['Apa yang dipelajari?']}],
        remedial={'description': 'Pendampingan \u2014 bertahap',
                  'tp_reference': ['TP-1']},
        enrichment={'description': 'Pengayaan studi kasus',
                    'tp_reference': ['TP-1']},
        references=[{'title': 'R', 'url': 'https://example.com/x'}],
        material_characteristics={
            'summary': 'Materi konseptual \u2014 normatif.',
            'prerequisites': ['Rukun iman'],
            'potential_misconceptions': ['Miskonsepsi satu']},
        pedagogical_practices=['Diskusi kelompok \u2014 santun'],
        learning_partnerships=[], learning_environment={},
        digital_use={}, unit={}, regulatory_consultation={'sources': []},
        curriculum_context=None,
        student_readiness='Sebagian murid paham wahyu.',
        learner_readiness={'summary': 'Sebagian murid paham wahyu.'},
        penyusun='Ibu Guru',
    )
    fields.update(overrides)
    return Module(**fields)


# ------------------------------------------------------------------
# Skill rule registry: the skill is the source of rules.
# ------------------------------------------------------------------

class TestSkillRegistry:
    def test_version_pinned(self):
        assert AntiSlopProcessor.ANTISLOP_SKILL_VERSION == \
            ANTISLOP_SKILL_VERSION
        assert ANTISLOP_SKILL_VERSION == '1.1'

    def test_rewrite_rules_present(self):
        ids = [rule['id'] for rule in AntiSlopProcessor.SKILL_RULES]
        for required in ('R-02', 'R-36-chatbot-closer',
                         'R-36-signposting', 'R-36-filler',
                         'R-36-informal-id', 'R-16'):
            assert required in ids

    def test_detect_rules_present(self):
        ids = [rule['id'] for rule in AntiSlopProcessor.SKILL_RULES]
        for required in ('R-36-fake-candid', 'R-36-authority-trope',
                         'R-36-caps', 'R-36-staccato', 'R-36-quotes',
                         'R-36-inline-header'):
            assert required in ids

    def test_ui_only_rules_excluded(self):
        names = ' '.join(rule['name'] for rule in
                         AntiSlopProcessor.SKILL_RULES)
        for ui_only in ('icon', 'layout', 'keyboard', 'theme', 'faq',
                        'navigation', 'testimonial'):
            assert ui_only not in names


# ------------------------------------------------------------------
# Normalizer unit behavior.
# ------------------------------------------------------------------

class TestNormalizer:
    def test_em_dash_becomes_comma(self):
        out, counts = SkillDrivenNormalizer.normalize(
            'Siswa mengamati \u2014 lalu mencatat.')
        assert out == 'Siswa mengamati, lalu mencatat.'
        assert counts.get('R-02') == 1

    def test_digit_range_untouched(self):
        out, counts = SkillDrivenNormalizer.normalize(
            'Belajar 10\u201312 menit dengan tertib.')
        assert '10\u201312' in out
        assert counts.get('R-02', 0) == 0

    def test_closer_sentence_dropped(self):
        out, counts = SkillDrivenNormalizer.normalize(
            'Siswa berdiskusi kelompok. Semoga bermanfaat!')
        assert out == 'Siswa berdiskusi kelompok.'
        assert counts.get('R-36-chatbot-closer') == 1

    def test_quoted_dalil_untouched(self):
        original = 'Baca "QS. Al-Baqarah \u2014 ayat 2" dengan tartil.'
        out, counts = SkillDrivenNormalizer.normalize(original)
        assert out == original
        assert counts == {}

    def test_curly_quoted_dalil_untouched(self):
        original = ('Baca \u201cQS. Al-Baqarah \u2014 ayat 2\u201d '
                    'dengan tartil.')
        out, counts = SkillDrivenNormalizer.normalize(original)
        assert out == original
        assert counts == {}

    def test_buzzword_detected_not_rewritten(self):
        findings = SkillDrivenNormalizer.scan(
            'Pembelajaran yang seamless untuk journey siswa.')
        assert any(f['rule'] == 'R-16' for f in findings)

    def test_empty_guard(self):
        out, counts = SkillDrivenNormalizer.normalize('   ')
        assert out == '   '
        assert counts == {}

    def test_informal_dan_lain_lain_dropped(self):
        out, counts = SkillDrivenNormalizer.normalize(
            'Murid membaca QS. Al-Fatihah, Peta Struktur Al-Qur\u2019an, '
            'dan lain-lain.')
        assert 'lain-lain' not in out.lower()
        assert 'Peta Struktur' in out
        assert counts.get('R-36-informal-id') == 1

    def test_informal_abbreviations_dropped(self):
        for teks in ('Murid membaca tafsir, dll.',
                     'Murid membaca tafsir, dsb.',
                     'Murid membaca tafsir, dst.',
                     'Murid membaca tafsir, etc.'):
            out, counts = SkillDrivenNormalizer.normalize(teks)
            assert 'Murid membaca tafsir' in out
            assert counts.get('R-36-informal-id') == 1

    def test_quoted_informal_untouched(self):
        original = 'Baca "catatan guru, dll." dengan tertib.'
        out, counts = SkillDrivenNormalizer.normalize(original)
        assert out == original
        assert counts == {}


# ------------------------------------------------------------------
# Module-level application + protected snapshot.
# ------------------------------------------------------------------

class TestModuleApplication:
    def test_narrative_fields_processed(self):
        module, report = AntiSlopProcessor.humanize_with_report(
            _bare_module())
        assert report['fields_processed'].get('activity_description') == 1
        assert report['fields_processed'].get('pedagogical_practices') == 1
        assert 'Semoga bermanfaat!' not in \
            module.learning_activities[0].description
        assert '\u2014' not in module.pedagogical_practices[0]
        assert report['skill_version'] == '1.1'

    def test_murid_term_enforced(self):
        module, _ = AntiSlopProcessor.humanize_with_report(_bare_module(
            learning_activities=[{
                'id': 'ACT-1', 'name': 'A1',
                'description': 'Peserta didik dan siswa berdiskusi.',
                'duration': 15, 'tp_linked': 'TP-1',
                'type': 'Diskusi', 'experience': 'mengaplikasi',
                'stage': 'Inti', 'meeting': 1}]))
        desc = module.learning_activities[0]['description']
        assert 'peserta didik' not in desc.lower()
        assert 'siswa' not in desc.lower()
        assert 'murid' in desc.lower()

    def test_snapshot_stable_on_clean_module(self):
        module = _bare_module()
        before = AntiSlopProcessor.snapshot_protected(module)
        AntiSlopProcessor.humanize(module)
        after = AntiSlopProcessor.snapshot_protected(module)
        ok, errors = AntiSlopProcessor.validate_antislop_snapshot(
            before, after)
        assert ok, errors

    def test_snapshot_catches_cp_mutation(self):
        module = _bare_module()
        before = AntiSlopProcessor.snapshot_protected(module)
        after = dict(before)
        after['cp'] = 'CP palsu'
        ok, errors = AntiSlopProcessor.validate_antislop_snapshot(
            before, after)
        assert not ok
        assert any('cp' in error for error in errors)

    def test_snapshot_catches_answer_key_mutation(self):
        module = _bare_module()
        before = AntiSlopProcessor.snapshot_protected(module)
        module.assessments['diagnostic'][0]['correct_answer'] = 'C'
        after = AntiSlopProcessor.snapshot_protected(module)
        ok, errors = AntiSlopProcessor.validate_antislop_snapshot(
            before, after)
        assert not ok

    def test_student_readiness_verbatim(self):
        module, _ = AntiSlopProcessor.humanize_with_report(_bare_module(
            student_readiness='Teks guru asli.'))
        assert module.student_readiness == 'Teks guru asli.'

    def test_material_lists_untouched(self):
        module, _ = AntiSlopProcessor.humanize_with_report(_bare_module())
        assert module.material_characteristics['prerequisites'] == \
            ['Rukun iman']
        assert module.guiding_questions == ['Mengapa taubat?']


# ------------------------------------------------------------------
# Full-pipeline integration (mock AI, real validators).
# ------------------------------------------------------------------

def _slop_meetings_fake(rows):
    from test_phase_c_module_generation import (
        fake_router_response, patch_pipeline_ai,
        mock_meeting_principles)

    def side_effect(prompt, system_instruction=None, **kwargs):
        if '"activities"' in prompt:
            acts = []
            for i, (meeting, stage, dur, tp, exp) in enumerate(rows):
                acts.append({
                    'name': f'A{i + 1}',
                    'description': _slop_description(),
                    'duration': dur, 'experience': exp, 'tp_linked': tp,
                    'stage': stage, 'meeting': meeting})
            return {'activities': acts,
                    'meeting_principles': mock_meeting_principles(2)}
        return fake_router_response(prompt, system_instruction, **kwargs)

    return side_effect


class TestPipelineWiring:
    def test_order_pedagogical_then_antislop_then_final(self, pipeline):
        import test_meetings_rpm as tmr
        from test_phase_c_module_generation import patch_pipeline_ai
        order = []
        orig_ped = pipeline.pedagogical_validator.validate_activity_alignment
        orig_final = pipeline.final_validator.validate_completeness
        orig_humanize = pipeline.anti_slop.humanize_with_report

        def ped(*args, **kwargs):
            order.append('pedagogical')
            return orig_ped(*args, **kwargs)

        def anti(module):
            order.append('antislop')
            return orig_humanize(module)

        def final(module):
            order.append('final')
            return orig_final(module)

        pipeline.pedagogical_validator.validate_activity_alignment = ped
        pipeline.anti_slop.humanize_with_report = anti
        pipeline.final_validator.validate_completeness = final
        try:
            with patch_pipeline_ai(pipeline, _slop_meetings_fake(
                    tmr.ROWS_D)):
                result = pipeline.generate(dict(tmr.MEET_PARAMS))
        finally:
            pipeline.pedagogical_validator.validate_activity_alignment = \
                orig_ped
            pipeline.anti_slop.humanize_with_report = orig_humanize
            pipeline.final_validator.validate_completeness = orig_final
        assert result['status'] == 'success', result['errors']
        assert order.index('pedagogical') < order.index('antislop') < \
            order.index('final'), order
        assert result['validation']['final']['passed'] is True
        record = result['validation']['anti_slop']
        assert record['passed'] is True
        assert record['skill'] == '1.1'
        assert 'R-02' in record['skill_rules']

    def test_skill_rule_applied_end_to_end(self, pipeline):
        import test_meetings_rpm as tmr
        from test_phase_c_module_generation import patch_pipeline_ai
        with patch_pipeline_ai(pipeline, _slop_meetings_fake(tmr.ROWS_D)):
            result = pipeline.generate(dict(tmr.MEET_PARAMS))
        assert result['status'] == 'success', result['errors']
        descriptions = [
            a['description']
            for a in result['module']['learning_activities']]
        assert descriptions
        assert all('\u2014' not in d for d in descriptions)
        assert all('Semoga bermanfaat!' not in d for d in descriptions)
        record = result['validation']['anti_slop']
        assert record['rewrite_counts'].get('R-02', 0) >= 1

    def test_protected_fields_identical_end_to_end(self, pipeline):
        import test_meetings_rpm as tmr
        from test_phase_c_module_generation import patch_pipeline_ai
        with patch_pipeline_ai(pipeline, _slop_meetings_fake(tmr.ROWS_D)):
            result = pipeline.generate(dict(tmr.MEET_PARAMS))
        assert result['status'] == 'success', result['errors']
        module = result['module']
        context = module.get('curriculum_context') or {}
        cp = context.get('cp') or {}
        assert cp.get('text')
        assert cp.get('source_document_id')
        assert module.get('phase') == 'D'
        assert module.get('subject') == 'Akidah Akhlak'
        for tp in module.get('learning_objectives', []):
            assert tp.get('cognitive_level') in ('C3', 'C4', 'C5', 'C6')

    def test_corrupt_antislop_fails_generation(self, pipeline):
        import test_meetings_rpm as tmr
        from test_phase_c_module_generation import patch_pipeline_ai
        orig = AntiSlopProcessor.__dict__['humanize_with_report']

        @staticmethod
        def hostile(module):
            module, report = orig.__func__(module)
            module.phase = 'Z'
            return module, report

        AntiSlopProcessor.humanize_with_report = hostile
        try:
            with patch_pipeline_ai(pipeline, _slop_meetings_fake(
                    tmr.ROWS_D)):
                result = pipeline.generate(dict(tmr.MEET_PARAMS))
        finally:
            AntiSlopProcessor.humanize_with_report = orig
        assert result['status'] != 'success'
        assert result['module'] is None
        assert result['errors']

    def test_readiness_verbatim_with_and_without(self, pipeline):
        import test_meetings_rpm as tmr
        from test_phase_c_module_generation import patch_pipeline_ai
        with patch_pipeline_ai(pipeline, _slop_meetings_fake(tmr.ROWS_D)):
            full = pipeline.generate(dict(tmr.MEET_PARAMS))
        assert full['status'] == 'success', full['errors']
        assert full['module']['student_readiness'] == \
            'Sebagian murid paham wahyu.'
        params = dict(tmr.MEET_PARAMS)
        params.pop('student_readiness', None)
        with patch_pipeline_ai(pipeline, _slop_meetings_fake(tmr.ROWS_D)):
            empty = pipeline.generate(params)
        assert empty['status'] == 'success', empty['errors']
        assert empty['module']['student_readiness'] == ''

    def test_db_records_untouched(self, pipeline):
        import sqlite3
        import test_meetings_rpm as tmr
        from test_phase_c_module_generation import patch_pipeline_ai
        db_path = str(pipeline.db_path)

        def digest():
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    'SELECT id, text, source_document, source_page '
                    'FROM learning_outcomes ORDER BY id LIMIT 50').fetchall()
                return rows
            finally:
                conn.close()

        before = digest()
        assert before
        with patch_pipeline_ai(pipeline, _slop_meetings_fake(tmr.ROWS_D)):
            result = pipeline.generate(dict(tmr.MEET_PARAMS))
        assert result['status'] == 'success', result['errors']
        assert digest() == before
