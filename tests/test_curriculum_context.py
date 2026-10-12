#!/usr/bin/env python3
"""
Tests for Curriculum Context (Phase 5)
Tests context object creation, serialization, and immutability
"""

import pytest
import sys
import json

# Fixtures from conftest will handle imports


# ============================================================================
# CP ENTRY TESTS
# ============================================================================

@pytest.mark.context
class TestCPEntry:
    """Test CPEntry dataclass."""
    
    def test_cp_entry_creation(self, sample_cp_entry):
        """CPEntry should be created with required fields."""
        cp = sample_cp_entry
        
        assert cp.id == "CP-TEST-001"
        assert cp.text == "Test CP text - Siswa dapat memahami konsep pembelajaran"
        assert cp.source_document_id == "DOC-TEST-001"
        assert cp.source_fragment_id == "FRAG-TEST-001"
        assert cp.source_page == 42
        assert cp.phase == "D"
        assert cp.element == "Akhlak"
    
    def test_cp_entry_has_required_fields(self, sample_cp_entry):
        """CPEntry should have all required attributes."""
        cp = sample_cp_entry
        
        assert hasattr(cp, 'id')
        assert hasattr(cp, 'text')
        assert hasattr(cp, 'source_document_id')
        assert hasattr(cp, 'source_fragment_id')
        assert hasattr(cp, 'source_page')
        assert hasattr(cp, 'phase')
        assert hasattr(cp, 'element')
    
    def test_cp_entry_is_immutable(self, sample_cp_entry):
        """CPEntry should be immutable (frozen dataclass)."""
        cp = sample_cp_entry
        
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            cp.text = "Modified text"
    
    def test_cp_entry_with_real_data(self):
        """CPEntry should work with realistic data."""
        cp = CPEntry(
            id="CP-Akidah-Akhlak-D-42",
            text="Siswa dapat menganalisis dimensi akhlak dalam kehidupan modern",
            source_document_id="DOC-SK-DIRJEN-9941",
            source_fragment_id="frag-9941-page-42",
            source_page=42,
            phase="D",
            element="Akhlak"
        )
        
        assert cp.id is not None
        assert cp.text is not None
        assert cp.source_document_id == "DOC-SK-DIRJEN-9941"
        assert cp.phase == "D"


# ============================================================================
# TP ENTRY TESTS
# ============================================================================

@pytest.mark.context
class TestTPEntry:
    """Test TPEntry dataclass."""
    
    def test_tp_entry_creation(self):
        """TPEntry should be created with required fields."""
        tp = TPEntry(
            id="TP-001",
            text="Menerapkan konsep pembelajaran",
            cognitive_level="C3",
            source_type="ai_generated"
        )
        
        assert tp.id == "TP-001"
        assert tp.text == "Menerapkan konsep pembelajaran"
        assert tp.cognitive_level == "C3"
        assert tp.source_type == "ai_generated"
    
    def test_tp_entry_has_optional_derived_from_id(self):
        """TPEntry should have optional derived_from_id field."""
        tp = TPEntry(
            id="TP-001",
            text="Menerapkan konsep",
            cognitive_level="C3",
            source_type="ai_generated",
            derived_from_id="CP-001"
        )
        
        assert tp.derived_from_id == "CP-001"
    
    def test_tp_entry_derived_from_id_optional(self):
        """TPEntry derived_from_id should default to None."""
        tp = TPEntry(
            id="TP-001",
            text="Menerapkan konsep",
            cognitive_level="C3",
            source_type="ai_generated"
        )
        
        assert tp.derived_from_id is None
    
    def test_tp_entry_source_types(self):
        """TPEntry should accept valid source types."""
        source_types = ["teacher", "school", "imported", "ai_generated"]
        
        for source_type in source_types:
            tp = TPEntry(
                id=f"TP-{source_type}",
                text="Test TP",
                cognitive_level="C3",
                source_type=source_type
            )
            assert tp.source_type == source_type
    
    def test_tp_entry_from_fixture(self, sample_tp_entries):
        """TPEntry from fixture should work correctly."""
        tp_list = sample_tp_entries
        
        assert len(tp_list) == 2
        assert tp_list[0].cognitive_level == "C3"
        assert tp_list[1].cognitive_level == "C4"


