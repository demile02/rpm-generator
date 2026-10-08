#!/usr/bin/env python3
"""Test renderer DOCX final RPM (src/docx_renderer.py).

Kontrak: hanya FINAL VALIDATED result yang boleh dirender; selain itu
ExportError tanpa file. Renderer representasi murni (tanpa AI).
"""
import copy
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from docx import Document

# Src imports (same sys.path convention as the other test modules).
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from docx_renderer import ExportError, render_final_rpm_docx
from module_generation_pipeline import ModuleGenerationPipeline
from test_phase_c_module_generation import (
    VALID_PARAMS, fake_router_response, patch_pipeline_ai,
)


@pytest.fixture
def final_result(test_db):
    """Hasil FINAL VALIDATED nyata dari pipeline penuh (mock AI, real
    validator di semua stage)."""
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    try:
        with patch_pipeline_ai(pipe, fake_router_response):
            result = pipe.generate(dict(VALID_PARAMS))
    finally:
        pipe.curriculum_validator.close()
    assert result['status'] == 'success', result['errors']
    assert result['validation']['final']['passed'] is True
    return result


def _doc_text(path):
    doc = Document(str(path))
    texts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            texts.extend(cell.text for cell in row.cells)
    return '\n'.join(texts), doc


def test_final_validated_renders_docx(final_result, tmp_path):
    out = render_final_rpm_docx(
        final_result, tmp_path / 'rpm.docx')
    assert out.endswith('.docx')
    assert Path(out).stat().st_size > 0


def test_output_is_valid_docx_package(final_result, tmp_path):
    out = render_final_rpm_docx(final_result, tmp_path / 'rpm.docx')
    assert zipfile.is_zipfile(out)
    text, _ = _doc_text(out)
    assert len(text.strip()) > 500


def test_main_heading_present(final_result, tmp_path):
    out = render_final_rpm_docx(final_result, tmp_path / 'rpm.docx')
    text, doc = _doc_text(out)
    assert 'PERENCANAAN PEMBELAJARAN MENDALAM' in text
    topik = (final_result['module'].get('topic') or '').strip()
    assert topik and topik in text
    # Subjek tetap tampil sebagai data (tabel identitas), bukan judul.
    assert final_result['module']['subject'] in text


def test_sections_a_to_e_present(final_result, tmp_path):
    out = render_final_rpm_docx(final_result, tmp_path / 'rpm.docx')
    text, _ = _doc_text(out)
    for section in ('A. IDENTITAS MODUL', 'B. IDENTIFIKASI',
                    'C. DESAIN PEMBELAJARAN', 'D. LANGKAH DAN PENGALAMAN PEMBELAJARAN',
                    'E. ASESMEN'):
        assert section in text


def test_content_comes_from_final_result(final_result, tmp_path):
    out = render_final_rpm_docx(final_result, tmp_path / 'rpm.docx')
    text, _ = _doc_text(out)
    outline = final_result['module']['master_outline']
    assert (outline['design']['cp'] or '')[:60] in text
    first_tp = outline['design']['tp'][0]['text']
    assert first_tp[:60] in text
    _, doc = _doc_text(out)
    assert len(doc.tables) >= 4  # identitas, TP, aktivitas, asesmen, ...


def test_validation_fail_rejected(tmp_path, test_db):
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    try:
        with patch_pipeline_ai(pipe, fake_router_response):
            bad = pipe.generate(dict(VALID_PARAMS, grade='MTs_99'))
    finally:
        pipe.curriculum_validator.close()
    assert bad['status'] == 'failed'
    with pytest.raises(ExportError):
        render_final_rpm_docx(bad, tmp_path / 'no.docx')
    assert not (tmp_path / 'no.docx').exists()


def test_draft_without_final_pass_rejected(final_result, tmp_path):
    draft = copy.deepcopy(final_result)
    draft['validation']['final'] = {'passed': False, 'errors': ['x']}
    with pytest.raises(ExportError):
        render_final_rpm_docx(draft, tmp_path / 'no.docx')
    assert not (tmp_path / 'no.docx').exists()
    nodict = copy.deepcopy(final_result)
    nodict['status'] = 'success'
    nodict['validation'] = {}
    with pytest.raises(ExportError):
        render_final_rpm_docx(nodict, tmp_path / 'no2.docx')


def test_kbc_only_for_madrasah(final_result, tmp_path):
    out = render_final_rpm_docx(final_result, tmp_path / 'rpm.docx')
    text, _ = _doc_text(out)
    assert 'Kurikulum Berbasis Cinta' in text
    school = copy.deepcopy(final_result)
    school['module']['curriculum_context']['education_system'] = \
        'KEMENDIKDASMEN'
    school['module']['master_outline']['general_information']['kbc'] = None
    out2 = render_final_rpm_docx(school, tmp_path / 'sekolah.docx')
    text2, _ = _doc_text(out2)
    assert 'Kurikulum Berbasis Cinta' not in text2


def test_renderer_calls_no_ai(final_result, tmp_path):
    """Renderer murni representasi: render berhasil walau seluruh entry
    AI pipeline dibuat raising, dan source tidak memakai klien AI."""
    import module_generation_pipeline as mgp

    def boom(*args, **kwargs):
        raise AssertionError('renderer memanggil AI')

    with patch.object(mgp.ModuleGenerationPipeline, '_generate_tp',
                      side_effect=boom):
        out = render_final_rpm_docx(final_result, tmp_path / 'rpm.docx')
    assert Path(out).exists()
    src = (Path(__file__).resolve().parents[1] / 'src' / 'docx_renderer.py'
           ).read_text(encoding='utf-8')
    assert 'generate_json' not in src and 'ai_client' not in src
    assert 'requests' not in src and 'NineRouter' not in src
