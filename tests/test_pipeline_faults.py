#!/usr/bin/env python3
"""Pipeline/curriculum fault fixes — targeted regression tests.

Covers:
- CP query filters (system/institution/version + active-only)
- source_fragment_id retained verbatim; missing -> fail closed
- curriculum_version override forbidden
- regulatory DB outage fails closed (fatal, no silent degrade)
- single mapping source (RuleEngine grade-phase from JSON, incl. KEMENDIKDASMEN)
- counts/link validators not weak (TP coverage, assessment traceability)
- blueprint has no inferred TP links
- topic preserved (seed vs refined) + refine wording explicit-only
- murid/formal validator across generated fields
- slop detect findings impact validation with documented regen path
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from module_generation_pipeline import (  # noqa: E402
    CurriculumValidator,
    FinalValidator,
    ModuleGenerationPipeline,
    PedagogicalValidator,
    build_blueprint,
    build_regulatory_context,
    default_curriculum_version,
)
from test_phase_c_module_generation import (  # noqa: E402
    VALID_PARAMS,
    fake_router_response,
    make_module,
    patch_pipeline_ai,
)


@pytest.fixture
def pipeline(test_db):
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    yield pipe
    pipe.curriculum_validator.close()


@pytest.fixture
def sample_context():
    from curriculum_context import CurriculumContext, CPEntry
    cp = CPEntry(
        id="CP-Akidah-Akhlak-D",
        text="Peserta didik menerapkan akhlak mulia melalui konsep taubat",
        source_document_id="DOC-SK-DIRJEN-9941",
        source_fragment_id="page-42",
        source_page=42,
        phase="D",
        element="Akhlak",
    )
    return CurriculumContext(
        education_system='KEMENAG',
        institution_type='MTs',
        grade='MTs_7',
        phase='D',
        subject='Akidah Akhlak',
        element='Akhlak',
        curriculum_version='KMA-1503-2025',
        cp=cp,
        tp_list=[],
        atp=None,
        rules={},
    )


# --- CP query filters -----------------------------------------------------

class TestCPQueryFilters:
    def test_active_only(self, curriculum_engine, test_db):
        import sqlite3
        con = sqlite3.connect(str(test_db))
        try:
            row = con.execute(
                "SELECT subject, phase FROM learning_outcomes "
                "WHERE status='active' LIMIT 1").fetchone()
            assert row, "need one active CP row in fixture DB"
            # Insert an inactive twin that must never leak into results.
            con.execute(
                "INSERT INTO learning_outcomes "
                "(id, subject, phase, element, text, source_page, "
                " source_document, education_system, institution_type, "
                " curriculum_version_id, program_type, status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ('CP-TEST-INACTIVE-1', row[0], row[1], 'Elemen Uji',
                 'Teks CP nonaktif yang tidak boleh bocor',
                 1, 'DOC-TEST', 'KEMENAG', 'madrasah',
                 'KMA-1503-2025', 'reguler', 'inactive'))
            con.commit()
        finally:
            con.close()
        got = curriculum_engine.get_cp_by_subject_phase(row[0], row[1])
        assert all('tidak boleh bocor' not in c.text for c in got)
        assert all((c.status or 'active') == 'active' for c in got)

    def test_system_filter_narrows(self, curriculum_engine):
        all_rows = curriculum_engine.get_cp_by_subject_phase(
            'Akidah Akhlak', 'D')
        kemenag_rows = curriculum_engine.get_cp_by_subject_phase(
            'Akidah Akhlak', 'D', education_system='KEMENAG')
        assert kemenag_rows
        assert {c.id for c in kemenag_rows} <= {c.id for c in all_rows}
        assert all(c.education_system == 'KEMENAG' for c in kemenag_rows)

    def test_version_filter_narrows(self, curriculum_engine):
        ver = default_curriculum_version('KEMENAG')
        rows = curriculum_engine.get_cp_by_subject_phase(
            'Akidah Akhlak', 'D', education_system='KEMENAG',
            curriculum_version_id=ver)
        assert rows
        assert all(c.curriculum_version_id == ver for c in rows)

    def test_missing_fragment_fails_closed(self, test_db):
        import sqlite3
        con = sqlite3.connect(str(test_db))
        try:
            con.execute(
                "UPDATE learning_outcomes SET source_fragment_id=NULL "
                "WHERE subject='Akidah Akhlak' AND phase='D' "
                "AND element='Pemahaman Konsep'")
            con.commit()
        finally:
            con.close()
        v = CurriculumValidator(str(test_db))
        try:
            ok, ctx, errors = v.validate(dict(VALID_PARAMS))
            assert ok is False and ctx is None
            assert any('CP_PROVENANCE_INVALID' in e for e in errors)
        finally:
            v.close()

    def test_version_override_forbidden(self, test_db):
        v = CurriculumValidator(str(test_db))
        try:
            params = dict(VALID_PARAMS, curriculum_version='HACK-1')
            ok, ctx, errors = v.validate(params)
            assert ok is False and ctx is None
            assert any('CURRICULUM_VERSION_OVERRIDE_FORBIDDEN' in e
                       for e in errors)
        finally:
            v.close()


# --- Regulatory outage fail closed ----------------------------------------

class TestRegulatoryFailClosed:
    def test_missing_db_is_fatal(self, tmp_path):
        rc = build_regulatory_context(
            'KEMENAG', 'Akidah Akhlak', 'D',
            db_path=str(tmp_path / 'nope.db'))
        assert rc['enabled'] is False
        assert rc.get('fatal') is True
        assert 'error' in rc

    def test_generate_stops_on_outage(self, pipeline):
        with patch.object(
                ModuleGenerationPipeline,
                'build_regulatory_context_for_generate',
                return_value={'enabled': False, 'sources': [],
                              'fatal': True, 'error': 'boom'}):
            result = pipeline.generate(dict(VALID_PARAMS))
        assert result['status'] == 'failed'
        assert result['validation']['regulatory_context']['passed'] is False


# --- Single mapping source -------------------------------------------------

class TestSingleMappingSource:
    def test_grade_phase_from_json_kemendikdasmen(self, rule_engine):
        from rule_engine import GradePhasePValidationRule
        import json
        with open('db/curriculum_mappings.json',
                  encoding='utf-8') as f:
            mappings = json.load(f)
        rule = GradePhasePValidationRule(mappings)
        gmap = mappings['grade_to_phase_mappings']['KEMENDIKDASMEN']
        inst = next(iter(gmap))
        grade = next(iter(gmap[inst]))
        phase = gmap[inst][grade]['phase']
        ok = rule.validate({'grade': grade, 'phase': phase,
                            'education_system': 'KEMENDIKDASMEN',
                            'institution_type': inst})
        assert ok.passed is True
        bad = rule.validate({'grade': grade, 'phase': 'ZZZ',
                             'education_system': 'KEMENDIKDASMEN',
                             'institution_type': inst})
        assert bad.passed is False


# --- Counts/link validators + blueprint ------------------------------------

class TestLinkValidators:
    def test_activity_count_without_links_fails(self):
        from module_generation_pipeline import ActivityEntry
        acts = [ActivityEntry(id='ACT-1', name='A', description='d',
                              duration=10, tp_linked='TP-1',
                              type='mengaplikasi'),
                ActivityEntry(id='ACT-2', name='B', description='d',
                              duration=10, tp_linked='TP-1',
                              type='mengaplikasi')]
        ok, errors = PedagogicalValidator.validate_activity_alignment(
            acts, 2)
        assert ok is False
        assert any('TP-2' in e for e in errors)

    def test_assessment_buckets_without_tp_links_fail(self):
        assessments = {
            'diagnostic': [{'question': 'q'}],
            'formative': [{'question': 'q'}],
            'summative': {'items': [{'question': 'q'}]},
        }
        ok, errors = PedagogicalValidator.validate_assessment_alignment(
            assessments, 2, 2)
        assert ok is False
        assert any('TP-1' in e for e in errors)

    def test_blueprint_no_inferred_links(self):
        tp_list = ['Menerapkan A', 'Menganalisis B']
        assessments = {'summative': {'items': [
            {'question': 'q1', 'type': 'essay',
             'tp_linked': 'TP-2', 'points': 10}]}}
        bp = build_blueprint(tp_list, assessments)
        assert bp[0]['tp_id'] == 'TP-1'
        assert bp[0]['item_count'] == 0
        assert bp[0]['question_form'] == []
        assert bp[1]['item_count'] == 1


# --- Topic / murid-formal / slop -------------------------------------------

class TestTopicMuridSlop:
    def test_topic_drift_fails(self, sample_context):
        module = make_module(sample_context, topic_seed='Zakat dan wakaf',
                             topic='Hujan badai fotosintesis kuantum')
        module.title = 'RPP/RPM X: Hujan'
        errors = FinalValidator.validate_topic_preserved(module)
        assert any('TOPIC_DRIFT' in e for e in errors)

    def test_topic_empty_refined_fails(self, sample_context):
        module = make_module(sample_context, topic_seed='Zakat',
                             topic='')
        errors = FinalValidator.validate_topic_preserved(module)
        assert any('TOPIC_DRIFT' in e for e in errors)

    def test_murid_term_flagged(self, sample_context):
        module = make_module(sample_context)
        module.guiding_questions = ['Peserta didik harus apa?']
        errors = FinalValidator.validate_murid_formal(module)
        assert any('MURID_TERM_INVALID' in e for e in errors)

    def test_siswa_term_flagged(self, sample_context):
        module = make_module(sample_context)
        module.guiding_questions = ['Siswa mengerjakan tugas dan lain-lain.']
        errors = FinalValidator.validate_murid_formal(module)
        assert any('MURID_TERM_INVALID' in e for e in errors)
        assert any('FORMAL_LANGUAGE_INVALID' in e for e in errors)

    def test_quoted_dalil_exempt(self, sample_context):
        module = make_module(sample_context)
        module.guiding_questions = ['"Peserta didik yang baik" adalah kutipan.']
        errors = FinalValidator.validate_murid_formal(module)
        assert not any('MURID_TERM_INVALID' in e for e in errors)

    def test_slop_ceiling_fails_with_regen_path(self, pipeline):
        report = {'findings': [{'rule': r, 'excerpt': 'x'}
                               for r in ['R-16', 'R-36-fake-candid',
                                         'R-36-authority-trope',
                                         'R-36-caps', 'R-36-staccato',
                                         'R-36-quotes',
                                         'R-36-inline-header']]}
        errors = pipeline._slop_gate(report)
        assert errors and 'SLOP_THRESHOLD_EXCEEDED' in errors[0]
        assert 'generate()' in errors[0]

    def test_slop_below_ceiling_passes(self, pipeline):
        report = {'findings': [{'rule': 'R-16', 'excerpt': 'x'}]}
        assert pipeline._slop_gate(report) == []

    def test_full_generate_still_success(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(dict(VALID_PARAMS))
        assert result['status'] == 'success', result.get('errors')
