#!/usr/bin/env python3
"""
Test Configuration and Shared Fixtures
pytest configuration and reusable fixtures for all tests
"""

import pytest
import sqlite3


def pytest_collection_modifyitems(config, items):
    """Tes bertanda `slow` (rebuild penuh dari PDF) hanya jalan bila diminta
    lewat -m slow / -m 'slow or ...'."""
    if config.getoption('-m') and 'slow' in config.getoption('-m'):
        return
    skip = pytest.mark.skip(reason='rebuild penuh; jalankan: pytest -m slow')
    for item in items:
        if 'slow' in item.keywords:
            item.add_marker(skip)
import json
import shutil
import sys
import os
import io
from pathlib import Path
from tempfile import TemporaryDirectory


# ============================================================================
# PATHS
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
DB_DIR = PROJECT_ROOT / "db"
ORIGINAL_DB = DB_DIR / "rpm_generator.db"


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def temp_db_dir():
    """Create temporary directory for test databases.

    ignore_cleanup_errors: on Windows, shortly-lived sqlite files can be
    briefly held by the OS indexer/AV at teardown, which would otherwise
    fail otherwise-green tests. This is disposable test scaffolding only —
    product assertions are unaffected."""
    import sys
    if sys.platform == 'win32':
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            yield Path(tmpdir)
    else:
        with TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)


@pytest.fixture(scope="function")
def test_db(temp_db_dir):
    """Create a copy of the production database for testing."""
    if not ORIGINAL_DB.exists():
        pytest.skip("Database not found")
    
    test_db_path = temp_db_dir / "test_rpm_generator.db"
    shutil.copy2(ORIGINAL_DB, test_db_path)
    
    # Also copy curriculum_mappings.json to temp dir so CurriculumEngine can find it
    mappings_src = DB_DIR / "curriculum_mappings.json"
    if mappings_src.exists():
        mappings_dest = temp_db_dir / "curriculum_mappings.json"
        shutil.copy2(mappings_src, mappings_dest)
    
    return test_db_path


@pytest.fixture(scope="function")
def db_connection(test_db):
    """Provide a database connection for testing."""
    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    yield conn
    
    conn.close()


# ============================================================================
# CURRICULUM MAPPINGS FIXTURE
# ============================================================================

