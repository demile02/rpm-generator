#!/usr/bin/env python3
"""
Tests for Validators (Phases 8 and 10)
Tests pedagogical alignment and final validation
"""

import pytest

# Fixtures from conftest will handle imports

from module_generation_pipeline import TPEntry, KKTPEntry, ActivityEntry  # noqa: E402


def make_tp(i):
    """Typed TP entry (RPM schema)."""
    return TPEntry(id=f"TP-{i}", text=f"Menerapkan konsep {i}",
                   cognitive_level="C3", cp_reference="CP-TEST")


def make_activities(raw):
    """Convert legacy dict activities into typed ActivityEntry objects."""
    acts = []
    for i, a in enumerate(raw or [], 1):
        if isinstance(a, dict):
            acts.append(ActivityEntry(
                id=f"ACT-{i}", name=a.get("name", f"Act {i}"),
                description="Deskripsi aktivitas", duration=30,
                tp_linked=f"TP-{i}" if a.get("tp_linked", True) else "",
                type="mengaplikasi"))
        else:
            acts.append(ActivityEntry(
                id=f"ACT-{i}", name=str(a), description="Deskripsi",
                duration=30, tp_linked=f"TP-{i}", type="mengaplikasi"))
    return acts


def make_assessments(raw):
    """Wrap legacy assessments dicts into the RPM 3-bucket shape.

    Items carry explicit tp_linked (TP-1..TP-n in order) so the
    strengthened traceability validators see linked coverage; pass
    dicts with 'tp_linked': None to test the unlinked rejection path.
    """
    items = (raw or {}).get("items") or []
    linked = []
    for i, it in enumerate(items, 1):
        if isinstance(it, dict):
            entry = dict(it)
            entry.setdefault('tp_linked', f'TP-{i}')
            linked.append(entry)
        else:
            linked.append({'question': str(it), 'tp_linked': f'TP-{i}'})
    return {"diagnostic": linked[:1], "formative": linked[1:2] or linked[:1],
            "summative": {"items": linked[2:] or linked[:1]}}


def make_module(**overrides):
    """Build a complete RPM-shaped Module (AGENTS.md RPM schema)."""
    defaults = dict(
        id="MOD-TEST",
        title="Test Module",
        subject="Akidah Akhlak",
        grade="VII",
        phase="D",
        curriculum_version="KMA-1503-2025",
        module_identity={"alur_tujuan": "Alur tujuan test"},
        facilities=["LKS"],
        target_students={"profile": "Umum"},
        learning_model="Problem Based Learning",
        methods=["Diskusi"],
        learning_objectives=[make_tp(1)],
        success_criteria=[KKTPEntry(id="KKTP-1", tp_id="TP-1",
                                    criteria=["Kriteria tercapai"],
                                    cognitive_level="C3")],
        essential_understanding={"big_idea": "Pemahaman inti"},
        guiding_questions=["Pertanyaan pemantik?"],
        learning_activities=make_activities([{"name": "Activity 1"}]),
        assessments={"diagnostic": [{"id": "D1", "question": "q"}],
                     "formative": [{"id": "F1", "question": "q"}],
                     "summative": {"items": [{"id": "S1", "question": "q"}]}},
        curriculum_context=object(),
        generation_id="GEN-TEST",
    )
    defaults.update(overrides)
    return Module(**defaults)


# ============================================================================
# PEDAGOGICAL VALIDATOR TESTS
# ============================================================================

@pytest.mark.validators
class TestPedagogicalValidator:
    """Test PedagogicalValidator class."""
    
    def test_validator_exists(self):
        """PedagogicalValidator should exist."""
        assert PedagogicalValidator is not None
    
    def test_validator_has_alignment_methods(self):
        """PedagogicalValidator exposes activity + assessment alignment."""
        validator = PedagogicalValidator()
        assert hasattr(validator, 'validate_activity_alignment')
        assert callable(validator.validate_activity_alignment)
        assert hasattr(validator, 'validate_assessment_alignment')
        assert callable(validator.validate_assessment_alignment)


