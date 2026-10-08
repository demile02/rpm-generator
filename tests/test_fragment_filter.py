#!/usr/bin/env python3
"""Filter fragmen remah di pdf_extraction.

Remah = chunk tanpa konten: kosong/terlalu pendek, atau tanpa kata
berhuruf >= 3 (sisa penomoran "1.2.", digit "63177", header halaman
"-10 -", ornamen "|"). Harus dibuang di create_fragments agar korpus
(DB + konteks konsultasi regulasi) bebas noise layout OCR.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from pdf_extraction import (  # noqa: E402
    MIN_FRAGMENT_CHARS,
    PDFExtractor,
    _is_fragment_debris,
)


class TestFragmentDebrisHeuristic:
    """Heuristik token: tanpa kata berhuruf >=3 = remah."""

    def test_short_chunks_are_debris(self):
        assert _is_fragment_debris('')
        assert _is_fragment_debris('  ')
        assert _is_fragment_debris('|')
        assert _is_fragment_debris('B.')
        assert _is_fragment_debris('x' * MIN_FRAGMENT_CHARS)

    def test_numbering_and_page_headers_are_debris(self):
        # Sisa penomoran tabel OCR BKPDM & header halaman KMA.
        for debris in ('1.2.', '2.10.', '-10 -', '- 14 -', '63177', '---'):
            assert _is_fragment_debris(debris), debris

    def test_real_content_is_kept(self):
        assert not _is_fragment_debris(
            'Mengubah ketentuan mengenai Capaian Pembelajaran')
        assert not _is_fragment_debris('Fase D (Kelas VII)')
        assert not _is_fragment_debris('1.2 Pemahaman Al-Qur\'an')
        # Angka boleh muncul, asal ada kata berhuruf >=3.
        assert not _is_fragment_debris('Permendikdasmen No. 13 Tahun 2025')

    def test_two_char_words_alone_are_debris(self):
        # "di", "ke" sendirian tanpa kata lain tetap remah.
        assert _is_fragment_debris('di ke')
        # ...tapi cukup bila satu kata >=3 huruf hadir.
        assert not _is_fragment_debris('di ke PTKE')


class TestCreateFragmentsFiltering:
    """Integrasi: create_fragments memakai filter heuristik."""

    def _extractor_with_content(self, content):
        ex = PDFExtractor('dummy.pdf')
        ex.content = dict(content)
        ex.page_methods = {}
        return ex

    def test_debris_never_becomes_fragment(self):
        ex = self._extractor_with_content({
            1: 'Kepala Badan Standar Kurikulum\n\n1.2.\n\n63177\n\n'
               'Perubahan atas Keputusan Kepala BSKAP',
        })
        frags = ex.create_fragments()
        texts = [f['text'] for f in frags]
        assert '1.2.' not in texts
        assert '63177' not in texts
        assert any('Perubahan atas' in t for t in texts)

    def test_clean_document_unchanged(self):
        ex = self._extractor_with_content({
            1: 'Capaian Pembelajaran Fase D\n\nMurid memahami akidah.',
        })
        frags = ex.create_fragments()
        assert len(frags) == 2
        assert all(f['text'] for f in frags)
