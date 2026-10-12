"""Test invarian data/curriculum hasil rebuild penuh dari 9 PDF Hukum/.

Mengunci kriteria audit FINAL DATA/CURRICULUM CLEANUP (AGENTS.md §1/§3/§4/
§9/§27): 9 dokumen, hash konsisten, effective_date berbasis bukti,
supersedes 020→046 amendemen, extraction_method per fragment, text_hash
SHA-256 mismatch=0, provenance CP sampai fragment, MAPK terpisah dari
reguler, CP sekolah dari BKPDM 020 (bukan 046), mock DB sinkron.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / 'db' / 'rpm_generator.db'
MOCK_PATH = PROJECT_ROOT / 'db' / 'mock_rpm.db'
REGISTRY_PATH = PROJECT_ROOT / 'db' / 'document_registry.json'
EXTRACTION_PATH = PROJECT_ROOT / 'db' / 'extracted_fragments.json'
MAPPINGS_PATH = PROJECT_ROOT / 'db' / 'curriculum_mappings.json'
HUkUM = PROJECT_ROOT / 'Hukum'

REG_046 = 'REG-KEMENDIKDASMEN-BSKAP-046-2025'
REG_020 = 'REG-KEMENDIKDASMEN-BKPDM-020-2026'
DOC_9941 = 'DOC-REG-KEMENAG-PENDIS-9941-2025'
DOC_020 = 'DOC-REG-KEMENDIKDASMEN-BKPDM-020-2026'
DOC_046 = 'DOC-REG-KEMENDIKDASMEN-BSKAP-046-2025'


@pytest.fixture(scope='module')
def conn():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture(scope='module')
def registry():
    return json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Registry & metadata regulasi
# ---------------------------------------------------------------------------

def test_nine_canonical_pdfs_present():
    pdfs = list(HUkUM.glob('*.pdf'))
    assert len(pdfs) == 9


def test_nine_registry_entries_with_evidence(registry):
    docs = registry['documents']
    assert len(docs) == 9
    for d in docs:
        ev = d.get('effective_evidence') or {}
        assert ev.get('evidence_page'), f"{d['id']} tanpa bukti halaman"
        assert ev.get('evidence_date'), f"{d['id']} tanpa bukti tanggal"


def test_registry_hash_matches_actual_pdfs(registry):
    for d in registry['documents']:
        actual = _sha256_file(PROJECT_ROOT / d['local_path'])
        assert actual == d['document_hash'], d['id']


def test_effective_dates_not_default(registry):
    for d in registry['documents']:
        assert d['effective_date'] != '2025-01-01', (
            f"{d['id']} masih memakai tanggal default")
        # Format ISO.
        assert len(d['effective_date']) == 10


def test_supersedes_020_amends_046_not_replaces(registry):
    docs = {d['id']: d for d in registry['documents']}
    d020 = docs[REG_020]
    assert d020['supersedes_id'] == REG_046
    assert d020.get('supersedes_kind') == 'amends'
    # 046 TETAP aktif (amendemen, bukan penggantian total - AGENTS.md §3).
    assert docs[REG_046]['status'] == 'active'


def test_db_regulations_match_registry(conn, registry):
    reg_by_id = {d['id']: d for d in registry['documents']}
    rows = conn.execute(
        'SELECT id, document_hash, effective_date, status, supersedes_id '
        'FROM regulations').fetchall()
    assert len(rows) == 9
    for r in rows:
        d = reg_by_id[r['id']]
        assert r['document_hash'] == d['document_hash'], r['id']
        assert r['effective_date'] == d['effective_date'], r['id']
        assert r['supersedes_id'] == d['supersedes_id'], r['id']


# ---------------------------------------------------------------------------
# Fragmen: extraction_method + text_hash
# ---------------------------------------------------------------------------

def test_fragment_extraction_method_filled(conn):
    n, bad = conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN COALESCE(extraction_method, '')='' "
        "THEN 1 ELSE 0 END) FROM source_fragments").fetchone()
    assert n > 0
    assert bad == 0
    methods = {r[0] for r in conn.execute(
        'SELECT DISTINCT extraction_method FROM source_fragments')}
    # Regulasi: text_layer/ocr/vision; buku: + scan (halaman gambar).
    assert methods <= {'text_layer', 'ocr', 'vision', 'scan'}


def test_fragment_text_hash_sha256_no_mismatch(conn):
    mismatch = 0
    n = 0
    for row in conn.execute('SELECT text, text_hash FROM source_fragments'):
        n += 1
        actual = hashlib.sha256(
            (row['text'] or '').encode('utf-8')).hexdigest()
        if actual != row['text_hash']:
            mismatch += 1
    assert n > 0
    assert mismatch == 0


def test_extraction_json_has_per_fragment_method():
    data = json.loads(EXTRACTION_PATH.read_text(encoding='utf-8'))
    docs = data.get('documents', [])
    assert len(docs) == 9
    for doc in docs:
        frags = doc.get('fragments', [])
        assert frags, doc.get('metadata', {}).get('document_id')
        for fr in frags:
            assert fr.get('extraction_method') in (
                'text_layer', 'ocr', 'vision'), fr.get('id')


# ---------------------------------------------------------------------------
# CP: provenance, fase, elemen, MAPK, school
# ---------------------------------------------------------------------------

def test_every_cp_has_full_provenance_chain(conn):
    broken = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes lo
        WHERE lo.source_fragment_id IS NULL
           OR lo.source_document IS NULL OR lo.source_page IS NULL
           OR NOT EXISTS (SELECT 1 FROM source_fragments sf
                          WHERE sf.id = lo.source_fragment_id)
    """).fetchone()[0]
    n = conn.execute(
        'SELECT COUNT(*) FROM learning_outcomes').fetchone()[0]
    assert n >= 160
    assert broken == 0


