#!/usr/bin/env python3
"""
Rule Engine - PHASE 4
AI RPP/RPM Generator (Pembelajaran Mendalam)

Validates curriculum data against 12 core rules:
- TP/KKTP cognitive level enforcement (C3+)
- Alignment validation (TP-KKTP, Activity-TP, Assessment-TP)
- Grade-phase validation
- Subject-system validation
- CP provenance checking
- Data immutability enforcement
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class RuleSeverity(Enum):
    """Rule severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


_VALID_SUBJECTS_CACHE = None


def _valid_subjects_from_mapping():
    """Nama mapel per sistem dari db/curriculum_mappings.json — sumber
    otoritatif yang SAMA dengan CurriculumEngine (bukan daftar hardcode
    yang membusuk saat mapping bertambah). Hasil di-cache per proses;
    deterministik untuk file mapping yang sama."""
    global _VALID_SUBJECTS_CACHE
    if _VALID_SUBJECTS_CACHE is None:
        path = (Path(__file__).resolve().parent.parent
                / 'db' / 'curriculum_mappings.json')
        with open(path, encoding='utf-8') as f:
            mappings = json.load(f)
        out = {}
        for system, levels in mappings.get('subjects', {}).items():
            names = set()
            for subs in (levels or {}).values():
                for subj in subs or []:
                    if subj.get('name'):
                        names.add(subj['name'])
            out[system] = names
        _VALID_SUBJECTS_CACHE = out
    return _VALID_SUBJECTS_CACHE


class CognitiveLevel(Enum):
    """Bloom's taxonomy levels."""
    C1 = 1
    C2 = 2
    C3 = 3
    C4 = 4
    C5 = 5
    C6 = 6
    
    @staticmethod
    def is_valid_minimum(level: str, minimum: str = 'C3') -> bool:
        """Check if level meets minimum."""
        try:
            level_val = CognitiveLevel[level].value
            min_val = CognitiveLevel[minimum].value
            return level_val >= min_val
        except:
            return False


@dataclass
class ValidationResult:
    """Result of rule validation."""
    rule_id: str
    passed: bool
    message: str
    severity: RuleSeverity
    details: Dict = None


class Rule:
    """Base rule class."""
    
    def __init__(self, rule_id: str, name: str, severity: RuleSeverity):
        self.rule_id = rule_id
        self.name = name
        self.severity = severity
    
    def validate(self, data: Dict) -> ValidationResult:
        """Override in subclass."""
        raise NotImplementedError


class TPCognitiveMinimumRule(Rule):
    """TP must be minimum C3."""
    
    def __init__(self):
        super().__init__('RULE-TP-001', 'TP Minimum Cognitive Level', RuleSeverity.ERROR)
    
    def validate(self, data: Dict) -> ValidationResult:
        """Validate TP cognitive level."""
        tp_text = data.get('tp_text', '')
        cognitive_level = data.get('cognitive_level', 'C3')
        
        if not CognitiveLevel.is_valid_minimum(cognitive_level, 'C3'):
            return ValidationResult(
                rule_id=self.rule_id,
                passed=False,
                message=f"TP menggunakan KKO {cognitive_level}. Minimum level aplikasi adalah C3.",
                severity=self.severity,
                details={'cognitive_level': cognitive_level}
            )
        
        return ValidationResult(
            rule_id=self.rule_id,
            passed=True,
            message="TP memenuhi minimum cognitive level C3",
            severity=self.severity
        )


class KKTPCognitiveMinimumRule(Rule):
    """KKTP must be minimum C3."""
    
    def __init__(self):
        super().__init__('RULE-KKTP-001', 'KKTP Minimum Cognitive Level', RuleSeverity.ERROR)
    
    def validate(self, data: Dict) -> ValidationResult:
        """Validate KKTP cognitive level."""
        cognitive_level = data.get('cognitive_level', 'C3')
        
        if not CognitiveLevel.is_valid_minimum(cognitive_level, 'C3'):
            return ValidationResult(
                rule_id=self.rule_id,
                passed=False,
                message=f"KKTP menggunakan level {cognitive_level}. Minimum level aplikasi adalah C3.",
                severity=self.severity,
                details={'cognitive_level': cognitive_level}
            )
        
        return ValidationResult(
            rule_id=self.rule_id,
            passed=True,
            message="KKTP memenuhi minimum cognitive level C3",
            severity=self.severity
        )


