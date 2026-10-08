#!/usr/bin/env python3
"""
PHASE C: Comprehensive Module Generation Tests
Tests for real AI module generation pipeline with full validation

Covers:
- CurriculumValidator (real DB retrieval)
- StructureValidator (JSON / TP / KKTP structure)
- RuleValidator (C3+ via KKO keyword extraction + RuleEngine)
- PedagogicalValidator (activity/assessment alignment, FATAL)
- ProtectionValidator (CP/phase/subject/element/education_system/
  curriculum_version/provenance immutable, AI override rejected)
- AntiSlopProcessor (protected fields untouched)
- FinalValidator (completeness + TP->KKTP->Activity->Assessment relationships)
- ModuleGenerationPipeline (instantiation, mocked E2E success + failure paths)
"""

import json
import re
import uuid
from unittest.mock import patch

import pytest

from module_generation_pipeline import (
    ModuleGenerationPipeline,
    CurriculumValidator,
    StructureValidator,
    ProtectionValidator,
    RuleValidator,
    PedagogicalValidator,
    AntiSlopProcessor,
    FinalValidator,
    MasterOutlineValidator,
    Module,
    TPEntry,
    KKTPEntry,
    ActivityEntry,
    AssessmentItem,
    ValidationResult,
    resolve_grade_key,
    allowed_profile_values,
    SCORING_INTERVALS,
)
from curriculum_context import CurriculumContext, CPEntry
from nine_router_client import NineRouterConfig, NineRouterError
from nine_router_client import AuthenticationError


VALID_PARAMS = {
    'education_system': 'KEMENAG',
    'institution_type': 'MTs',
    'grade': 'MTs_7',
    'subject': 'Akidah Akhlak',
    # Elemen resmi parser v2 (item bernomor per fase di 9941/2025):
    # Pemahaman Konsep / Keterampilan Proses. Cakupan (Akidah, Akhlak,
    # Adab, Kisah Keteladanan) adalah sub_element, bukan element.
    'element': 'Pemahaman Konsep',
    'topic': 'Taubat',
    'requested_tp_count': 3
}


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def pipeline(test_db):
    """Pipeline wired to a temp copy of the production database."""
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    yield pipe
    # Release the sqlite connection so Windows can clean up the temp dir
    pipe.curriculum_validator.close()


@pytest.fixture
def sample_context():
    """A minimal valid CurriculumContext."""
    cp = CPEntry(
        id="CP-Akidah-Akhlak-D",
        text="Peserta didik menerapkan akhlak mulia melalui konsep taubat",
        source_document_id="DOC-SK-DIRJEN-9941",
        source_fragment_id="page-42",
        source_page=42,
        phase="D",
        element="Akhlak"
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
        rules={}
    )


def make_module(context, **overrides):
    """Build a complete valid Module for validator tests."""
    module = Module(
        id="MOD-TEST-001",
        title="Modul Taubat",
        subject=context.subject,
        grade=context.grade,
        phase=context.phase,
        curriculum_version=context.curriculum_version,
        module_identity={},
        facilities=[],
        target_students={},
        learning_model="Discovery Learning",
        methods=[],
        learning_objectives=[
            TPEntry(id="TP-1", text="Menerapkan konsep taubat",
                    cognitive_level="C3", cp_reference=context.cp.id),
            TPEntry(id="TP-2", text="Menganalisis perilaku taubat",
                    cognitive_level="C4", cp_reference=context.cp.id),
        ],
        success_criteria=[
            KKTPEntry(id="KKTP-1", tp_id="TP-1",
                      criteria=["Menerapkan tiga langkah taubat"], cognitive_level="C3"),
            KKTPEntry(id="KKTP-2", tp_id="TP-2",
                      criteria=["Menganalisis dua contoh kasus"], cognitive_level="C4"),
        ],
        essential_understanding={},
        guiding_questions=[],
        learning_activities=[
            ActivityEntry(id="ACT-1", name="Diskusi", description="Menerapkan konsep",
                          duration=45, tp_linked="TP-1", type="Diskusi"),
            ActivityEntry(id="ACT-2", name="Studi kasus", description="Menganalisis kasus",
                          duration=45, tp_linked="TP-2", type="Studi Kasus"),
        ],
        assessments={
            "diagnostic": [{"question": "Apa itu taubat?", "type": "multiple_choice"}],
            "formative": [{"question": "Terapkan langkah taubat", "type": "short_answer",
                           "tp_linked": "TP-1"}],
            "summative": {"items": [{"question": "Uji kasus", "type": "essay",
                                     "tp_linked": "TP-2", "kktp_linked": "KKTP-2",
                                     "points": 100}], "rubric": "Rubrik"},
        },
        curriculum_context=context,
        generation_id=str(uuid.uuid4()),
        generated_at="2026-09-19T00:00:00",
    )
    for key, value in overrides.items():
        setattr(module, key, value)
    return module


# ============================================================================
# CURRICULUM VALIDATOR (real DB)
# ============================================================================

@pytest.mark.curriculum
class TestCurriculumValidator:
    """CurriculumValidator retrieves real CP from the database."""

    def test_curriculum_validator_exists(self, test_db):
        validator = CurriculumValidator(str(test_db))
        assert validator is not None

    def test_validate_accepts_valid_params(self, test_db):
        validator = CurriculumValidator(str(test_db))
        try:
            is_valid, context, errors = validator.validate(VALID_PARAMS)
            assert is_valid is True, errors
            assert context is not None
            assert context.phase == 'D'
            assert context.cp.text  # Real CP text from DB
            assert context.cp.source_document_id  # Real provenance
        finally:
            validator.close()

    def test_validate_rejects_missing_fields(self, test_db):
        validator = CurriculumValidator(str(test_db))
        is_valid, context, errors = validator.validate({})
        assert is_valid is False
        assert context is None
        # 'element' is now optional (BLOCKER 3 deterministic resolution)
        assert len(errors) >= 4

    def test_validate_rejects_invalid_education_system(self, test_db):
        validator = CurriculumValidator(str(test_db))
        params = dict(VALID_PARAMS, education_system='INVALID')
        is_valid, context, errors = validator.validate(params)
        assert is_valid is False
        assert any('education_system' in e for e in errors)

    def test_validate_rejects_invalid_grade(self, test_db):
        validator = CurriculumValidator(str(test_db))
        params = dict(VALID_PARAMS, grade='MTs_99')
        is_valid, context, errors = validator.validate(params)
        assert is_valid is False

    def test_validate_rejects_wrong_subject_for_system(self, test_db):
        validator = CurriculumValidator(str(test_db))
        params = dict(VALID_PARAMS, subject='Pendidikan Agama dan Budi Pekerti')
        is_valid, context, errors = validator.validate(params)
        assert is_valid is False


# ============================================================================
# STRUCTURE VALIDATOR
# ============================================================================

class TestStructureValidator:
    """JSON parsing and TP/KKTP structure checks."""

    def test_validate_json_valid(self):
        is_valid, data, error = StructureValidator.validate_json('{"a": 1}')
        assert is_valid is True
        assert data == {"a": 1}
        assert error == ""

    def test_validate_json_invalid(self):
        is_valid, data, error = StructureValidator.validate_json('not json {')
        assert is_valid is False
        assert data is None
        assert 'Invalid JSON' in error

    def test_validate_json_rejects_non_object(self):
        is_valid, data, error = StructureValidator.validate_json('[1, 2, 3]')
        assert is_valid is False
        assert 'JSON object' in error

    def test_validate_tp_structure_valid(self):
        is_valid, errors = StructureValidator.validate_tp_structure(
            ["Menerapkan A", "Menganalisis B"]
        )
        assert is_valid is True
        assert errors == []

    def test_validate_tp_structure_empty(self):
        is_valid, errors = StructureValidator.validate_tp_structure([])
        assert is_valid is False
        assert 'empty' in errors[0].lower()

    def test_validate_tp_structure_not_list(self):
        is_valid, errors = StructureValidator.validate_tp_structure("TP-1")
        assert is_valid is False

    def test_validate_tp_structure_too_many(self):
        is_valid, errors = StructureValidator.validate_tp_structure(["TP"] * 7)
        assert is_valid is False

    def test_validate_kktp_structure_valid(self):
        kktp = [KKTPEntry(id="KKTP-1", tp_id="TP-1", criteria=["c1"], cognitive_level="C3")]
        is_valid, errors = StructureValidator.validate_kktp_structure(kktp)
        assert is_valid is True

    def test_validate_kktp_structure_empty_list_rejected(self):
        is_valid, errors = StructureValidator.validate_kktp_structure([])
        assert is_valid is False

    def test_validate_kktp_structure_missing_criteria_rejected(self):
        kktp = [KKTPEntry(id="KKTP-1", tp_id="TP-1", criteria=[], cognitive_level="C3")]
        is_valid, errors = StructureValidator.validate_kktp_structure(kktp)
        assert is_valid is False
        assert any('criteria' in e for e in errors)

    def test_validate_kktp_structure_misaligned_tp_rejected(self):
        kktp = [KKTPEntry(id="KKTP-1", tp_id="TP-9", criteria=["c"], cognitive_level="C3")]
        is_valid, errors = StructureValidator.validate_kktp_structure(kktp)
        assert is_valid is False


# ============================================================================
# RULE VALIDATOR (C3+ KKO extraction)
# ============================================================================

class TestRuleValidator:
    """Cognitive level enforcement via KKO keyword extraction."""

    @pytest.fixture
    def rule_validator(self, test_db):
        return RuleValidator(str(test_db))

    def test_rule_validator_exists(self, rule_validator):
        assert rule_validator is not None
        assert rule_validator.rule_engine is not None

    def test_cognitive_level_extraction_c3(self, rule_validator):
        assert rule_validator._extract_cognitive_level(
            "Siswa menerapkan konsep taubat") == 'C3'

    def test_cognitive_level_extraction_c4(self, rule_validator):
        assert rule_validator._extract_cognitive_level(
            "Siswa menganalisis kasus taubat") == 'C4'

    def test_cognitive_level_extraction_c5(self, rule_validator):
        assert rule_validator._extract_cognitive_level(
            "Siswa mengevaluasi praktik taubat") == 'C5'

    def test_cognitive_level_extraction_c6(self, rule_validator):
        assert rule_validator._extract_cognitive_level(
            "Siswa merancang program taubat") == 'C6'

    def test_cognitive_level_c3_accepted(self, rule_validator):
        is_valid, level, error = rule_validator.validate_tp_cognitive_level(
            "Menerapkan konsep taubat dalam kehidupan")
        assert is_valid is True
        assert level == 'C3'

    def test_cognitive_level_c4_accepted(self, rule_validator):
        is_valid, level, _ = rule_validator.validate_tp_cognitive_level(
            "Menganalisis perilaku taubat")
        assert is_valid is True

    def test_cognitive_level_c5_accepted(self, rule_validator):
        is_valid, level, _ = rule_validator.validate_tp_cognitive_level(
            "Mengevaluasi kejujuran dalam taubat")
        assert is_valid is True

    def test_cognitive_level_c6_accepted(self, rule_validator):
        is_valid, level, _ = rule_validator.validate_tp_cognitive_level(
            "Merancang kampanye taubat digital")
        assert is_valid is True

    def test_cognitive_level_c2_rejected(self, rule_validator):
        is_valid, level, error = rule_validator.validate_tp_cognitive_level(
            "Membandingkan dua pendapat ulama")
        assert is_valid is False
        assert level == 'C2'
        assert 'C3' in error

    def test_cognitive_level_c1_rejected(self, rule_validator):
        is_valid, level, error = rule_validator.validate_tp_cognitive_level(
            "Menyebutkan rukun taubat")
        assert is_valid is False
        assert level == 'C1'

    def test_unknown_level_rejected(self, rule_validator):
        is_valid, level, _ = rule_validator.validate_tp_cognitive_level(
            "Taubat itu penting")
        assert is_valid is False
        assert level == 'UNKNOWN'

    def test_kktp_cognitive_level_validated(self, rule_validator):
        is_valid, level, _ = rule_validator.validate_kktp_cognitive_level(
            "Menerapkan langkah taubat dengan benar")
        assert is_valid is True
        is_valid, level, _ = rule_validator.validate_kktp_cognitive_level(
            "Menyebutkan definisi taubat")
        assert is_valid is False


