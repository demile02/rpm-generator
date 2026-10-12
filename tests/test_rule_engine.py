#!/usr/bin/env python3
"""
Tests for Rule Engine (Phase 4)
Tests all validation rules including cognitive levels, provenance, and alignment
"""

import pytest
import sys

# Fixtures from conftest will handle imports


# ============================================================================
# COGNITIVE LEVEL TESTS
# ============================================================================

@pytest.mark.rules
class TestCognitiveLevel:
    """Test cognitive level validation."""
    
    def test_cognitive_level_c1_value(self):
        """C1 should have value 1."""
        assert CognitiveLevel.C1.value == 1
    
    def test_cognitive_level_c6_value(self):
        """C6 should have value 6."""
        assert CognitiveLevel.C6.value == 6
    
    def test_cognitive_level_c3_minimum_accepts_c3(self):
        """C3 should pass C3 minimum."""
        is_valid = CognitiveLevel.is_valid_minimum('C3', 'C3')
        assert is_valid is True
    
    def test_cognitive_level_c3_minimum_accepts_c4(self):
        """C4 should pass C3 minimum."""
        is_valid = CognitiveLevel.is_valid_minimum('C4', 'C3')
        assert is_valid is True
    
    def test_cognitive_level_c3_minimum_accepts_c5(self):
        """C5 should pass C3 minimum."""
        is_valid = CognitiveLevel.is_valid_minimum('C5', 'C3')
        assert is_valid is True
    
    def test_cognitive_level_c3_minimum_accepts_c6(self):
        """C6 should pass C3 minimum."""
        is_valid = CognitiveLevel.is_valid_minimum('C6', 'C3')
        assert is_valid is True
    
    def test_cognitive_level_c3_minimum_rejects_c1(self):
        """C1 should fail C3 minimum."""
        is_valid = CognitiveLevel.is_valid_minimum('C1', 'C3')
        assert is_valid is False
    
    def test_cognitive_level_c3_minimum_rejects_c2(self):
        """C2 should fail C3 minimum."""
        is_valid = CognitiveLevel.is_valid_minimum('C2', 'C3')
        assert is_valid is False


# ============================================================================
# TP COGNITIVE MINIMUM RULE TESTS
# ============================================================================

@pytest.mark.rules
class TestTPCognitiveMinimumRule:
    """Test TP minimum cognitive level enforcement."""
    
    def test_tp_rule_rejects_c1(self):
        """TP with C1 should be rejected."""
        rule = TPCognitiveMinimumRule()
        data = {'cognitive_level': 'C1', 'tp_text': 'Menyebutkan'}
        result = rule.validate(data)
        
        assert result.passed is False
        assert result.severity == RuleSeverity.ERROR
        assert 'C1' in result.message
    
    def test_tp_rule_rejects_c2(self):
        """TP with C2 should be rejected."""
        rule = TPCognitiveMinimumRule()
        data = {'cognitive_level': 'C2', 'tp_text': 'Memahami'}
        result = rule.validate(data)
        
        assert result.passed is False
        assert result.severity == RuleSeverity.ERROR
        assert 'C2' in result.message
    
    def test_tp_rule_accepts_c3(self):
        """TP with C3 should be accepted."""
        rule = TPCognitiveMinimumRule()
        data = {'cognitive_level': 'C3', 'tp_text': 'Menerapkan'}
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_tp_rule_accepts_c4(self):
        """TP with C4 should be accepted."""
        rule = TPCognitiveMinimumRule()
        data = {'cognitive_level': 'C4', 'tp_text': 'Menganalisis'}
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_tp_rule_accepts_c5(self):
        """TP with C5 should be accepted."""
        rule = TPCognitiveMinimumRule()
        data = {'cognitive_level': 'C5', 'tp_text': 'Mengevaluasi'}
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_tp_rule_accepts_c6(self):
        """TP with C6 should be accepted."""
        rule = TPCognitiveMinimumRule()
        data = {'cognitive_level': 'C6', 'tp_text': 'Menciptakan'}
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_tp_rule_returns_validation_result(self):
        """TP rule should return ValidationResult object."""
        rule = TPCognitiveMinimumRule()
        data = {'cognitive_level': 'C3', 'tp_text': 'Test'}
        result = rule.validate(data)
        
        assert isinstance(result, ValidationResult)
        assert result.rule_id == 'RULE-TP-001'


# ============================================================================
# KKTP COGNITIVE MINIMUM RULE TESTS
# ============================================================================