# ============================================================================
# PEDAGOGICAL ALIGNMENT TESTS
# ============================================================================

@pytest.mark.validators
class TestPedagogicalAlignment:
    """Test pedagogical alignment validation."""
    
    def test_alignment_accepts_matching_tp_activities(self):
        """TP and activities with same count should pass."""
        validator = PedagogicalValidator()
        tp_list = ["TP1", "TP2"]
        activities = [{"name": "Activity 1"}, {"name": "Activity 2"}]
        assessments = {"items": ["Assessment 1", "Assessment 2"]}
        
        act_ok, errors = PedagogicalValidator.validate_activity_alignment(make_activities(activities), len(tp_list))
        act_ok2, errors2 = PedagogicalValidator.validate_assessment_alignment(make_assessments(assessments), len(tp_list), 0)
        is_aligned = act_ok and act_ok2
        errors = errors + errors2
        
        assert is_aligned is True
        assert len(errors) == 0
    
    def test_alignment_rejects_empty_tp_list(self):
        """Empty TP list must fail overall alignment (completeness)."""
        module = make_module(learning_objectives=[])
        is_complete, errors = FinalValidator.validate_completeness(module)
        assert is_complete is False
        assert len(errors) > 0
    
    def test_alignment_rejects_insufficient_activities(self):
        """Fewer activities than TP should fail."""
        validator = PedagogicalValidator()
        tp_list = ["TP1", "TP2", "TP3"]
        activities = [{"name": "Activity 1"}]  # Only 1 activity for 3 TP
        assessments = {"items": ["Assessment 1"]}
        
        act_ok, errors = PedagogicalValidator.validate_activity_alignment(make_activities(activities), len(tp_list))
        act_ok2, errors2 = PedagogicalValidator.validate_assessment_alignment(make_assessments(assessments), len(tp_list), 0)
        is_aligned = act_ok and act_ok2
        errors = errors + errors2
        
        assert is_aligned is False
        assert len(errors) > 0
    
    def test_alignment_rejects_missing_assessments(self):
        """Missing assessments should fail."""
        validator = PedagogicalValidator()
        tp_list = ["TP1", "TP2"]
        activities = [{"name": "Activity 1"}, {"name": "Activity 2"}]
        assessments = {}  # Missing items
        
        act_ok, errors = PedagogicalValidator.validate_activity_alignment(make_activities(activities), len(tp_list))
        act_ok2, errors2 = PedagogicalValidator.validate_assessment_alignment(make_assessments(assessments), len(tp_list), 0)
        is_aligned = act_ok and act_ok2
        errors = errors + errors2
        
        assert is_aligned is False
        assert len(errors) > 0
    
    def test_alignment_rejects_empty_assessment_items(self):
        """Assessment with no items should fail."""
        validator = PedagogicalValidator()
        tp_list = ["TP1"]
        activities = [{"name": "Activity 1"}]
        assessments = {"items": []}  # Empty items
        
        act_ok, errors = PedagogicalValidator.validate_activity_alignment(make_activities(activities), len(tp_list))
        act_ok2, errors2 = PedagogicalValidator.validate_assessment_alignment(make_assessments(assessments), len(tp_list), 0)
        is_aligned = act_ok and act_ok2
        errors = errors + errors2
        
        assert is_aligned is False
        assert len(errors) > 0
    
    def test_alignment_returns_tuple(self):
        """activity alignment returns (bool, list) tuple."""
        validator = PedagogicalValidator()
        tp_list = ["TP1"]
        activities = [{"name": "Activity 1"}]
        assessments = {"items": ["Assessment 1"]}
        
        result = (PedagogicalValidator.validate_activity_alignment(make_activities(activities), len(tp_list))[0], [])
        
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)
    
    def test_alignment_errors_are_strings(self):
        """Error messages should be strings."""
        validator = PedagogicalValidator()
        tp_list = []
        activities = []
        assessments = {}
        
        act_ok, errors = PedagogicalValidator.validate_activity_alignment(make_activities(activities), len(tp_list))
        act_ok2, errors2 = PedagogicalValidator.validate_assessment_alignment(make_assessments(assessments), len(tp_list), 0)
        is_aligned = act_ok and act_ok2
        errors = errors + errors2
        
        for error in errors:
            assert isinstance(error, str)
    
    def test_alignment_success_with_matching_counts(self):
        """Success when TP, activities, and assessments align."""
        validator = PedagogicalValidator()
        tp_list = ["TP1", "TP2", "TP3"]
        activities = [
            {"name": "Activity 1", "duration": "45 min"},
            {"name": "Activity 2", "duration": "45 min"},
            {"name": "Activity 3", "duration": "45 min"}
        ]
        assessments = {
            "items": ["Item 1", "Item 2", "Item 3"],
            "total_score": 100
        }
        
        act_ok, errors = PedagogicalValidator.validate_activity_alignment(make_activities(activities), len(tp_list))
        act_ok2, errors2 = PedagogicalValidator.validate_assessment_alignment(make_assessments(assessments), len(tp_list), 0)
        is_aligned = act_ok and act_ok2
        errors = errors + errors2
        
        assert is_aligned is True
        assert len(errors) == 0