@pytest.fixture(scope="session")
def curriculum_mappings():
    """Load curriculum mappings from JSON."""
    mappings_path = DB_DIR / "curriculum_mappings.json"
    
    if not mappings_path.exists():
        pytest.skip("curriculum_mappings.json not found")
    
    with open(mappings_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================================
# ENGINE FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def curriculum_engine(test_db):
    """Create a CurriculumEngine instance for testing."""
    sys_path_backup = __import__('sys').path.copy()
    __import__('sys').path.insert(0, str(SRC_DIR))
    
    try:
        from curriculum_engine import CurriculumEngine
        engine = CurriculumEngine(str(test_db))
        engine.connect()
        
        yield engine
        
        engine.close()
    finally:
        __import__('sys').path = sys_path_backup


@pytest.fixture(scope="function")
def rule_engine(test_db):
    """Create a RuleEngine instance for testing."""
    sys_path_backup = __import__('sys').path.copy()
    __import__('sys').path.insert(0, str(SRC_DIR))
    
    try:
        from rule_engine import RuleEngine
        engine = RuleEngine(str(test_db))
        
        yield engine
    finally:
        __import__('sys').path = sys_path_backup


# ============================================================================
# CONTEXT FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def sample_cp_entry():
    """Create a sample CP entry for testing."""
    sys_path_backup = __import__('sys').path.copy()
    __import__('sys').path.insert(0, str(SRC_DIR))
    
    try:
        from curriculum_context import CPEntry
        return CPEntry(
            id="CP-TEST-001",
            text="Test CP text - Siswa dapat memahami konsep pembelajaran",
            source_document_id="DOC-TEST-001",
            source_fragment_id="FRAG-TEST-001",
            source_page=42,
            phase="D",
            element="Akhlak"
        )
    finally:
        __import__('sys').path = sys_path_backup


@pytest.fixture(scope="function")
def sample_tp_entries():
    """Create sample TP entries for testing."""
    sys_path_backup = __import__('sys').path.copy()
    __import__('sys').path.insert(0, str(SRC_DIR))
    
    try:
        from curriculum_context import TPEntry
        return [
            TPEntry(
                id="TP-TEST-001",
                text="Menerapkan konsep pembelajaran dalam kehidupan",
                cognitive_level="C3",
                source_type="ai_generated"
            ),
            TPEntry(
                id="TP-TEST-002",
                text="Menganalisis dimensi pembelajaran dalam konteks modern",
                cognitive_level="C4",
                source_type="ai_generated"
            )
        ]
    finally:
        __import__('sys').path = sys_path_backup


@pytest.fixture(scope="function")
def sample_atp_entry():
    """Create a sample ATP entry for testing."""
    sys_path_backup = __import__('sys').path.copy()
    __import__('sys').path.insert(0, str(SRC_DIR))
    
    try:
        from curriculum_context import ATPEntry
        return ATPEntry(
            id="ATP-TEST-001",
            tp_ids=["TP-TEST-001", "TP-TEST-002"]
        )
    finally:
        __import__('sys').path = sys_path_backup


# ============================================================================
# FLASK APP FIXTURE
# ============================================================================

@pytest.fixture(scope="function")
def flask_app():
    """Create a Flask app for testing."""
    # Temporarily restore original sys.stdout to avoid pytest capture issues
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    sys_path_backup = __import__('sys').path.copy()
    __import__('sys').path.insert(0, str(SRC_DIR))
    
    try:
        # Suppress stdout/stderr before importing app which tries to wrap stdout
        devnull = open(os.devnull, 'w')
        sys.stdout = devnull
        sys.stderr = devnull
        
        # Import app and set to testing mode
        from app import app as flask_app_instance
        
        # Restore stdout/stderr
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        devnull.close()
        
        flask_app_instance.config['TESTING'] = True
        
        yield flask_app_instance
    finally:
        # Ensure restoration
        if sys.stdout != original_stdout:
            sys.stdout = original_stdout
        if sys.stderr != original_stderr:
            sys.stderr = original_stderr
        
        __import__('sys').path = sys_path_backup


@pytest.fixture(scope="function")
def flask_client(flask_app):
    """Create a Flask test client."""
    return flask_app.test_client()


# ============================================================================
# TEST DATA FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def valid_tp_data():
    """Valid TP data that should pass validation."""
    return {
        'tp_text': 'Menerapkan konsep Akidah dalam kehidupan',
        'cognitive_level': 'C3',
        'grade': 'MTs_7',
        'phase': 'D',
        'education_system': 'KEMENAG',
        'institution_type': 'MTs',
        'subject': 'Akidah Akhlak',
        'source_document_id': 'DOC-SK-DIRJEN-9941',
        'source_fragment_id': 'frag-001'
    }


@pytest.fixture(scope="function")
def invalid_tp_c1_data():
    """Invalid TP data with C1 cognitive level."""
    return {
        'tp_text': 'Menyebutkan konsep Akidah',
        'cognitive_level': 'C1',  # Too low
        'grade': 'MTs_7',
        'phase': 'D',
        'education_system': 'KEMENAG',
        'institution_type': 'MTs',
        'subject': 'Akidah Akhlak',
        'source_document_id': 'DOC-SK-DIRJEN-9941',
        'source_fragment_id': 'frag-001'
    }


@pytest.fixture(scope="function")
def invalid_tp_c2_data():
    """Invalid TP data with C2 cognitive level."""
    return {
        'tp_text': 'Memahami konsep Akidah',
        'cognitive_level': 'C2',  # Too low
        'grade': 'MTs_7',
        'phase': 'D',
        'education_system': 'KEMENAG',
        'institution_type': 'MTs',
        'subject': 'Akidah Akhlak',
        'source_document_id': 'DOC-SK-DIRJEN-9941',
        'source_fragment_id': 'frag-001'
    }


@pytest.fixture(scope="function")
def invalid_phase_data():
    """Invalid data with mismatched grade-phase."""
    return {
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


@pytest.fixture(scope="function")
def invalid_subject_system_data():
    """Invalid data with subject not in system."""
    return {
        'tp_text': 'Menerapkan konsep pembelajaran',
        'cognitive_level': 'C3',
        'grade': 'MTs_7',
        'phase': 'D',
        'education_system': 'KEMENAG',
        'institution_type': 'MTs',
        'subject': 'Pendidikan Agama dan Budi Pekerti',  # Wrong for KEMENAG/MTs
        'source_document_id': 'DOC-SK-DIRJEN-9941',
        'source_fragment_id': 'frag-001'
    }


@pytest.fixture(scope="function")
def missing_provenance_data():
    """Data missing CP provenance."""
    return {
        'tp_text': 'Menerapkan konsep Akidah',
        'cognitive_level': 'C3',
        'grade': 'MTs_7',
        'phase': 'D',
        'education_system': 'KEMENAG',
        'institution_type': 'MTs',
        'subject': 'Akidah Akhlak',
        'source_document_id': None,  # Missing source
        'source_fragment_id': None
    }


# ============================================================================
# MARKERS
# ============================================================================

def pytest_configure(config):
    """Register custom markers and setup module imports."""
    config.addinivalue_line(
        "markers", "curriculum: tests for curriculum engine"
    )
    config.addinivalue_line(
        "markers", "rules: tests for rule engine"
    )
    config.addinivalue_line(
        "markers", "context: tests for curriculum context"
    )
    config.addinivalue_line(
        "markers", "validators: tests for validation logic"
    )
    config.addinivalue_line(
        "markers", "database: tests for database operations"
    )
    config.addinivalue_line(
        "markers", "antislop: tests for anti-slop protection"
    )
    config.addinivalue_line(
        "markers", "api: tests for Flask API"
    )
    config.addinivalue_line(
        "markers", "integration: integration tests"
    )
    config.addinivalue_line(
        "markers", "phase_c: Phase C module generation pipeline tests"
    )
    config.addinivalue_line(
        "markers", "slow: rebuild penuh dari PDF, jalan hanya bila diminta eksplisit"
    )

    # Import all test modules into globals
    sys_path_backup = sys.path.copy()
    sys.path.insert(0, str(SRC_DIR))

    try:
        import builtins
        
        # Imports from the RPM pipeline (validators live in
        # module_generation_pipeline).
        from module_generation_pipeline import (
            AntiSlopProcessor as AntiSlop,
            PedagogicalValidator,
            FinalValidator,
            Module,
            ActivityEntry,
        )
        from curriculum_context import (
            CPEntry, TPEntry, ATPEntry, CurriculumContext,
            CurriculumContextGenerator, ContextValidator
        )
        from curriculum_engine import CurriculumEngine, GradePhaseValidator
        import module_generation_pipeline  # noqa: F401  # populate sys.modules
        from rule_engine import (
            RuleEngine, RuleSeverity, CognitiveLevel, ValidationResult,
            TPCognitiveMinimumRule, KKTPCognitiveMinimumRule,
            GradePhasePValidationRule, CPProvenanceRule, SubjectSystemValidationRule
        )
        
        # Store in builtins so tests can access them
        builtins.AntiSlop = AntiSlop
        builtins.PedagogicalValidator = PedagogicalValidator
        builtins.FinalValidator = FinalValidator
        builtins.Module = Module
        builtins.ActivityEntry = ActivityEntry
        builtins.CPEntry = CPEntry
        builtins.TPEntry = TPEntry
        builtins.ATPEntry = ATPEntry
        builtins.CurriculumContext = CurriculumContext
        builtins.CurriculumContextGenerator = CurriculumContextGenerator
        builtins.ContextValidator = ContextValidator
        builtins.CurriculumEngine = CurriculumEngine
        builtins.GradePhaseValidator = GradePhaseValidator
        builtins.RuleEngine = RuleEngine
        builtins.RuleSeverity = RuleSeverity
        builtins.CognitiveLevel = CognitiveLevel
        builtins.ValidationResult = ValidationResult
        builtins.TPCognitiveMinimumRule = TPCognitiveMinimumRule
        builtins.KKTPCognitiveMinimumRule = KKTPCognitiveMinimumRule
        builtins.GradePhasePValidationRule = GradePhasePValidationRule
        builtins.CPProvenanceRule = CPProvenanceRule
        builtins.SubjectSystemValidationRule = SubjectSystemValidationRule
    finally:
        sys.path = sys_path_backup