@pytest.mark.rules
class TestKKTPCognitiveMinimumRule:
    """Test KKTP minimum cognitive level enforcement."""
    
    def test_kktp_rule_rejects_c1(self):
        """KKTP with C1 should be rejected."""
        rule = KKTPCognitiveMinimumRule()
        data = {'cognitive_level': 'C1'}
        result = rule.validate(data)
        
        assert result.passed is False
        assert result.severity == RuleSeverity.ERROR
    
    def test_kktp_rule_rejects_c2(self):
        """KKTP with C2 should be rejected."""
        rule = KKTPCognitiveMinimumRule()
        data = {'cognitive_level': 'C2'}
        result = rule.validate(data)
        
        assert result.passed is False
        assert result.severity == RuleSeverity.ERROR
    
    def test_kktp_rule_accepts_c3(self):
        """KKTP with C3 should be accepted."""
        rule = KKTPCognitiveMinimumRule()
        data = {'cognitive_level': 'C3'}
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_kktp_rule_accepts_c4(self):
        """KKTP with C4 should be accepted."""
        rule = KKTPCognitiveMinimumRule()
        data = {'cognitive_level': 'C4'}
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_kktp_rule_accepts_c5(self):
        """KKTP with C5 should be accepted."""
        rule = KKTPCognitiveMinimumRule()
        data = {'cognitive_level': 'C5'}
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_kktp_rule_accepts_c6(self):
        """KKTP with C6 should be accepted."""
        rule = KKTPCognitiveMinimumRule()
        data = {'cognitive_level': 'C6'}
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_kktp_rule_id(self):
        """KKTP rule should have correct ID."""
        rule = KKTPCognitiveMinimumRule()
        assert rule.rule_id == 'RULE-KKTP-001'


# ============================================================================
# GRADE-PHASE VALIDATION RULE TESTS
# ============================================================================

@pytest.mark.rules
class TestGradePhaseValidationRule:
    """Test grade-to-phase validation rule."""
    
    def test_grade_phase_rule_accepts_valid_mts7_d(self):
        """Valid MTs grade 7 → Phase D should pass."""
        rule = GradePhasePValidationRule()
        data = {
            'grade': 'MTs_7',
            'phase': 'D',
            'education_system': 'KEMENAG',
            'institution_type': 'MTs'
        }
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_grade_phase_rule_rejects_mismatched_phase(self):
        """MTs grade 7 with Phase E (wrong) should fail."""
        rule = GradePhasePValidationRule()
        data = {
            'grade': 'MTs_7',
            'phase': 'E',  # Wrong
            'education_system': 'KEMENAG',
            'institution_type': 'MTs'
        }
        result = rule.validate(data)
        
        assert result.passed is False
        assert result.severity == RuleSeverity.ERROR
    
    def test_grade_phase_rule_accepts_ma10_e(self):
        """Valid MA grade 10 → Phase E should pass."""
        rule = GradePhasePValidationRule()
        data = {
            'grade': 'MA_10',
            'phase': 'E',
            'education_system': 'KEMENAG',
            'institution_type': 'MA'
        }
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_grade_phase_rule_accepts_ma11_f(self):
        """Valid MA grade 11 → Phase F should pass."""
        rule = GradePhasePValidationRule()
        data = {
            'grade': 'MA_11',
            'phase': 'F',
            'education_system': 'KEMENAG',
            'institution_type': 'MA'
        }
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_grade_phase_rule_rule_id(self):
        """Rule should have correct ID."""
        rule = GradePhasePValidationRule()
        assert rule.rule_id == 'RULE-CURRICULUM-001'


# ============================================================================
# CP PROVENANCE RULE TESTS
# ============================================================================

@pytest.mark.rules
class TestCPProvenanceRule:
    """Test CP provenance (source tracking) rule."""
    
    def test_provenance_rule_accepts_with_source(self):
        """CP with source should pass."""
        rule = CPProvenanceRule()
        data = {
            'source_document_id': 'DOC-SK-DIRJEN-9941',
            'source_fragment_id': 'frag-001'
        }
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_provenance_rule_rejects_missing_source_document(self):
        """CP without source_document_id should fail."""
        rule = CPProvenanceRule()
        data = {
            'source_document_id': None,
            'source_fragment_id': 'frag-001'
        }
        result = rule.validate(data)
        
        assert result.passed is False
        assert result.severity == RuleSeverity.ERROR
    
    def test_provenance_rule_rejects_missing_source_fragment(self):
        """CP without source_fragment_id should fail."""
        rule = CPProvenanceRule()
        data = {
            'source_document_id': 'DOC-SK-DIRJEN-9941',
            'source_fragment_id': None
        }
        result = rule.validate(data)
        
        assert result.passed is False
        assert result.severity == RuleSeverity.ERROR
    
    def test_provenance_rule_rejects_both_missing(self):
        """CP without both source fields should fail."""
        rule = CPProvenanceRule()
        data = {
            'source_document_id': None,
            'source_fragment_id': None
        }
        result = rule.validate(data)
        
        assert result.passed is False
    
    def test_provenance_rule_id(self):
        """Rule should have correct ID."""
        rule = CPProvenanceRule()
        assert rule.rule_id == 'RULE-CURRICULUM-002'