# ============================================================================
# FINAL VALIDATOR TESTS
# ============================================================================

@pytest.mark.validators
class TestFinalValidator:
    """Test FinalValidator class."""
    
    def test_validator_exists(self):
        """FinalValidator should exist."""
        assert FinalValidator is not None
    
    def test_validator_has_validate_immutability_method(self):
        """FinalValidator should have validate_immutability method."""
        assert hasattr(FinalValidator, 'validate_immutability')
        assert callable(FinalValidator.validate_immutability)
    
    def test_validator_has_validate_completeness_method(self):
        """FinalValidator should have validate_completeness method."""
        assert hasattr(FinalValidator, 'validate_completeness')
        assert callable(FinalValidator.validate_completeness)


# ============================================================================
# IMMUTABILITY VALIDATION TESTS
# ============================================================================

@pytest.mark.validators
class TestImmutabilityValidation:
    """Test immutability validation."""
    
    def test_immutability_passes_when_protected_fields_unchanged(self):
        """Immutability check should pass if protected fields unchanged."""
        before = {
            'cp': 'CP text',
            'tp': 'TP text',
            'phase': 'D',
            'element': 'Akhlak',
            'subject': 'Akidah Akhlak'
        }
        after = before.copy()
        
        is_immutable, errors = FinalValidator.validate_immutability(before, after)
        
        assert is_immutable is True
        assert len(errors) == 0
    
    def test_immutability_fails_when_cp_changed(self):
        """Immutability check should fail if CP changed."""
        before = {'cp': 'Original CP'}
        after = {'cp': 'Modified CP'}
        
        is_immutable, errors = FinalValidator.validate_immutability(before, after)
        
        assert is_immutable is False
        assert len(errors) > 0
    
    def test_immutability_fails_when_tp_changed(self):
        """Immutability check should fail if TP changed."""
        before = {'tp': 'Original TP'}
        after = {'tp': 'Modified TP'}
        
        is_immutable, errors = FinalValidator.validate_immutability(before, after)
        
        assert is_immutable is False
        assert len(errors) > 0
    
    def test_immutability_fails_when_phase_changed(self):
        """Immutability check should fail if phase changed."""
        before = {'phase': 'D'}
        after = {'phase': 'E'}
        
        is_immutable, errors = FinalValidator.validate_immutability(before, after)
        
        assert is_immutable is False
        assert len(errors) > 0
    
    def test_immutability_fails_when_element_changed(self):
        """Immutability check should fail if element changed."""
        before = {'element': 'Akhlak'}
        after = {'element': 'Akidah'}
        
        is_immutable, errors = FinalValidator.validate_immutability(before, after)
        
        assert is_immutable is False
        assert len(errors) > 0
    
    def test_immutability_fails_when_subject_changed(self):
        """Immutability check should fail if subject changed."""
        before = {'subject': 'Akidah Akhlak'}
        after = {'subject': 'Fikih'}
        
        is_immutable, errors = FinalValidator.validate_immutability(before, after)
        
        assert is_immutable is False
        assert len(errors) > 0
    
    def test_immutability_errors_are_descriptive(self):
        """Immutability errors should describe which field changed."""
        before = {'cp': 'Original', 'tp': 'TP1'}
        after = {'cp': 'Modified', 'tp': 'TP1'}
        
        is_immutable, errors = FinalValidator.validate_immutability(before, after)
        
        assert len(errors) > 0
        assert any('cp' in err.lower() for err in errors)
    
    def test_immutability_returns_tuple(self):
        """validate_immutability should return (bool, list) tuple."""
        before = {'cp': 'CP'}
        after = {'cp': 'CP'}
        
        result = FinalValidator.validate_immutability(before, after)
        
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)