# ============================================================================
# PEDAGOGICAL VALIDATOR
# ============================================================================

class TestPedagogicalValidator:
    """Alignment checks that are fatal in the pipeline."""

    def test_pedagogical_validator_exists(self):
        assert PedagogicalValidator is not None

    def test_activity_alignment_sufficient(self):
        activities = [ActivityEntry(id=f"ACT-{i}", name="A", description="d",
                                    duration=45, tp_linked=f"TP-{i}", type="Diskusi")
                      for i in range(1, 4)]
        is_valid, errors = PedagogicalValidator.validate_activity_alignment(
            activities, 3)
        assert is_valid is True

    def test_activity_alignment_insufficient(self):
        activities = [ActivityEntry(id="ACT-1", name="A", description="d",
                                    duration=45, tp_linked="TP-1", type="Diskusi")]
        is_valid, errors = PedagogicalValidator.validate_activity_alignment(
            activities, 3)
        assert is_valid is False
        assert len(errors) > 0

    def test_assessment_alignment_complete(self):
        assessments = {
            "diagnostic": [{"question": "q", "tp_linked": "TP-1"}],
            "formative": [{"question": "q", "tp_linked": "TP-2"}],
            "summative": {"items": [{"question": "q",
                                      "tp_linked": "TP-1"}]},
        }
        is_valid, errors = PedagogicalValidator.validate_assessment_alignment(
            assessments, 2, 2)
        assert is_valid is True

    def test_assessment_alignment_unlinked_rejected(self):
        # Buckets present but no explicit tp_linked: weak coverage that
        # must fail (every TP needs a linked assessment item).
        assessments = {
            "diagnostic": [{"question": "q"}],
            "formative": [{"question": "q"}],
            "summative": {"items": [{"question": "q"}]},
        }
        is_valid, errors = PedagogicalValidator.validate_assessment_alignment(
            assessments, 2, 2)
        assert is_valid is False
        assert any('TP-1' in e for e in errors)

    def test_assessment_alignment_missing_diagnostic(self):
        # R-42: bucket kosong dilewati; item tanpa tp_linked tetap gagal.
        assessments = {"formative": [{"q": 1}], "summative": {"items": []}}
        is_valid, errors = PedagogicalValidator.validate_assessment_alignment(
            assessments, 2, 2)
        assert is_valid is False

    def test_assessment_alignment_missing_formative(self):
        assessments = {"diagnostic": [{"q": 1}], "summative": {"items": []}}
        is_valid, errors = PedagogicalValidator.validate_assessment_alignment(
            assessments, 2, 2)
        assert is_valid is False

    def test_assessment_alignment_missing_summative(self):
        assessments = {"diagnostic": [{"q": 1}], "formative": [{"q": 1}]}
        is_valid, errors = PedagogicalValidator.validate_assessment_alignment(
            assessments, 2, 2)
        assert is_valid is False

    def test_assessment_alignment_empty_rejected(self):
        is_valid, errors = PedagogicalValidator.validate_assessment_alignment(
            {}, 2, 2)
        assert is_valid is False


# ============================================================================
# PROTECTION VALIDATOR
# ============================================================================

class TestProtectionValidator:
    """AI output cannot change protected curriculum fields."""

    def test_protection_validator_exists(self):
        assert ProtectionValidator is not None

    def test_protected_fields_set_defined(self):
        assert 'cp' in ProtectionValidator.PROTECTED_FIELDS
        assert 'phase' in ProtectionValidator.PROTECTED_FIELDS
        assert 'subject' in ProtectionValidator.PROTECTED_FIELDS
        assert 'element' in ProtectionValidator.PROTECTED_FIELDS
        assert 'education_system' in ProtectionValidator.PROTECTED_FIELDS
        assert 'curriculum_version' in ProtectionValidator.PROTECTED_FIELDS

    def test_untouched_module_passes(self, sample_context):
        module = make_module(sample_context)
        is_valid, errors = ProtectionValidator().validate(sample_context, module)
        assert is_valid is True, errors

    def test_protected_cp_cannot_change(self, sample_context):
        tampered_ctx = CurriculumContext(
            education_system=sample_context.education_system,
            institution_type=sample_context.institution_type,
            grade=sample_context.grade,
            phase=sample_context.phase,
            subject=sample_context.subject,
            element=sample_context.element,
            curriculum_version=sample_context.curriculum_version,
            cp=CPEntry(
                id=sample_context.cp.id,
                text="CP YANG SUDAH DIUBAH OLEH AI",
                source_document_id=sample_context.cp.source_document_id,
                source_fragment_id=sample_context.cp.source_fragment_id,
                source_page=sample_context.cp.source_page,
                phase=sample_context.phase,
                element=sample_context.element,
            ),
            tp_list=[],
            atp=None,
            rules={}
        )
        module = make_module(sample_context, curriculum_context=tampered_ctx)
        is_valid, errors = ProtectionValidator().validate(sample_context, module)
        assert is_valid is False
        assert any('CP' in e for e in errors)

    def test_protected_phase_cannot_change(self, sample_context):
        tampered_ctx = CurriculumContext(
            education_system=sample_context.education_system,
            institution_type=sample_context.institution_type,
            grade=sample_context.grade,
            phase='E',  # AI tried to change phase
            subject=sample_context.subject,
            element=sample_context.element,
            curriculum_version=sample_context.curriculum_version,
            cp=sample_context.cp,
            tp_list=[],
            atp=None,
            rules={}
        )
        module = make_module(sample_context, curriculum_context=tampered_ctx)
        is_valid, errors = ProtectionValidator().validate(sample_context, module)
        assert is_valid is False
        assert any('Phase' in e for e in errors)

    def test_protected_subject_cannot_change(self, sample_context):
        module = make_module(sample_context, subject='Fikih')
        is_valid, errors = ProtectionValidator().validate(sample_context, module)
        assert is_valid is False
        assert any('subject' in e.lower() for e in errors)

    def test_protected_element_cannot_change(self, sample_context):
        module = make_module(
            sample_context,
            curriculum_context=CurriculumContext(
                education_system=sample_context.education_system,
                institution_type=sample_context.institution_type,
                grade=sample_context.grade,
                phase=sample_context.phase,
                subject=sample_context.subject,
                element='Keterampilan Proses',  # changed
                curriculum_version=sample_context.curriculum_version,
                cp=sample_context.cp,
                tp_list=[],
                atp=None,
                rules={}
            )
        )
        is_valid, errors = ProtectionValidator().validate(sample_context, module)
        assert is_valid is False
        assert any('Element' in e for e in errors)

    def test_provenance_cannot_change(self, sample_context):
        tampered_ctx = CurriculumContext(
            education_system=sample_context.education_system,
            institution_type=sample_context.institution_type,
            grade=sample_context.grade,
            phase=sample_context.phase,
            subject=sample_context.subject,
            element=sample_context.element,
            curriculum_version=sample_context.curriculum_version,
            cp=CPEntry(
                id=sample_context.cp.id,
                text=sample_context.cp.text,
                source_document_id="FAKE-DOC",  # provenance tampered
                source_fragment_id=sample_context.cp.source_fragment_id,
                source_page=sample_context.cp.source_page,
                phase=sample_context.phase,
                element=sample_context.element,
            ),
            tp_list=[],
            atp=None,
            rules={}
        )
        module = make_module(sample_context, curriculum_context=tampered_ctx)
        is_valid, errors = ProtectionValidator().validate(sample_context, module)
        assert is_valid is False
        assert any('source' in e.lower() for e in errors)

    def test_ai_output_cannot_define_protected_fields(self):
        validator = ProtectionValidator()
        is_valid, errors = validator.validate_ai_output(
            None, {"tp_list": ["x"], "subject": "Fikih", "phase": "F"})
        assert is_valid is False
        assert len(errors) == 2

    def test_ai_output_without_protected_fields_passes(self):
        validator = ProtectionValidator()
        is_valid, errors = validator.validate_ai_output(
            None, {"tp_list": ["Menerapkan X"]})
        assert is_valid is True


# ============================================================================
# ANTI-SLOP PROCESSOR
# ============================================================================

class TestAntiSlopProcessor:
    """Humanization never touches protected fields."""

    def test_protected_fields_untouched(self):
        for field_name in ['cp', 'tp', 'kktp', 'phase', 'subject', 'element',
                           'citations', 'references', 'dates']:
            text = f"NORMATIVE {field_name} TEXT"
            assert AntiSlopProcessor.humanize_section(text, field_name) == text

    def test_humanizable_fields_processed(self):
        result = AntiSlopProcessor.humanize_section(
            "Aktivitas untuk peserta didik", 'activity_description')
        assert result == "Aktivitas untuk murid"

    def test_humanize_preserves_cp_tp_and_links(self, sample_context):
        module = make_module(sample_context)
        cp_before = module.curriculum_context.cp.text
        tp_before = [tp.text for tp in module.learning_objectives]
        links_before = [a.tp_linked for a in module.learning_activities]
        kktp_before = [k.criteria for k in module.success_criteria]

        module = AntiSlopProcessor.humanize(module)

        assert module.curriculum_context.cp.text == cp_before
        assert [tp.text for tp in module.learning_objectives] == tp_before
        assert [a.tp_linked for a in module.learning_activities] == links_before
        assert [k.criteria for k in module.success_criteria] == kktp_before


# ============================================================================
# FINAL VALIDATOR
# ============================================================================

class TestFinalValidator:
    """Completeness and explicit relationship validation."""

    def test_complete_module_passes(self, sample_context):
        is_valid, errors = FinalValidator.validate_completeness(
            make_module(sample_context))
        assert is_valid is True, errors

    def test_missing_tp_rejected(self, sample_context):
        module = make_module(sample_context, learning_objectives=[])
        is_valid, errors = FinalValidator.validate_completeness(module)
        assert is_valid is False
        assert any('objectives' in e.lower() for e in errors)

    def test_missing_kktp_rejected(self, sample_context):
        module = make_module(sample_context, success_criteria=[])
        is_valid, errors = FinalValidator.validate_completeness(module)
        assert is_valid is False
        assert any('KKTP' in e for e in errors)

    def test_missing_activity_rejected(self, sample_context):
        module = make_module(sample_context, learning_activities=[])
        is_valid, errors = FinalValidator.validate_completeness(module)
        assert is_valid is False

    def test_missing_assessment_passes(self, sample_context):
        # R-42: tanpa asesmen tetap lengkap (asesmen opsional).
        module = make_module(sample_context, assessments={})
        is_valid, errors = FinalValidator.validate_completeness(module)
        assert is_valid is True

    def test_missing_generation_id_rejected(self, sample_context):
        module = make_module(sample_context, generation_id="")
        is_valid, errors = FinalValidator.validate_completeness(module)
        assert is_valid is False
        assert any('Generation ID' in e for e in errors)

    def test_tp_kktp_alignment_valid(self, sample_context):
        is_valid, errors = FinalValidator.validate_relationships(
            make_module(sample_context))
        assert is_valid is True, errors

    def test_kktp_referencing_missing_tp_rejected(self, sample_context):
        module = make_module(sample_context)
        module.success_criteria[0].tp_id = "TP-99"
        is_valid, errors = FinalValidator.validate_relationships(module)
        assert is_valid is False
        assert any('KKTP-1' in e for e in errors)

    def test_activity_referencing_missing_tp_rejected(self, sample_context):
        module = make_module(sample_context)
        module.learning_activities[0].tp_linked = "TP-99"
        is_valid, errors = FinalValidator.validate_relationships(module)
        assert is_valid is False

    def test_assessment_referencing_missing_kktp_rejected(self, sample_context):
        module = make_module(sample_context)
        module.assessments["summative"]["items"][0]["kktp_linked"] = "KKTP-99"
        is_valid, errors = FinalValidator.validate_relationships(module)
        assert is_valid is False
        assert any('KKTP-99' in e for e in errors)

    def test_immutability_helper(self):
        is_valid, errors = FinalValidator.validate_immutability(
            {'cp': 'A', 'phase': 'D'}, {'cp': 'A', 'phase': 'D'})
        assert is_valid is True
        is_valid, errors = FinalValidator.validate_immutability(
            {'cp': 'A'}, {'cp': 'B'})
        assert is_valid is False