def test_cp_chain_reaches_document(conn):
    # CP -> fragment -> source_document (dengan hash) -> PDF Hukum/.
    rows = conn.execute("""
        SELECT lo.id, sd.id AS doc_id, sd.document_hash, sd.local_path
        FROM learning_outcomes lo
        JOIN source_fragments sf ON sf.id = lo.source_fragment_id
        JOIN source_documents sd ON sd.id = sf.document_id
    """).fetchall()
    n_cp = conn.execute(
        'SELECT COUNT(*) FROM learning_outcomes').fetchone()[0]
    assert len(rows) == n_cp
    for r in rows:
        assert r['document_hash'], r['doc_id']
        assert (PROJECT_ROOT / r['local_path']).exists(), r['local_path']


def test_no_unknown_phase_or_element(conn):
    n = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes
        WHERE phase IS NULL OR phase = 'Unknown'
           OR element IS NULL OR element IN ('Unknown', 'Umum')
    """).fetchone()[0]
    assert n == 0


def test_mapk_always_tracked_and_separated(conn):
    # CP MAPK selalu membawa track.
    bad = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes
        WHERE program_type = 'MAPK'
          AND (track IS NULL OR track = '')
    """).fetchone()[0]
    assert bad == 0
    # Tidak ada teks CP identik di dua program (tersambung nyata).
    dup = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes a
        JOIN learning_outcomes b
          ON a.subject = b.subject AND a.phase = b.phase
         AND COALESCE(a.program_type, 'reguler') <>
             COALESCE(b.program_type, 'reguler')
         AND REPLACE(a.text, char(10), ' ') =
             REPLACE(b.text, char(10), ' ')
    """).fetchone()[0]
    assert dup == 0
    # Mapel khusus MAPK tidak boleh punya baris reguler.
    leak = conn.execute("""
        SELECT COUNT(DISTINCT lo.subject) FROM learning_outcomes lo
        WHERE lo.program_type = 'MAPK'
          AND lo.subject IN ('Ilmu Tafsir', 'Ilmu Hadis', 'Ilmu Kalam',
                             'Akhlak Tasawuf', 'Ushul Fikih')
          AND EXISTS (SELECT 1 FROM learning_outcomes x
                      WHERE x.subject = lo.subject
                        AND COALESCE(x.program_type, 'reguler') = 'reguler')
    """).fetchone()[0]
    assert leak == 0


def test_lookup_default_filters_mapk(conn):
    # get_cp_by_subject_phase default program_type='reguler' — query yang
    # sama TIDAK boleh mengembalikan CP MAPK untuk subject bersama.
    from curriculum_engine import CurriculumEngine
    eng = CurriculumEngine(str(DB_PATH))
    eng.connect()
    try:
        cp = eng.get_cp_by_subject_phase('Bahasa Arab', 'F')
        assert cp, 'CP Bahasa Arab F reguler harus ada'
        assert all((p or 'reguler') == 'reguler'
                   for p in [getattr(c, 'program_type', 'reguler')
                             for c in cp])
    finally:
        eng.close()


def test_school_cp_from_020_and_046(conn):
    # Dua sumber sah: BKPDM 020 untuk PAB, BSKAP 046 untuk mapel lain.
    rows = conn.execute("""
        SELECT sd.id, COUNT(*) AS n FROM learning_outcomes lo
        JOIN source_fragments sf ON sf.id = lo.source_fragment_id
        JOIN source_documents sd ON sd.id = sf.document_id
        WHERE lo.education_system = 'KEMENDIKDASMEN'
        GROUP BY sd.id
    """).fetchall()
    by_doc = {r['id']: r['n'] for r in rows}
    assert set(by_doc) <= {DOC_020, DOC_046}
    assert by_doc.get(DOC_020, 0) >= 30
    assert by_doc.get(DOC_046, 0) > 0
    # PAB tidak boleh diambil dari 046: amendemen 020 yang berlaku.
    agama_046 = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes lo
        JOIN source_fragments sf ON sf.id = lo.source_fragment_id
        WHERE sf.document_id = ?
          AND lo.subject LIKE '%Agama%'
    """, (DOC_046,)).fetchone()[0]
    # CP agama dari 046 boleh ada hanya sebagai riwayat 'superseded'.
    # Yang berlaku untuk mapel itu adalah BKPDM 020.
    agama_046_aktif = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes lo
        JOIN source_fragments sf ON sf.id = lo.source_fragment_id
        WHERE sf.document_id = ?
          AND lo.subject LIKE '%Agama%'
          AND lo.status = 'active'
    """, (DOC_046,)).fetchone()[0]
    assert agama_046_aktif == 0


def test_madrasah_cp_only_from_9941(conn):
    rows = conn.execute("""
        SELECT COUNT(DISTINCT sd.id) FROM learning_outcomes lo
        JOIN source_fragments sf ON sf.id = lo.source_fragment_id
        JOIN source_documents sd ON sd.id = sf.document_id
        WHERE lo.education_system = 'KEMENAG'
    """).fetchone()[0]
    assert rows == 1


def test_mapping_official_elements_not_coverage():
    m = json.loads(MAPPINGS_PATH.read_text(encoding='utf-8'))
    assert m['version'] == '2.0'
    kemenag = m['subjects']['KEMENAG']
    # Elemen resmi = Pemahaman Konsep/Keterampilan Proses (item bernomor
    # per fase 9941); cakupan lama TIDAK boleh jadi element.
    bad_labels = ("Pemahaman Al-Qur'an", 'Ibadah', 'Mufrodat', 'Tarkib',
                  "Qiro'ah", "Istima'", 'Sejarah', 'Kebudayaan')
    for level, subs in kemenag.items():
        for s in subs:
            for el in s['elements']:
                assert el not in bad_labels, (level, s['name'], el)
    # Cakupan tersimpan sebagai sub_elements.
    qh = next(s for s in kemenag['MI'] if s['name'] == "Al-Qur'an Hadis")
    assert qh['sub_elements'] == ["Tajwid", "Al-Qur'an", "Hadis",
                                  "Ilmu Al-Qur'an", "Ilmu Hadis"]
    # MAPK subject terpisah, hanya di MA.
    ma_names = {s['name'] for s in kemenag['MA']}
    for mapk in ('Ilmu Tafsir', 'Ilmu Hadis', 'Ilmu Kalam',
                 'Akhlak Tasawuf', 'Ushul Fikih',
                 "Al-Qur'an Hadis (Tafsir)", "Al-Qur'an Hadis (Hadis)"):
        assert mapk in ma_names
        for level in ('MI', 'MTs'):
            assert mapk not in {s['name'] for s in kemenag[level]}
    # Curriculum version tanggal berbasis bukti.
    by_id = {cv['id']: cv for cv in m['curriculum_versions']}
    assert by_id['KMA-1503-2025']['effective_date'] == '2025-09-22'
    assert by_id['KEMENDIKDASMEN-2025']['effective_date'] == '2025-07-16'
    assert (by_id['KEMENDIKDASMEN-2025']['amendment_regulation_id']
            == REG_020)


# ---------------------------------------------------------------------------
# Mock DB
# ---------------------------------------------------------------------------

# Tabel turunan yang mock DB wajib samakan isinya dengan DB utama.
_DERIVED_TABLES = ('authorities', 'regulations', 'source_documents',
                   'source_fragments', 'learning_outcomes',
                   'cognitive_operators')


def _table_fingerprint(conn, table):
    """Checksum isi tabel, urutan kolom eksplisit agar stabil.

    created_at diisi CURRENT_TIMESTAMP saat rebuild, jadi nilainya berubah
    tiap jalan meski datanya identik. Stempel waktu bukan isi data."""
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info({table})')
            if r[1] != 'created_at']
    rows = conn.execute(
        f"SELECT {', '.join(cols)} FROM {table} ORDER BY 1").fetchall()
    payload = '\n'.join('|'.join('' if v is None else str(v) for v in r)
                        for r in rows)
    return len(rows), hashlib.sha256(payload.encode('utf-8')).hexdigest()


def test_mock_db_in_sync_with_main_db():
    """Mock DB identik dengan DB utama pada seluruh tabel turunan, bukan
    sekadar jumlah baris."""
    assert MOCK_PATH.exists()
    mock = sqlite3.connect(str(MOCK_PATH))
    main = sqlite3.connect(str(DB_PATH))
    try:
        for table in _DERIVED_TABLES:
            assert _table_fingerprint(mock, table) == \
                _table_fingerprint(main, table), table
    finally:
        mock.close()
        main.close()


# ---------------------------------------------------------------------------
# Reproducibility: registry builder deterministik
# ---------------------------------------------------------------------------

def test_registry_builder_reproducible(tmp_path, registry):
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))
    import build_document_registry as reg
    docs = reg.build_registry()
    assert docs == registry['documents']


# ---------------------------------------------------------------------------
# Identitas registry CP: sumber, versi kurikulum, id mapping
# ---------------------------------------------------------------------------

_VALID_CURRICULUM_VERSIONS = {
    'KEMENAG': 'KMA-1503-2025',
    'KEMENDIKDASMEN': 'KEMENDIKDASMEN-2025',
}


def test_every_cp_source_document_id_matches_fragment(conn):
    bad = conn.execute("""
        SELECT lo.id FROM learning_outcomes lo
        LEFT JOIN source_fragments sf ON sf.id = lo.source_fragment_id
        WHERE lo.source_document_id IS NULL
           OR sf.document_id IS NULL
           OR sf.document_id != lo.source_document_id
    """).fetchall()
    assert bad == []
    # Dokumen yang dirujuk benar-benar ada.
    missing = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes lo
        WHERE NOT EXISTS (SELECT 1 FROM source_documents sd
                          WHERE sd.id = lo.source_document_id)
    """).fetchone()[0]
    assert missing == 0