# ============================================================================
# ATP ENTRY TESTS
# ============================================================================

@pytest.mark.context
class TestATPEntry:
    """Test ATPEntry dataclass."""
    
    def test_atp_entry_creation(self):
        """ATPEntry should be created with ID and TP list."""
        atp = ATPEntry(
            id="ATP-001",
            tp_ids=["TP-001", "TP-002", "TP-003"]
        )
        
        assert atp.id == "ATP-001"
        assert len(atp.tp_ids) == 3
        assert atp.tp_ids[0] == "TP-001"
    
    def test_atp_entry_maintains_order(self):
        """ATPEntry should maintain TP order (sequence)."""
        tp_ids = ["TP-001", "TP-002", "TP-003"]
        atp = ATPEntry(id="ATP-001", tp_ids=tp_ids)
        
        assert atp.tp_ids == tp_ids
        assert atp.tp_ids[0] == "TP-001"
        assert atp.tp_ids[1] == "TP-002"
        assert atp.tp_ids[2] == "TP-003"
    
    def test_atp_entry_from_fixture(self, sample_atp_entry):
        """ATPEntry from fixture should work correctly."""
        atp = sample_atp_entry
        
        assert atp.id == "ATP-TEST-001"
        assert len(atp.tp_ids) == 2


# ============================================================================
# CURRICULUM CONTEXT TESTS
# ============================================================================

