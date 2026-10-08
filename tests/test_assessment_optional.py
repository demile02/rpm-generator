#!/usr/bin/env python3
"""R-42: asesmen opsional per-bucket (0 = tidak digenerate)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))

from module_generation_pipeline import (
    ModuleGenerationPipeline,
    PedagogicalValidator,
    FinalValidator,
    MasterOutlineValidator,
)
from curriculum_context import CurriculumContext, CPEntry
from test_phase_c_module_generation import make_module


def _ctx():
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
        element='Pemahaman Konsep',
        curriculum_version='KMA-1503-2025',
        cp=cp,
        tp_list=[],
        atp=None,
        rules={},
        topic='Taubat',
    )


class TestCountsNol:
    def test_nol_diterima(self):
        counts, err = ModuleGenerationPipeline.resolve_assessment_counts(
            {'diagnostic': 0, 'formative': 5, 'summative': 0})
        assert err is None
        assert counts == {'diagnostic': 0, 'formative': 5, 'summative': 0}

    def test_semua_nol_ditolak(self):
        _, err = ModuleGenerationPipeline.resolve_assessment_counts(
            {'diagnostic': 0, 'formative': 0, 'summative': 0})
        assert err is not None

    def test_negatif_ditolak(self):
        _, err = ModuleGenerationPipeline.resolve_assessment_counts(
            {'diagnostic': -1})
        assert err is not None

    def test_kosong_default_lama(self):
        counts, err = ModuleGenerationPipeline.resolve_assessment_counts(
            None)
        assert err is None
        assert counts == {'diagnostic': 10, 'formative': 10,
                          'summative': 5}


class TestBatteryTanpaAsesmen:
    def test_alignment_kosong_tetap_gagal(self):
        ok, _ = PedagogicalValidator.validate_assessment_alignment(
            {}, 1, 1)
        assert ok is False

    def test_sebagian_bucket_lolos_hubungan(self):
        ok, _ = PedagogicalValidator.validate_assessment_alignment(
            {'diagnostic': [{'question': 'q', 'tp_linked': 'TP-1'}]},
            1, 1)
        assert ok is True

    def test_completeness_tanpa_asesmen_lolos(self):
        m = make_module(_ctx(), assessments={})
        ok, _ = FinalValidator.validate_completeness(m)
        assert ok is True

    def test_mo_tanpa_asesmen_tanpa_trace_error(self):
        m = make_module(_ctx(), assessments={})
        ok, errors = MasterOutlineValidator.validate(m)
        assert not any(e.get('code') == 'ASSESSMENT_ERROR'
                       for e in errors)