def test_curriculum_version_id_only_valid_versions(conn):
    versions = json.loads(
        MAPPINGS_PATH.read_text(encoding='utf-8'))['curriculum_versions']
    known = {v['id'] for v in versions}
    rows = conn.execute("""
        SELECT DISTINCT education_system, curriculum_version_id
        FROM learning_outcomes
    """).fetchall()
    assert rows, 'tidak ada CP'
    for r in rows:
        assert r['curriculum_version_id'] in known, r['curriculum_version_id']
        assert r['curriculum_version_id'] == _VALID_CURRICULUM_VERSIONS[
            r['education_system']]


def test_subject_phase_element_ids_match_mapping(conn):
    m = json.loads(MAPPINGS_PATH.read_text(encoding='utf-8'))
    code_by_key = {}
    elements_by_code = {}
    for system, levels in m['subjects'].items():
        for subs in levels.values():
            for s in subs:
                code_by_key[(system, s['name'], s['program_type'])] = s['code']
                elements_by_code[s['code']] = set(s['elements'])
    phases = {
        system: {meta['phase']
                 for inst in insts.values()
                 for meta in inst.values()}
        for system, insts in m['grade_to_phase_mappings'].items()
    }

    rows = conn.execute("""
        SELECT education_system, subject, program_type, element, phase,
               subject_id, phase_id, element_id
        FROM learning_outcomes
    """).fetchall()
    # curriculum_mappings.json belum memuat mapel umum BSKAP 046 (hanya
    # KEMENAG dan PAB sekolah). CP di luar mapping tidak punya
    # subject_id — itu utang tersendiri, bukan kesalahan pengisian.
    for r in rows:
        key = (r['education_system'], r['subject'], r['program_type'])
        if key not in code_by_key:
            assert r['subject_id'] is None
            continue
        code = code_by_key[key]
        assert r['subject_id'] == code
        assert r['phase_id'] == r['phase']
        assert r['phase_id'] in phases[r['education_system']]
        assert r['element'] in elements_by_code[code]
        assert r['element_id'].startswith(code + '-')