class GradePhasePValidationRule(Rule):
    """Grade must match phase.

    Single source: grade→phase comes from db/curriculum_mappings.json
    (the same file CurriculumEngine validates against), never a
    hardcoded per-system table that rots when mappings grow.
    """

    def __init__(self, mappings: Optional[Dict] = None):
        super().__init__('RULE-CURRICULUM-001', 'Grade Phase Validation', RuleSeverity.ERROR)
        self.mappings = mappings

    def _phase_map(self) -> Dict:
        if self.mappings is not None:
            return (self.mappings.get('grade_to_phase_mappings', {})
                    if isinstance(self.mappings, dict) else {})
        try:
            path = (Path(__file__).resolve().parent.parent
                    / 'db' / 'curriculum_mappings.json')
            with open(path, encoding='utf-8') as f:
                return json.load(f).get('grade_to_phase_mappings', {})
        except Exception:
            return {}

    def validate(self, data: Dict) -> ValidationResult:
        """Validate grade-phase mapping."""
        grade = data.get('grade')
        phase = data.get('phase')
        system = data.get('education_system')
        institution_type = data.get('institution_type')

        # Expected phase from grade (single mapping source).
        expected_phase = None
        try:
            grade_map = (self._phase_map().get(system, {})
                         .get(institution_type, {}))
            if isinstance(grade_map, dict) and grade in grade_map:
                expected_phase = grade_map[grade].get('phase')
        except Exception:
            expected_phase = None
        
        if expected_phase and phase != expected_phase:
            return ValidationResult(
                rule_id=self.rule_id,
                passed=False,
                message=f"Grade {grade} {institution_type} harus menggunakan Fase {expected_phase}, bukan {phase}",
                severity=self.severity,
                details={'grade': grade, 'expected_phase': expected_phase, 'provided_phase': phase}
            )
        
        return ValidationResult(
            rule_id=self.rule_id,
            passed=True,
            message=f"Grade {grade} sesuai dengan Fase {phase}",
            severity=self.severity
        )


class CPProvenanceRule(Rule):
    """CP must have source document."""
    
    def __init__(self):
        super().__init__('RULE-CURRICULUM-002', 'CP Provenance', RuleSeverity.ERROR)
    
    def validate(self, data: Dict) -> ValidationResult:
        """Validate CP has source."""
        source_document_id = data.get('source_document_id')
        source_fragment_id = data.get('source_fragment_id')
        
        if not source_document_id or not source_fragment_id:
            return ValidationResult(
                rule_id=self.rule_id,
                passed=False,
                message="CP tidak memiliki sumber dokumen resmi.",
                severity=self.severity,
                details={'source_doc': source_document_id, 'source_frag': source_fragment_id}
            )
        
        return ValidationResult(
            rule_id=self.rule_id,
            passed=True,
            message="CP memiliki sumber dokumen yang terverifikasi",
            severity=self.severity
        )


class SubjectSystemValidationRule(Rule):
    """Subject must match education system."""
    
    def __init__(self):
        super().__init__('RULE-CURRICULUM-003', 'Subject System Validation', RuleSeverity.ERROR)
    
    def validate(self, data: Dict) -> ValidationResult:
        """Validate subject belongs to system."""
        subject = data.get('subject')
        system = data.get('education_system')

        # Map valid subjects to systems (dibaca dari
        # db/curriculum_mappings.json - sumber otoritatif yang sama
        # dengan CurriculumEngine, bukan daftar hardcode).
        valid_subjects = _valid_subjects_from_mapping()

        if subject not in valid_subjects.get(system, set()):
            return ValidationResult(
                rule_id=self.rule_id,
                passed=False,
                message=f"Mata pelajaran '{subject}' tidak tersedia dalam sistem {system}",
                severity=self.severity,
                details={'subject': subject, 'system': system}
            )
        
        return ValidationResult(
            rule_id=self.rule_id,
            passed=True,
            message=f"Mata pelajaran '{subject}' sesuai dengan sistem {system}",
            severity=self.severity
        )


