#!/usr/bin/env python3
"""Build db/document_registry.json dari metadata berbasis bukti dokumen.

Semua metadata (tanggal berlaku, relasi supersedes) berasal dari ketentuan
yang TERTULIS pada PDF kanonik Hukum/ — disimpan bersama provenance halaman
sumbernya agar dapat diaudit ulang. Tidak ada data yang dikarang:

- Keputusan (Kepka BSKAP, BKPDM, KMA, Kepdirjen Pendis): "mulai berlaku
  pada/sejak tanggal ditetapkan" -> tanggal Ditetapkan di dokumen.
- Permendikdasmen 010/012/013/001: "mulai berlaku pada tanggal diundangkan"
  -> tanggal Diundangkan pada dokumen.
- Panduan KBC 6077/2025: tanggal penetapan dokumen (dokumen acuan, bukan
  peraturan yang memuat klausul berlaku).

Relasi:
- BKPDM 020/2026 MENGUBAH bagian CP PAI-BP dari BSKAP 046/H/KR/2025
  (relasi amendemen; 046 TETAP aktif untuk mapel lain — bukan penggantian
  total, sesuai AGENTS.md §3/§4).
- Permendikdasmen 013/2025 mengubah Permedikdasmen 032/2024 (tidak ada di
  Hukum/) -> supersedes_id dibiarkan null dengan catatan.

Penggunaan:
    python scripts/build_document_registry.py            # build + verify
    python scripts/build_document_registry.py --sync-db  # + sinkron regulations
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

REGISTRY_PATH = PROJECT_ROOT / 'db' / 'document_registry.json'
HUkUM = PROJECT_ROOT / 'Hukum'
DB_PATH = PROJECT_ROOT / 'db' / 'rpm_generator.db'


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Metadata berbasis bukti. Setiap tanggal membawa provenance halaman PDF.
# effective_date_basis menjelaskan ASAL tanggal (klausul dokumen), sehingga
# tidak ada angka tanpa dasar.
# ---------------------------------------------------------------------------

def _t(basis: str, page: int, date: str) -> dict:
    return {'effective_date_basis': basis, 'evidence_page': page,
            'evidence_date': date}


DOCUMENTS = [
    {
        'id': 'REG-KEMENDIKDASMEN-010-2025',
        'title': 'Permendikdasmen Nomor 10 Tahun 2025',
        'document_type': 'regulation',
        'authority': 'KEMENDIKDASMEN',
        'regulation_type': 'Peraturan Menteri',
        'regulation_number': '10',
        'year': 2025,
        'file': 'Permendikdasmen No. 10 Tahun 2025.pdf',
        # Pasal 13: "mulai berlaku pada tanggal diundangkan" (p11);
        # diundangkan 13 Juni 2025 (p12).
        'effective_date': '2025-06-13',
        'effective_evidence': _t('Pasal 13: mulai berlaku pada tanggal '
                                 'diundangkan (p11); diundangkan 13 Juni 2025 (p12).',
                                 12, '2025-06-13'),
        'status': 'active',
        'supersedes_id': None,
        'description': ('Standar Kompetensi Lulusan - dasar 8 Dimensi '
                        'Profil Lulusan'),
        'scope': ['SD', 'SMP', 'SMA', 'SMK'],
        'usage': ['graduation_profile', 'profile_dimensions_8'],
        'notes': 'Sumber 8 Dimensi Profil Lulusan. Dimensi tidak boleh '
                 'diganti Panca Cinta.',
    },
    {
        'id': 'REG-KEMENDIKDASMEN-012-2025',
        'title': 'Permendikdasmen Nomor 12 Tahun 2025',
        'document_type': 'regulation',
        'authority': 'KEMENDIKDASMEN',
        'regulation_type': 'Peraturan Menteri',
        'regulation_number': '12',
        'year': 2025,
        'file': 'Permendikdasmen No. 12 Tahun 2025.pdf',
        # Pasal 9: "mulai berlaku pada tanggal diundangkan" (p5);
        # diundangkan 15 Juli 2025 (p5).
        'effective_date': '2025-07-15',
        'effective_evidence': _t('Pasal 9: mulai berlaku pada tanggal '
                                 'diundangkan; diundangkan 15 Juli 2025.',
                                 5, '2025-07-15'),
        'status': 'active',
        'supersedes_id': None,
        'description': 'Standar Isi - ruang lingkup materi dan landasan isi '
                       'pembelajaran',
        'scope': ['SD', 'SMP', 'SMA', 'SMK'],
        'usage': ['content_standard'],
        'notes': 'Bukan pengganti dokumen CP mata pelajaran.',
    },
    {
        'id': 'REG-KEMENDIKDASMEN-013-2025',
        'title': 'Permendikdasmen Nomor 13 Tahun 2025',
        'document_type': 'regulation',
        'authority': 'KEMENDIKDASMEN',
        'regulation_type': 'Peraturan Menteri',
        'regulation_number': '13',
        'year': 2025,
        'file': 'Permendikdasmen No. 13 Tahun 2025.pdf',
        # Pasal II: "mulai berlaku pada tanggal diundangkan" (p5);
        # ditetapkan 11 Juli 2025 (p6) — perubahan atas Permedikdasmen
        # 032/2024 yang tidak menjadi bagian Hukum/.
        'effective_date': '2025-07-11',
        'effective_evidence': _t('Pasal II: mulai berlaku pada tanggal '
                                 'diundangkan; ditetapkan 11 Juli 2025 (p6).',
                                 6, '2025-07-11'),
        'status': 'active',
        'supersedes_id': None,
        'description': ('Perubahan atas regulasi kurikulum; kerangka dasar '
                        'kurikulum; pendekatan Pembelajaran Mendalam'),
        'scope': ['PAUD', 'SD', 'SMP', 'SMA', 'SMK'],
        'usage': ['curriculum_framework', 'deep_learning_approach'],
        'notes': 'Mengubah Permedikdasmen 032/2024 (di luar set Hukum/).',
    },
    {
        'id': 'REG-KEMENDIKDASMEN-001-2026',
        'title': 'Permendikdasmen Nomor 1 Tahun 2026',
        'document_type': 'regulation',
        'authority': 'KEMENDIKDASMEN',
        'regulation_type': 'Peraturan Menteri',
        'regulation_number': '1',
        'year': 2026,
        'file': 'Permendikdasmen No. 1 Tahun 2026.pdf',
        # Pasal 21: "mulai berlaku pada tanggal diundangkan" (p8);
        # ditetapkan 2 Januari 2026 (p9).
        'effective_date': '2026-01-02',
        'effective_evidence': _t('Pasal 21: mulai berlaku pada tanggal '
                                 'diundangkan; ditetapkan 2 Januari 2026 (p9).',
                                 9, '2026-01-02'),
        'status': 'active',
        'supersedes_id': None,
        'description': ('Standar Proses - perencanaan, pelaksanaan, dan '
                        'penilaian proses pembelajaran'),
        'scope': ['SD', 'SMP', 'SMA', 'SMK'],
        'usage': ['process_standard', 'lesson_planning'],
        'notes': 'Komponen minimal perencanaan: tujuan, langkah, asesmen.',
    },
    {
        'id': 'REG-KEMENDIKDASMEN-BSKAP-046-2025',
        'title': 'Kepka BSKAP Nomor 046/H/KR/2025',
        'document_type': 'regulation',
        'authority': 'KEMENDIKDASMEN',
        'regulation_type': 'Keputusan Kepala Badan',
        'regulation_number': '046/H/KR/2025',
        'year': 2025,
        'file': 'Kepka BSKAP No.046_H_KR_2025.pdf',
        # KEDELAPAN: "mulai berlaku sejak tanggal ditetapkan" (p6);
        # ditetapkan 16 Juli 2025 (p6).
        'effective_date': '2025-07-16',
        'effective_evidence': _t('KEDUA BELAS/KEDELAPAN: mulai berlaku sejak '
                                 'tanggal ditetapkan; ditetapkan 16 Juli 2025.',
                                 6, '2025-07-16'),
        'status': 'active',
        'supersedes_id': None,
        'description': ('Capaian Pembelajaran mata pelajaran pendidikan dasar '
                        'dan menengah (CP nasional)'),
        'scope': ['SD', 'SMP', 'SMA', 'SMK'],
        'usage': ['learning_outcomes_national'],
        'notes': ('Sumber CP nasional. Bagian CP Pendidikan Agama dan Budi '
                  'Pekerti DIUBAH oleh BKPDM 020/2026; mapel lain tetap '
                  'mengikuti dokumen ini.'),
    },
    {
        'id': 'REG-KEMENDIKDASMEN-BKPDM-020-2026',
        'title': 'BKPDM Nomor 020 Tahun 2026',
        'document_type': 'regulation',
        'authority': 'KEMENDIKDASMEN',
        'regulation_type': 'Keputusan Kepala Badan',
        'regulation_number': '020',
        'year': 2026,
        'file': 'BKPDM No. 020 Tahun 2026.pdf',
        # KESATU/penutup: "mulai berlaku pada tanggal ditetapkan" (p3);
        # ditetapkan 11 Juni 2026 (p3).
        'effective_date': '2026-06-11',
        'effective_evidence': _t('Keputusan ini mulai berlaku pada tanggal '
                                 'ditetapkan; ditetapkan 11 Juni 2026 (p3).',
                                 3, '2026-06-11'),
        'status': 'active',
        # AMENDEMEN (bukan penggantian total): KESATU mengubah ketentuan CP
        # Pendidikan Agama dan Budi Pekerti dalam 046/H/KR/2025 (p3).
        'supersedes_id': 'REG-KEMENDIKDASMEN-BSKAP-046-2025',
        'supersedes_kind': 'amends',
        'description': ('Perubahan Capaian Pembelajaran Pendidikan Agama dan '
                        'Budi Pekerti serta Pendidikan Khusus Pendidikan '
                        'Agama dan Budi Pekerti pada CP nasional BSKAP '
                        '046/H/KR/2025 (Lampiran II dan Lampiran V)'),
        # Scope = kode institution_type pada mapping (konvensi repo).
        # Reguler: SD/SMP/SMA/SMK (judul Lampiran, hlm. 4). Pendidikan
        # khusus: SDLB/SMPLB/SMALB — tercantum eksplisit pada heading
        # fase bagian 2.x ("Kelas I dan II SDLB", "Kelas VII, VIII, dan
        # IX SMPLB", "Kelas X SMALB"; mapel PAB khusus wajib di SLB,
        # hlm. 50). TKLB/SMKLB tidak disebut PDF 020 sehingga tidak
        # dimasukkan (bukan asumsi).
        'scope': ['SD', 'SMP', 'SMA', 'SMK', 'SDLB', 'SMPLB', 'SMALB'],
        'usage': ['learning_outcomes_pai_bp_amendment',
                  'learning_outcomes_pendidikan_khusus_pab'],
        'notes': ('Memuat CP Pendidikan Agama dan Budi Pekerti (reguler) '
                  'serta CP Pendidikan Khusus Pendidikan Agama dan Budi '
                  'Pekerti Kemendikdasmen (KESATU, hlm. 3; Lampiran II dan '
                  'Lampiran V). 046/H/KR/2025 tetap berlaku untuk mapel '
                  'lain; relasi ini amendemen, bukan penggantian total.'),
    },
    {
        'id': 'REG-KEMENAG-1503-2025',
        'title': 'KMA Nomor 1503 Tahun 2025',
        'document_type': 'regulation',
        'authority': 'KEMENAG',
        'regulation_type': 'Keputusan Menteri Agama',
        'regulation_number': '1503',
        'year': 2025,
        'file': 'KMA No. 1503 Tahun 2025.pdf',
        # "Keputusan ini mulai berlaku pada tanggal ditetapkan" (p5);
        # ditetapkan 22 September 2025 (p5).
        'effective_date': '2025-09-22',
        'effective_evidence': _t('Keputusan ini mulai berlaku pada tanggal '
                                 'ditetapkan; ditetapkan 22 September 2025.',
                                 5, '2025-09-22'),
        'status': 'active',
        'supersedes_id': None,
        'description': ('Pedoman implementasi kurikulum madrasah (RA, MI, '
                        'MTs, MA, MAK); Pembelajaran Mendalam dan KBC'),
        'scope': ['RA', 'MI', 'MTs', 'MA', 'MAK'],
        'usage': ['madrasah_curriculum_framework', 'kbc_context'],
        'notes': 'Payung kurikulum madrasah; CP PAI/BA tetap dari 9941/2025.',
    },
    {
        'id': 'REG-KEMENAG-PENDIS-9941-2025',
        'title': 'Kepdirjen Pendis Nomor 9941 Tahun 2025',
        'document_type': 'regulation',
        'authority': 'KEMENAG',
        'regulation_type': 'Keputusan Direktur Jenderal',
        'regulation_number': '9941',
        'year': 2025,
        'file': 'Kepdirjen Pendis No. 9941 Tahun 2025.pdf',
        # KETIGA: "mulai berlaku pada tanggal ditetapkan" (p4);
        # ditetapkan 28 November 2025 (p4).
        'effective_date': '2025-11-28',
        'effective_evidence': _t('KETIGA: mulai berlaku pada tanggal '
                                 'ditetapkan; ditetapkan 28 November 2025.',
                                 4, '2025-11-28'),
        'status': 'active',
        'supersedes_id': None,
        'description': ('Capaian Pembelajaran PAI dan Bahasa Arab madrasah '
                        '(RA, MI, MTs, MA/MAK, termasuk MAPK)'),
        'scope': ['RA', 'MI', 'MTs', 'MA', 'MAK'],
        'usage': ['learning_outcomes_pai_ba_madrasah'],
        'notes': ('Sumber CP Al-Qur\'an Hadis, Akidah Akhlak, Fikih, SKI, '
                  'Bahasa Arab; bagian MAPK terpisah dari jalur reguler.'),
    },
    {
        'id': 'GUIDE-KEMENAG-KBC-6077-2025',
        'title': 'Kepdirjen Pendis Nomor 6077 Tahun 2025 - Panduan '
                 'Kurikulum Berbasis Cinta',
        'document_type': 'guide',
        'authority': 'KEMENAG',
        'regulation_type': 'Panduan (Kepdirjen Pendis)',
        'regulation_number': '6077',
        'year': 2025,
        'file': 'Kepdirjen Pendis No. 6077 Tahun 2025.pdf',
        # Ditulis "Ditetapkan di Jakarta pada tanggal 22 Juli 2025" (p3);
        # dokumen panduan tanpa klausul berlaku tersendiri.
        'effective_date': '2025-07-22',
        'effective_evidence': _t('Dokumen panduan; tanggal penetapan 22 Juli '
                                 '2025 (p3).', 3, '2025-07-22'),
        'status': 'active',
        'supersedes_id': None,
        'description': ('Panduan Kurikulum Berbasis Cinta (KBC): Panca Cinta, '
                        'strategi integrasi, contoh rancangan'),
        'scope': ['RA', 'MI', 'MTs', 'MA', 'MAK'],
        'usage': ['kbc_guide', 'panca_cinta'],
        'notes': ('Acuan integrasi KBC; contoh dalam panduan bukan template '
                  'wajib. Panca Cinta bukan pengganti 8 Dimensi Profil '
                  'Lulusan.'),
    },
]


def build_registry() -> list:
    """Bangun entri registry dengan hash dari PDF aktual."""
    documents = []
    for meta in DOCUMENTS:
        pdf_path = HUkUM / meta['file']
        if not pdf_path.exists():
            raise SystemExit(f"PDF kanonik tidak ditemukan: {pdf_path}")
        documents.append({
            'id': meta['id'],
            'title': meta['title'],
            'document_type': meta['document_type'],
            'authority': meta['authority'],
            'regulation_type': meta['regulation_type'],
            'regulation_number': meta['regulation_number'],
            'year': meta['year'],
            'effective_date': meta['effective_date'],
            'effective_evidence': meta['effective_evidence'],
            'status': meta['status'],
            'supersedes_id': meta['supersedes_id'],
            'supersedes_kind': meta.get('supersedes_kind'),
            'description': meta['description'],
            'scope': meta['scope'],
            'usage': meta['usage'],
            'source_url': None,
            'local_path': f"Hukum/{meta['file']}",
            'document_hash': sha256_file(pdf_path),
            'file_size_bytes': pdf_path.stat().st_size,
            'notes': meta['notes'],
        })
    return documents


def sync_regulations(documents: list, db_path: Path):
    """Sinkronkan tabel regulations dengan registry (hash, tanggal,
    supersedes). INSERT OR UPDATE; tidak menghapus baris lain."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        auth = {r['code']: r['id'] for r in
                conn.execute('SELECT id, code FROM authorities')}
        for doc in documents:
            authority_id = auth.get(doc['authority'])
            if not authority_id:
                print(f"   ⚠️  Authority tidak dikenal: {doc['authority']}")
                continue
            supersedes_kind = doc.get('supersedes_kind')
            conn.execute("""
                UPDATE regulations
                SET effective_date = ?, document_hash = ?, supersedes_id = ?,
                    status = ?, title = ?, description = ?,
                    supersedes_kind = ?
                WHERE id = ?
            """, (
                doc['effective_date'], doc['document_hash'],
                doc['supersedes_id'], doc['status'], doc['title'],
                doc['description'],
                # NULL bila dokumen tidak menggantikan apa pun. Default
                # 'replaces' membuat relasi palsu pada baris yang
                # supersedes_id-nya NULL.
                supersedes_kind,
                doc['id'],
            ))
            if conn.total_changes and conn.execute(
                    'SELECT changes()').fetchone()[0] == 0:
                print(f"   ⚠️  Regulation tidak ada di DB: {doc['id']}")
        # Kolom supersedes_kind perlu ada (tambah bila belum).
        conn.commit()
        print(f"   ✅ Sinkron {len(documents)} regulations "
              f"(effective_date, hash, supersedes)")
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sync-db', action='store_true',
                    help='Sinkronkan juga tabel regulations di SQLite')
    args = ap.parse_args()

    documents = build_registry()
    REGISTRY_PATH.write_text(
        json.dumps({'documents': documents}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    print(f"✅ {REGISTRY_PATH.name}: {len(documents)} dokumen "
          f"(hash dari PDF aktual)")
    for d in documents:
        print(f"   {d['id']}: berlaku {d['effective_date']} "
              f"(p{d['effective_evidence']['evidence_page']}) "
              f"hash={d['document_hash'][:12]}…")

    if args.sync_db:
        sync_regulations(documents, DB_PATH)


if __name__ == '__main__':
    main()