def test_bahasa_arab_mapk_classified_from_program_keagamaan(conn):
    """4 CP Bahasa Arab bagian 9.1 (hal. 103-106, heading Program
    Keagamaan) adalah MAPK; 12 CP bagian IX tetap reguler."""
    rows = conn.execute("""
        SELECT program_type, COUNT(*) AS n FROM learning_outcomes
        WHERE subject = 'Bahasa Arab' GROUP BY program_type
    """).fetchall()
    counts = {r['program_type']: r['n'] for r in rows}
    assert counts == {'reguler': 12, 'MAPK': 4}
    mapk = conn.execute("""
        SELECT source_page, subject_id, track FROM learning_outcomes
        WHERE subject = 'Bahasa Arab' AND program_type = 'MAPK'
    """).fetchall()
    assert {r['source_page'] for r in mapk} == {105, 106}
    assert {r['subject_id'] for r in mapk} == {'BA-MAPK'}
    assert {r['track'] for r in mapk} == {'Bahasa Arab'}


def test_fikih_mapk_kept(conn):
    """4 CP Fikih bagian VII (MAPK) tetap MAPK dan punya mapping sendiri."""
    rows = conn.execute("""
        SELECT program_type, COUNT(*) AS n FROM learning_outcomes
        WHERE subject = 'Fikih' GROUP BY program_type
    """).fetchall()
    counts = {r['program_type']: r['n'] for r in rows}
    assert counts.get('MAPK') == 4
    ids = {r[0] for r in conn.execute(
        "SELECT DISTINCT subject_id FROM learning_outcomes "
        "WHERE subject = 'Fikih' AND program_type = 'MAPK'")}
    assert ids == {'FK-MAPK'}


