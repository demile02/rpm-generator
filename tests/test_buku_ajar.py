#!/usr/bin/env python3
"""R-43: buku ajar user sebagai sumber materi (verbatim struktur)."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from module_generation_pipeline import (
    format_buku_ajar_for_prompt,
    validasi_struktur_materi,
)
import pytest


@pytest.fixture
def api_pipeline(test_db):
    import app as app_module
    from module_generation_pipeline import ModuleGenerationPipeline
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    app_module._generation_pipeline = pipe
    yield pipe
    app_module._generation_pipeline = None
    pipe.curriculum_validator.close()


def _frag(fid, teks, hal=47):
    return {'id': fid, 'page_number': hal, 'text': teks}


BUKU = [
    _frag('BUKU-X-H47-1',
          'Secara garis besar ada dua aspek kemukjizatan al-Quran yaitu: '
          'a. Gaya Bahasa (Uslub). b. Isi Kandungannya.'),
    _frag('BUKU-X-H49-1',
          'Dilihat dari isi kandungannya, kemukjizatan al-Quran antara '
          'lain adalah: 1) berita gaib. 2) ijaz ilmi. 3) sumber aturan '
          'hukum universal.'),
]


class TestFormatPrompt:
    def test_blok_memuat_id_dan_halaman(self):
        blok = format_buku_ajar_for_prompt(BUKU, 'Buku Uji')
        assert 'BUKU-X-H47-1' in blok
        assert 'hal. 47' in blok
        assert 'DILARANG membuat struktur' in blok

    def test_kosong_string_kosong(self):
        assert format_buku_ajar_for_prompt([], 'x') == ''


class TestValidasiStruktur:
    def test_dua_aspek_berujuk_lolos(self):
        mc = ('Secara garis besar ada dua aspek kemukjizatan al-Quran '
              '[BUKU-X-H47-1].')
        assert validasi_struktur_materi(mc, BUKU) == []

    def test_empat_aspek_ditolak(self):
        mc = ('Ada 4 aspek kemukjizatan al-Quran [BUKU-X-H47-1].')
        errs = validasi_struktur_materi(mc, BUKU)
        assert any('MATERI_STRUKTUR_BEDA' in e for e in errs)

    def test_tanpa_rujukan_ditolak(self):
        mc = 'Ada dua aspek kemukjizatan al-Quran.'
        errs = validasi_struktur_materi(mc, BUKU)
        assert any('MATERI_TANPA_RUJUKAN' in e for e in errs)

    def test_rujukan_asing_ditolak(self):
        mc = 'Ada dua aspek [BUKU-ASING-H1-1].'
        errs = validasi_struktur_materi(mc, BUKU)
        assert any('MATERI_RUJUKAN_ASING' in e for e in errs)

    def test_tanpa_fragmen_tidak_dicek(self):
        assert validasi_struktur_materi('Ada 4 aspek.', []) == []


class TestEndpointBuku:
    def test_daftar_buku_ada(self, flask_client, api_pipeline):
        resp = flask_client.get('/api/buku')
        assert resp.status_code == 200
        import json
        body = json.loads(resp.data)
        assert body['status'] == 'success'
        assert isinstance(body['buku'], list)

    def test_upload_tanpa_file_400(self, flask_client, api_pipeline):
        resp = flask_client.post('/api/buku/upload', data={},
                                 content_type='multipart/form-data')
        assert resp.status_code == 400

    def test_upload_ekstensi_salah_422(self, flask_client, api_pipeline):
        resp = flask_client.post(
            '/api/buku/upload',
            data={'file': (io.BytesIO(b'x'), 'a.txt')},
            content_type='multipart/form-data')
        assert resp.status_code == 422