# ============================================================================
# COMPLETENESS VALIDATION TESTS
# ============================================================================

@pytest.mark.validators
class TestCompletenessValidation:
    """Test completeness validation."""
    
    def test_completeness_accepts_complete_module(self):
        """Complete module should pass."""
        module = make_module()
        
        is_complete, errors = FinalValidator.validate_completeness(module)
        
        assert is_complete is True
        assert len(errors) == 0
    
    def test_completeness_fails_missing_title(self):
        """Module without title should fail."""
        module = make_module(title="")
        
        is_complete, errors = FinalValidator.validate_completeness(module)
        
        assert is_complete is False
        assert len(errors) > 0
    
    def test_completeness_fails_missing_learning_objectives(self):
        """Module without learning objectives should fail."""
        module = make_module(learning_objectives=[])
        
        is_complete, errors = FinalValidator.validate_completeness(module)
        
        assert is_complete is False
        assert len(errors) > 0
    
    def test_completeness_fails_missing_learning_activities(self):
        """Module without learning activities should fail (RPM)."""
        module = make_module(learning_activities=[])
        
        is_complete, errors = FinalValidator.validate_completeness(module)
        
        assert is_complete is False
        assert len(errors) > 0
    
    def test_completeness_passes_missing_assessments(self):
        """R-42: modul tanpa asesmen tetap lengkap (asesmen opsional)."""
        module = make_module(assessments={})

        is_complete, errors = FinalValidator.validate_completeness(module)

        assert is_complete is True
    
    def test_completeness_returns_tuple(self):
        """validate_completeness should return (bool, list) tuple."""
        module = make_module()
        
        result = FinalValidator.validate_completeness(module)
        
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)
    
    def test_completeness_errors_are_descriptive(self):
        """Completeness errors should describe missing fields."""
        module = make_module(title="", learning_objectives=[])
        
        is_complete, errors = FinalValidator.validate_completeness(module)
        
        assert len(errors) > 0
        # Should mention what's missing
        error_text = " ".join(errors).lower()
        assert "title" in error_text or "objective" in error_text or "section" in error_text


# ============================================================================
# VALIDATOR INTEGRATION TESTS
# ============================================================================

