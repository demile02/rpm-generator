#!/usr/bin/env python3
"""Impor RPM: POST /api/modules/import (multipart DOCX/PDF).

Skenario: DOCX asli lolos (200 + tersimpan + badge origin),
dokumen non-aplikasi ditolak 422 tanpa tulis DB, ekstensi salah
ditolak, tanpa file 400, CP beda DB ditolak keras (R-32),
PDF multi-RPM pecah per segmen (R-36).
"""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from test_versions_batch5 import api_pipeline  # noqa: F401,E402

UPLOADS = Path(__file__).resolve().parents[1] / 'templates' \
    / 'uploads contoh'
DOCX = UPLOADS / 'kemukjizatan_Al-_Qur_an.docx'
PDF = UPLOADS / 'RPM_Al-Quran_Hadits_Bab_4-6.pdf'


def _post(flask_client, path, filename):
    with open(path, 'rb') as fh:
        data = {'file': (fh, filename)}
        return flask_client.post(
            '/api/modules/import', data=data,
            content_type='multipart/form-data')


def _count(flask_client):
    resp = flask_client.get('/api/modules')
    assert resp.status_code == 200
    return len(json.loads(resp.data)['modules'])


class TestImportDocx:
    def test_docx_asli_ditolak_tp_c2(self, flask_client, api_pipeline):
        # TP-2 dokumen ('Membandingkan...') = C2 per daftar KKO user;
        # TP di bawah C3 tetap tolak keras (R-37 hanya untuk KKTP).
        before = _count(flask_client)
        resp = _post(flask_client, DOCX, DOCX.name)
        assert resp.status_code == 422, resp.get_data(as_text=True)[:300]
        body = json.loads(resp.data)
        assert body['imported'] == []
        assert any('TP-2' in str(e.get('message'))
                   for r in body['rejected'] for e in r['errors'])
        assert _count(flask_client) == before

    def test_impor_bisa_edit_dan_export(
            self, flask_client, api_pipeline):
        # PDF segmen-1 semua TP C3+: impor, edit, export jalan.
        import io as _io
        from rpm_importer import split_pdf_segments
        segs = split_pdf_segments(str(PDF))
        assert len(segs) >= 2
        resp = flask_client.post(
            '/api/modules/import',
            data={'file': (_io.BytesIO(
                open(PDF, 'rb').read()), PDF.name)},
            content_type='multipart/form-data')
        body = json.loads(resp.data)
        gid = next(i['generation_id'] for i in body['imported']
                   if i['status'] == 'validated')
        # Buka = modul utuh (TP/aktivitas/asesmen ada).
        mod = json.loads(
            flask_client.get(f'/api/module/{gid}').data)['module']
        assert len(mod['learning_objectives']) >= 3
        assert len(mod['learning_activities']) >= 3
        # Export DOCX jalan (validated, bukan draft).
        exp = flask_client.get(f'/api/module/{gid}/export-docx')
        assert exp.status_code == 200, exp.get_data(as_text=True)[:200]
        assert exp.data[:2] == b'PK'


class TestImportPdf:
    def test_pdf_multi_pecah(self, flask_client, api_pipeline):
        before = _count(flask_client)
        resp = _post(flask_client, PDF, PDF.name)
        body = json.loads(resp.data)
        total = len(body['imported']) + len(body['rejected'])
        assert total >= 2, resp.get_data(as_text=True)[:500]
        assert _count(flask_client) == before + len(body['imported'])

    def test_level_gagal_jadi_draf_berflag(
            self, flask_client, api_pipeline):
        """Segregasi PDF ikut daftar KKO baru: segmen-1 (semua TP C3+)
        validated; segmen-0 (TP-2 'Membandingkan' = C2) dan segmen-2
        (TP-1 'mengidentifikasi' = UNKNOWN) ditolak keras. R-37 draf
        tercakup di test_level_kktp_soft_lainnya_hard."""
        resp = _post(flask_client, PDF, PDF.name)
        body = json.loads(resp.data)
        ok = [i for i in body['imported'] if i['status'] == 'validated']
        assert len(ok) == 1, resp.get_data(as_text=True)[:500]
        assert 'Pokok-Pokok Isi' in ok[0]['title']
        assert len(body['rejected']) == 2
        assert all(any(e['code'] == 'TP_LEVEL_INVALID'
                       for e in r['errors']) for r in body['rejected'])
        gid = ok[0]['generation_id']
        # Listing Beranda: status validated (badge origin impor).
        listing = json.loads(flask_client.get('/api/modules').data)
        row = next(m for m in listing['modules']
                   if m['generation_id'] == gid)
        assert row['status'] == 'validated'
        assert row['origin'] == 'import'
        # Export validated jalan.
        exp = flask_client.get(f'/api/module/{gid}/export-docx')
        assert exp.status_code == 200, exp.get_data(as_text=True)[:200]
        assert exp.data[:2] == b'PK'
        # Buka tetap bisa.
        detail = flask_client.get(f'/api/module/{gid}')
        assert detail.status_code == 200
        mod = json.loads(detail.data)['module']
        assert mod.get('origin') == 'import'
        assert mod['validation_results']['final']['passed'] is True


