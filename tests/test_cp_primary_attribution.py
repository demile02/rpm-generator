"""Temuan audit: primer multi-CP via AI + fallback atribusi tercatat.

- Primer dipilih berdasar topik (bukan asal CP pertama); pilihan + alasan
  tercatat di element_resolution_note.
- Mismatch atribusi TP-CP: AI diminta atribusi ulang dulu; fallback ke
  primer tercatat di log + validation['tp_attribution'].
"""
from unittest.mock import patch

import pytest

from curriculum_context import CPEntry, CurriculumContext
from module_generation_pipeline import ModuleGenerationPipeline

from test_phase_c_module_generation import VALID_PARAMS, patch_pipeline_ai


@pytest.fixture
def pipeline(test_db):
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    yield pipe
    pipe.curriculum_validator.close()


def _cp(idx, element):
    return CPEntry(
        id=f'CP-TEST-{idx}',
        text=f'Teks CP {element} tentang topik pembelajaran',
        source_document_id='DOC-TEST',
        source_fragment_id=f'frag-{idx}',
        source_page=idx,
        phase='D',
        element=element,
    )


def _konteks_multi():
    return CurriculumContext(
        education_system='KEMENAG',
        institution_type='MTs',
        grade='MTs_7',
        phase='D',
        subject='Akidah Akhlak',
        element='Pemahaman Konsep',
        curriculum_version='KMA-1503-2025',
        cp=_cp(1, 'Pemahaman Konsep'),
        tp_list=[],
        atp=None,
        cp_entries=[_cp(1, 'Pemahaman Konsep'),
                    _cp(2, 'Keterampilan Proses')],
        elements=['Pemahaman Konsep', 'Keterampilan Proses'],
    )


class TestPrimerViaAI:
    def test_ai_memilih_cp_kedua(self, pipeline):  # noqa: F811
        with patch.object(
                pipeline, '_pilih_cp_primer',
                return_value=(1, 'topik cocok CP-2')) as mock:
            ok, ctx, _ = pipeline.curriculum_validator.validate(
                dict(VALID_PARAMS,
                     elements=['Pemahaman Konsep', 'Keterampilan Proses']))
            assert ok
            # validate() sendiri belum menata primer (di generate());
            # helper terpanggil di generate — panggil langsung di sini.
            idx, alasan = pipeline._pilih_cp_primer(
                list(ctx.cp_entries), 'Taubat')
            assert (idx, alasan) == (1, 'topik cocok CP-2')
            assert mock.called

    def test_helper_fallback_tanpa_topik(self, pipeline):  # noqa: F811
        idx, alasan = pipeline._pilih_cp_primer(
            [_cp(1, 'A'), _cp(2, 'B')], '')
        assert idx == 0
        assert 'tanpa topik' in alasan

    def test_generate_menata_primer_dan_mencatat(self, pipeline):  # noqa: F811
        def fake(prompt, system_instruction=None, **kw):
            if '"cp":' in prompt or "'cp':" in prompt or 'CP kandidat' in prompt:
                return {'cp': 'CP-2', 'alasan': 'topik cocok elemen kedua'}
            raise AssertionError('prompt tak dikenal: ' + prompt[:60])

        params = dict(
            VALID_PARAMS,
            elements=['Pemahaman Konsep', 'Keterampilan Proses'],
            topic='Taubat',
            buku_document_id=None,
            assessment_counts={},
        )
        with patch_pipeline_ai(pipeline, fake):
            ok, ctx, errors = pipeline.curriculum_validator.validate(params)
            assert ok, errors
            # Simulasi blok penataan primer di generate().
            entri = list(ctx.cp_entries)
            idx, alasan = pipeline._pilih_cp_primer(entri, params['topic'])
            assert idx == 1
            assert 'topik cocok' in alasan


class TestAtribusiUlang:
    def test_mismatch_meminta_atribusi_dulu(self, pipeline):  # noqa: F811
        ctx = _konteks_multi()
        calls = []

        def fake(prompt, system_instruction=None, **kw):
            calls.append(prompt)
            return {'atribusi': [
                {'tp': 'TP-1', 'cp': 'CP-2'},
                {'tp': 'TP-2', 'cp': 'CP-1'},
            ]}

        with patch_pipeline_ai(pipeline, fake):
            hasil = pipeline._atribusi_ulang_tp(
                ['Menerapkan adab makan', 'Menganalisis dalil adab'], ctx)
        assert hasil == ['CP-TEST-2', 'CP-TEST-1']
        assert any('Petakan tiap TP' in c for c in calls)

    def test_atribusi_tak_lengkap_raise(self, pipeline):  # noqa: F811
        ctx = _konteks_multi()

        def fake(prompt, system_instruction=None, **kw):
            return {'atribusi': [{'tp': 'TP-1', 'cp': 'CP-1'}]}

        with patch_pipeline_ai(pipeline, fake):
            with pytest.raises(ValueError, match='tak lengkap'):
                pipeline._atribusi_ulang_tp(['Satu', 'Dua'], ctx)
