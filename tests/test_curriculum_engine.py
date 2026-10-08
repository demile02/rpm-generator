#!/usr/bin/env python3
"""
Tests for Curriculum Engine (Phase 3)
Tests grade-phase mapping, subject retrieval, system separation, and CP queries
"""

import pytest
import sys

# Fixtures from conftest will handle imports


# ============================================================================
# GRADE → PHASE MAPPING TESTS
# ============================================================================

@pytest.mark.curriculum
class TestGradePhaseMapping:
    """Test grade-to-phase mapping validation."""
    
    def test_mts_grade_7_maps_to_phase_d(self, curriculum_engine):
        """MTs grade 7 (kelas VII) should map to Fase D."""
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('KEMENAG', 'MTs_7')
        assert is_valid is True
        assert phase == 'D'
        assert msg == ""
    
    def test_mts_grade_8_maps_to_phase_d(self, curriculum_engine):
        """MTs grade 8 (kelas VIII) should map to Fase D."""
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('KEMENAG', 'MTs_8')
        assert is_valid is True
        assert phase == 'D'
    
    def test_mts_grade_9_maps_to_phase_d(self, curriculum_engine):
        """MTs grade 9 (kelas IX) should map to Fase D."""
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('KEMENAG', 'MTs_9')
        assert is_valid is True
        assert phase == 'D'
    
    def test_ma_grade_10_maps_to_phase_e(self, curriculum_engine):
        """MA grade 10 (kelas X) should map to Fase E."""
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('KEMENAG', 'MA_10')
        assert is_valid is True
        assert phase == 'E'
    
    def test_ma_grade_11_maps_to_phase_f(self, curriculum_engine):
        """MA grade 11 (kelas XI) should map to Fase F."""
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('KEMENAG', 'MA_11')
        assert is_valid is True
        assert phase == 'F'
    
    def test_ma_grade_12_maps_to_phase_f(self, curriculum_engine):
        """MA grade 12 (kelas XII) should map to Fase F."""
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('KEMENAG', 'MA_12')
        assert is_valid is True
        assert phase == 'F'
    
    def test_mi_grade_1_maps_to_phase_a(self, curriculum_engine):
        """MI grade 1 should map to Fase A."""
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('KEMENAG', 'MI_1')
        assert is_valid is True
        assert phase == 'A'
    
    def test_mi_grade_2_maps_to_phase_a(self, curriculum_engine):
        """MI grade 2 should map to Fase A."""
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('KEMENAG', 'MI_2')
        assert is_valid is True
        assert phase == 'A'
    
    def test_mi_grade_5_maps_to_phase_c(self, curriculum_engine):
        """MI grade 5 should map to Fase C."""
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('KEMENAG', 'MI_5')
        assert is_valid is True
        assert phase == 'C'
    
    def test_invalid_grade_returns_false(self, curriculum_engine):
        """Invalid grade should return False."""
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('KEMENAG', 'INVALID_GRADE')
        assert is_valid is False
        assert phase is None
        assert "tidak ditemukan" in msg or "not found" in msg.lower()
    
    def test_invalid_system_returns_false(self, curriculum_engine):
        """Invalid system should return False."""
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('INVALID_SYSTEM', 'MTs_7')
        assert is_valid is False
        assert phase is None


# ============================================================================
# SUBJECT RETRIEVAL TESTS
# ============================================================================

@pytest.mark.curriculum
class TestSubjectRetrieval:
    """Test subject retrieval by system and institution."""
    
    def test_get_subjects_for_kemenag(self, curriculum_engine):
        """Should retrieve subjects for KEMENAG system."""
        subjects = curriculum_engine.get_subjects_for_system('KEMENAG')
        assert len(subjects) > 0
        subject_names = [s.name for s in subjects]
        assert 'Akidah Akhlak' in subject_names
        assert 'Al-Qur\'an Hadis' in subject_names
    
    def test_get_subjects_for_kemenag_mts(self, curriculum_engine):
        """Should retrieve subjects for KEMENAG/MTs."""
        subjects = curriculum_engine.get_subjects_for_system('KEMENAG', 'MTs')
        assert len(subjects) > 0
        subject_names = [s.name for s in subjects]
        assert any('Akidah' in name or 'Akhlak' in name for name in subject_names)
    
    def test_subjects_have_required_fields(self, curriculum_engine):
        """Subjects should have code, name, system, elements."""
        subjects = curriculum_engine.get_subjects_for_system('KEMENAG', 'MTs')
        assert len(subjects) > 0
        
        subject = subjects[0]
        assert hasattr(subject, 'code')
        assert hasattr(subject, 'name')
        assert hasattr(subject, 'system')
        assert hasattr(subject, 'elements')
        assert subject.system == 'KEMENAG'
    
    def test_akidah_akhlak_has_elements(self, curriculum_engine):
        """Akidah Akhlak should have defined elements."""
        subjects = curriculum_engine.get_subjects_for_system('KEMENAG', 'MTs')
        akidah = next((s for s in subjects if 'Akidah Akhlak' in s.name), None)
        
        assert akidah is not None
        assert len(akidah.elements) > 0
    
    def test_get_subjects_for_kemendikdasmen(self, curriculum_engine):
        """Should retrieve subjects for Kemendikdasmen if available."""
        subjects = curriculum_engine.get_subjects_for_system('KEMENDIKDASMEN')
        # May be empty or have subjects, just test it doesn't error
        assert isinstance(subjects, list)