# ============================================================================
# DATACLASSES
# ============================================================================

class TestModuleStructure:

    def test_module_creation_minimal(self, sample_context):
        module = make_module(sample_context)
        assert module.title == "Modul Taubat"
        assert module.phase == 'D'

    def test_module_creation_phase_c_fields(self, sample_context):
        module = make_module(sample_context)
        assert module.generation_id
        assert module.generated_by == "9router-rpm"
        assert module.curriculum_context is sample_context

    def test_module_to_dict(self, sample_context):
        data = make_module(sample_context).to_dict()
        assert isinstance(data, dict)
        assert data['id'] == "MOD-TEST-001"

    def test_module_to_json(self, sample_context):
        parsed = json.loads(make_module(sample_context).to_json())
        assert parsed['subject'] == 'Akidah Akhlak'

    def test_tp_entry_creation(self):
        tp = TPEntry(id="TP-1", text="Menerapkan", cognitive_level="C3",
                     cp_reference="CP-1")
        assert tp.source_type == "ai_generated"

    def test_tp_entry_with_source_type(self):
        tp = TPEntry(id="TP-1", text="x", cognitive_level="C3", cp_reference="CP-1",
                     source_type="teacher")
        assert tp.source_type == "teacher"

    def test_kktp_entry_creation(self):
        kktp = KKTPEntry(id="KKTP-1", tp_id="TP-1", criteria=["a"], cognitive_level="C3")
        assert kktp.tp_id == "TP-1"

    def test_kktp_entry_alignment_with_tp(self):
        kktp = KKTPEntry(id="KKTP-1", tp_id="TP-1", criteria=["a"], cognitive_level="C3")
        assert kktp.id == "KKTP-1" and kktp.tp_id == "TP-1"

    def test_activity_entry_creation(self):
        activity = ActivityEntry(id="ACT-1", name="A", description="d", duration=45,
                                 tp_linked="TP-1", type="Diskusi")
        assert activity.resources == []

    def test_activity_entry_with_resources(self):
        activity = ActivityEntry(id="ACT-1", name="A", description="d", duration=45,
                                 tp_linked="TP-1", type="Diskusi",
                                 resources=["Al-Qur'an"])
        assert activity.resources == ["Al-Qur'an"]

    def test_assessment_item_creation(self):
        item = AssessmentItem(id="AS-1", question="q", type="essay")
        assert item.points == 0

    def test_assessment_item_with_points(self):
        item = AssessmentItem(id="AS-1", question="q", type="essay", points=10)
        assert item.points == 10

    def test_validation_result_creation(self):
        vr = ValidationResult(stage_name="s", passed=True)
        assert vr.passed is True

    def test_validation_result_with_errors(self):
        vr = ValidationResult(stage_name="s", passed=False, errors=["e1"])
        assert vr.errors == ["e1"]


# ============================================================================
# PIPELINE INSTANTIATION & CONFIG
# ============================================================================

@pytest.mark.integration
class TestModuleGenerationPipeline:

    def test_pipeline_initialization(self, pipeline):
        assert pipeline is not None
        assert pipeline.ai_client is not None
        assert pipeline.curriculum_validator.curriculum_engine.connection is not None

    def test_pipeline_has_validators(self, pipeline):
        assert pipeline.structure_validator is not None
        assert pipeline.protection_validator is not None
        assert pipeline.rule_validator is not None
        assert pipeline.pedagogical_validator is not None
        assert pipeline.anti_slop is not None
        assert pipeline.final_validator is not None

    def test_combo_is_rpm(self, pipeline):
        """Default combo is the RPM Pembelajaran Mendalam product."""
        with patch.dict('os.environ', {}, clear=True):
            config = NineRouterConfig.from_environment()
        assert config.combo == "rpm"
        assert pipeline.ai_client.config.combo == "rpm"

    def test_result_starts_failed_not_success(self, pipeline):
        """Status must be earned: the initial result state is 'failed'."""
        params = dict(VALID_PARAMS, grade='MTs_99')
        result = pipeline.generate(params)
        assert result['status'] == 'failed'
        assert result['module'] is None


# ============================================================================
# MOCKED END-TO-END SCENARIOS
# ============================================================================

def mock_meeting_principles(n: int = 2):
    """Prinsip per pertemuan yang valid untuk mock meetings (test helper).

    Teks berbeda per prinsip dan per pertemuan (memenuhi kontrak
    _validate_meeting_principles)."
    """
    verbs = {
        'berkesadaran': 'menyadari tujuan dan langkah kegiatan',
        'bermakna': 'menghubungkan materi dengan pengalaman nyata',
        'menggembirakan': 'belajar melalui permainan dan apresiasi',
    }
    out = []
    for meeting in range(1, n + 1):
        out.append({
            'meeting': meeting,
            'berkesadaran': (
                f"Pertemuan {meeting}: siswa {verbs['berkesadaran']} "
                f"pada kegiatan pertemuan {meeting}."),
            'bermakna': (
                f"Pertemuan {meeting}: siswa {verbs['bermakna']} "
                f"pada kegiatan pertemuan {meeting}."),
            'menggembirakan': (
                f"Pertemuan {meeting}: siswa {verbs['menggembirakan']} "
                f"pada kegiatan pertemuan {meeting}."),
        })
    return out


def fake_router_response(prompt: str, system_instruction=None, **kwargs):
    """Dispatch fake 9Router responses based on prompt markers."""
    if 'topik_rpm' in prompt:
        seed = ''
        m = re.search(r'Topik dari guru.*?:\n(.+?)\n', prompt, re.DOTALL)
        if m:
            seed = m.group(1).strip().split('\n')[0]
        return {"topik_rpm": f"{seed} dalam Pembelajaran"}
    if 'tp_list' in prompt:
        return {"tp_list": [
            "Menerapkan konsep taubat dalam kehidupan sehari-hari",
            "Menganalisis dampak taubat terhadap perilaku siswa",
            "Mengevaluasi praktik taubat yang sesuai tuntunan Islam",
        ]}
    if 'criteria' in prompt:
        return {"criteria": ["Menerapkan langkah taubat dengan benar",
                             "Menganalisis contoh kasus taubat"],
                "level": _tp_level_from_prompt(prompt)}
    if 'introduction' in prompt:
        return {"introduction": "Pengenalan materi taubat",
                "main_content": "Isi utama materi taubat",
                "key_concepts": ["Taubat", "Muhasabah"],
                "essential_understanding": {
                    "core_insight": "Taubat adalah mekanisme penghapus dosa "
                                    "yang memulihkan hubungan hamba dengan Allah",
                    "relationship": "Keikhlasan menentukan diterimanya taubat",
                    "application": "Siswa membiasakan muhasabah harian",
                    "value": "Menumbuhkan kerendahan hati dan harapan",
                }}
    if 'activities' in prompt:
        n = 0
        m = re.search(r'pertemuan 1\.\.(\d+)', prompt)
        if m:
            n = int(m.group(1))
        resp = {"activities": [
            {"name": "Apersepsi taubat", "description": "Siswa mengingat kembali konsep dasar",
             "duration": 15, "experience": "memahami"},
            {"name": "Diskusi taubat", "description": "Siswa menerapkan konsep taubat",
             "duration": 45, "experience": "mengaplikasi", "tp_linked": "TP-1"},
            {"name": "Studi kasus", "description": "Siswa menganalisis kasus",
             "duration": 45, "experience": "mengaplikasi", "tp_linked": "TP-2"},
            {"name": "Evaluasi praktik", "description": "Siswa mengevaluasi praktik",
             "duration": 45, "experience": "mengaplikasi", "tp_linked": "TP-3"},
            {"name": "Refleksi pengalaman", "description": "Siswa merefleksikan pembelajaran",
             "duration": 15, "experience": "merefleksi"},
        ]}
        if n >= 1:
            resp["meeting_principles"] = mock_meeting_principles(n)
        return resp
    if 'triggering_questions' in prompt:
        return {
            "triggering_questions": ["Mengapa taubat penting bagi seorang muslim?"],
            "initial_competence": {"description": "Siswa sudah memahami iman",
                                    "prerequisites": ["Rukun iman"]},
            "student_reflection": ["Apa yang saya pelajari hari ini?"],
            "teacher_reflection": ["Apakah pembelajaran berjalan efektif?"],
            "lkpd": [
                {"id": "LKPD-1", "tp_linked": "TP-1", "title": "LKPD Taubat 1",
                 "instructions": "Kerjakan langkah taubat", "task": "Tuliskan langkahnya"},
                {"id": "LKPD-2", "tp_linked": "TP-2", "title": "LKPD Taubat 2",
                 "instructions": "Analisis kasus berikut", "task": "Analisis dampaknya"},
                {"id": "LKPD-3", "tp_linked": "TP-3", "title": "LKPD Taubat 3",
                 "instructions": "Evaluasi praktik", "task": "Buat penilaian"},
            ],
            "remedial": {"description": "Pendampingan langkah taubat",
                          "tp_reference": ["TP-1"]},
            "enrichment": {"description": "Studi kasus taubat nabi",
                            "tp_reference": ["TP-3"]},
            "profile_dimensions": ["Kolaborasi", "Kreativitas"],
            "profile_dimension_notes": {
                "Kolaborasi": "Kolaborasi relevan karena siswa berdiskusi "
                              "kelompok menganalisis kasus taubat dan "
                              "mempresentasikan hasilnya bersama.",
                "Kreativitas": "Kreativitas terwujud saat siswa merancang "
                               "rencana perbaikan diri dan menyusun peta "
                               "konsep taubat nasuha.",
            },
            "pedagogical_practices": ["Pembelajaran berbasis masalah", "Diskusi kelompok"],
            "learner_readiness": {"hasil_diagnostik": "Sebagian besar murid sudah memahami konsep dasar"},
            "material_characteristics": {"tingkat_kompleksitas": "Sedang - konsep normatif"},
            "learning_environment": {"setting": "Kelas dan lingkungan sekolah"},
            "digital_use": {"media": "LKS digital dan video pembelajaran"},
            "kbc": {"themes": ["Cinta Allah dan Rasul-Nya"],
                    "insertion_material": ["Insersi cerita taubat nabi"],
                    "integration_note": "Ditautkan pada pengalaman belajar merefleksi"},
        }
    if 'diagnostic' in prompt:
        counts = {}
        for key in ('diagnostic', 'formative', 'summative'):
            m = re.search(key + r' PERSIS (\d+)', prompt)
            counts[key] = int(m.group(1)) if m else None
        n_diag = counts['diagnostic'] or 1
        n_form = counts['formative'] or 3
        n_sum = counts['summative'] or 3

        def _tp(i):
            return f"TP-{(i % 3) + 1}"

        def _kktp(i):
            return f"KKTP-{(i % 3) + 1}"

        def _mc(i):
            return {
                "question": f"Apa pengertian taubat? (diagnostik {i + 1})"
                if i else "Apa pengertian taubat?",
                "type": "multiple_choice",
                "options": [
                    {"label": "A", "text": "Jawaban A taubat"},
                    {"label": "B", "text": "Jawaban B taubat"},
                    {"label": "C", "text": "Jawaban C taubat"},
                    {"label": "D", "text": "Jawaban D taubat"},
                ],
                "correct_answer": "B",
            }

        diagnostic = [_mc(i) for i in range(n_diag)]
        formative = [{
            "question": (["Terapkan langkah taubat",
                          "Analisis dampak taubat",
                          "Evaluasi praktik taubat"][i]
                         if i < 3 else f"Soal formatif {i + 1} tentang taubat"),
            "type": "short_answer", "tp_linked": _tp(i),
            "kktp_linked": _kktp(i)} for i in range(n_form)]
        summ_items = [{
            "question": (["Analisis kasus taubat", "Evaluasi kebijakan taubat",
                          "Rancang program taubat"][i]
                         if i < 3 else f"Soal sumatif {i + 1} tentang taubat"),
            "type": "essay", "tp_linked": _tp(i), "kktp_linked": _kktp(i),
            "points": [40, 30, 30][i] if i < 3 else 10}
            for i in range(n_sum)]
        return {
            "diagnostic": diagnostic,
            "formative": formative,
            "summative": {"items": summ_items,
                "rubric": "Rubrik analisis"},
            "rubric_descriptors": {
                "KKTP-1": [
                    "Belum dapat menerapkan satu pun langkah taubat dengan benar",
                    "Menerapkan sebagian langkah taubat dengan bimbingan",
                    "Menerapkan seluruh langkah taubat secara mandiri",
                    "Menerapkan seluruh langkah taubat dan menjelaskan hikmahnya",
                ],
                "KKTP-2": [
                    "Tidak mengenali unsur kasus taubat yang dianalisis",
                    "Mengenali sebagian unsur kasus tanpa penjelasan sebab-akibat",
                    "Mengenali unsur kasus dan menjelaskan sebab-akibatnya",
                    "Mengenali unsur kasus, menjelaskan sebab-akibat, dan menarik simpulan",
                ],
                "KKTP-3": [
                    "Belum dapat menilai praktik taubat dengan dalil yang relevan",
                    "Menilai praktik taubat dengan dalil yang kurang tepat",
                    "Menilai praktik taubat dengan dalil yang relevan",
                    "Menilai praktik taubat dengan dalil dan mengusulkan perbaikan",
                ],
            },
        }
    raise AssertionError(f"Unexpected prompt in fake router: {prompt[:80]}")