@pytest.mark.context
class TestCurriculumContext:
    """Test CurriculumContext class."""
    
    def test_curriculum_context_creation(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """CurriculumContext should be created with required data."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        assert context.education_system == "KEMENAG"
        assert context.institution_type == "MTs"
        assert context.grade == "VII"
        assert context.phase == "D"
        assert context.subject == "Akidah Akhlak"
        assert context.element == "Akhlak"
        assert context.curriculum_version == "KMA-1503-2025"
    
    def test_curriculum_context_has_cp(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """CurriculumContext should have CP reference."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        assert context.cp is not None
        assert context.cp.id == "CP-TEST-001"
    
    def test_curriculum_context_has_tp_list(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """CurriculumContext should have TP list."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        assert context.tp_list is not None
        assert len(context.tp_list) == 2
    
    def test_curriculum_context_has_atp(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """CurriculumContext should have ATP reference."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        assert context.atp is not None
        assert context.atp.id == "ATP-TEST-001"
    
    def test_curriculum_context_has_rules(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """CurriculumContext should have rules."""
        rules = {
            'minimum_tp_level': 'C3',
            'minimum_kktp_level': 'C3'
        }
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry,
            rules=rules
        )
        
        assert context.rules is not None
        assert context.rules['minimum_tp_level'] == 'C3'


# ============================================================================
# CONTEXT SERIALIZATION TESTS
# ============================================================================

@pytest.mark.context
class TestContextSerialization:
    """Test context serialization (to_dict, to_json)."""
    
    def test_context_to_dict(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """CurriculumContext.to_dict() should return dictionary."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        context_dict = context.to_dict()
        
        assert isinstance(context_dict, dict)
        assert context_dict['education_system'] == "KEMENAG"
        assert context_dict['subject'] == "Akidah Akhlak"
    
    def test_context_to_dict_contains_required_keys(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """to_dict() should contain all required keys."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        context_dict = context.to_dict()
        
        required_keys = [
            'education_system', 'institution_type', 'grade', 'phase',
            'subject', 'element', 'curriculum_version', 'cp', 'tp', 'atp'
        ]
        
        for key in required_keys:
            assert key in context_dict
    
    def test_context_to_dict_has_cp_data(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """to_dict() should include CP data."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        context_dict = context.to_dict()
        
        assert 'cp' in context_dict
        assert context_dict['cp']['id'] == "CP-TEST-001"
        assert context_dict['cp']['text'] is not None
    
    def test_context_to_dict_has_tp_list(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """to_dict() should include TP list."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        context_dict = context.to_dict()
        
        assert 'tp' in context_dict
        assert isinstance(context_dict['tp'], list)
        assert len(context_dict['tp']) == 2
    
    def test_context_to_json(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """CurriculumContext.to_json() should return valid JSON string."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        json_str = context.to_json()
        
        assert isinstance(json_str, str)
        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed['education_system'] == "KEMENAG"
    
    def test_context_json_roundtrip(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """Context to JSON and back should preserve data."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        json_str = context.to_json()
        parsed = json.loads(json_str)
        
        assert parsed['education_system'] == context.education_system
        assert parsed['subject'] == context.subject
        assert parsed['phase'] == context.phase


# ============================================================================
# CONTEXT CONSISTENCY TESTS
# ============================================================================

@pytest.mark.context
class TestContextConsistency:
    """Test context data consistency and immutability."""
    
    def test_context_phase_matches_grade(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """Context should maintain phase-grade consistency."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",  # MTs 7 should be D
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        # Grade 7 (VII) for MTs should be phase D
        assert context.grade == "VII"
        assert context.phase == "D"
    
    def test_context_subject_matches_system(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """Context should maintain subject-system consistency."""
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",  # Valid for KEMENAG
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=sample_cp_entry,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        assert context.education_system == "KEMENAG"
        assert context.subject == "Akidah Akhlak"
    
    def test_context_cp_phase_matches_context_phase(self, sample_tp_entries, sample_atp_entry):
        """CP phase should match context phase."""
        cp = CPEntry(
            id="CP-001",
            text="Test",
            source_document_id="DOC-001",
            source_fragment_id="FRAG-001",
            source_page=42,
            phase="D",  # Matches context phase
            element="Akhlak"
        )
        
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=cp,
            tp_list=sample_tp_entries,
            atp=sample_atp_entry
        )
        
        assert context.phase == context.cp.phase


# ============================================================================
# CONTEXT VALIDATOR TESTS
# ============================================================================

@pytest.mark.context
class TestContextValidator:
    """Test ContextValidator class."""
    
    def test_context_validator_creation(self, test_db):
        """ContextValidator should be created with database path."""
        validator = ContextValidator(str(test_db))
        assert validator is not None
    
    def test_context_validator_has_db_path(self, test_db):
        """ContextValidator should store database path."""
        db_path = str(test_db)
        validator = ContextValidator(db_path)
        assert str(validator.db_path) == db_path


# ============================================================================
# CONTEXT GENERATOR TESTS
# ============================================================================

@pytest.mark.context
class TestCurriculumContextGenerator:
    """Test CurriculumContextGenerator class."""
    
    def test_context_generator_creation(self):
        """CurriculumContextGenerator should be created."""
        generator = CurriculumContextGenerator()
        assert generator is not None
    
    def test_context_generator_has_validate_inputs_method(self):
        """Generator should have _validate_inputs method."""
        generator = CurriculumContextGenerator()
        assert hasattr(generator, '_validate_inputs')
    
    def test_context_generator_has_generate_hash_method(self):
        """Generator should have _generate_hash method."""
        generator = CurriculumContextGenerator()
        assert hasattr(generator, '_generate_hash')


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.context
@pytest.mark.integration
class TestContextIntegration:
    """Integration tests for curriculum context."""
    
    def test_complete_context_creation_workflow(self, sample_cp_entry, sample_tp_entries, sample_atp_entry):
        """Complete workflow should create valid context."""
        # 1. Create entries
        cp = sample_cp_entry
        tp_list = sample_tp_entries
        atp = sample_atp_entry
        
        # 2. Create context
        context = CurriculumContext(
            education_system="KEMENAG",
            institution_type="MTs",
            grade="VII",
            phase="D",
            subject="Akidah Akhlak",
            element="Akhlak",
            curriculum_version="KMA-1503-2025",
            cp=cp,
            tp_list=tp_list,
            atp=atp
        )
        
        # 3. Verify context
        assert context.education_system == "KEMENAG"
        assert len(context.tp_list) == 2
        
        # 4. Serialize
        context_dict = context.to_dict()
        json_str = context.to_json()
        
        # 5. Verify serialization
        assert isinstance(context_dict, dict)
        assert isinstance(json_str, str)
        
        parsed = json.loads(json_str)
        assert parsed['subject'] == "Akidah Akhlak"