# ============================================================================
# SUBJECT-SYSTEM VALIDATION TESTS
# ============================================================================

@pytest.mark.curriculum
class TestSubjectSystemValidation:
    """Test subject-system validation."""
    
    def test_akidah_akhlak_valid_for_kemenag(self, curriculum_engine):
        """Akidah Akhlak should be valid for KEMENAG."""
        is_valid = curriculum_engine.validate_subject_system('Akidah Akhlak', 'KEMENAG')
        assert is_valid is True
    
    def test_alquran_hadis_valid_for_kemenag(self, curriculum_engine):
        """Al-Qur'an Hadis should be valid for KEMENAG."""
        is_valid = curriculum_engine.validate_subject_system('Al-Qur\'an Hadis', 'KEMENAG')
        assert is_valid is True
    
    def test_fikih_valid_for_kemenag(self, curriculum_engine):
        """Fikih should be valid for KEMENAG."""
        is_valid = curriculum_engine.validate_subject_system('Fikih', 'KEMENAG')
        assert is_valid is True
    
    def test_ski_valid_for_kemenag(self, curriculum_engine):
        """SKI (Sejarah Kebudayaan Islam) should be valid for KEMENAG."""
        is_valid = curriculum_engine.validate_subject_system('Sejarah Kebudayaan Islam', 'KEMENAG')
        assert is_valid is True
    
    def test_bahasa_arab_valid_for_kemenag(self, curriculum_engine):
        """Bahasa Arab should be valid for KEMENAG."""
        is_valid = curriculum_engine.validate_subject_system('Bahasa Arab', 'KEMENAG')
        assert is_valid is True
    
    def test_invalid_subject_for_system(self, curriculum_engine):
        """Invalid subject should return False."""
        is_valid = curriculum_engine.validate_subject_system('INVALID_SUBJECT', 'KEMENAG')
        assert is_valid is False
    
    def test_mixed_subject_system_rejection(self, curriculum_engine):
        """KEMENAG subjects should not be valid for Kemendikdasmen."""
        # Akidah Akhlak is KEMENAG-specific
        is_valid = curriculum_engine.validate_subject_system('Akidah Akhlak', 'KEMENDIKDASMEN')
        # Should be False since Akidah Akhlak is not in Kemendikdasmen curriculum
        assert is_valid is False


# ============================================================================
# CP RETRIEVAL TESTS
# ============================================================================

@pytest.mark.curriculum
@pytest.mark.database
class TestCPRetrieval:
    """Test CP (Capaian Pembelajaran) retrieval."""
    
    def test_get_cp_by_subject_phase_returns_results(self, curriculum_engine):
        """Should retrieve CP for valid subject-phase combination."""
        cp_list = curriculum_engine.get_cp_by_subject_phase('Akidah Akhlak', 'D')
        assert len(cp_list) > 0
    
    def test_cp_entry_has_required_fields(self, curriculum_engine):
        """CP entry should have all required fields."""
        cp_list = curriculum_engine.get_cp_by_subject_phase('Akidah Akhlak', 'D')
        assert len(cp_list) > 0
        
        cp = cp_list[0]
        assert hasattr(cp, 'id')
        assert hasattr(cp, 'text')
        assert hasattr(cp, 'subject')
        assert hasattr(cp, 'phase')
        assert hasattr(cp, 'element')
        assert hasattr(cp, 'source_page')
        assert hasattr(cp, 'source_document')
    
    def test_cp_entries_have_provenance(self, curriculum_engine):
        """All CP entries should have source information."""
        cp_list = curriculum_engine.get_cp_by_subject_phase('Akidah Akhlak', 'D')
        
        for cp in cp_list:
            assert cp.source_document is not None
            assert cp.source_page is not None
            assert cp.id is not None
    
    def test_cp_retrieval_respects_subject(self, curriculum_engine):
        """CP should only return entries for requested subject."""
        cp_list = curriculum_engine.get_cp_by_subject_phase('Akidah Akhlak', 'D')
        
        for cp in cp_list:
            assert cp.subject == 'Akidah Akhlak'
    
    def test_cp_retrieval_respects_phase(self, curriculum_engine):
        """CP should only return entries for requested phase."""
        cp_list = curriculum_engine.get_cp_by_subject_phase('Akidah Akhlak', 'D')
        
        for cp in cp_list:
            assert cp.phase == 'D'
    
    def test_invalid_phase_returns_empty(self, curriculum_engine):
        """Invalid phase should return empty list or None."""
        cp_list = curriculum_engine.get_cp_by_subject_phase('Akidah Akhlak', 'INVALID')
        assert len(cp_list) == 0