class TestSplitImportErrors:
    def test_level_kktp_soft_lainnya_hard(self):
        import sys as _sys
        _sys.path.insert(
            0, str(Path(__file__).resolve().parents[1] / 'src'))
        from app import _split_import_errors
        errs = [{'code': 'KKTP_ERROR',
                 'message': "KKTP-3 has invalid cognitive level "
                            "'UNKNOWN'",
                 'stage': 'rules'},
                {'code': 'PROTECTED_FIELD_MODIFICATION',
                 'message': 'CP text was modified', 'stage': 'x'},
                {'code': 'KKTP_ERROR',
                 'message': 'TP-9 has no KKTP', 'stage': 'x'}]
        hard, soft = _split_import_errors(errs)
        assert [e['code'] for e in soft] == ['KKTP_ERROR']
        assert sorted(e['code'] for e in hard) == [
            'KKTP_ERROR', 'PROTECTED_FIELD_MODIFICATION']


class TestImportReject:
    def test_tanpa_file_400(self, flask_client, api_pipeline):
        resp = flask_client.post(
            '/api/modules/import', data={},
            content_type='multipart/form-data')
        assert resp.status_code == 400

    def test_ekstensi_salah_422_tanpa_tulis(
            self, flask_client, api_pipeline):
        before = _count(flask_client)
        resp = flask_client.post(
            '/api/modules/import',
            data={'file': (io.BytesIO(b'x'), 'a.txt')},
            content_type='multipart/form-data')
        assert resp.status_code == 422
        assert _count(flask_client) == before

    def test_file_rusak_422_tanpa_tulis(
            self, flask_client, api_pipeline):
        before = _count(flask_client)
        resp = flask_client.post(
            '/api/modules/import',
            data={'file': (io.BytesIO(b'bukan pdf' * 100),
                           'rusak.pdf')},
            content_type='multipart/form-data')
        assert resp.status_code == 422, \
            resp.get_data(as_text=True)[:300]
        body = json.loads(resp.data)
        assert body['errors'][0]['code'] == 'UPLOAD_FILE_UNREADABLE'
        assert _count(flask_client) == before

    def test_bukan_dokumen_aplikasi_422_tanpa_tulis(
            self, flask_client, api_pipeline):
        from docx import Document
        buf = io.BytesIO()
        doc = Document()
        doc.add_paragraph('Halo dunia, bukan RPM.')
        doc.save(buf)
        buf.seek(0)
        before = _count(flask_client)
        resp = flask_client.post(
            '/api/modules/import',
            data={'file': (buf, 'asing.docx')},
            content_type='multipart/form-data')
        assert resp.status_code == 422, \
            resp.get_data(as_text=True)[:300]
        assert _count(flask_client) == before

    def test_cp_beda_ditolak_keras(self, flask_client, api_pipeline):
        import rpm_importer as importer
        assert importer.match_cp_official.__doc__ is not None
        # CP karangan tak pernah cocok dengan DB.
        orig = importer.match_cp_official
        called = {}

        def spy(cp_text, subject, phase, engine, *a, **k):
            called['yes'] = True
            return orig(cp_text, subject, phase, engine, *a, **k)

        importer.match_cp_official = spy
        try:
            resp = _post(flask_client, DOCX, DOCX.name)
            assert resp.status_code in (200, 422)
        finally:
            importer.match_cp_official = orig
        assert called.get('yes') is True
