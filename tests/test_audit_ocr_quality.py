#!/usr/bin/env python3
"""Smoke test alat audit kualitas OCR (scripts/audit_ocr_quality.py).

Metrik murni diuji tanpa DB/PDF/Tesseract; CLI dijalankan via subprocess
pada SATU dokumen dengan 1 halaman sampel agar runtime tetap singkat
(OCR ~2s/halaman).
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / 'scripts' / 'audit_ocr_quality.py'
sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))

import audit_ocr_quality as aq  # noqa: E402


class TestPureMetrics:
    def test_normalize_and_word_set(self):
        # TANPA collapse-spasi: konsisten dengan metode audit baseline
        # (SequenceMatcher peka spasi, tidak dinormalisasi ganda).
        assert aq.normalize_text('Fase D (Kelas VII)!') == 'fase d  kelas vii  '
        assert aq.word_set('Fase D fase') == {'fase', 'd'}

    def test_page_metrics_perfect_match(self):
        m = aq.page_metrics('Capaian Pembelajaran adalah kompetensi.',
                            'Capaian Pembelajaran adalah kompetensi.')
        assert m['containment'] == 100.0
        assert m['similarity_raw'] == 100.0
        assert m['similarity_fair'] == 100.0

    def test_page_metrics_debris_in_ocr_does_not_penalize_fair(self):
        db = 'Madrasah Aliyah Kejuruan pembelajaran mendalam.'
        ocr = '-10 -\n' + db + '\n|'
        m = aq.page_metrics(db, ocr)
        # containment dihitung terhadap re-OCR MENTAH (lebih ketat)...
        assert m['containment'] == 100.0  # kata DB tetap ada di mentah
        # ...tapi similarity fair membersihkan baris remah -> sempurna.
        assert m['similarity_fair'] == 100.0
        assert m['similarity_raw'] < 100.0

    def test_page_metrics_empty_ocr(self):
        m = aq.page_metrics('Teks db yang ada.', '')
        assert m['containment'] == 0.0
        assert m['similarity_raw'] == 0.0

    def test_aggregate(self):
        agg = aq.aggregate([
            {'containment': 100.0, 'similarity_raw': 90.0, 'similarity_fair': 95.0},
            {'containment': 80.0, 'similarity_raw': 100.0, 'similarity_fair': 100.0},
        ])
        assert agg['containment'] == 90.0
        assert agg['similarity_raw'] == 95.0
        assert agg['similarity_fair'] == 97.5
        assert aq.aggregate([])['containment'] == 0.0


class TestRenderHtml:
    def _result(self):
        return {
            'document_id': 'DOC-X',
            'document_title': 'Dok Uji <&>',
            'pdf_path': 'dummy.pdf',
            'seed': 7,
            'sample': [1],
            'pages': [{
                'page': 1, 'db_chars': 10, 'ocr_chars': 10,
                'containment': 100.0, 'similarity_raw': 99.0,
                'similarity_fair': 100.0, 'db_text': 'teks uji',
                'img_b64': 'QUJD',
            }],
            'summary': aq.aggregate(
                [{'containment': 100.0, 'similarity_raw': 99.0,
                  'similarity_fair': 100.0}]),
        }

    def test_renders_escaped_html(self):
        html = aq.render_html([self._result()], seed=7)
        assert 'Dok Uji &lt;&amp;&gt;' in html  # di-escape
        assert 'seed 7' in html
        assert 'apple-to-apple=100.0' in html
        assert 'data:image/jpeg;base64,QUJD' in html  # gambar dari img_b64

    def test_no_raw_html_injection(self):
        html = aq.render_html([self._result()], seed=7)
        # teks DB tidak boleh lewat sebagai tag mentah
        assert '<teks-uji>' not in html

    def test_render_without_image_is_pure(self):
        """Tanpa img_b64: render tetap jalan (tidak menyentuh PDF)."""
        r = self._result()
        r['pages'][0].pop('img_b64')
        html = aq.render_html([r], seed=7)
        assert '<img' not in html
        assert 'teks uji' in html


class TestCliSmoke:
    """CLI via subprocess pada satu dokumen, 1 halaman."""

    def test_cli_runs_and_writes_outputs(self, tmp_path):
        out_html = tmp_path / 'audit.html'
        out_json = tmp_path / 'audit.json'
        # Subprocess CLI wajib memakai stdio UTF-8: konsol Windows
        # (cp1252) gagal mencetak emoji log OCR. Tanpa ini
        # UnicodeEncodeError — bukan kegagalan logika audit.
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        proc = subprocess.run(
            [sys.executable, str(SCRIPT),
             '--doc', '1503', '--pages', '1', '--seed', '5',
             '--output', str(out_html), '--json', str(out_json)],
            capture_output=True, text=True, timeout=180,
            cwd=str(PROJECT_ROOT), env=env)
        assert proc.returncode == 0, proc.stderr[-2000:]
        assert out_html.exists() and out_html.stat().st_size > 50_000
        assert 'apple-to-apple' in out_html.read_text(encoding='utf-8')

        data = json.loads(out_json.read_text(encoding='utf-8'))
        assert data['seed'] == 5
        assert len(data['results']) == 1
        res = data['results'][0]
        assert res['document_id'] == 'DOC-REG-KEMENAG-1503-2025'
        assert len(res['pages']) == 1
        pg = res['pages'][0]
        assert pg['containment'] > 90, pg
        assert pg['similarity_fair'] > 90, pg
        # 'sample' list int dan pdf_path tidak diekspor
        assert isinstance(res['sample'], list)
        assert 'pdf_path' not in res