# ============================================================================
# INSTITUTION TYPE TESTS
# ============================================================================

@pytest.mark.curriculum
class TestInstitutionTypeSystem:
    """Test institution type to system mapping."""
    
    def test_get_system_for_mts(self, curriculum_engine):
        """MTs should map to KEMENAG."""
        system = curriculum_engine.get_system_for_institution('MTs')
        assert system == 'KEMENAG'
    
    def test_get_system_for_ma(self, curriculum_engine):
        """MA should map to KEMENAG."""
        system = curriculum_engine.get_system_for_institution('MA')
        assert system == 'KEMENAG'
    
    def test_get_system_for_mi(self, curriculum_engine):
        """MI should map to KEMENAG."""
        system = curriculum_engine.get_system_for_institution('MI')
        assert system == 'KEMENAG'
    
    def test_get_system_for_invalid_type(self, curriculum_engine):
        """Invalid institution type should return None."""
        system = curriculum_engine.get_system_for_institution('INVALID_TYPE')
        assert system is None


# ============================================================================
# GRADE PHASE VALIDATOR TESTS
# ============================================================================

@pytest.mark.curriculum
class TestGradePhaseValidator:
    """Test GradePhaseValidator class."""
    
    def test_validator_accepts_valid_grade_phase(self, curriculum_mappings):
        """Validator should accept valid grade-phase combinations."""
        validator = GradePhaseValidator(curriculum_mappings)
        is_valid, phase, msg = validator.validate_and_get_phase('KEMENAG', 'MTs', 'MTs_7')
        
        assert is_valid is True
        assert phase == 'D'
    
    def test_validator_rejects_invalid_institution(self, curriculum_mappings):
        """Validator should reject invalid institution type."""
        validator = GradePhaseValidator(curriculum_mappings)
        is_valid, phase, msg = validator.validate_and_get_phase('KEMENAG', 'INVALID_TYPE', 'MTs_7')
        
        assert is_valid is False
        assert phase is None
        assert msg != ""
    
    def test_validator_rejects_invalid_grade(self, curriculum_mappings):
        """Validator should reject invalid grade."""
        validator = GradePhaseValidator(curriculum_mappings)
        is_valid, phase, msg = validator.validate_and_get_phase('KEMENAG', 'MTs', 'INVALID_GRADE')
        
        assert is_valid is False
        assert phase is None
        assert msg != ""


# ============================================================================
# DATABASE CONNECTION TESTS
# ============================================================================

@pytest.mark.curriculum
@pytest.mark.database
class TestEngineConnection:
    """Test engine database connection management."""
    
    def test_engine_connects_to_database(self, curriculum_engine):
        """Engine should successfully connect to database."""
        assert curriculum_engine.connection is not None
        assert curriculum_engine.cursor is not None
    
    def test_engine_can_query_database(self, curriculum_engine):
        """Engine should be able to execute queries."""
        curriculum_engine.cursor.execute("SELECT COUNT(*) as count FROM learning_outcomes")
        result = curriculum_engine.cursor.fetchone()
        assert result is not None
        assert 'count' in result.keys()
    
    def test_engine_loads_mappings(self, curriculum_engine):
        """Engine should load curriculum mappings."""
        assert curriculum_engine.mappings is not None
        assert 'grade_to_phase_mappings' in curriculum_engine.mappings


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.curriculum
@pytest.mark.integration
class TestCurriculumEngineIntegration:
    """Integration tests for curriculum engine workflow."""
    
    def test_full_workflow_kemenag_mts_vii(self, curriculum_engine):
        """Test complete workflow: verify grade, get subjects, get CP."""
        # 1. Validate grade-phase
        is_valid, phase, msg = curriculum_engine.validate_grade_phase('KEMENAG', 'MTs_7')
        assert is_valid is True
        assert phase == 'D'
        
        # 2. Get subjects for KEMENAG/MTs
        subjects = curriculum_engine.get_subjects_for_system('KEMENAG', 'MTs')
        assert len(subjects) > 0
        
        # 3. Validate subject exists
        is_valid = curriculum_engine.validate_subject_system('Akidah Akhlak', 'KEMENAG')
        assert is_valid is True
        
        # 4. Get CP for subject-phase
        cp_list = curriculum_engine.get_cp_by_subject_phase('Akidah Akhlak', phase)
        assert len(cp_list) > 0
        
        # 5. Verify CP has provenance
        for cp in cp_list:
            assert cp.source_document is not None
            assert cp.phase == phase