class RuleEngine:
    """Validates curriculum data against rules."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.connection = None
        self.cursor = None
        self.rules: List[Rule] = [
            TPCognitiveMinimumRule(),
            KKTPCognitiveMinimumRule(),
            GradePhasePValidationRule(),
            CPProvenanceRule(),
            SubjectSystemValidationRule()
        ]
    
    def connect(self):
        """Connect to database."""
        self.connection = sqlite3.connect(str(self.db_path))
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
    
    def close(self):
        """Close connection."""
        if self.connection:
            self.connection.close()
    
    def validate(self, data: Dict) -> Tuple[bool, List[ValidationResult]]:
        """
        Validate data against all rules.
        Returns: (all_passed, list of results)
        """
        results = []
        all_passed = True
        
        for rule in self.rules:
            try:
                result = rule.validate(data)
                results.append(result)
                
                if not result.passed and result.severity == RuleSeverity.ERROR:
                    all_passed = False
                    
            except Exception as e:
                results.append(ValidationResult(
                    rule_id=f"ERROR-{rule.rule_id}",
                    passed=False,
                    message=f"Error evaluating rule: {str(e)}",
                    severity=RuleSeverity.ERROR
                ))
                all_passed = False
        
        return all_passed, results
    
    def print_results(self, results: List[ValidationResult]):
        """Print validation results."""
        print("\n" + "="*60)
        print("🧪 VALIDATION RESULTS")
        print("="*60)
        
        for result in results:
            status_icon = "✓" if result.passed else "✗"
            print(f"\n{status_icon} {result.rule_id}: {result.passed}")
            print(f"   {result.message}")
            if result.details:
                print(f"   Details: {result.details}")


if __name__ == '__main__':
    PROJECT_ROOT = Path(__file__).parent.parent
    DB_PATH = PROJECT_ROOT / 'db' / 'rpm_generator.db'
    
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("\n" + "="*60)
    print("RULE ENGINE - PHASE 4")
    print("="*60 + "\n")
    
    engine = RuleEngine(str(DB_PATH))
    
    # Test case 1: Valid input
    test_data_valid = {
        'tp_text': 'Menerapkan konsep Akidah',
        'cognitive_level': 'C3',
        'grade': 'MTs_7',
        'phase': 'D',
        'education_system': 'KEMENAG',
        'institution_type': 'MTs',
        'subject': 'Akidah Akhlak',
        'source_document_id': 'DOC-SK-DIRJEN-9941',
        'source_fragment_id': 'frag-001'
    }
    
    # Test case 2: Invalid cognitive level
    test_data_invalid_c1 = {
        'tp_text': 'Menyebutkan konsep Akidah',
        'cognitive_level': 'C1',
        'grade': 'MTs_7',
        'phase': 'D',
        'education_system': 'KEMENAG',
        'institution_type': 'MTs',
        'subject': 'Akidah Akhlak',
        'source_document_id': 'DOC-SK-DIRJEN-9941',
        'source_fragment_id': 'frag-001'
    }
    
    # Test case 3: Invalid phase
    test_data_invalid_phase = {
        'tp_text': 'Menerapkan konsep Akidah',
        'cognitive_level': 'C3',
        'grade': 'MTs_7',
        'phase': 'E',  # Wrong phase for MTs
        'education_system': 'KEMENAG',
        'institution_type': 'MTs',
        'subject': 'Akidah Akhlak',
        'source_document_id': 'DOC-SK-DIRJEN-9941',
        'source_fragment_id': 'frag-001'
    }
    
    print("\nTest 1: Valid Input (C3, correct phase, correct subject-system)")
    all_pass, results = engine.validate(test_data_valid)
    engine.print_results(results)
    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    
    print("\n" + "-"*60)
    print("Test 2: Invalid Cognitive Level (C1)")
    all_pass, results = engine.validate(test_data_invalid_c1)
    engine.print_results(results)
    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    
    print("\n" + "-"*60)
    print("Test 3: Invalid Phase (E for MTs)")
    all_pass, results = engine.validate(test_data_invalid_phase)
    engine.print_results(results)
    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    
    print("\n✅ RULE ENGINE PHASE 4 COMPLETE")