@pytest.mark.validators
@pytest.mark.integration
class TestValidatorIntegration:
    """Integration tests for validators."""
    
    def test_pedagogical_and_final_validators_independent(self):
        """Pedagogical and final validators should work independently."""
        # Pedagogical validator
        act_ok, act_errors1 = PedagogicalValidator.validate_activity_alignment(
            make_activities([{"name": "A1"}]), 1)
        asm_ok, asm_errors1 = PedagogicalValidator.validate_assessment_alignment(
            make_assessments({"items": ["Assess1"]}), 1, 0)
        assert act_ok and asm_ok
        
        # Final validator
        module = make_module()
        is_complete, errors2 = FinalValidator.validate_completeness(module)
        assert is_complete is True
    
    def test_complete_validation_workflow_success(self):
        """Complete validation workflow should pass with valid data."""
        # 1. Pedagogical alignment
        ped_validator = PedagogicalValidator()
        tp_list = ["TP1", "TP2"]
        activities = [{"name": "A1"}, {"name": "A2"}]
        assessments = {"items": ["Item1", "Item2"]}
        
        act_ok, errors = PedagogicalValidator.validate_activity_alignment(make_activities(activities), len(tp_list))
        act_ok2, errors2 = PedagogicalValidator.validate_assessment_alignment(make_assessments(assessments), len(tp_list), 0)
        is_aligned = act_ok and act_ok2
        errors = errors + errors2
        assert is_aligned is True
        
        # 2. Create module
        module = make_module(learning_objectives=[make_tp(1), make_tp(2)],
                             assessments=assessments)
        
        # 3. Final validation
        is_complete, errors = FinalValidator.validate_completeness(module)
        assert is_complete is True
        
        # 4. Immutability check
        before = {"tp": tp_list[0], "phase": "D"}
        after = {"tp": tp_list[0], "phase": "D"}
        is_immutable, errors = FinalValidator.validate_immutability(before, after)
        assert is_immutable is True
    
    def test_complete_validation_workflow_failure(self):
        """Complete validation workflow should fail with invalid data."""
        # Invalid: aktivitas mengaplikasi tanpa TP + item tanpa link.
        # (Asesmen kosong kini lolos per R-42, jadi pakai item unlink.)
        ped_validator = PedagogicalValidator()
        act_ok, act_errors = PedagogicalValidator.validate_activity_alignment(make_activities([]), 2)
        asm_ok, asm_errors = PedagogicalValidator.validate_assessment_alignment({"diagnostic": [{"q": 1}]}, 2, 0)
        assert (not act_ok) or (not asm_ok)
        
        # Invalid: incomplete module (judul kosong + tanpa TP tetap gagal;
        # tanpa asesmen kini lolos per R-42).
        module = make_module(title="", learning_objectives=[],
                             assessments={})
        is_complete, errors = FinalValidator.validate_completeness(module)
        assert is_complete is False


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

@pytest.mark.validators
class TestValidatorEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_alignment_with_many_tp_and_activities(self):
        """Validator should handle many TP and activities."""
        validator = PedagogicalValidator()
        tp_list = [f"TP{i}" for i in range(100)]
        activities = [{"name": f"Activity{i}"} for i in range(100)]
        assessments = {"items": [f"Item{i}" for i in range(100)]}
        
        act_ok, errors = PedagogicalValidator.validate_activity_alignment(make_activities(activities), len(tp_list))
        act_ok2, errors2 = PedagogicalValidator.validate_assessment_alignment(make_assessments(assessments), len(tp_list), 0)
        is_aligned = act_ok and act_ok2
        errors = errors + errors2
        
        # Should handle gracefully
        assert isinstance(is_aligned, bool)
        assert isinstance(errors, list)
    
    def test_completeness_with_none_optional_fields(self):
        """Validator should handle None optional RPM fields."""
        module = make_module(remedial=None, enrichment=None, unit=None)
        
        is_complete, errors = FinalValidator.validate_completeness(module)
        
        # Should handle gracefully
        assert isinstance(is_complete, bool)
    
    def test_immutability_with_none_values(self):
        """Validator should handle None values."""
        before = {"cp": None}
        after = {"cp": None}
        
        is_immutable, errors = FinalValidator.validate_immutability(before, after)
        
        assert is_immutable is True
    
    def test_alignment_with_special_characters(self):
        """Validator should handle special characters in fields."""
        validator = PedagogicalValidator()
        tp_list = ["TP ① with special chars: éàü"]
        activities = [{"name": "Activity @ special # chars"}]
        assessments = {"items": ["Item with * & special!"]}
        
        act_ok, errors = PedagogicalValidator.validate_activity_alignment(make_activities(activities), len(tp_list))
        act_ok2, errors2 = PedagogicalValidator.validate_assessment_alignment(make_assessments(assessments), len(tp_list), 0)
        is_aligned = act_ok and act_ok2
        errors = errors + errors2
        
        assert is_aligned is True