# ============================================================================
# SUBJECT-SYSTEM VALIDATION RULE TESTS
# ============================================================================

@pytest.mark.rules
class TestSubjectSystemValidationRule:
    """Test subject-system separation rule."""
    
    def test_subject_system_rule_accepts_akidah_kemenag(self):
        """Akidah Akhlak in KEMENAG should pass."""
        rule = SubjectSystemValidationRule()
        data = {
            'subject': 'Akidah Akhlak',
            'education_system': 'KEMENAG'
        }
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_subject_system_rule_accepts_fikih_kemenag(self):
        """Fikih in KEMENAG should pass."""
        rule = SubjectSystemValidationRule()
        data = {
            'subject': 'Fikih',
            'education_system': 'KEMENAG'
        }
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_subject_system_rule_accepts_bahasa_arab_kemenag(self):
        """Bahasa Arab in KEMENAG should pass."""
        rule = SubjectSystemValidationRule()
        data = {
            'subject': 'Bahasa Arab',
            'education_system': 'KEMENAG'
        }
        result = rule.validate(data)
        
        assert result.passed is True
    
    def test_subject_system_rule_rejects_akidah_kemendikdasmen(self):
        """Akidah Akhlak in Kemendikdasmen should fail."""
        rule = SubjectSystemValidationRule()
        data = {
            'subject': 'Akidah Akhlak',
            'education_system': 'KEMENDIKDASMEN'
        }
        result = rule.validate(data)
        
        assert result.passed is False
        assert result.severity == RuleSeverity.ERROR
    
    def test_subject_system_rule_rejects_invalid_subject(self):
        """Invalid subject should fail."""
        rule = SubjectSystemValidationRule()
        data = {
            'subject': 'INVALID_SUBJECT',
            'education_system': 'KEMENAG'
        }
        result = rule.validate(data)
        
        assert result.passed is False
    
    def test_subject_system_rule_id(self):
        """Rule should have correct ID."""
        rule = SubjectSystemValidationRule()
        assert rule.rule_id == 'RULE-CURRICULUM-003'


# ============================================================================
# RULE ENGINE TESTS
# ============================================================================

@pytest.mark.rules
class TestRuleEngine:
    """Test RuleEngine orchestration."""
    
    def test_rule_engine_has_5_rules(self, rule_engine):
        """RuleEngine should have 5 rules defined."""
        assert len(rule_engine.rules) == 5
    
    def test_rule_engine_validate_with_valid_data(self, rule_engine, valid_tp_data):
        """Validation with valid data should pass all rules."""
        all_pass, results = rule_engine.validate(valid_tp_data)
        
        assert all_pass is True
        assert len(results) == 5
        assert all(r.passed is True for r in results)
    
    def test_rule_engine_validate_with_c1_tp(self, rule_engine, invalid_tp_c1_data):
        """Validation with C1 TP should fail."""
        all_pass, results = rule_engine.validate(invalid_tp_c1_data)
        
        assert all_pass is False
        # Should have at least TP rule failing
        failed_rules = [r for r in results if not r.passed]
        assert len(failed_rules) > 0
    
    def test_rule_engine_validate_with_c2_tp(self, rule_engine, invalid_tp_c2_data):
        """Validation with C2 TP should fail."""
        all_pass, results = rule_engine.validate(invalid_tp_c2_data)
        
        assert all_pass is False
        failed_rules = [r for r in results if not r.passed]
        assert len(failed_rules) > 0
    
    def test_rule_engine_validate_with_invalid_phase(self, rule_engine, invalid_phase_data):
        """Validation with invalid phase should fail."""
        all_pass, results = rule_engine.validate(invalid_phase_data)
        
        assert all_pass is False
        failed_rules = [r for r in results if not r.passed]
        assert len(failed_rules) > 0
    
    def test_rule_engine_validate_with_invalid_subject_system(self, rule_engine, invalid_subject_system_data):
        """Validation with invalid subject-system should fail."""
        all_pass, results = rule_engine.validate(invalid_subject_system_data)
        
        assert all_pass is False
        failed_rules = [r for r in results if not r.passed]
        assert len(failed_rules) > 0
    
    def test_rule_engine_validate_with_missing_provenance(self, rule_engine, missing_provenance_data):
        """Validation with missing provenance should fail."""
        all_pass, results = rule_engine.validate(missing_provenance_data)
        
        assert all_pass is False
        # CP provenance rule should fail
        cp_prov_result = next((r for r in results if 'RULE-CURRICULUM-002' in r.rule_id), None)
        assert cp_prov_result is not None
        assert cp_prov_result.passed is False
    
    def test_rule_engine_returns_validation_results(self, rule_engine, valid_tp_data):
        """RuleEngine.validate should return structured results."""
        all_pass, results = rule_engine.validate(valid_tp_data)
        
        assert isinstance(all_pass, bool)
        assert isinstance(results, list)
        assert all(isinstance(r, ValidationResult) for r in results)
    
    def test_rule_engine_validation_result_has_details(self, rule_engine, invalid_tp_c1_data):
        """Validation results should include details."""
        all_pass, results = rule_engine.validate(invalid_tp_c1_data)
        
        failed = [r for r in results if not r.passed]
        assert len(failed) > 0
        
        # Check that at least one failed result has details
        has_details = any(r.details is not None for r in failed)
        assert has_details