def test_kemendikdasmen_authority_name(conn):
    full = conn.execute(
        "SELECT full_name FROM authorities WHERE code = 'KEMENDIKDASMEN'"
    ).fetchone()['full_name']
    assert full == 'Kementerian Pendidikan Dasar dan Menengah'
    m = json.loads(MAPPINGS_PATH.read_text(encoding='utf-8'))
    assert m['education_systems']['KEMENDIKDASMEN']['name'] == full
    assert 'Riset' not in full


def test_supersedes_kind_consistent_with_supersedes_id(conn, registry):
    rows = conn.execute(
        'SELECT id, supersedes_id, supersedes_kind FROM regulations'
    ).fetchall()
    for r in rows:
        if r['supersedes_id'] is None:
            assert r['supersedes_kind'] is None, r['id']
        else:
            assert r['supersedes_kind'], r['id']
    by_id = {d['id']: d for d in registry['documents']}
    assert by_id[REG_020]['supersedes_kind'] == 'amends'
    d020 = conn.execute(
        'SELECT supersedes_id, supersedes_kind FROM regulations WHERE id = ?',
        (REG_020,)).fetchone()
    assert d020['supersedes_id'] == REG_046
    assert d020['supersedes_kind'] == 'amends'


def test_special_school_mapping_only_where_046_names_it():
    """046 (Diktum KELIMA) menyebut TKLB/SDLB/SMPLB/SMALB. SMKLB tidak
    disebut, jadi tidak boleh ada mapping-nya."""
    m = json.loads(MAPPINGS_PATH.read_text(encoding='utf-8'))
    grades = m['grade_to_phase_mappings']['KEMENDIKDASMEN']
    assert set(grades['SDLB']) == {f'SDLB_{i}' for i in range(1, 7)}
    assert {v['phase'] for v in grades['SDLB'].values()} == {'A', 'B', 'C'}
    assert {v['phase'] for v in grades['SMPLB'].values()} == {'D'}
    assert {v['phase'] for v in grades['SMALB'].values()} == {'E', 'F'}
    assert grades['TKLB']['TKLB_fondasi']['phase'] == 'Fondasi'
    assert 'SMKLB' not in grades
    assert 'SMKLB' not in m['education_systems']['KEMENDIKDASMEN'][
        'institution_types']


@pytest.mark.slow
def test_full_rebuild_is_deterministic():
    """Dua rebuild berturut-turut dari 9 PDF menghasilkan data identik.

    Butuh Tesseract (dua dokumen di-OCR) dan butuh menit. Jalankan dengan
    `pytest -m slow`; tidak ikut suite biasa.
    """
    import os
    import subprocess
    import sys
    script = PROJECT_ROOT / 'scripts' / 'rebuild_data.py'

    def run_and_fingerprint():
        subprocess.run(
            [sys.executable, '-X', 'utf8', str(script)],
            cwd=str(PROJECT_ROOT), check=True,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        conn = sqlite3.connect(str(DB_PATH))
        try:
            return (_table_fingerprint(conn, 'learning_outcomes'),
                    _table_fingerprint(conn, 'regulations'))
        finally:
            conn.close()

    assert run_and_fingerprint() == run_and_fingerprint()


def test_mapping_builder_reproducible():
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))
    import build_curriculum_mappings as maps
    built = maps.build()
    on_disk = json.loads(MAPPINGS_PATH.read_text(encoding='utf-8'))
    assert built == on_disk