def patch_pipeline_ai(pipeline, side_effect):
    """Replace the pipeline's 9Router client calls with a fake."""
    return patch.object(
        pipeline.ai_client, 'generate_json', side_effect=side_effect
    )


def run_generation(pipeline, side_effect):
    """Run a full generation with the 9Router client mocked."""
    with patch_pipeline_ai(pipeline, side_effect):
        return pipeline.generate(VALID_PARAMS)


# ---------------------------------------------------------------------------
# Scenario factories (A-J): realistic 9Router mock variants. None of them
# bypass pipeline validation - every scenario still goes through all stages.
# ---------------------------------------------------------------------------

_TP_VERBS = {
    'C1': 'Menyebutkan', 'C2': 'Menjelaskan', 'C3': 'Menerapkan',
    'C4': 'Menganalisis', 'C5': 'Mengevaluasi', 'C6': 'Merancang',
}

# Same KKO map the production rule validator uses, mirrored here so the
# mock router can declare KKTP levels consistent with its TP verbs.
_KKO_LEVELS = {
    'Menyebutkan': 'C1', 'Menjelaskan': 'C2', 'Menerapkan': 'C3',
    'Menganalisis': 'C4', 'Mengevaluasi': 'C5', 'Merancang': 'C6',
    'Menciptakan': 'C6',
}


def _tp_level_from_prompt(prompt: str) -> str:
    """Derive the TP cognitive level from the verb in the prompt's TP line
    (first verb by position wins)."""
    tp_line = next(
        (ln for ln in prompt.splitlines() if ln.strip().startswith('Untuk TP:')),
        '',
    )
    best = None
    for verb, lv in _KKO_LEVELS.items():
        pos = tp_line.find(verb)
        if pos != -1 and (best is None or pos < best[0]):
            best = (pos, lv)
    return best[1] if best else 'C3'


def tp_level_scenario(level):
    """Full valid flow, but every generated TP uses the given cognitive level."""

    def side_effect(prompt, system_instruction=None, **kwargs):
        if 'tp_list' in prompt:
            return {"tp_list": [
                f"{_TP_VERBS[level]} konsep taubat dalam kehidupan sehari-hari",
                f"{_TP_VERBS[level]} dampak taubat terhadap perilaku siswa",
                f"{_TP_VERBS[level]} praktik taubat yang sesuai tuntunan Islam",
            ]}
        return fake_router_response(prompt, system_instruction, **kwargs)

    return side_effect


def kktp_scenario(level="C3"):
    """Valid flow, but the FIRST KKTP of every generation attempt declares
    the given cognitive level (use None or C1/C2 to make it invalid).
    Persistently invalid across regeneration attempts (first call of each
    3-call KKTP group) so a failure stays attributable to the single
    invalid KKTP even with bounded stage-level regeneration; the other
    KKTP stay valid."""
    counter = {"i": 0}

    def side_effect(prompt, system_instruction=None, **kwargs):
        response = fake_router_response(prompt, system_instruction, **kwargs)
        if 'criteria' in prompt and 'tp_list' not in prompt:
            i = counter["i"]
            counter["i"] += 1
            if i % 3 == 0:
                response = dict(response)
                response["level"] = level
        return response

    return side_effect


def missing_activity_scenario():
    """Scenario E: only 1 activity for 3 TP (AI under-delivers)."""

    def side_effect(prompt, system_instruction=None, **kwargs):
        response = fake_router_response(prompt, system_instruction, **kwargs)
        if 'activities' in prompt:
            response = {"activities": response["activities"][:1]}
        return response

    return side_effect


def missing_assessment_scenario():
    """Scenario F: formative assessment bucket missing entirely."""

    def side_effect(prompt, system_instruction=None, **kwargs):
        response = fake_router_response(prompt, system_instruction, **kwargs)
        if 'diagnostic' in prompt:
            response = {
                k: v for k, v in response.items() if k != 'formative'
            }
        return response

    return side_effect


def cp_override_scenario():
    """Scenario G: AI attempts to redefine the protected CP."""

    def side_effect(prompt, system_instruction=None, **kwargs):
        response = fake_router_response(prompt, system_instruction, **kwargs)
        if 'tp_list' in prompt:
            response = dict(response)
            response['cp'] = 'CP palsu karangan AI'
            response['subject'] = 'Fikih'
        return response

    return side_effect


def phase_override_scenario():
    """Scenario H: AI attempts to redefine the protected phase."""

    def side_effect(prompt, system_instruction=None, **kwargs):
        response = fake_router_response(prompt, system_instruction, **kwargs)
        if 'tp_list' in prompt:
            response = dict(response)
            response['phase'] = 'F'
        return response

    return side_effect


def subject_override_scenario():
    """AI attempts to redefine the protected subject."""

    def side_effect(prompt, system_instruction=None, **kwargs):
        response = fake_router_response(prompt, system_instruction, **kwargs)
        if 'tp_list' in prompt:
            response = dict(response)
            response['subject'] = 'Fikih'
        return response

    return side_effect


def element_override_scenario():
    """AI attempts to redefine the protected element."""

    def side_effect(prompt, system_instruction=None, **kwargs):
        response = fake_router_response(prompt, system_instruction, **kwargs)
        if 'tp_list' in prompt:
            response = dict(response)
            response['element'] = 'Elemen karangan AI'
        return response

    return side_effect


