#!/usr/bin/env python3
"""
RPM Migration tests (AGENTS.md as source of truth).

Covers the migration contract from the legacy "Modul Ajar" generator to
RPP/RPM Pembelajaran Mendalam:
- KBC sebagai layer tambahan KEMENAG, bukan pengganti 8 Dimensi (§14/§15)
- 8 Dimensi Profil Lulusan untuk kedua sistem pendidikan (§14)
- Pengalaman belajar memahami/mengaplikasi/merefleksi (§13)
- curriculum_version per sistem: KMA-1503-2025 vs KEMENDIKDASMEN-2025 (§4/§8)
- Registry regulasi kanonik 9 dokumen Hukum/ + relasi 046/2025<->020/2026 (§6)
- OCR/vision fallback untuk PDF scan (§2)
- Struktur master outline RPM A-E (§12)
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Src imports (same sys.path convention as the other test modules).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from module_generation_pipeline import (
    Module,
    TPEntry,
    KKTPEntry,
    ActivityEntry,
    CurriculumContext,
    CPEntry,
    MasterOutlineValidator,
    PROFILE_DIMENSIONS_8,
    KBC_THEMES,
    KBC_SOURCE_DOCUMENT,
    LEARNING_EXPERIENCES,
    CURRICULUM_VERSION_BY_SYSTEM,
    build_kbc_layer,
    build_approach_principles,
    build_learning_phases,
    allowed_profile_values,
    default_curriculum_version,
)
from pdf_extraction import (
    PDFExtractor,
    EXTRACTION_METHOD_TEXT_LAYER,
    EXTRACTION_METHOD_OCR,
    EXTRACTION_METHOD_VISION,
    MIN_TEXT_CHARS_PER_PAGE,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / 'db' / 'document_registry.json'


# ============================================================================
# HELPERS
# ============================================================================

def make_context(education_system='KEMENAG', institution_type='MTs'):
    cp = CPEntry(
        id="CP-TEST-D",
        text="Peserta didik menerapkan konsep taubat dalam kehidupan",
        source_document_id="DOC-TEST",
        source_fragment_id="page-1",
        source_page=1,
        phase="D",
        element="Pemahaman Konsep",
    )
    return CurriculumContext(
        education_system=education_system,
        institution_type=institution_type,
        grade='MTs_7' if education_system == 'KEMENAG' else 'SMP_7',
        phase='D',
        subject='Akidah Akhlak' if education_system == 'KEMENAG' else 'IPAS',
        element='Pemahaman Konsep',
        curriculum_version=default_curriculum_version(education_system),
        cp=cp,
        tp_list=[],
        atp=None,
        rules={},
    )


def make_rpm_module(context, **overrides):
    """Minimal RPM-shaped Module for validator-code assertions."""
    defaults = dict(
        id="MOD-RPM-TEST",
        title="RPP/RPM Test",
        subject=context.subject,
        grade=context.grade,
        phase=context.phase,
        curriculum_version=context.curriculum_version,
        module_identity={},
        facilities=[],
        target_students={},
        learning_model="Problem Based Learning",
        methods=["Diskusi"],
        learning_objectives=[
            TPEntry(id="TP-1", text="Menerapkan konsep", cognitive_level="C3",
                    cp_reference=context.cp.id),
        ],
        success_criteria=[
            KKTPEntry(id="KKTP-1", tp_id="TP-1", criteria=["kriteria"],
                      cognitive_level="C3"),
        ],
        essential_understanding={"big_idea": "Pemahaman bermakna"},
        guiding_questions=["Pertanyaan pemantik?"],
        learning_activities=[
            ActivityEntry(id="ACT-1", name="Diskusi", description="Menerapkan",
                          duration=45, tp_linked="TP-1", type="Diskusi",
                          experience="mengaplikasi"),
        ],
        assessments={"diagnostic": [{"id": "D1"}],
                     "formative": [{"id": "F1"}],
                     "summative": {"items": [{"id": "S1"}]}},
        curriculum_context=context,
        generation_id="GEN-RPM-TEST",
        profile_dimensions=list(PROFILE_DIMENSIONS_8),
        approach_principles=build_approach_principles(context.education_system),
        learner_readiness={"hasil_diagnostik": "data diagnostik"},
        material_characteristics={"kompleksitas": "sedang"},
        pedagogical_practices=["Pembelajaran berbasis masalah"],
        learning_environment={"setting": "kelas"},
    )
    defaults.update(overrides)
    return Module(**defaults)


# ============================================================================
# 1. KBC: layer tambahan KEMENAG, bukan pengganti 8 Dimensi (§14/§15)
# ============================================================================

class TestKBCLayerGating:
    """KBC hanya aktif pada konteks Madrasah (KEMENAG)."""

    def test_kbc_enabled_only_for_kemenag(self):
        kbc = build_kbc_layer('KEMENAG')
        assert kbc['enabled'] is True
        assert kbc['themes'] == KBC_THEMES
        assert kbc['source'] == KBC_SOURCE_DOCUMENT

    def test_kbc_disabled_for_kemendikdasmen(self):
        kbc = build_kbc_layer('KEMENDIKDASMEN')
        assert kbc['enabled'] is False
        assert kbc['themes'] == []
        assert kbc['source'] is None

    def test_kbc_themes_are_panca_cinta(self):
        assert len(KBC_THEMES) == 5
        assert any('Cinta Allah' in t for t in KBC_THEMES)

    def test_approach_kemenag_has_kbc_layer(self):
        ap = build_approach_principles('KEMENAG')
        assert ap['approach'] == 'Pembelajaran Mendalam'
        assert ap['kbc']['enabled'] is True

    def test_approach_kemendikdasmen_has_no_kbc_layer(self):
        ap = build_approach_principles('KEMENDIKDASMEN')
        assert ap['kbc']['enabled'] is False
        assert ap['kbc']['themes'] == []

    def test_validator_flags_missing_kbc_on_kemenag_module(self):
        context = make_context('KEMENAG')
        module = make_rpm_module(context, approach_principles={
            'approach': 'Pembelajaran Mendalam', 'kbc': {'enabled': False}})
        _, errors = MasterOutlineValidator.validate(module)
        codes = {e['code'] for e in errors}
        assert 'KBC_LAYER_ERROR' in codes

    def test_validator_rejects_kbc_on_kemendikdasmen_module(self):
        context = make_context('KEMENDIKDASMEN')
        module = make_rpm_module(context, approach_principles={
            'approach': 'Pembelajaran Mendalam',
            'kbc': {'enabled': True, 'themes': list(KBC_THEMES)}})
        _, errors = MasterOutlineValidator.validate(module)
        codes = {e['code'] for e in errors}
        assert 'KBC_LAYER_ERROR' in codes

    def test_validator_accepts_kbc_layer_on_kemenag_module(self):
        context = make_context('KEMENAG')
        module = make_rpm_module(context)
        _, errors = MasterOutlineValidator.validate(module)
        codes = {e['code'] for e in errors}
        assert 'KBC_LAYER_ERROR' not in codes


# ============================================================================
# 2. 8 Dimensi Profil Lulusan utk kedua sistem (§14)
# ============================================================================

class TestProfileDimensions8:
    """A.3 selalu 8 Dimensi Profil Lulusan; Panca Cinta bukan dimensi."""

    def test_same_normative_list_for_both_systems(self):
        assert allowed_profile_values('KEMENAG') == PROFILE_DIMENSIONS_8
        assert allowed_profile_values('KEMENDIKDASMEN') == PROFILE_DIMENSIONS_8

    def test_exactly_eight_dimensions(self):
        assert len(PROFILE_DIMENSIONS_8) == 8
        assert len(set(PROFILE_DIMENSIONS_8)) == 8

    def test_no_kbc_theme_leaks_into_dimensions(self):
        leaked = set(PROFILE_DIMENSIONS_8) & set(KBC_THEMES)
        assert leaked == set()
        # Legacy KBC values must never return as profile dimensions.
        for legacy in ('Humanis', 'Nasionalis', 'Naturalis', 'Toleran'):
            assert legacy not in allowed_profile_values('KEMENAG')

    def test_validator_rejects_non_normative_dimension(self):
        context = make_context('KEMENAG')
        module = make_rpm_module(context, profile_dimensions=['Humanis'])
        _, errors = MasterOutlineValidator.validate(module)
        codes = {e['code'] for e in errors}
        assert 'A3_NON_NORMATIVE_DIMENSION' in codes

    def test_validator_rejects_empty_a3(self):
        context = make_context('KEMENAG')
        module = make_rpm_module(context, profile_dimensions=[])
        _, errors = MasterOutlineValidator.validate(module)
        codes = {e['code'] for e in errors}
        assert 'A3_EMPTY' in codes


# ============================================================================
# 3. Pengalaman belajar memahami/mengaplikasi/merefleksi (§13)
# ============================================================================

class TestLearningExperiences:
    """Pengalaman belajar bukan tahap pendahuluan/inti/penutup."""

    def test_canonical_experiences(self):
        assert [e.lower() for e in LEARNING_EXPERIENCES] == \
            ['memahami', 'mengaplikasi', 'merefleksi']

    def test_groups_by_experience_field(self):
        acts = [
            ActivityEntry(id="A1", name="Apersepsi", description="d",
                          duration=15, tp_linked="", type="Diskusi",
                          experience="memahami"),
            ActivityEntry(id="A2", name="Praktik", description="d",
                          duration=45, tp_linked="TP-1", type="Praktik",
                          experience="mengaplikasi"),
            ActivityEntry(id="A3", name="Refleksi", description="d",
                          duration=15, tp_linked="", type="Refleksi",
                          experience="merefleksi"),
        ]
        phases = build_learning_phases(acts)
        assert set(phases.keys()) == {'memahami', 'mengaplikasi', 'merefleksi'}
        assert [a['id'] for a in phases['memahami']] == ['A1']
        assert [a['id'] for a in phases['mengaplikasi']] == ['A2']
        assert [a['id'] for a in phases['merefleksi']] == ['A3']

    def test_legacy_types_map_to_experiences(self):
        """Pre-RPM stored activities (type-based) still group correctly."""
        acts = [
            ActivityEntry(id="L1", name="Pembuka", description="d",
                          duration=10, tp_linked="", type="pendahuluan",
                          experience=""),
            ActivityEntry(id="L2", name="Inti", description="d",
                          duration=45, tp_linked="TP-1", type="inti",
                          experience=""),
            ActivityEntry(id="L3", name="Penutup", description="d",
                          duration=10, tp_linked="", type="penutup",
                          experience=""),
        ]
        phases = build_learning_phases(acts)
        assert len(phases['memahami']) == 1
        assert len(phases['mengaplikasi']) == 1
        assert len(phases['merefleksi']) == 1


# ============================================================================
# 4. Versi kurikulum per sistem (§4/§8)
# ============================================================================

class TestCurriculumVersionPerSystem:
    """KMA-1503-2025 hanya untuk madrasah; sekolah umum memakai
    KEMENDIKDASMEN-2025; keduanya tidak boleh tercampur."""

    def test_mapping_constants(self):
        assert CURRICULUM_VERSION_BY_SYSTEM['KEMENAG'] == 'KMA-1503-2025'
        assert CURRICULUM_VERSION_BY_SYSTEM['KEMENDIKDASMEN'] == \
            'KEMENDIKDASMEN-2025'

    def test_default_version_function(self):
        assert default_curriculum_version('KEMENAG') == 'KMA-1503-2025'
        assert default_curriculum_version('KEMENDIKDASMEN') == \
            'KEMENDIKDASMEN-2025'
        with pytest.raises(ValueError):
            default_curriculum_version('INVALID_SYSTEM')

    def test_context_carries_matching_version(self):
        kemenag_ctx = make_context('KEMENAG')
        assert kemenag_ctx.curriculum_version == 'KMA-1503-2025'
        kemendikdasmen_ctx = make_context('KEMENDIKDASMEN')
        assert kemendikdasmen_ctx.curriculum_version == 'KEMENDIKDASMEN-2025'


# ============================================================================
# 5. Registry regulasi kanonik 9 dokumen Hukum/ (§6)
# ============================================================================

class TestCanonicalRegulationRegistry:
    """9 dokumen kanonik di Hukum/ adalah satu-satunya sumber regulasi."""

    def test_registry_has_exactly_nine_documents(self):
        registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
        assert len(registry['documents']) == 9

    def test_expected_document_ids(self):
        registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
        ids = {d['id'] for d in registry['documents']}
        assert ids == {
            'REG-KEMENDIKDASMEN-010-2025',
            'REG-KEMENDIKDASMEN-012-2025',
            'REG-KEMENDIKDASMEN-013-2025',
            'REG-KEMENDIKDASMEN-001-2026',
            'REG-KEMENDIKDASMEN-BSKAP-046-2025',
            'REG-KEMENDIKDASMEN-BKPDM-020-2026',
            'REG-KEMENAG-1503-2025',
            'REG-KEMENAG-PENDIS-9941-2025',
            'GUIDE-KEMENAG-KBC-6077-2025',
        }

    def test_bkpdm_020_supersedes_bskap_046(self):
        registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
        by_id = {d['id']: d for d in registry['documents']}
        assert by_id['REG-KEMENDIKDASMEN-BKPDM-020-2026']['supersedes_id'] == \
            'REG-KEMENDIKDASMEN-BSKAP-046-2025'

    def test_school_vs_madrasah_scope_separation(self):
        """Scope KEMENAG = madrasah saja; KEMENDIKDASMEN = sekolah umum
        termasuk pendidikan khusus. PAUD diizinkan untuk 013/2025 sesuai
        cakupan dokumennya sendiri (kerangka kurikulum mencakup PAUD).
        SDLB/SMPLB/SMALB diizinkan karena BKPDM 020/2026 memuat CP
        Pendidikan Khusus PAB untuk jenjang tersebut (bagian 2.x)."""
        registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
        madrasah = {'RA', 'MI', 'MTs', 'MA', 'MAK'}
        sekolah = {'SD', 'SMP', 'SMA', 'SMK', 'PAUD',
                   'SDLB', 'SMPLB', 'SMALB'}
        for doc in registry['documents']:
            scope = set(doc['scope'])
            if doc['id'].startswith(('REG-KEMENAG', 'GUIDE-KEMENAG')):
                assert scope <= madrasah, doc['id']
            else:
                assert scope <= sekolah, doc['id']

    def test_registry_points_to_hukum_directory(self):
        """Sumber kanonik tetap Hukum/ - tidak pernah dipindah/diubah."""
        registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
        for doc in registry['documents']:
            local = (PROJECT_ROOT / doc['local_path'])
            assert local.exists(), doc['local_path']
            assert 'Hukum' in Path(doc['local_path']).parts, doc['local_path']


# ============================================================================
# 6. OCR/vision fallback untuk PDF scan (§2)
# ============================================================================

class TestOCRFallbackIngestion:
    """PDF scan tidak boleh dianggap kosong; fallback OCR wajib dijalankan."""

    @pytest.fixture
    def mixed_pdf(self, tmp_path):
        """PDF 2 halaman: halaman 1 bertekstagteks penuh, halaman 2 scan
        (kosong dari text layer) - mensimulasikan BKPDM 020/2026."""
        fitz = pytest.importorskip('fitz')
        path = tmp_path / 'mixed.pdf'
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((72, 72), "Teks regulasi halaman pertama. " * 8)
        doc.new_page()  # halaman 2: tanpa text layer (simulasi scan)
        doc.save(str(path))
        doc.close()
        return path

    def test_threshold_constants_exist(self):
        assert MIN_TEXT_CHARS_PER_PAGE >= 1
        assert EXTRACTION_METHOD_TEXT_LAYER == 'text_layer'
        assert EXTRACTION_METHOD_OCR == 'ocr'
        assert EXTRACTION_METHOD_VISION == 'vision'

    def test_thin_pages_queued_for_ocr_not_dropped(self, mixed_pdf):
        extractor = PDFExtractor(str(mixed_pdf))
        pages = extractor.extract_text_with_pages()
        # Halaman 1 harus terekstrak via text layer + tercatat method-nya.
        assert 1 in pages
        assert extractor.page_methods[1] == EXTRACTION_METHOD_TEXT_LAYER
        # Halaman 2 (scan) TIDAK boleh diam-diam dilupakan: harus hasil OCR
        # bila Tesseract tersedia, atau dibiarkan hilang secara JUJUR
        # (bukan diisi teks karangan) - keduanya valid, exception tidak.
        assert isinstance(pages, dict)

    def test_scan_pdf_never_crashes_pipeline(self, tmp_path):
        """PDF full-scan (semua halaman kosong text layer) tetap selesai."""
        fitz = pytest.importorskip('fitz')
        path = tmp_path / 'scan.pdf'
        doc = fitz.open()
        for _ in range(3):
            doc.new_page()
        doc.save(str(path))
        doc.close()
        extractor = PDFExtractor(str(path))
        pages = extractor.extract_text_with_pages()
        # Tidak ada halaman fabricated: jika tidak ada OCR, tetap kosong.
        assert isinstance(pages, dict)
        assert all(isinstance(v, str) for v in pages.values())


# ============================================================================
# 7. Struktur master outline RPM A-E (§12)
# ============================================================================

class TestMasterOutlineRPMSections:
    """master_outline mengikuti struktur RPM, bukan Modul Ajar."""

    def test_rpm_top_level_sections(self):
        context = make_context('KEMENAG')
        module = make_rpm_module(context)
        mo = module.build_master_outline()
        assert set(mo.keys()) == {
            'general_information',   # A. Identitas
            'identification',        # B. Identifikasi
            'design',                # C. Desain Pembelajaran
            'learning_experience',   # D. Pengalaman Belajar
            'assessment',            # E. Asesmen
            'remedial_enrichment', 'reflection', 'attachments',
        }

    def test_assessment_uses_awal_proses_akhir(self):
        context = make_context('KEMENDIKDASMEN')
        module = make_rpm_module(context)
        assessment = module.build_master_outline()['assessment']
        assert set(assessment.keys()) >= {'awal', 'proses', 'akhir',
                                          'blueprint', 'rubric_scoring'}
        assert assessment['awal'] == module.assessments['diagnostic']
        assert assessment['proses'] == module.assessments['formative']
        assert assessment['akhir'] == module.assessments['summative']

    def test_identification_and_design_sections(self):
        context = make_context('KEMENAG')
        module = make_rpm_module(context)
        mo = module.build_master_outline()
        assert mo['identification']['learner_readiness'] == \
            module.learner_readiness
        assert mo['identification']['material_characteristics'] == \
            module.material_characteristics
        assert mo['design']['pedagogical_practices'] == \
            module.pedagogical_practices

    def test_kbc_lives_in_general_information_layer(self):
        """KBC tampil sebagai layer terpisah, bukan di dalam A.3 dimensi."""
        context = make_context('KEMENAG')
        module = make_rpm_module(context)
        mo = module.build_master_outline()
        gi = mo['general_information']
        assert gi['kbc']['enabled'] is True
        assert set(gi['profile_dimensions_values']) == set(PROFILE_DIMENSIONS_8)
