#!/usr/bin/env python3
"""
Parser CP School (Pendidikan Agama dan Budi Pekerti) dari BKPDM 020/2026.

Mengunci:
- jumlah & distribusi CP (6 fase x 5 elemen) dari dokumen kanonik;
- provenance halaman (source_document + source_page terhubung fragmen);
- isolasi School vs Madrasah (tidak ada saling menimpa);
- jalur generate KEMENDIKDASMEN end-to-end via pipeline (fake AI).
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from curriculum_engine import CurriculumEngine  # noqa: E402
from module_generation_pipeline import ModuleGenerationPipeline  # noqa: E402


@pytest.fixture
def pipeline(test_db):
    """Pipeline wired to a temp copy of the production database
    (sama dengan fixture di test_phase_c_module_generation)."""
    pipe = ModuleGenerationPipeline(db_path=str(test_db))
    yield pipe
    pipe.curriculum_validator.close()

SCHOOL_SUBJECT = 'Pendidikan Agama dan Budi Pekerti'
SCHOOL_DOC = 'BKPDM-020-2026'
MADRASAH_DOCS = {'SK-Dirjen-Pendis-9941-2025'}


# ============================================================================
# PARSER (dijalankan terhadap DB produksi yang disalin per test)
# ============================================================================

@pytest.fixture(scope='function')
def school_cp_entries(test_db):
    """Hasil parser CP School terhadap salinan DB produksi."""
    engine = CurriculumEngine(str(test_db))
    engine.connect()
    try:
        return engine.extract_school_cp_from_fragments()
    finally:
        engine.close()


class TestSchoolCPParse:
    """Struktur hasil parser CP School BKPDM 020/2026."""

    def test_exactly_30_cp(self, school_cp_entries):
        assert len(school_cp_entries) == 30

    def test_phase_distribution(self, school_cp_entries):
        from collections import Counter
        dist = Counter(e.phase for e in school_cp_entries)
        assert dist == {'A': 5, 'B': 5, 'C': 5, 'D': 5, 'E': 5, 'F': 5}

    def test_element_distribution(self, school_cp_entries):
        from collections import Counter
        dist = Counter(e.element for e in school_cp_entries)
        assert dist == {
            "Al-Qur'an Hadis": 6,
            'Akidah': 6,
            'Akhlak': 6,
            'Fikih': 6,
            'Sejarah Peradaban Islam': 6,
        }

    def test_subject_is_school_subject(self, school_cp_entries):
        assert all(e.subject == SCHOOL_SUBJECT for e in school_cp_entries)

    def test_provenance_pages_within_window(self, school_cp_entries):
        # CP PAI-BP reguler ada di lampiran hal. 6-9 dokumen BKPDM.
        for e in school_cp_entries:
            assert 6 <= e.source_page <= 9, e
            assert e.source_document == SCHOOL_DOC

    def test_no_phase_parenthetical_leaked_into_text(self, school_cp_entries):
        for e in school_cp_entries:
            assert '(Umumnya' not in e.text, e.text[:80]
            assert not e.text.startswith('('), e.text[:80]

    def test_cp_texts_are_verbatim_document_fragments(self, school_cp_entries,
                                                      db_connection):
        """Setiap teks CP harus ada (subset kata) di fragmen halaman
        provensinya — bukti tidak ada teks karangan parser."""
        cursor = db_connection.cursor()
        for e in school_cp_entries:
            first_words = ' '.join(e.text.split()[:6])
            assert len(first_words) > 10
            row = cursor.execute(
                "SELECT text FROM source_fragments WHERE document_id = ? "
                "AND page_number = ?",
                (CurriculumEngine._CP_SCHOOL_DOC_ID, e.source_page),
            ).fetchall()
            joined = ' '.join(r['text'] for r in row)
            # Cek kata-kata kunci awal CP ada di halaman sumbernya
            # (teks asli dokumen, bukan hasil parafrase).
            for w in first_words.split():
                assert w.lower() in joined.lower(), (e.id, w)


class TestReligionCP:
    """CP agama selain PAI-BP dari BKPDM 020/2026.

    Diktum KESATU mengubah CP keenam agama, reguler dan pendidikan
    khusus. OCR menghilangkan nomor item di sebagian fase, jadi jumlah
    di bawah lengkap. Yang ada wajib utuh: elemen resmi, provenance,
    dan teks yang benar-benar ada di fragmen sumbernya."""

    EXPECTED = {
        'Pendidikan Agama Hindu dan Budi Pekerti':
            {'Kitab Suci Weda', 'Sraddha dan Bhakti', 'Susila', 'Acara',
             'Sejarah Agama Hindu'},
        'Pendidikan Agama Buddha dan Budi Pekerti':
            {'Sejarah', 'Ritual', 'Etika'},
        'Pendidikan Agama Khonghucu dan Budi Pekerti':
            {'Sejarah Suci', 'Kitab Suci', 'Keimanan', 'Tata Ibadah',
             'Perilaku Junzi'},
        'Pendidikan Khusus Agama Islam dan Budi Pekerti':
            {"Al-Qur'an Hadis", 'Akidah', 'Akhlak', 'Fikih',
             'Sejarah Peradaban Islam'},
        'Pendidikan Khusus Agama Katolik dan Budi Pekerti':
            {'Pribadi Murid', 'Yesus Kristus', 'Gereja', 'Masyarakat'},
        'Pendidikan Khusus Agama Hindu dan Budi Pekerti':
            {'Kitab Suci Weda', 'Sraddha dan Bhakti', 'Susila', 'Acara',
             'Sejarah Agama Hindu'},
        'Pendidikan Khusus Agama Buddha dan Budi Pekerti':
            {'Sejarah', 'Ritual', 'Etika'},
        'Pendidikan Khusus Agama Khonghucu dan Budi Pekerti':
            {'Sejarah Suci', 'Kitab Suci', 'Keimanan', 'Tata Ibadah',
             'Perilaku Junzi'},
    }

    @pytest.fixture
    def religion_cp(self, test_db):
        engine = CurriculumEngine(str(test_db))
        engine.connect()
        try:
            return engine.extract_religion_cp_from_fragments()
        finally:
            engine.close()

    def test_all_expected_subjects_present(self, religion_cp):
        found = {e.subject for e in religion_cp}
        assert set(self.EXPECTED) <= found

    def test_elements_are_official(self, religion_cp):
        from collections import defaultdict
        by_subject = defaultdict(set)
        for e in religion_cp:
            by_subject[e.subject].add(e.element)
        for subject, elements in self.EXPECTED.items():
            assert by_subject[subject] <= elements, subject

    def test_every_phase_present(self, religion_cp):
        assert {e.phase for e in religion_cp} == set('ABCDEF')

    def test_special_education_flagged(self, religion_cp):
        for e in religion_cp:
            if e.subject.startswith('Pendidikan Khusus'):
                assert e.institution_type == 'pendidikan_khusus'
            else:
                assert e.institution_type == 'sekolah'

    def test_provenance_points_at_020(self, religion_cp):
        for e in religion_cp:
            assert e.source_document == SCHOOL_DOC
            assert e.source_page and e.source_page > 9

    def test_text_comes_from_source_fragment(self, religion_cp, db_connection):
        cursor = db_connection.cursor()
        for e in religion_cp:
            words = e.text.split()[:5]
            rows = cursor.execute(
                "SELECT text FROM source_fragments WHERE document_id = ? "
                "AND page_number = ?",
                (CurriculumEngine._CP_SCHOOL_DOC_ID, e.source_page),
            ).fetchall()
            joined = ' '.join(r['text'] for r in rows).lower()
            for w in words:
                assert w.lower() in joined, (e.subject, e.phase, w)


class TestSchoolMadrasahIsolation:
    """Jalur School vs Madrasah tidak boleh tercampur."""

    def test_school_cp_not_from_madrasah_documents(self, db_connection):
        cursor = db_connection.cursor()
        rows = cursor.execute(
            "SELECT DISTINCT source_document FROM learning_outcomes "
            "WHERE subject = ?", (SCHOOL_SUBJECT,)
        ).fetchall()
        docs = {r['source_document'] for r in rows}
        assert docs == {SCHOOL_DOC}
        assert not (docs & MADRASAH_DOCS)

    def test_madrasah_cp_counts_unchanged(self, db_connection):
        """Parser v2: 132 CP madrasah (reguler + MAPK terpisah, 0 Unknown,
        langkah KP yang diulang antar-fase di dokumen tetap ter-emit per
        fase). Angka 205 lama adalah hasil parser lama yang mencampur
        cakupan sebagai elemen dan MAPK ke jalur reguler."""
        cursor = db_connection.cursor()
        row = cursor.execute(
            "SELECT COUNT(*) as c FROM learning_outcomes "
            "WHERE source_document = ?", ('SK-Dirjen-Pendis-9941-2025',)
        ).fetchone()
        assert row['c'] == 132
        # Tidak ada fase/element Unknown pada CP madrasah.
        bad = cursor.execute(
            "SELECT COUNT(*) as c FROM learning_outcomes "
            "WHERE source_document = ? AND (phase = 'Unknown' "
            "OR element IN ('Unknown', 'Umum'))",
            ('SK-Dirjen-Pendis-9941-2025',)).fetchone()
        assert bad['c'] == 0

    def test_no_subject_mixing(self, db_connection):
        """Nama mapel madrasah tidak boleh membawa CP dari dokumen
        Kemendikdasmen, dan sebaliknya."""
        cursor = db_connection.cursor()
        rows = cursor.execute(
            "SELECT subject, source_document, status FROM learning_outcomes"
        ).fetchall()
        for r in rows:
            if r['subject'] == SCHOOL_SUBJECT:
                # PAB yang berlaku hanya dari BKPDM 020. Edisi 046 mapel
                # yang sama tersimpan sebagai riwayat 'superseded'.
                assert r['source_document'] == SCHOOL_DOC or (
                    r['source_document'] == 'BSKAP-046/H/KR/2025'
                    and r['status'] == 'superseded')
            elif r['source_document'] not in (
                    'BSKAP-046/H/KR/2025', SCHOOL_DOC):
                # CP sekolah hanya dari 046 (mapel umum) dan 020 (agama).
                # Selain itu wajib dari 9941 (madrasah).
                assert r['source_document'] == 'SK-Dirjen-Pendis-9941-2025'


class TestSchoolGenerationPath:
    """Jalur generate KEMENDIKDASMEN end-to-end (pipeline + fake AI)."""

    def _params(self):
        return {
            'education_system': 'KEMENDIKDASMEN',
            'institution_type': 'SMP',
            'grade': 'SMP_7',
            'subject': SCHOOL_SUBJECT,
            'element': 'Akidah',
            'topic': 'Rukun Iman',
            'requested_tp_count': 3,
        }

    def test_school_cp_retrievable(self, curriculum_engine):
        cp_list = curriculum_engine.get_cp_by_subject_phase(SCHOOL_SUBJECT, 'D')
        elements = {c.element for c in cp_list}
        assert elements == {"Al-Qur'an Hadis", 'Akidah', 'Akhlak', 'Fikih',
                            'Sejarah Peradaban Islam'}

    def test_generate_kemendikdasmen_end_to_end(self, pipeline):
        from test_phase_c_module_generation import fake_router_response, \
            patch_pipeline_ai

        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(self._params())
        assert result['status'] == 'success', result['errors']
        m = result['module']

        # CP sekolah dengan provenance BKPDM
        cp = m['curriculum_context']['cp']
        assert cp['source_document_id'] == SCHOOL_DOC
        assert 6 <= cp['source_page'] <= 9
        assert cp['phase'] == 'D'
        assert cp['element'] == 'Akidah'

        # TP tetap tervalidasi (C3+ via rule engine, bukan mock lepas)
        tp = [t['text'] for t in m['learning_objectives']]
        assert len(tp) == 3
        assert all(t.split()[0] in ('Menerapkan', 'Menganalisis',
                                    'Mengevaluasi', 'Menciptakan')
                   for t in tp)

        # Konsultasi regulasi: jalur sekolah harus KEMENDIKDASMEN (BKPDM),
        # bukan KMA madrasah
        rc = m.get('regulatory_consultation', {})
        doc_ids = [s['document_id'] for s in rc.get('sources', [])]
        assert doc_ids and all('KEMENDIKDASMEN' in d for d in doc_ids)

    def test_school_element_resolution_explicit(self, pipeline):
        """Elemen eksplisit 'Akidah' harus match CP — resolusi tidak boleh
        diam-diam memilih elemen lain (BLOCKER 3)."""
        from test_phase_c_module_generation import fake_router_response, \
            patch_pipeline_ai

        params = self._params()
        params['element'] = 'Akhlak'  # elemen berbeda, tetap valid
        with patch_pipeline_ai(pipeline, fake_router_response):
            result = pipeline.generate(params)
        assert result['status'] == 'success', result['errors']
        assert result['module']['curriculum_context']['cp']['element'] == 'Akhlak'

    def test_school_unknown_element_rejected(self, pipeline):
        params = self._params()
        params['element'] = 'Akidah dan Akhlak'  # label lama yang salah
        result = pipeline.generate(params)
        assert result['status'] == 'failed'
        assert any('ELEMENT_NOT_FOUND' in e for e in result['errors'])