@pytest.mark.integration
class TestEndToEndScenarios:
    """Mocked end-to-end generation through the full pipeline."""

    def test_valid_module_creation_scenario(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)

        assert result['status'] == 'success', result['errors']
        module = result['module']
        assert module is not None
        assert module['generation_id'] == result['generation_id']
        assert len(module['learning_objectives']) == 3
        assert len(module['success_criteria']) == 3
        assert len(module['learning_activities']) == 5  # 1 intro + 3 core + 1 closing
        assert set(module['assessments'].keys()) >= {
            'diagnostic', 'formative', 'summative'}
        # All validation stages passed
        for stage, outcome in module['validation_results'].items():
            assert outcome['passed'] is True, (stage, outcome)

    def test_generation_id_exists(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        assert result['generation_id']
        uuid.UUID(result['generation_id'])  # must be a valid UUID

    def test_tp_kktp_alignment_in_generated_module(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        module = result['module']
        tp_ids = {tp['id'] for tp in module['learning_objectives']}
        for kktp in module['success_criteria']:
            assert kktp['tp_id'] in tp_ids
        shared_phase_types = {
            'pendahuluan', 'introduction', 'pembuka', 'apersepsi',
            'penutup', 'closing',
        }
        for activity in module['learning_activities']:
            if activity['tp_linked']:
                assert activity['tp_linked'] in tp_ids
            # RPM: shared-experience activities (memahami/merefleksi) may be
            # unlinked; legacy pre-RPM stored types remain recognized.
            else:
                assert (activity.get('experience') in
                        {'memahami', 'merefleksi'}) or (
                        activity['type'] in shared_phase_types)

    def test_b4_synthesis_present(self, pipeline):
        """B.4 is the four-part AI synthesis; the legacy L.1/F/G
        completion stage no longer exists in the RPM product."""
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        module = result['module']
        eu = module['essential_understanding']
        assert eu['core_insight'] and eu['relationship']             and eu['application'] and eu['value']
        assert 'main_content' not in eu

    def test_invalid_json_ai_response_fails(self, pipeline):
        from nine_router_client import ValidationError

        def bad_json(prompt, system_instruction=None, **kwargs):
            # Mirrors real client behavior on unparseable AI output
            raise ValidationError("AI response is not valid JSON: invalid")

        with patch_pipeline_ai(pipeline, bad_json):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        assert result['module'] is None
        assert any('AI generation failed' in e for e in result['errors'])

    def test_ai_protected_field_override_fails(self, pipeline):
        def overriding_ai(prompt, system_instruction=None, **kwargs):
            if 'tp_list' in prompt:
                return {"tp_list": ["Menerapkan konsep taubat"],
                        "subject": "Fikih", "phase": "F"}
            return fake_router_response(prompt)

        with patch_pipeline_ai(pipeline, overriding_ai):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        assert result['module'] is None
        assert any('protected' in e.lower() for e in result['errors'])

    def test_tp_c1_fails_generation(self, pipeline):
        def c1_ai(prompt, system_instruction=None, **kwargs):
            if 'tp_list' in prompt:
                return {"tp_list": ["Menyebutkan rukun taubat",
                                    "Mengingat definisi taubat"]}
            return fake_router_response(prompt)

        with patch_pipeline_ai(pipeline, c1_ai):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        assert result['module'] is None
        assert any('C1' in e or 'C2' in e or 'cognitive' in e.lower()
                   for e in result['errors'])

    def test_tp_c2_fails_generation(self, pipeline):
        def c2_ai(prompt, system_instruction=None, **kwargs):
            if 'tp_list' in prompt:
                return {"tp_list": ["Memahami konsep taubat"]}
            return fake_router_response(prompt)

        with patch_pipeline_ai(pipeline, c2_ai):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'

    def test_missing_kktp_fails_generation(self, pipeline):
        def no_kktp(prompt, system_instruction=None, **kwargs):
            if 'criteria' in prompt:
                return {"criteria": [], "level": "C3"}
            return fake_router_response(prompt)

        with patch_pipeline_ai(pipeline, no_kktp):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        assert result['module'] is None
        assert any('criteria' in e.lower() for e in result['errors'])

    def test_missing_activity_fails_generation(self, pipeline):
        def no_activities(prompt, system_instruction=None, **kwargs):
            if 'activities' in prompt:
                return {"activities": []}
            return fake_router_response(prompt)

        with patch_pipeline_ai(pipeline, no_activities):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_missing_assessment_fails_generation(self, pipeline):
        def no_assessment(prompt, system_instruction=None, **kwargs):
            if 'diagnostic' in prompt:
                return {"diagnostic": [], "formative": [],
                        "summative": {"items": []}}
            return fake_router_response(prompt)

        with patch_pipeline_ai(pipeline, no_assessment):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_missing_formative_assessment_fails(self, pipeline):
        def no_formative(prompt, system_instruction=None, **kwargs):
            if 'diagnostic' in prompt:
                response = fake_router_response(prompt)
                del response['formative']
                return response
            return fake_router_response(prompt)

        with patch_pipeline_ai(pipeline, no_formative):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        assert any('formative' in e.lower() for e in result['errors'])

    def test_protected_fields_survive_full_generation(self, pipeline):
        """CP/phase/subject/element in the emitted module match the input CP."""
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        module = result['module']
        ctx = module['curriculum_context']
        assert ctx['cp']['text']  # Real CP text present
        assert module['phase'] == 'D'
        assert module['subject'] == 'Akidah Akhlak'
        assert ctx['subject'] == 'Akidah Akhlak'
        assert ctx['education_system'] == 'KEMENAG'
        assert module['curriculum_version'] == 'KMA-1503-2025'
        # CP provenance preserved
        assert ctx['cp']['source_document_id']


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:

    def test_tp_with_multiple_cognitive_keywords(self, test_db):
        """Highest cognitive keyword wins (C6 checked before C1)."""
        validator = RuleValidator(str(test_db))
        level = validator._extract_cognitive_level(
            "Menyebutkan lalu menerapkan lalu merancang taubat")
        assert level == 'C6'

    def test_very_long_module_title(self, sample_context):
        module = make_module(sample_context, title="M" * 5000)
        is_valid, errors = FinalValidator.validate_completeness(module)
        assert is_valid is True

    def test_module_with_special_characters(self, sample_context):
        module = make_module(
            sample_context, title="Modul Taubat ① éàü & #special")
        is_valid, errors = FinalValidator.validate_completeness(module)
        assert is_valid is True

    def test_resolve_grade_key_variants(self):
        assert resolve_grade_key('MTs', '7') == 'MTs_7'
        assert resolve_grade_key('MTs', 'MTs_7') == 'MTs_7'
        assert resolve_grade_key('MA', '10') == 'MA_10'

    def test_grade_as_int_accepted_by_validator(self, test_db):
        validator = CurriculumValidator(str(test_db))
        try:
            params = dict(VALID_PARAMS, grade=7)
            is_valid, context, errors = validator.validate(params)
            assert is_valid is True, errors
            assert context.phase == 'D'
        finally:
            validator.close()


# ============================================================================
# PHASE C.2 REQUIRED-NAME CHECKLIST + MOCK SCENARIOS A-J
# ============================================================================

@pytest.mark.integration
class TestPhaseC2RequiredChecklist:
    """The 28 required Phase C.2 test names, all through the real pipeline
    with mocked 9Router (scenarios A-J share the mock matrix)."""

    # -- Initialization & curriculum resolution -----------------------------

    def test_pipeline_can_initialize(self, pipeline):
        assert pipeline is not None
        assert pipeline.curriculum_validator is not None
        assert pipeline.context_validator is not None
        assert pipeline.rule_validator is not None

    def test_pipeline_resolves_curriculum_context(self, pipeline):
        validator = CurriculumValidator(str(pipeline.db_path))
        try:
            is_valid, context, errors = validator.validate(VALID_PARAMS)
            assert is_valid is True, errors
            # Context fully resolved from the real DB + context generator
            assert context.subject == 'Akidah Akhlak'
            assert context.phase == 'D'
            assert context.education_system == 'KEMENAG'
            assert context.curriculum_version
            assert validator.last_context is context
        finally:
            validator.close()

    def test_pipeline_retrieves_cp(self, pipeline):
        validator = CurriculumValidator(str(pipeline.db_path))
        try:
            is_valid, context, errors = validator.validate(VALID_PARAMS)
            assert is_valid is True, errors
            assert context.cp.text
            assert context.cp.source_document_id
            assert context.cp.source_page
        finally:
            validator.close()

    def test_pipeline_rejects_invalid_context(self, pipeline):
        params = dict(VALID_PARAMS, subject='Fisika')  # not valid for KEMENAG
        result = pipeline.generate(params)
        assert result['status'] == 'failed'
        assert result['module'] is None

    # -- TP generation + cognitive levels -----------------------------------

    def test_pipeline_generates_tp(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        assert len(result['module']['learning_objectives']) == 3

    def _run(self, pipeline, side_effect):
        with patch_pipeline_ai(pipeline, side_effect):
            return pipeline.generate(VALID_PARAMS)

    def test_pipeline_rejects_c1_tp(self, pipeline):
        result = self._run(pipeline, tp_level_scenario('C1'))
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_pipeline_rejects_c2_tp(self, pipeline):
        result = self._run(pipeline, tp_level_scenario('C2'))
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_pipeline_accepts_c3_tp(self, pipeline):
        result = self._run(pipeline, tp_level_scenario('C3'))
        assert result['status'] == 'success', result['errors']

    def test_pipeline_accepts_c4_tp(self, pipeline):
        result = self._run(pipeline, tp_level_scenario('C4'))
        assert result['status'] == 'success', result['errors']

    def test_pipeline_accepts_c5_tp(self, pipeline):
        result = self._run(pipeline, tp_level_scenario('C5'))
        assert result['status'] == 'success', result['errors']

    def test_pipeline_accepts_c6_tp(self, pipeline):
        result = self._run(pipeline, tp_level_scenario('C6'))
        assert result['status'] == 'success', result['errors']

    # -- KKTP generation + validation ---------------------------------------

    def test_pipeline_generates_kktp(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        assert len(result['module']['success_criteria']) == 3

    def test_pipeline_rejects_invalid_kktp(self, pipeline):
        result = self._run(pipeline, kktp_scenario(level='C1'))
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_pipeline_validates_tp_kktp_alignment(self, pipeline):
        # KKTP tp_id is assigned by the pipeline, so misalignment is injected
        # at the generation boundary; the structure/final gates must reject it.
        misaligned = [KKTPEntry(
            id="KKTP-1", tp_id="TP-9",
            criteria=["Menerapkan langkah taubat"], cognitive_level="C3"
        )]
        with patch_pipeline_ai(pipeline, fake_router_response), \
                patch.object(pipeline, '_generate_kktp', return_value=misaligned):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        assert result['module'] is None
        assert any('KKTP' in e for e in result['errors'])

    # -- Materials / activities / assessments --------------------------------

    def test_pipeline_generates_activities(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        activities = result['module']['learning_activities']
        # RPM pengalaman belajar: memahami / mengaplikasi / merefleksi
        # (AGENTS.md §13) — bukan tahap pendahuluan/inti/penutup.
        experiences = {a['experience'] for a in activities}
        assert experiences == {'memahami', 'mengaplikasi', 'merefleksi'}
        assert all(a['name'] and a['description'] and a['duration'] > 0
                   for a in activities)

    def test_pipeline_generates_assessments(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        assert set(result['module']['assessments'].keys()) >= {
            'diagnostic', 'formative', 'summative'}

    def test_pipeline_validates_activity_alignment(self, pipeline):
        # Scenario E: only 1 activity for 3 TP -> alignment must fail
        result = self._run(pipeline, missing_activity_scenario())
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_pipeline_validates_assessment_alignment(self, pipeline):
        # Scenario F: formative bucket missing -> assessment alignment fails
        result = self._run(pipeline, missing_assessment_scenario())
        assert result['status'] == 'failed'
        assert result['module'] is None

    # -- Protection (pipeline-level, via AI response tampering) --------------

    def test_pipeline_protects_cp(self, pipeline):
        result = self._run(pipeline, cp_override_scenario())
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_pipeline_protects_phase(self, pipeline):
        result = self._run(pipeline, phase_override_scenario())
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_pipeline_protects_subject(self, pipeline):
        result = self._run(pipeline, subject_override_scenario())
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_pipeline_protects_element(self, pipeline):
        result = self._run(pipeline, element_override_scenario())
        assert result['status'] == 'failed'
        assert result['module'] is None

    # -- Anti-Slop / FinalValidator / success gating --------------------------

    def test_pipeline_runs_antislop(self, pipeline):
        with patch.object(
            pipeline.anti_slop, 'humanize_with_report',
            wraps=pipeline.anti_slop.humanize_with_report
        ) as spy:
            with patch_pipeline_ai(pipeline, fake_router_response):
                result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        assert spy.called, "Anti-Slop must actually run in the pipeline"

    def test_pipeline_runs_final_validator(self, pipeline):
        with patch.object(
            pipeline.final_validator, 'validate_completeness',
            wraps=pipeline.final_validator.validate_completeness
        ) as spy:
            with patch_pipeline_ai(pipeline, fake_router_response):
                result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        assert spy.called, "FinalValidator must actually run in the pipeline"

    def test_invalid_module_cannot_return_success(self, pipeline):
        # Scenario D: KKTP level missing entirely -> module invalid, no success
        result = self._run(pipeline, kktp_scenario(level=None))
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_success_requires_all_validation_stages(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success'
        required_stages = {
            'curriculum', 'context', 'structure', 'protection', 'rules',
            'pedagogical', 'anti_slop', 'final'
        }
        reported = set(result['module']['validation_results'].keys())
        missing = required_stages - reported
        assert not missing, f"Stages missing from validation report: {missing}"
        for stage, outcome in result['module']['validation_results'].items():
            assert outcome['passed'] is True, (stage, outcome)

    def test_generation_id_exists(self, pipeline):
        result = self._run(pipeline, fake_router_response)
        assert result['generation_id']
        uuid.UUID(result['generation_id'])


@pytest.mark.integration
class TestPhaseC2MockScenarios:
    """Explicit mock scenarios A-J (realistic mocks, no auto-valid bypass)."""

    def test_scenario_a_complete_valid_module(self, pipeline):
        result = run_generation(pipeline, fake_router_response)
        assert result['status'] == 'success'
        assert result['module']['generation_id'] == result['generation_id']

    def test_scenario_b_invalid_tp_c1(self, pipeline):
        result = run_generation(pipeline, tp_level_scenario('C1'))
        assert result['status'] == 'failed'

    def test_scenario_c_invalid_tp_c2(self, pipeline):
        result = run_generation(pipeline, tp_level_scenario('C2'))
        assert result['status'] == 'failed'

    def test_scenario_d_invalid_kktp(self, pipeline):
        result = run_generation(pipeline, kktp_scenario(level='C2'))
        assert result['status'] == 'failed'

    def test_scenario_e_missing_activity(self, pipeline):
        result = run_generation(pipeline, missing_activity_scenario())
        assert result['status'] == 'failed'

    def test_scenario_f_missing_assessment(self, pipeline):
        result = run_generation(pipeline, missing_assessment_scenario())
        assert result['status'] == 'failed'

    def test_scenario_g_modified_cp(self, pipeline):
        result = run_generation(pipeline, cp_override_scenario())
        assert result['status'] == 'failed'

    def test_scenario_h_modified_phase(self, pipeline):
        result = run_generation(pipeline, phase_override_scenario())
        assert result['status'] == 'failed'

    def test_scenario_i_invalid_json(self, pipeline):
        from nine_router_client import ValidationError

        def bad_json(prompt, system_instruction=None, **kwargs):
            raise ValidationError("AI response is not valid JSON: invalid")

        result = run_generation(pipeline, bad_json)
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_scenario_j_api_failure(self, pipeline):
        def api_down(prompt, system_instruction=None, **kwargs):
            raise NineRouterError("Connection refused by 9Router")

        result = run_generation(pipeline, api_down)
        assert result['status'] == 'failed'
        assert result['module'] is None
        assert any('AI generation failed' in e for e in result['errors'])


@pytest.mark.api
class TestModuleGenerationRestContract:
    """REST contract of /api/module/generate (real pipeline, mocked AI)."""

    @pytest.fixture
    def api_pipeline(self, test_db):
        """Flask app wired to the real pipeline on the temp test DB."""
        import app as app_module
        from module_generation_pipeline import ModuleGenerationPipeline
        pipe = ModuleGenerationPipeline(db_path=str(test_db))
        app_module._generation_pipeline = pipe
        yield pipe
        # Close whatever pipeline is currently installed: restart-safety
        # tests may REPLACE the singleton, and on Windows an unclosed
        # sqlite handle keeps the temp DB file locked.
        current = app_module._generation_pipeline
        if current is not None:
            try:
                current.curriculum_validator.close()
            except Exception:
                pass
        app_module._generation_pipeline = None
        pipe.curriculum_validator.close()

    def _post_generate(self, flask_client):
        # Request-scoped generate: every curriculum field in ONE request.
        # /api/context/generate is a read-only preview (no hidden state).
        return flask_client.post('/api/module/generate', json={
            'education_system': 'KEMENAG',
            'institution_type': 'MTs',
            'grade': 'MTs_7',
            'subject': 'Akidah Akhlak',
            'element': 'Pemahaman Konsep',
            'phase': 'D',
        })

    def test_success_response_structure(self, flask_client, api_pipeline):
        with patch_pipeline_ai(api_pipeline, fake_router_response):
            response = self._post_generate(flask_client)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'
        assert data['generation_id']
        assert data['module']
        assert isinstance(data['validation'], dict)

    def test_validation_failure_returns_422_with_errors(self, flask_client,
                                                        api_pipeline):
        with patch_pipeline_ai(api_pipeline, tp_level_scenario('C1')):
            response = self._post_generate(flask_client)
        assert response.status_code == 422
        data = json.loads(response.data)
        assert data['status'] == 'error'
        assert data['generation_id']
        assert data['errors']
        for err in data['errors']:
            assert 'code' in err and 'message' in err and 'stage' in err

    def test_no_context_returns_400_with_code(self, flask_client, api_pipeline):
        import app as app_module
        # Clear state that may leak from other tests
        app_module.generation_context.pop('current', None)
        response = flask_client.post('/api/module/generate', json={})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['status'] == 'error'
        assert data['errors'][0]['code'] == 'INVALID_PARAMS'

    def test_internal_error_returns_500_without_secrets(self, flask_client,
                                                       api_pipeline):
        with patch_pipeline_ai(
            api_pipeline,
            side_effect=RuntimeError("boom: NINE_ROUTER_API_KEY=secret-value")
        ):
            response = self._post_generate(flask_client)
        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['status'] == 'error'
        assert data['errors'][0]['code'] == 'INTERNAL_ERROR'
        body = response.get_data(as_text=True)
        assert 'secret-value' not in body
        assert 'NINE_ROUTER_API_KEY' not in body

    def test_api_context_carries_topic_into_generation(self, flask_client,
                                                       api_pipeline):
        """BLOCKER 1 REST lifecycle: the generate request carries the topic;
        the generation prompts actually receive it (never 'Topic: None')."""
        import app as app_module
        app_module.generation_context.pop('current', None)
        prompts = []

        def recording(prompt, system_instruction=None, **kwargs):
            prompts.append(prompt)
            return fake_router_response(prompt, system_instruction)

        with patch_pipeline_ai(api_pipeline, recording):
            resp = flask_client.post('/api/module/generate', json={
                'education_system': 'KEMENAG', 'institution_type': 'MTs',
                'grade': 'MTs_7', 'subject': 'Akidah Akhlak', 'phase': 'D',
                'element': 'Pemahaman Konsep', 'topic': 'Taubat',
            })
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert any('Topic: Taubat' in p or 'Topic/Materi: Taubat' in p
                   for p in prompts)
        assert not any('Topic: None' in p for p in prompts)


# ============================================================================
# MASTER OUTLINE IMPLEMENTATION TESTS (spec sections 2-22)
# ============================================================================

@pytest.mark.usefixtures('pipeline')
class TestMasterOutlineSchema:
    """Task section 22 items 1-7: schema + info umum + core components."""

    def _generate(self, pipeline):
        result = run_generation(pipeline, fake_router_response)
        assert result['status'] == 'success', result['errors']
        return result

    def test_new_schema_valid(self, pipeline):
        """Item 1: master_outline view (RPM structure) fully present."""
        result = self._generate(pipeline)
        mo = result['module']['master_outline']
        assert set(mo.keys()) == {
            'general_information', 'identification', 'design',
            'learning_experience', 'assessment', 'remedial_enrichment',
            'reflection', 'attachments'}
        gi = mo['general_information']
        assert set(gi.keys()) >= {
            'identity', 'initial_competence', 'profile_dimensions_values',
            'kbc', 'facilities_infrastructure', 'target_students',
            'learning_model', 'approach_principles'}
        # B Identifikasi (kesiapan murid + karakteristik materi)
        assert set(mo['identification'].keys()) == {
            'learner_readiness', 'material_characteristics',
            'profile_dimensions', 'profile_dimension_notes'}
        # C Desain Pembelajaran
        assert set(mo['design'].keys()) >= {
            'cp', 'cp_provenance', 'tp', 'atp', 'kktp',
            'pedagogical_practices', 'learning_partnerships',
            'learning_environment', 'digital_use',
            'meaningful_understanding', 'triggering_questions'}
        # D Pengalaman Belajar: memahami / mengaplikasi / merefleksi
        assert set(mo['learning_experience'].keys()) >= {
            'experiences', 'principles'}
        assert set(mo['assessment'].keys()) >= {
            'awal', 'proses', 'akhir', 'blueprint', 'rubric_scoring'}
        assert set(mo['attachments'].keys()) >= {
            'lkpd', 'instrument_recap', 'supporting'}

    def test_legacy_schema_compatibility(self, pipeline):
        """Item 2: all legacy flat fields still exist and stay populated."""
        result = self._generate(pipeline)
        module = result['module']
        for legacy_key in ('id', 'title', 'subject', 'grade', 'phase',
                           'learning_objectives', 'success_criteria',
                           'essential_understanding', 'guiding_questions',
                           'learning_activities', 'assessments',
                           'reflection', 'curriculum_context'):
            assert legacy_key in module, legacy_key
        assert module['learning_objectives']
        assert module['success_criteria']
        assert module['assessments']['diagnostic']

    def test_cp_immutable_and_from_database(self, pipeline):
        """Item 3: CP comes from the DB; AI never authors it."""
        result = self._generate(pipeline)
        core = result['module']['master_outline']['design']
        assert core['cp']
        assert result['module']['curriculum_context']['cp']['id']

    def test_provenance_preserved(self, pipeline):
        """Item 4: CP provenance (document, fragment/page, version)."""
        prov = self._generate(pipeline)[
            'module']['master_outline']['design']['cp_provenance']
        assert prov['source_document_id']
        assert prov['source_fragment_id'] or prov['source_page']
        assert prov['curriculum_version']
        assert prov['phase'] and prov['element']

    def test_initial_competence(self, pipeline):
        """Item 5: A.2 from AI with description + prerequisites."""
        ic = self._generate(pipeline)[
            'module']['master_outline']['general_information'][
            'initial_competence']
        assert ic['description']
        assert isinstance(ic['prerequisites'], list)

    def test_profile_values_filtered_to_normative(self, pipeline):
        """Item 6: A.3 values restricted to the normative list."""
        values = self._generate(pipeline)[
            'module']['master_outline']['general_information'][
            'profile_dimensions_values']
        allowed = allowed_profile_values('KEMENAG')
        assert all(v in allowed for v in values)
        assert 'Kolaborasi' in values and 'Kreativitas' in values

    def test_approach_principles_deterministic(self, pipeline):
        """Item 7: A.7 is deterministic metadata, never AI-authored."""
        ap = self._generate(pipeline)[
            'module']['master_outline']['general_information'][
            'approach_principles']
        assert ap['approach'] == 'Pembelajaran Mendalam'
        assert 'Permendikdasmen No. 13 Tahun 2025' in ap['source']
        assert ap['values']
        # KBC lives only in its dedicated layer, never replaces the 8
        # Dimensi Profil Lulusan.
        assert all(v in allowed_profile_values('KEMENAG')
                   for v in ap['values'])

    def test_three_experience_activities(self, pipeline):
        """Item 8: D experiences populated; every experience non-empty;
        mengaplikasi links TP (AGENTS.md §13)."""
        result = self._generate(pipeline)
        experiences = result['module']['master_outline'][
            'learning_experience']['experiences']
        for exp in ('memahami', 'mengaplikasi', 'merefleksi'):
            assert experiences[exp], exp
        assert all(act.get('tp_linked')
                   for act in experiences['mengaplikasi'])


class TestMasterOutlineAlignmentAndAppendices:
    """Task section 22 items 9-21: alignment + derived + appendices."""

    def _generate(self, pipeline):
        result = run_generation(pipeline, fake_router_response)
        assert result['status'] == 'success', result['errors']
        return result

    def test_tp_kktp_alignment(self, pipeline):
        """Item 9: every TP has a KKTP (STAGE 7b KKTP_ERROR otherwise)."""
        result = self._generate(pipeline)
        tp_ids = {tp['id'] for tp in result['module']['learning_objectives']}
        kktp_tp = {k['tp_id'] for k in result['module']['success_criteria']}
        assert tp_ids == kktp_tp

    def test_tp_activity_alignment(self, pipeline):
        """Item 10: every mengaplikasi activity links to a valid TP."""
        result = self._generate(pipeline)
        tp_ids = {tp['id'] for tp in result['module']['learning_objectives']}
        experiences = result['module']['master_outline'][
            'learning_experience']['experiences']
        assert all(a['tp_linked'] in tp_ids
                   for a in experiences['mengaplikasi'])

    def test_tp_assessment_alignment(self, pipeline):
        """Item 11: every TP traceable to an assessment item."""
        result = self._generate(pipeline)
        tp_ids = {tp['id'] for tp in result['module']['learning_objectives']}
        linked = set()
        for item in result['module']['assessments']['formative']:
            linked.add(item['tp_linked'])
        for item in result['module']['assessments']['summative']['items']:
            linked.add(item['tp_linked'])
        assert tp_ids <= linked

    def test_blueprint_coverage(self, pipeline):
        """Item 12: C.4 one row per TP with cognitive level + question form."""
        result = self._generate(pipeline)
        blueprint = result['module']['master_outline'][
            'assessment']['blueprint']
        assert len(blueprint) == 3
        assert {row['tp_id'] for row in blueprint} == {'TP-1', 'TP-2', 'TP-3'}
        assert all(row['cognitive_level'] in {'C3', 'C4', 'C5', 'C6'}
                   for row in blueprint)
        assert all(row['question_form'] for row in blueprint)

    def test_rubric_kktp_alignment(self, pipeline):
        """Item 13: C.5 rubric covers every KKTP + scoring intervals."""
        result = self._generate(pipeline)
        rubric = result['module']['master_outline'][
            'assessment']['rubric_scoring']
        kktp_ids = {k['id'] for k in result['module']['success_criteria']}
        assert {r['kktp_id'] for r in rubric['kktp_rubric']} == kktp_ids
        assert rubric['scoring_intervals']

    def test_remedial_conditional(self, pipeline):
        """Item 14: remedial absent when AI returns none (never invented)."""
        result = self._generate(pipeline)
        assert result['module']['remedial']  # mock provides one here

        def no_remedial(prompt, system_instruction=None, **kwargs):
            response = fake_router_response(prompt, system_instruction)
            if 'triggering_questions' in prompt:
                response = dict(response)
                response['remedial'] = None
            return response

        result2 = run_generation(pipeline, no_remedial)
        assert result2['status'] == 'success'
        assert result2['module']['remedial'] is None

    def test_enrichment_conditional(self, pipeline):
        """Item 15: enrichment conditional with TP reference when present."""
        result = self._generate(pipeline)
        enr = result['module']['enrichment']
        assert enr and set(enr['tp_reference']) <= {
            'TP-1', 'TP-2', 'TP-3'}

    def test_reflection_both_roles(self, pipeline):
        """Item 16: E has student + teacher reflection questions."""
        refl = self._generate(pipeline)[
            'module']['master_outline']['reflection']
        assert refl['student'][0]['questions']
        assert refl['teacher'][0]['questions']

    def test_lkpd_not_generated_by_default(self, pipeline):
        """Batch 8.5 §8: LKPD bukan bagian default RPM (tidak digenerate)."""
        result = self._generate(pipeline)
        assert result['status'] == 'success', result['errors']
        assert result['module']['lkpd'] == []
        assert result['module']['master_outline']['attachments']['lkpd'] == []


class TestMasterOutlineGates:
    """Task section 22 items 21-28: gates, failure paths, combo contract."""

    def test_antislop_protected_fields(self, pipeline):
        """Item 21: Anti-Slop leaves protected fields byte-identical."""
        result = run_generation(pipeline, fake_router_response)
        assert result['status'] == 'success'
        module = result['module']
        ctx_cp = module['curriculum_context']['cp']['text']
        assert module['master_outline']['design']['cp'] == ctx_cp
        assert module['phase'] == 'D' and module['subject'] == 'Akidah Akhlak'
        tp_texts = [tp['text'] for tp in module['learning_objectives']]
        assert tp_texts[0].startswith('Menerapkan konsep taubat')
        assert tp_texts[1].startswith('Menganalisis dampak taubat')
        assert tp_texts[2].startswith('Mengevaluasi praktik taubat')

    def test_final_success_gating(self, pipeline):
        """Item 22: success only after all stages pass (incl. master_outline)."""
        result = run_generation(pipeline, fake_router_response)
        assert result['status'] == 'success'
        stages = result['module']['validation_results']
        assert {'master_outline'} <= set(stages.keys())
        assert all(v['passed'] for v in stages.values())

    def test_malformed_ai_json(self, pipeline):
        """Item 23: unparseable AI output cannot yield success."""
        from nine_router_client import ValidationError

        def bad(prompt, system_instruction=None, **kwargs):
            raise ValidationError("AI response is not valid JSON: x")

        result = run_generation(pipeline, bad)
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_ai_missing_required_section(self, pipeline):
        """Item 24: missing AI outline section is fatal (LKPD dikecualikan:
        Batch 8.5 §8, bukan bagian default RPM)."""
        def missing_section(prompt, system_instruction=None, **kwargs):
            resp = fake_router_response(prompt, system_instruction, **kwargs)
            if 'triggering_questions' in prompt:
                resp.pop('student_reflection')
            return resp
        result = run_generation(pipeline, missing_section)
        assert result['status'] == 'failed'
        assert result['module'] is None
        assert any('student_reflection' in e for e in result['errors'])

    def test_ai_modifying_cp(self, pipeline):
        """Item 25: AI-authored CP override is rejected before final gate."""
        def cp_override(prompt, system_instruction=None, **kwargs):
            response = fake_router_response(prompt, system_instruction)
            if 'triggering_questions' in prompt:
                response = dict(response)
                response['capaian_pembelajaran'] = "AI-authored CP"
            return response

        result = run_generation(pipeline, cp_override)
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_api_failure(self, pipeline):
        """Item 27: 9Router outage cannot yield success."""
        def down(prompt, system_instruction=None, **kwargs):
            raise NineRouterError("Connection refused by 9Router")

        result = run_generation(pipeline, down)
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_router_combo_must_be_rpm(self, pipeline):
        """Item 28: production combo stays 'rpm' (never bu/automation)."""
        assert pipeline.ai_client.config.combo == 'rpm'
        with patch.dict('os.environ', {}, clear=True):
            config = NineRouterConfig.from_environment()
        assert config.combo == 'rpm'


# ============================================================================
# AUDIT BLOCKER FIXES (docs/real-module-quality-audit.md blockers 1-4)
# ============================================================================

@pytest.mark.usefixtures('pipeline')
class TestAuditBlockerFixes:
    """Regression tests for the four audit blockers."""

    # -- BLOCKER 1: topic end-to-end -----------------------------------------

    def test_topic_flows_into_context(self, pipeline):
        """topic from params lands on the validated context."""
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(dict(VALID_PARAMS))
        assert result['status'] == 'success'
        assert pipeline.curriculum_validator.last_context.topic == \
            'Taubat dalam Pembelajaran'

    def test_topic_reaches_every_ai_prompt(self, pipeline):
        """Prompts that reference topic carry the real topic; 'None' never."""
        prompts = []

        def recording(prompt, system_instruction=None, **kwargs):
            prompts.append(prompt)
            return fake_router_response(prompt, system_instruction)

        with patch_pipeline_ai(pipeline, recording):
            result = pipeline.generate(dict(VALID_PARAMS))
        assert result['status'] == 'success'
        assert any('Topic/Materi: Taubat' in p for p in prompts)
        assert any('Topic: Taubat' in p for p in prompts)
        assert not any('Topic: None' in p or 'Topic/Materi: None' in p
                       for p in prompts)

    def test_title_contains_topic_and_never_none(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(dict(VALID_PARAMS))
        assert result['status'] == 'success'
        assert result['module']['title'] == \
            'RPP/RPM Akidah Akhlak: Taubat dalam Pembelajaran'

    def test_title_without_topic_has_no_none(self, pipeline):
        params = {k: v for k, v in VALID_PARAMS.items() if k != 'topic'}
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(params)
        assert result['status'] == 'success'
        assert result['module']['title'] == \
            'RPP/RPM Akidah Akhlak'
        assert 'None' not in result['module']['title']

    # -- BLOCKER 2: KKTP declared level vs TP level ---------------------------

    def test_kktp_declared_level_persists(self, pipeline):
        """AI-declared KKTP level is stored and must match its TP verb."""
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(dict(VALID_PARAMS))
        assert result['status'] == 'success'
        kktp_levels = [k['cognitive_level']
                       for k in result['module']['success_criteria']]
        assert kktp_levels == ['C3', 'C4', 'C5']  # follows TP verbs

    def test_kktp_c3_for_c6_tp_fails(self, pipeline):
        """TP C6 with KKTP declared C3 must FAIL (audit blocker 2).
        Persistently invalid on every attempt (first KKTP call of each
        3-call group) so bounded regeneration cannot heal it."""
        base = tp_level_scenario('C6')
        counter = {'i': 0}

        def side_effect(prompt, system_instruction=None, **kwargs):
            response = base(prompt, system_instruction)
            if 'criteria' in prompt and 'tp_list' not in prompt:
                i = counter['i']
                counter['i'] += 1
                if i % 3 == 0:
                    response = dict(response)
                    response['level'] = 'C3'
            return response

        result = run_generation(pipeline, side_effect)
        assert result['status'] == 'failed'
        assert result['module'] is None
        assert any('KKTP' in str(e) and 'C3' in str(e)
                   for e in result['errors'])

    def test_kktp_missing_level_fails(self, pipeline):
        result = run_generation(pipeline, kktp_scenario(level=None))
        assert result['status'] == 'failed'
        assert result['module'] is None

    def test_kktp_malformed_level_fails(self, pipeline):
        result = run_generation(pipeline, kktp_scenario(level='C9'))
        assert result['status'] == 'failed'
        assert result['module'] is None

    # -- BLOCKER 3: element resolution ----------------------------------------

    def test_invalid_element_fatal_not_fallback(self, pipeline):
        """Requested element without CP -> ELEMENT_NOT_FOUND, never fallback."""
        # 'Ibadah' adalah cakupan Fikih (sub_element) - bukan elemen resmi
        # Akidah Akhlak fase D (Pemahaman Konsep/Keterampilan Proses).
        params = dict(VALID_PARAMS, element='Ibadah')
        result = pipeline.generate(params)
        assert result['status'] == 'failed'
        assert result['module'] is None
        assert any('ELEMENT_NOT_FOUND' in str(e) for e in result['errors'])
        assert any('Pemahaman Konsep' in str(e)
                   for e in result['errors'])  # available

    def test_explicit_element_match_uses_that_cp(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(dict(VALID_PARAMS))
        assert result['status'] == 'success'
        ctx = result['module']['curriculum_context']
        assert ctx['element'] == 'Pemahaman Konsep'
        assert ctx['cp']['element'] == 'Pemahaman Konsep'

    def test_no_element_unique_match_resolves_and_records(self, pipeline):
        """Without explicit element, the unique match is used AND recorded."""
        # SKI fase B hanya punya elemen 'Pemahaman Konsep'
        # (dokumen 9941 p89: satu item PK fase B) -> match unik.
        # Fase B = MI kelas 3-4.
        params = {k: v for k, v in VALID_PARAMS.items() if k != 'element'}
        params['subject'] = 'Sejarah Kebudayaan Islam'
        params['institution_type'] = 'MI'
        params['grade'] = 'MI_3'
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(params)
        assert result['status'] == 'success', result['errors']
        ctx = result['module']['curriculum_context']
        assert ctx['element'] == 'Pemahaman Konsep'
        assert 'resolved uniquely' in ctx['element_resolution_note']

    def test_no_element_multiple_candidates_requires_explicit(self, pipeline):
        """Fase E has Akidah + Akhlak: no element -> explicit error."""
        params = {k: v for k, v in VALID_PARAMS.items()
                  if k not in ('element', 'grade')}
        params['grade'] = 'MA_10'  # fase E
        params['institution_type'] = 'MA'
        result = pipeline.generate(params)
        assert result['status'] == 'failed'
        assert result['module'] is None
        assert any('ELEMENT_NOT_FOUND' in str(e) and 'multiple' in str(e)
                   for e in result['errors'])

    def test_fase_e_explicit_keterampilan_element_matches(self, pipeline):
        """Fase E does have 'Keterampilan Proses': explicit request must
        succeed on it."""
        params = dict(VALID_PARAMS, grade='MA_10',
                      element='Keterampilan Proses',
                      institution_type='MA')
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(params)
        assert result['status'] == 'success', result['errors']
        ctx = result['module']['curriculum_context']
        assert ctx['element'] == 'Keterampilan Proses'
        assert ctx['cp']['element'] == 'Keterampilan Proses'


# ============================================================================
# QUALITY AUDIT MAJOR-FIX TESTS (A.3 / C.5 / B.4)
# ============================================================================

@pytest.mark.phase_c
class TestA3ProfileDimensions:
    """A.3 is DETERMINISTIC from the normative value list of the education
    system — AI suggestions may only narrow it, never invent it."""

    def test_valid_authoritative_profile_populated(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        pd = result['module']['profile_dimensions']
        assert pd, "A.3 must be populated"
        allowed = allowed_profile_values('KEMENAG')
        assert all(v in allowed for v in pd)

    def test_pipeline_preserves_profile_in_rubric_pass(self, pipeline):
        """Profile survives the full validation chain intact."""
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        allowed = allowed_profile_values('KEMENAG')
        pd = result['module']['profile_dimensions']
        assert pd and set(pd) <= set(allowed)

    def test_no_ai_arbitrary_profile(self, pipeline):
        """AI-suggested non-normative values are dropped, normative ones kept."""
        def narrowing_ai(prompt, system_instruction=None, **kwargs):
            resp = fake_router_response(prompt, system_instruction, **kwargs)
            if 'triggering_questions' in prompt:
                resp = dict(resp)
                resp['profile_dimensions'] = ['Kolaborasi', 'Valoran Sneaky']
            return resp
        with patch_pipeline_ai(pipeline, narrowing_ai):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        pd = result['module']['profile_dimensions']
        assert 'Kolaborasi' in pd
        assert 'Valoran Sneaky' not in pd
        assert all(v in allowed_profile_values('KEMENAG') for v in pd)

    def test_ai_silence_fails_closed_not_full_list(self, pipeline):
        """AI diam/tak-usable -> A.3 kosong jujur -> validator A3_EMPTY
        menutup generation. Tidak ada fallback otomatis ke seluruh 8
        dimensi (mengklaim semuanya relevan tanpa dasar)."""
        def silent_ai(prompt, system_instruction=None, **kwargs):
            resp = fake_router_response(prompt, system_instruction, **kwargs)
            if 'triggering_questions' in prompt:
                resp = dict(resp)
                resp['profile_dimensions'] = []
            return resp
        with patch_pipeline_ai(pipeline, silent_ai):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        assert result['module'] is None
        assert any('A3_EMPTY' in str(e) for e in result['errors'])

    def test_a3_empty_is_validator_error(self):
        """Accidental empty A.3 is detected by the MasterOutlineValidator."""
        context = sample_context.__wrapped__()
        module = make_module(context)
        module.profile_dimensions = []
        ok, errors = MasterOutlineValidator.validate(module)
        assert not ok
        assert any(e['code'] == 'A3_EMPTY' for e in errors)


@pytest.mark.phase_c
class TestRubricDescriptors:
    """C.5: every declared rubric level must carry an observable,
    criterion-specific descriptor (RUBRIC_DESCRIPTOR_WEAK)."""

    def _module_with_rubric(self, descriptors):
        context = sample_context.__wrapped__()
        kktp = KKTPEntry(
            id="KKTP-1", tp_id="TP-1",
            criteria=["Menganalisis unsur kasus taubat"], cognitive_level="C4",
        )
        module = make_module(context)
        module.success_criteria = [kktp]
        module.learning_objectives = [TPEntry(
            id="TP-1", text="Menganalisis unsur kasus taubat",
            cognitive_level="C4", cp_reference=context.cp.id)]
        module.rubric = {
            'kktp_rubric': [{
                'kktp_id': 'KKTP-1', 'tp_id': 'TP-1',
                'criteria': kktp.criteria,
                'levels': ['Kurang', 'Cukup', 'Baik', 'Sangat Baik'],
                'descriptors': descriptors,
            }],
            'scoring_intervals': SCORING_INTERVALS,
        }
        # Satisfy unrelated structural checks minimally
        module.essential_understanding = {
            'core_insight': 'Sintesis pemahaman inti modul ini.',
        }
        return module

    def test_every_level_has_descriptor_passes(self):
        module = self._module_with_rubric([
            "Tidak mengenali unsur kasus yang dianalisis",
            "Mengenali sebagian unsur kasus tanpa sebab-akibat",
            "Mengenali unsur kasus dan menjelaskan sebab-akibatnya",
            "Menganalisis kasus lengkap dan menarik simpulan",
        ])
        ok, errors = MasterOutlineValidator.validate(module)
        rubric_errs = [e for e in errors
                       if e['code'] == 'RUBRIC_DESCRIPTOR_WEAK']
        assert not rubric_errs, rubric_errs

    def test_label_only_rubric_rejected(self):
        module = self._module_with_rubric([
            "Kurang", "Cukup", "Baik", "Sangat Baik"])
        ok, errors = MasterOutlineValidator.validate(module)
        assert any(e['code'] == 'RUBRIC_DESCRIPTOR_WEAK' for e in errors)

    def test_missing_descriptors_rejected(self):
        module = self._module_with_rubric(None)
        module.rubric['kktp_rubric'][0].pop('descriptors')
        ok, errors = MasterOutlineValidator.validate(module)
        assert any(e['code'] == 'RUBRIC_DESCRIPTOR_WEAK' for e in errors)

    def test_identical_descriptors_rejected(self):
        same = "Menganalisis kasus dengan cara yang cukup baik"
        module = self._module_with_rubric([same] * 4)
        ok, errors = MasterOutlineValidator.validate(module)
        assert any(e['code'] == 'RUBRIC_DESCRIPTOR_WEAK' for e in errors)

    def test_generic_unrelated_descriptors_rejected(self):
        module = self._module_with_rubric([
            "Peserta didik belum menunjukkan kemampuan secara nyata",
            "Peserta didik menunjukkan kemampuan secara cukup nyata",
            "Peserta didik menunjukkan kemampuan secara lebih nyata",
            "Peserta didik menunjukkan kemampuan secara paling nyata",
        ])
        ok, errors = MasterOutlineValidator.validate(module)
        assert any(e['code'] == 'RUBRIC_DESCRIPTOR_WEAK' for e in errors)

    def test_generated_module_rubric_has_descriptors(self, pipeline):
        """Integration: real pipeline flow produces descriptor-aligned rubric."""
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        rows = result['module']['rubric']['kktp_rubric']
        kktps = {k['id']: k for k in result['module']['success_criteria']}
        for row in rows:
            assert len(row['descriptors']) == len(row['levels'])
            kk = kktps[row['kktp_id']]
            # Descriptor must be criterion-specific, not generic filler
            assert any(w in ' '.join(row['descriptors']).lower()
                       for w in ('menerapkan', 'menganalisis', 'menilai',
                                 'langkah', 'kasus'))


class TestTPLabelNormalization:
    """Real routers sometimes echo list labels into TP text ("TP1: ...",
    "2. ..."). Mock responses never do, so this is covered explicitly —
    stored TP text must stay clean (found in real-AI verification)."""

    @staticmethod
    def _dispatch(payload_tp):
        """Override only the TP branch; delegate the rest of the flow to
        the canonical fake router (KKTP level derives from the TP verb)."""
        def side_effect(*args, prompt='', **kw):
            if 'tp_list' in prompt:
                return {'tp_list': payload_tp}
            return fake_router_response(prompt, **kw)
        return side_effect

    def test_tp_labels_from_real_router_are_stripped(self, pipeline):
        with patch_pipeline_ai(pipeline, self._dispatch([
                'TP1: Menerapkan langkah taubat nasuha dalam kehidupan sehari-hari.',
                '2. Menganalisis keterkaitan asmaulhusna dengan perilaku bertaubat.',
                'Menciptakan rencana perbaikan diri berbasis taubat.'])):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        texts = [t['text'] for t in result['module']['learning_objectives']]
        for t in texts:
            assert not t.startswith(('TP1:', 'TP2:', 'TP3:', '1.', '2.', '3.')), t
        assert texts[0].startswith('Menerapkan')
        assert texts[1].startswith('Menganalisis')

    def test_tp_normalization_keeps_body_text(self, pipeline):
        with patch_pipeline_ai(pipeline, self._dispatch([
                'Menerapkan langkah 2. dari tuntunan taubat dalam praktik.',
                'Menganalisis dampak taubat terhadap perilaku siswa',
                'Mengevaluasi praktik taubat yang sesuai tuntunan Islam'])):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        texts = [t['text'] for t in result['module']['learning_objectives']]
        assert texts[0] == 'Menerapkan langkah 2. dari tuntunan taubat dalam praktik.'


# ============================================================================
# STAGE-LEVEL REGENERATION (bounded recovery, real-AI reliability)
# ============================================================================

class TestStageRegeneration:
    """_ai_stage_call: respons gagal (shape/field/semantik) memicu
    regenerasi stage yang sama dengan feedback — bounded, tanpa
    bypass validator, tanpa sukses palsu. Semua dengan mock."""

    def test_recovers_after_one_shape_failure(self, pipeline):
        """Satu respons top-level array lalu respons benar -> success,
        dan prompt regenerasi membawa feedback perbaikan."""
        seen_prompts = []
        state = {'failed_once': False}

        def flaky(prompt, system_instruction=None, **kwargs):
            seen_prompts.append(prompt)
            if not state['failed_once']:
                state['failed_once'] = True
                return [{"question": "hanya array"}]
            return fake_router_response(prompt, system_instruction, **kwargs)

        with patch_pipeline_ai(pipeline, flaky):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        assert any('CATATAN PERBAIKAN' in p for p in seen_prompts)

    def test_gives_up_after_max_attempts(self, pipeline):
        """Gagal terus -> failed jujur (tidak infinite loop)."""
        calls = []

        def always_bad(prompt, system_instruction=None, **kwargs):
            calls.append(prompt)
            raise ValueError("Assessment response is not a JSON object")

        with patch_pipeline_ai(pipeline, always_bad):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        assert result['module'] is None
        # 1 initial + 2 regenerasi bounded untuk stage TP yang gagal
        assert len(calls) == pipeline.AI_STAGE_MAX_ATTEMPTS

    def test_auth_failure_fails_fast_without_regeneration(self, pipeline):
        """AuthenticationError tidak di-retry di level stage."""
        calls = []

        def deny(prompt, system_instruction=None, **kwargs):
            calls.append(prompt)
            raise AuthenticationError("bad key")

        with patch.object(pipeline.ai_client, 'generate_json',
                          side_effect=deny):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        assert len(calls) == 1


# ============================================================================
# GENERATION LOGS + PROMPT VERSIONING (audit trail terstruktur)
# ============================================================================

class TestGenerationLogs:
    """Log terstruktur per stage-attempt + versi prompt deterministik.

    Semua memakai mock AI (fakta integrasi dibuktikan via result dan
    GenerationLogStore di DB temp, bukan teks AI)."""

    def test_generation_id_created_and_consistent(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        gen_id = result['generation_id']
        assert gen_id
        assert result['module']['generation_id'] == gen_id
        assert result['generation_log']
        assert {r['generation_id'] for r in result['generation_log']} == {gen_id}

    def test_every_ai_stage_has_prompt_version(self):
        from module_generation_pipeline import ModuleGenerationPipeline as P
        assert set(P.PROMPT_VERSIONS) == {
            'tp', 'kktp', 'materials', 'activities', 'assessments',
            'outline', 'glosarium', 'topic'}
        for stage in P.PROMPT_VERSIONS:
            assert P.get_prompt_version(stage)
        with pytest.raises(KeyError):
            P.get_prompt_version('nope')

    def test_log_stores_prompt_version_and_hash(self, pipeline):
        from module_generation_pipeline import ModuleGenerationPipeline as P
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        ai_recs = [r for r in result['generation_log']
                   if r['stage'] != 'final']
        assert ai_recs
        for r in ai_recs:
            assert r['prompt_version'] == P.PROMPT_VERSIONS[r['stage']], r
            assert re.fullmatch(r'[0-9a-f]{64}', r['prompt_hash'] or ''), r
            assert r['model'] and r['provider'] == '9router'
            assert r['attempt'] >= 1
            assert r['duration_ms'] is not None

    def test_retry_yields_new_attempt_same_generation(self, pipeline):
        seen = {'n': 0}

        def flaky(prompt, system_instruction=None, **kwargs):
            seen['n'] += 1
            if seen['n'] == 1:
                return [{"hanya": "array"}]
            return fake_router_response(prompt, system_instruction, **kwargs)

        with patch_pipeline_ai(pipeline, flaky):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        # Panggilan AI pertama adalah refinement topik: retry tercatat
        # di stage topic dengan generation_id yang sama.
        topic_recs = sorted(
            (r for r in result['generation_log'] if r['stage'] == 'topic'),
            key=lambda r: r['attempt'])
        assert [r['attempt'] for r in topic_recs] == [1, 2]
        assert [r['status'] for r in topic_recs] == ['failed', 'success']
        assert topic_recs[0]['error_category']
        assert {r['generation_id'] for r in topic_recs} == {
            result['generation_id']}

    def test_failure_stage_recorded(self, pipeline):
        def always_bad(prompt, system_instruction=None, **kwargs):
            raise ValueError("Assessment response is not a JSON object")

        with patch_pipeline_ai(pipeline, always_bad):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'failed'
        fails = [r for r in result['generation_log']
                 if r['status'] == 'failed']
        assert fails
        # Tahap AI pertama adalah refinement topik (Batch 8.5 §5).
        assert fails[0]['stage'] == 'topic'
        assert fails[0]['error_category'] == 'format'
        assert 'JSON object' in (fails[0]['error'] or '')
        finals = [r for r in result['generation_log']
                  if r['stage'] == 'final']
        assert len(finals) == 1 and finals[0]['status'] == 'failed'

    def test_final_pass_recorded(self, pipeline):
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        finals = [r for r in result['generation_log']
                  if r['stage'] == 'final']
        assert len(finals) == 1
        assert finals[0]['status'] == 'success'
        assert finals[0]['duration_ms'] is not None

    def test_no_secret_in_logs(self, pipeline, test_db):
        from module_store import GenerationLogStore
        secret = 'test-secret-xyz-123'
        pipeline.ai_client.config.api_key = secret
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(VALID_PARAMS)
        assert result['status'] == 'success', result['errors']
        blob = json.dumps(result['generation_log'])
        assert secret not in blob
        assert 'Authorization' not in blob
        assert 'Bearer' not in blob
        stored = GenerationLogStore(str(test_db)).fetch(
            result['generation_id'])
        assert stored
        assert secret not in json.dumps(stored)

    def test_prompt_change_yields_different_version_material(self, pipeline):
        from module_generation_pipeline import ModuleGenerationPipeline as P
        h1 = P._prompt_hash('sys', 'prompt A')
        h2 = P._prompt_hash('sys', 'prompt B')
        assert h1 != h2
        assert len(h1) == 64
        # Versi eksplisit per stage (bukan timestamp, bukan env).
        assert P.PROMPT_VERSIONS['tp'] == '1.0'
        assert P.get_prompt_version('outline') == '1.2'

    def test_old_generation_traceable_by_its_version(self, test_db):
        from module_store import GenerationLogStore
        store = GenerationLogStore(str(test_db))
        store.save_records([
            {'generation_id': 'gen-old', 'stage': 'tp', 'attempt': 1,
             'prompt_version': '0.9', 'prompt_hash': 'a' * 64,
             'model': 'rpm', 'provider': '9router', 'status': 'success',
             'error_category': None, 'error': None, 'duration_ms': 1.0},
            {'generation_id': 'gen-new', 'stage': 'tp', 'attempt': 1,
             'prompt_version': '1.0', 'prompt_hash': 'b' * 64,
             'model': 'rpm', 'provider': '9router', 'status': 'success',
             'error_category': None, 'error': None, 'duration_ms': 1.0},
        ])
        old = store.fetch('gen-old')
        new = store.fetch('gen-new')
        assert [r['prompt_version'] for r in old] == ['0.9']
        assert [r['prompt_version'] for r in new] == ['1.0']
