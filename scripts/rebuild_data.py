#!/usr/bin/env python3
"""Rebuild PENUH seluruh data turunan dari 9 PDF kanonik di Hukum/.

Tahapan (reproducible — hasil identik jika dijalankan ulang dari PDF):

  1. Hapus data turunan lama: rpm_generator.db, extracted_fragments.json,
     document_registry.json, mock_rpm.db. PDF Hukum/ TIDAK disentuh.
  2. db/document_registry.json  (scripts/build_document_registry.py —
     metadata berbasis bukti + hash SHA-256 PDF aktual).
  3. db/extracted_fragments.json (src/pdf_extraction.py — fragmen per
     halaman dengan extraction_method per fragment + text_hash).
  4. db/rpm_generator.db        (src/db_initialization.py — schema,
     authorities, regulations dari registry, fragments dari ekstraksi).
  5. db/curriculum_mappings.json (scripts/build_curriculum_mappings.py —
     elemen resmi 9941/2025 + PAB BKPDM 020/2026).
  6. learning_outcomes          (src/curriculum_engine.py — parser CP
     madrasah 9941 + sekolah BKPDM 020, provenance sampai fragment).
  7. db/mock_rpm.db             (salinan DB utama untuk UI/test mock).
  8. Verifikasi invarian audit (lihat laporan akhir).

Penggunaan:
    python scripts/rebuild_data.py            # rebuild + verifikasi
    python scripts/rebuild_data.py --verify   # verifikasi saja
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))
sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))

DB_PATH = PROJECT_ROOT / 'db' / 'rpm_generator.db'
MOCK_PATH = PROJECT_ROOT / 'db' / 'mock_rpm.db'
REGISTRY_PATH = PROJECT_ROOT / 'db' / 'document_registry.json'
EXTRACTION_PATH = PROJECT_ROOT / 'db' / 'extracted_fragments.json'
MAPPINGS_PATH = PROJECT_ROOT / 'db' / 'curriculum_mappings.json'
HUkUM = PROJECT_ROOT / 'Hukum'

# regulations/registry memakai id REG-*; source_documents memakai
# id DOC-REG-* (lihat populate_regulations_from_registry).
DOC_9941 = 'DOC-REG-KEMENAG-PENDIS-9941-2025'
DOC_046 = 'DOC-REG-KEMENDIKDASMEN-BSKAP-046-2025'
DOC_020 = 'DOC-REG-KEMENDIKDASMEN-BKPDM-020-2026'
REG_9941 = 'REG-KEMENAG-PENDIS-9941-2025'
REG_046 = 'REG-KEMENDIKDASMEN-BSKAP-046-2025'
REG_020 = 'REG-KEMENDIKDASMEN-BKPDM-020-2026'


def step(n, title):
    print(f"\n{'=' * 62}\n[{n}/8] {title}\n{'=' * 62}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Rebuild
# ---------------------------------------------------------------------------

def rebuild():
    step(1, 'Hapus data turunan lama')
    removed = []
    for p in (DB_PATH, MOCK_PATH, REGISTRY_PATH, EXTRACTION_PATH):
        if p.exists():
            p.unlink()
            removed.append(p.name)
    print(f"   🗑️  Dihapus: {', '.join(removed) or '(tidak ada)'}")
    print(f"   🔒 PDF kanonik {HUkUM.name}/ tidak disentuh "
          f"({len(list(HUkUM.glob('*.pdf')))} PDF)")

    step(2, 'document_registry.json (metadata berbasis bukti + hash PDF)')
    import build_document_registry as reg
    docs = reg.build_registry()
    reg.REGISTRY_PATH.write_text(
        json.dumps({'documents': docs}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    print(f"   ✅ registry: {len(docs)} dokumen "
          f"(hash dari PDF aktual)")

    step(3, 'extracted_fragments.json (ekstraksi 9 PDF)')
    from pdf_extraction import PDFExtractionPipeline
    pipeline = PDFExtractionPipeline(str(HUkUM))
    pipeline.save_results(str(EXTRACTION_PATH))

    step(4, 'rpm_generator.db (schema, authorities, regulations, fragments)')
    from db_initialization import DatabaseInitializer
    initializer = DatabaseInitializer(str(DB_PATH))
    initializer.initialize_and_populate(str(REGISTRY_PATH),
                                        str(EXTRACTION_PATH))

    step(5, 'curriculum_mappings.json (elemen resmi, MAPK terpisah)')
    import build_curriculum_mappings as maps
    maps.main()

    step(6, 'learning_outcomes (parser CP madrasah + sekolah)')
    from curriculum_engine import CurriculumEngine
    engine = CurriculumEngine(str(DB_PATH))
    engine.connect()
    cp_entries = engine.extract_all_cp()
    engine.populate_cp_table(cp_entries)
    engine.close()

    # Mappings 046 di langkah 5 dibaca saat learning_outcomes masih
    # kosong, sehingga subject_id/element_id CP 046 belum terisi.
    # Bangun ulang mappings dari CP yang sudah ter-populate, lalu
    # sinkronkan kembali kolom ID (teks/provenance CP tidak berubah).
    maps.main()
    id_engine = CurriculumEngine(str(DB_PATH))
    id_engine.connect()
    n_ids = id_engine.refresh_cp_registry_ids()
    id_engine.close()
    print(f"   ✅ registry IDs disinkron untuk {n_ids} CP")

    step(7, 'mock_rpm.db (salinan DB utama untuk UI/test mock)')
    shutil.copyfile(DB_PATH, MOCK_PATH)
    print(f"   ✅ {MOCK_PATH.name} dibuat dari {DB_PATH.name}")


# ---------------------------------------------------------------------------
# Verifikasi invarian
# ---------------------------------------------------------------------------

def verify() -> bool:
    step(8, 'Verifikasi invarian audit')
    ok = True
    fail = []

    def check(name, cond, detail=''):
        nonlocal ok
        mark = '✅' if cond else '❌'
        print(f"   {mark} {name}" + (f" — {detail}" if detail else ''))
        if not cond:
            ok = False
            fail.append(name)

    registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
    docs = registry['documents']
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # --- 9 dokumen terdaftar
    pdfs = sorted(p.name for p in HUkUM.glob('*.pdf'))
    check('9 PDF di Hukum/', len(pdfs) == 9, f'{len(pdfs)} PDF')
    check('9 entri registry', len(docs) == 9, f'{len(docs)} entri')

    # --- hash registry == PDF aktual == source_documents
    reg_by_id = {d['id']: d for d in docs}
    hash_bad = []
    for d in docs:
        actual = sha256_file(PROJECT_ROOT / d['local_path'])
        if actual != d['document_hash']:
            hash_bad.append(d['id'])
    check('hash registry == PDF aktual', not hash_bad, str(hash_bad))
    sd_bad = []
    for row in conn.execute('SELECT id, document_hash FROM source_documents'):
        reg = reg_by_id.get(row['id'])
        if reg and row['document_hash'] != reg['document_hash']:
            sd_bad.append(row['id'])
    check('hash source_documents == registry', not sd_bad, str(sd_bad))
    regrows = {r['id']: r for r in conn.execute(
        'SELECT id, document_hash, effective_date, supersedes_id '
        'FROM regulations')}
    rg_bad = [rid for rid, r in regrows.items()
              if reg_by_id.get(rid)
              and (r['document_hash'] != reg_by_id[rid]['document_hash']
                   or r['effective_date'] != reg_by_id[rid]['effective_date'])]
    check('regulations DB == registry (hash+tanggal)', not rg_bad, str(rg_bad))

    # --- effective_date bukan default & berbasis bukti
    no_ev = [d['id'] for d in docs
             if not d.get('effective_evidence', {}).get('evidence_page')]
    check('effective_date berbasis bukti halaman', not no_ev, str(no_ev))

    # --- supersedes: 020 amends 046
    d020 = reg_by_id.get(REG_020, {})
    check('supersedes 020 -> 046 (amendemen)',
          d020.get('supersedes_id') == REG_046
          and d020.get('supersedes_kind') == 'amends')
    check('046 tetap aktif (bukan tergantikan)',
          reg_by_id.get(REG_046, {}).get('status') == 'active')

    # --- fragments: extraction_method + text_hash
    n_frag = conn.execute(
        'SELECT COUNT(*) FROM source_fragments').fetchone()[0]
    n_nomethod = conn.execute(
        "SELECT COUNT(*) FROM source_fragments "
        "WHERE COALESCE(extraction_method, '') = ''").fetchone()[0]
    check('extraction_method per fragment terisi', n_nomethod == 0,
          f'{n_nomethod}/{n_frag} kosong')
    mismatch = 0
    for row in conn.execute('SELECT text, text_hash FROM source_fragments'):
        actual = hashlib.sha256((row['text'] or '').encode('utf-8')).hexdigest()
        if actual != row['text_hash']:
            mismatch += 1
    check('text_hash mismatch = 0', mismatch == 0,
          f'{mismatch} mismatch dari {n_frag} fragmen')

    # --- CP: provenance penuh
    n_cp = conn.execute('SELECT COUNT(*) FROM learning_outcomes').fetchone()[0]
    cp_broken = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes lo
        WHERE lo.source_fragment_id IS NULL
           OR NOT EXISTS (SELECT 1 FROM source_fragments sf
                          WHERE sf.id = lo.source_fragment_id)
    """).fetchone()[0]
    check('semua CP terhubung source_fragment', cp_broken == 0,
          f'{cp_broken}/{n_cp} putus')
    cp_nodoc = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes lo
        WHERE lo.source_document IS NULL OR lo.source_page IS NULL
    """).fetchone()[0]
    check('semua CP membawa document+page', cp_nodoc == 0)

    # --- identitas registry: sumber, versi kurikulum, id mapping
    cp_baddoc = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes lo
        WHERE lo.source_document_id IS NULL
           OR NOT EXISTS (SELECT 1 FROM source_fragments sf
                          WHERE sf.id = lo.source_fragment_id
                            AND sf.document_id = lo.source_document_id)
    """).fetchone()[0]
    check('source_document_id = document_id fragmen sumber', cp_baddoc == 0,
          f'{cp_baddoc}/{n_cp} salah')
    bad_ver = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes
        WHERE (education_system = 'KEMENAG'
               AND curriculum_version_id != 'KMA-1503-2025')
           OR (education_system = 'KEMENDIKDASMEN'
               AND curriculum_version_id != 'KEMENDIKDASMEN-2025')
    """).fetchone()[0]
    check('curriculum_version_id hanya versi kurikulum sah', bad_ver == 0,
          f'{bad_ver} CP pakai id lain')
    no_ids = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes
        WHERE subject_id IS NULL OR phase_id IS NULL OR element_id IS NULL
    """).fetchone()[0]
    # curriculum_mappings.json baru memuat mapel KEMENAG dan PAB sekolah.
    # CP mapel umum BSKAP 046 belum punya entri mapping (technical debt,
    # lihat HANDOFF_PROGRESS.md §9.1), jadi subject_id-nya kosong. Yang
    # wajib terisi: CP yang mapelnya SUDAH ada di mapping.
    no_ids_mapped = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes
        WHERE source_document != 'BSKAP-046/H/KR/2025'
          AND (subject_id IS NULL OR phase_id IS NULL OR element_id IS NULL)
    """).fetchone()[0]
    check('subject_id/phase_id/element_id terisi untuk mapel yang ada di mapping',
          no_ids_mapped == 0,
          f'{no_ids_mapped} kosong di luar 046; {no_ids}/{n_cp} kosong total')

    # --- supersedes_kind konsisten & nama otoritas
    kind_bad = conn.execute("""
        SELECT COUNT(*) FROM regulations
        WHERE (supersedes_id IS NULL AND supersedes_kind IS NOT NULL)
           OR (supersedes_id IS NOT NULL AND supersedes_kind IS NULL)
    """).fetchone()[0]
    check('supersedes_kind NULL persis bila supersedes_id NULL',
          kind_bad == 0, f'{kind_bad} baris')
    full_name = conn.execute(
        "SELECT full_name FROM authorities WHERE code = 'KEMENDIKDASMEN'"
    ).fetchone()
    check('nama kementerian Kemendikdasmen sesuai dokumen',
          full_name is not None and full_name['full_name']
          == 'Kementerian Pendidikan Dasar dan Menengah',
          repr(full_name['full_name']) if full_name else 'tidak ada')
    cp_fragdoc = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes lo
        JOIN source_fragments sf ON sf.id = lo.source_fragment_id
        JOIN source_documents sd ON sd.id = sf.document_id
        WHERE sd.document_hash IS NULL
    """).fetchone()[0]
    check('rantai CP -> fragment -> document utuh', cp_fragdoc == 0)

    # --- MAPK terpisah dari reguler
    mix = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes
        WHERE program_type = 'MAPK'
          AND (track IS NULL OR track = '')
    """).fetchone()[0]
    check('CP MAPK selalu membawa track', mix == 0)
    # Subject sama boleh ada di dua program (dokumen memang memuat
    # Bahasa Arab reguler bagian IX dan Bahasa Arab MAPK 9.1 dengan CP
    # berbeda) - yang dilarang adalah TERSAMBURNYA: teks CP identik di
    # dua program, atau CP MAPK bocor ke lookup reguler.
    dup_cross = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes a
        JOIN learning_outcomes b
          ON a.subject = b.subject AND a.phase = b.phase
         AND COALESCE(a.program_type, 'reguler') <>
             COALESCE(b.program_type, 'reguler')
         AND REPLACE(a.text, char(10), ' ') =
             REPLACE(b.text, char(10), ' ')
    """).fetchone()[0]
    check('tidak ada teks CP identik lintas program', dup_cross == 0)
    mapk_only = conn.execute("""
        SELECT COUNT(DISTINCT lo.subject) FROM learning_outcomes lo
        WHERE lo.program_type = 'MAPK'
          AND lo.subject IN (
              'Ilmu Tafsir', 'Ilmu Hadis', 'Ilmu Kalam',
              'Akhlak Tasawuf', 'Ushul Fikih')
          AND EXISTS (SELECT 1 FROM learning_outcomes x
                      WHERE x.subject = lo.subject
                        AND COALESCE(x.program_type, 'reguler')
                            = 'reguler')
    """).fetchone()[0]
    check('mapel khusus MAPK tanpa baris reguler', mapk_only == 0)
    n_mapk = conn.execute(
        "SELECT COUNT(*) FROM learning_outcomes "
        "WHERE program_type = 'MAPK'").fetchone()[0]
    print(f"   ℹ️  CP MAPK: {n_mapk} dari {n_cp}")

    # --- CP 020 (sekolah) terpisah dari 046
    n_school = conn.execute(
        "SELECT COUNT(*) FROM learning_outcomes "
        "WHERE education_system = 'KEMENDIKDASMEN'").fetchone()[0]
    school_doc = conn.execute("""
        SELECT sd.id, COUNT(*) FROM learning_outcomes lo
        JOIN source_fragments sf ON sf.id = lo.source_fragment_id
        JOIN source_documents sd ON sd.id = sf.document_id
        WHERE lo.education_system = 'KEMENDIKDASMEN'
        GROUP BY sd.id
    """).fetchall()
    # Dua sumber sah untuk CP sekolah: BKPDM 020 (hanya PAB) dan
    # BSKAP 046 (mapel lain). Tidak boleh ada sumber ketiga.
    school_ids = {r[0] for r in school_doc}
    check('CP sekolah hanya dari BKPDM 020 dan BSKAP 046',
          school_ids <= {DOC_020, DOC_046} and DOC_020 in school_ids,
          str([tuple(r) for r in school_doc]))
    mad_doc = conn.execute("""
        SELECT sd.id, COUNT(*) FROM learning_outcomes lo
        JOIN source_fragments sf ON sf.id = lo.source_fragment_id
        JOIN source_documents sd ON sd.id = sf.document_id
        WHERE lo.education_system = 'KEMENAG'
        GROUP BY sd.id
    """).fetchall()
    check('CP madrasah hanya dari 9941/2025',
          len(mad_doc) == 1 and mad_doc[0][0] == DOC_9941,
          str([tuple(r) for r in mad_doc]))
    # 046 adalah sumber CP mapel umum, termasuk Pendidikan Agama edisi
    # 046 yang berstatus 'superseded' (riwayat, lihat _cp046_amended).
    # Yang berlaku untuk mapel itu adalah BKPDM 020, jadi 046 tidak boleh
    # menyumbang CP agama yang masih 'active'.
    n_046_pab = conn.execute("""
        SELECT COUNT(*) FROM learning_outcomes lo
        JOIN source_fragments sf ON sf.id = lo.source_fragment_id
        WHERE sf.document_id = ?
          AND lo.subject LIKE '%Agama%'
          AND lo.status = 'active'
    """, (DOC_046,)).fetchone()[0]
    check('046 tidak memuat CP Pendidikan Agama yang masih berlaku',
          n_046_pab == 0, f'{n_046_pab} CP agama active dari 046')

    # --- Unknown & label
    n_unknown_phase = conn.execute(
        "SELECT COUNT(*) FROM learning_outcomes "
        "WHERE phase IS NULL OR phase = 'Unknown'").fetchone()[0]
    check('CP tanpa fase = 0', n_unknown_phase == 0)
    n_unknown_elem = conn.execute(
        "SELECT COUNT(*) FROM learning_outcomes "
        "WHERE element IS NULL OR element = 'Unknown' "
        "OR element = 'Umum'").fetchone()[0]
    check('CP element Unknown/Umum = 0', n_unknown_elem == 0)

    # --- mock DB sinkron
    if MOCK_PATH.exists():
        mock = sqlite3.connect(str(MOCK_PATH))
        mock.row_factory = sqlite3.Row
        mf = mock.execute(
            'SELECT COUNT(*) FROM source_fragments').fetchone()[0]
        mc = mock.execute(
            'SELECT COUNT(*) FROM learning_outcomes').fetchone()[0]
        check('mock DB sinkron dengan DB utama',
              mf == n_frag and mc == n_cp,
              f'frag {mf}/{n_frag}, cp {mc}/{n_cp}')
        mock.close()
    else:
        check('mock DB ada', False)

    conn.close()

    print(f"\n{'✅ VERIFIKASI LOLOS' if ok else '❌ VERIFIKASI GAGAL'}"
          + (f" — {fail}" if fail else ''))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true',
                    help='Verifikasi invarian saja tanpa rebuild')
    args = ap.parse_args()
    if not args.verify:
        rebuild()
    ok = verify()
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