# ============================================================================
# RULE SEVERITY TESTS
# ============================================================================

@pytest.mark.rules
class TestRuleSeverity:
    """Test rule severity levels."""
    
    def test_rule_severity_error(self):
        """ERROR severity should be defined."""
        assert RuleSeverity.ERROR.value == "error"
    
    def test_rule_severity_warning(self):
        """WARNING severity should be defined."""
        assert RuleSeverity.WARNING.value == "warning"
    
    def test_rule_severity_info(self):
        """INFO severity should be defined."""
        assert RuleSeverity.INFO.value == "info"
    
    def test_tp_rule_has_error_severity(self):
        """TP rule should have ERROR severity."""
        rule = TPCognitiveMinimumRule()
        assert rule.severity == RuleSeverity.ERROR
    
    def test_kktp_rule_has_error_severity(self):
        """KKTP rule should have ERROR severity."""
        rule = KKTPCognitiveMinimumRule()
        assert rule.severity == RuleSeverity.ERROR
    
    def test_provenance_rule_has_error_severity(self):
        """Provenance rule should have ERROR severity."""
        rule = CPProvenanceRule()
        assert rule.severity == RuleSeverity.ERROR


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

@pytest.mark.rules
@pytest.mark.integration
class TestRuleEngineIntegration:
    """Integration tests for rule engine."""
    
    def test_all_rules_reject_c1_independently(self):
        """Each rule class should independently reject C1."""
        data_c1 = {'cognitive_level': 'C1'}
        
        tp_rule = TPCognitiveMinimumRule()
        kktp_rule = KKTPCognitiveMinimumRule()
        
        tp_result = tp_rule.validate(data_c1)
        kktp_result = kktp_rule.validate(data_c1)
        
        assert tp_result.passed is False
        assert kktp_result.passed is False
    
    def test_all_rules_accept_c3_independently(self):
        """Each rule class should independently accept C3."""
        data_c3 = {'cognitive_level': 'C3'}
        
        tp_rule = TPCognitiveMinimumRule()
        kktp_rule = KKTPCognitiveMinimumRule()
        
        tp_result = tp_rule.validate(data_c3)
        kktp_result = kktp_rule.validate(data_c3)
        
        assert tp_result.passed is True
        assert kktp_result.passed is True
    
    def test_full_validation_pipeline_success(self, rule_engine, valid_tp_data):
        """Complete validation pipeline should succeed with valid data."""
        all_pass, results = rule_engine.validate(valid_tp_data)
        
        assert all_pass is True
        assert all(r.passed is True for r in results)
        assert all(r.severity == RuleSeverity.ERROR for r in results)  # All are ERROR severity
    
    def test_full_validation_pipeline_failure(self, rule_engine):
        """Complete validation pipeline should fail with invalid data."""
        invalid_data = {
            'cognitive_level': 'C1',  # Invalid
            'grade': 'MTS_7',  # Valid
            'phase': 'E',  # Invalid
            'education_system': 'KEMENAG',
            'institution_type': 'MTs',
            'subject': 'INVALID_SUBJECT',  # Invalid
            'source_document_id': None,  # Invalid
            'source_fragment_id': None
        }
        
        all_pass, results = rule_engine.validate(invalid_data)
        
        assert all_pass is False
        failed = [r for r in results if not r.passed]
        assert len(failed) >= 3  # At least 3 rules should fail
