#!/usr/bin/env python3
"""Bangun db/curriculum_mappings.json dari struktur RESMI dokumen sumber.

Sumber kebenaran (dibaca langsung dari PDF Hukum/, provenance halaman):

- Kepdirjen Pendis 9941/2025: elemen RESMI setiap mapel = item bernomor
  per fase ("1.1 Pemahaman Konsep" / "1.2 Keterampilan Proses"; Bahasa
  Arab: "Komponen Bahasa" / "Keterampilan Bahasa"; RA: tiga elemen
  stimulasi). Cakupan materi (Tajwid, Ibadah, Al-Qur'an, ...) adalah
  SUB-ELEMEN pada tabel elemen per mapel - BUKAN elemen (§2 tugas).
  Bagian III/V/7.2/9.1 adalah jalur MAPK - subject terpisah dari reguler.
- BKPDM 020/2026 (amendemen CP PAB atas BSKAP 046/H/KR/2025): elemen
  Pendidikan Agama dan Budi Pekerti = Al-Qur'an Hadis, Akidah, Akhlak,
  Fikih, Sejarah Peradaban Islam (lampiran CP p6-9).

Struktur lama (elemen = "Pemahaman Al-Qur'an"/"Ibadah"/"Mufrodat"/...)
adalah konflasi cakupan sebagai elemen - dihapus, tidak dipertahankan.

Penggunaan:
    python scripts/build_curriculum_mappings.py
"""
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAPPINGS_PATH = PROJECT_ROOT / 'db' / 'curriculum_mappings.json'

# Elemen resmi standar (item bernomor per fase di 9941/2025).
_STD_ELEMENTS = ['Pemahaman Konsep', 'Keterampilan Proses']
_BA_ELEMENTS = ['Komponen Bahasa', 'Keterampilan Bahasa']
_RA_ELEMENTS = ['Nilai Agama dan Budi Pekerti',
                'Jati Diri',
                'Dasar-Dasar Literasi, Matematika, Sains, Teknologi, '
                'Rekayasa, dan Seni']
# Elemen PAB sekolah (BKPDM 020/2026, amendemen CP 046/H/KR/2025).
_PAB_ELEMENTS = ["Al-Qur'an Hadis", 'Akidah', 'Akhlak', 'Fikih',
                 'Sejarah Peradaban Islam']

# Elemen agama lain di BKPDM 020/2026 (bagian 1.2-1.6 reguler dan
# 2.1-2.6 pendidikan khusus). Diambil dari label item CP di lampiran.
_RELIGION_SUBJECTS = [
    ('PAB-K', 'Pendidikan Agama Kristen dan Budi Pekerti',
     ['Allah Berkarya', 'Manusia dan Nilai-nilai Kristiani',
      'Gereja dan Masyarakat Majemuk', 'Alam dan Lingkungan Hidup']),
    ('PAB-KA', 'Pendidikan Agama Katolik dan Budi Pekerti',
     ['Pribadi Murid', 'Yesus Kristus', 'Gereja', 'Masyarakat']),
    ('PAB-H', 'Pendidikan Agama Hindu dan Budi Pekerti',
     ['Kitab Suci Weda', 'Sraddha dan Bhakti', 'Susila', 'Acara',
      'Sejarah Agama Hindu']),
    ('PAB-B', 'Pendidikan Agama Buddha dan Budi Pekerti',
     ['Sejarah', 'Ritual', 'Etika']),
    ('PAB-KH', 'Pendidikan Agama Khonghucu dan Budi Pekerti',
     ['Sejarah Suci', 'Kitab Suci', 'Keimanan', 'Tata Ibadah',
      'Perilaku Junzi']),
    ('PK-PAB-I', 'Pendidikan Khusus Agama Islam dan Budi Pekerti',
     ["Al-Qur'an Hadis", 'Akidah', 'Akhlak', 'Fikih',
      'Sejarah Peradaban Islam']),
    ('PK-PAB-K', 'Pendidikan Khusus Agama Kristen dan Budi Pekerti',
     ['Allah Berkarya', 'Manusia dan Nilai-nilai Kristiani',
      'Gereja dan Masyarakat Majemuk', 'Alam dan Lingkungan Hidup']),
    ('PK-PAB-KA', 'Pendidikan Khusus Agama Katolik dan Budi Pekerti',
     ['Pribadi Murid', 'Yesus Kristus', 'Gereja', 'Masyarakat']),
    ('PK-PAB-H', 'Pendidikan Khusus Agama Hindu dan Budi Pekerti',
     ['Kitab Suci Weda', 'Sraddha dan Bhakti', 'Susila', 'Acara',
      'Sejarah Agama Hindu']),
    ('PK-PAB-B', 'Pendidikan Khusus Agama Buddha dan Budi Pekerti',
     ['Sejarah', 'Ritual', 'Etika']),
    ('PK-PAB-KH', 'Pendidikan Khusus Agama Khonghucu dan Budi Pekerti',
     ['Sejarah Suci', 'Kitab Suci', 'Keimanan', 'Tata Ibadah',
      'Perilaku Junzi']),
]

# Cakupan/substansi per mapel (tabel elemen 9941/2025) - sub_element,
# bukan element. Nama = label persis dokumen.
_COVERAGE = {
    "Al-Qur'an Hadis": ["Tajwid", "Al-Qur'an", "Hadis",
                        "Ilmu Al-Qur'an", "Ilmu Hadis"],
    'Akidah Akhlak': ['Akidah', 'Akhlak', 'Adab', 'Kisah Keteladanan'],
    'Fikih': ['Ibadah', 'Muamalah'],
}


def _subj(code: str, name: str, elements: list,
          program: str = 'reguler',
          sub_elements: list = None) -> dict:
    d = {'code': code, 'name': name,
         'element_count': len(elements), 'elements': elements,
         'program_type': program}
    if sub_elements:
        d['sub_elements'] = sub_elements
    return d


def _madrasah_subjects(levels: list) -> dict:
    """Mapel reguler 9941/2025 untuk jenjang yang diberikan."""
    out = {}
    for level in levels:
        out[level] = [
            _subj('QH', "Al-Qur'an Hadis", _STD_ELEMENTS,
                  sub_elements=_COVERAGE["Al-Qur'an Hadis"]),
            _subj('AA', 'Akidah Akhlak', _STD_ELEMENTS,
                  sub_elements=_COVERAGE['Akidah Akhlak']),
            _subj('FK', 'Fikih', _STD_ELEMENTS,
                  sub_elements=_COVERAGE['Fikih']),
            _subj('SKI', 'Sejarah Kebudayaan Islam', _STD_ELEMENTS),
            _subj('BA', 'Bahasa Arab', _BA_ELEMENTS),
        ]
    return out


# Jenjang tempat tiap kelompok mapel sekolah diajarkan (Diktum KESATU
# dan KELIMA Kepka BSKAP 046/H/KR/2025).
_SCHOOL_LEVELS = {
    'umum': ('SD', 'SMP', 'SMA', 'SMK'),
    'kejuruan': ('SMK',),
    'khusus': ('TKLB', 'SDLB', 'SMPLB', 'SMALB'),
}

# Kode mapel yang bentrok dengan mapel madrasah atau singkatan lain.
# Sisanya diturunkan dari inisial nama.
_SUBJECT_CODES = {
    'BAHASA ARAB': 'B-ARB',
    'BAHASA INDONESIA': 'B-IND',
    'BAHASA INDONESIA TINGKAT LANJUT': 'B-IND-L',
    'BAHASA INGGRIS': 'B-ING',
    'BAHASA INGGRIS TINGKAT LANJUT': 'B-ING-L',
    'BAHASA JEPANG': 'B-JPN',
    'BAHASA JERMAN': 'B-DEU',
    'BAHASA KOREA': 'B-KOR',
    'BAHASA MANDARIN': 'B-MAN',
    'BAHASA PRANCIS': 'B-FRA',
    'INTERIOR KAPAL': 'IKPL',
    'PENDIDIKAN AGAMA ISLAM DAN BUDI PEKERTI': 'PAB-I',
    'PENDIDIKAN AGAMA KRISTEN DAN BUDI PEKERTI': 'PAB-K',
    'PENDIDIKAN AGAMA KATOLIK DAN BUDI PEKERTI': 'PAB-KA',
    'PENDIDIKAN AGAMA HINDU DAN BUDI PEKERTI': 'PAB-H',
    'PENDIDIKAN AGAMA BUDDHA DAN BUDI PEKERTI': 'PAB-B',
    'PENDIDIKAN AGAMA KHONGHUCU DAN BUDI PEKERTI': 'PAB-KH',
    'PENDIDIKAN KHUSUS AGAMA ISLAM DAN BUDI PEKERTI': 'PK-PAB-I',
    'PENDIDIKAN KHUSUS AGAMA KRISTEN DAN BUDI PEKERTI': 'PK-PAB-K',
    'PENDIDIKAN KHUSUS AGAMA KATOLIK DAN BUDI PEKERTI': 'PK-PAB-KA',
    'PENDIDIKAN KHUSUS AGAMA HINDU DAN BUDI PEKERTI': 'PK-PAB-H',
    'PENDIDIKAN KHUSUS AGAMA BUDDHA DAN BUDI PEKERTI': 'PK-PAB-B',
    'PENDIDIKAN KHUSUS AGAMA KHONGHUCU DAN BUDI PEKERTI': 'PK-PAB-KH',
}


def _subject_code(name: str, taken: set) -> str:
    """Kode mapel: pemetaan eksplisit bila ada, selain itu inisial.

    Inisial yang bentrok diberi nomor urut. Hasil deterministik karena
    nama diproses terurut."""
    if name in _SUBJECT_CODES:
        return _SUBJECT_CODES[name]
    words = re.findall(r'[A-Za-z0-9]+', name)
    stop = {'DAN', 'ATAU', 'YANG', 'UNTUK', 'PADA', 'DENGAN', 'SERTA',
            'DI', 'KE', 'DARI', 'THE', 'AND', 'OF'}
    base = ''.join(w[0] for w in words if w.upper() not in stop)[:8]
    code = base
    n = 2
    while code in taken:
        code = f'{base}-{n}'
        n += 1
    return code


def _subject_group(name: str) -> str:
    """Kelompok mapel menentukan jenjang yang memuatnya."""
    if name.startswith('PENDIDIKAN KHUSUS') \
            or name.startswith('PROGRAM KEBUTUHAN') \
            or name.startswith('FASE FONDASI'):
        return 'khusus'
    if name.startswith('DASAR-DASAR ') or name.startswith('MUATAN '):
        return 'kejuruan'
    return 'umum'


def _school_subjects() -> dict:
    """Mapel sekolah dari CP BSKAP 046 yang sudah ter-parse.

    Elemen tiap mapel = nama elemen berbeda yang muncul di CP-nya,
    terurut alfabet. Sumbernya parser 046, bukan daftar yang diketik
    tangan: mapel kejuruan punya elemen spesifik per mapel."""
    import sqlite3
    db = PROJECT_ROOT / 'db' / 'rpm_generator.db'
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT subject, element FROM learning_outcomes "
        "WHERE source_document_id = 'DOC-REG-KEMENDIKDASMEN-BSKAP-046-2025'"
    ).fetchall()
    conn.close()

    by_subject: dict = {}
    for subject, element in rows:
        if 'AGAMA' in subject:
            # CP agama di 046 berstatus superseded. Yang berlaku BKPDM 020.
            continue
        by_subject.setdefault(subject, set()).add(element)

    levels: dict = {}
    taken: set = set()
    for name in sorted(by_subject):
        code = _subject_code(name, taken)
        taken.add(code)
        entry = _subj(code, name, sorted(by_subject[name]))
        for level in _SCHOOL_LEVELS[_subject_group(name)]:
            levels.setdefault(level, []).append(entry)
    return levels


def _mapk_subjects() -> list:
    """Mapel MAPK (bagian III, V, 7.2, 9.1 di 9941/2025) - subject
    TERPISAH dari reguler sesuai heading dokumen."""
    return [
        _subj('QH-TAF', "Al-Qur'an Hadis (Tafsir)", _STD_ELEMENTS, 'MAPK'),
        _subj('QH-HAD', "Al-Qur'an Hadis (Hadis)", _STD_ELEMENTS, 'MAPK'),
        _subj('IT', 'Ilmu Tafsir', _STD_ELEMENTS, 'MAPK'),
        _subj('IH', 'Ilmu Hadis', _STD_ELEMENTS, 'MAPK'),
        _subj('IK', 'Ilmu Kalam', _STD_ELEMENTS, 'MAPK'),
        _subj('AT', 'Akhlak Tasawuf', _STD_ELEMENTS, 'MAPK'),
        _subj('UF', 'Ushul Fikih', _STD_ELEMENTS, 'MAPK'),
        # Fikih bagian VII (hal. 76) dan Bahasa Arab bagian 9.1 (hal. 103):
        # nama mapel sama dengan jalur reguler, dibedakan program_type.
        # Kode diberi sufiks agar subject_id deterministik dan tidak
        # bertabrakan dengan FK/BA reguler.
        _subj('FK-MAPK', 'Fikih', _STD_ELEMENTS, 'MAPK'),
        _subj('BA-MAPK', 'Bahasa Arab', _STD_ELEMENTS, 'MAPK'),
    ]


# Jenjang pendidikan khusus persis menurut Diktum KELIMA Kepka BSKAP
# 046/H/KR/2025 (hal. 4-5). Fase 'Fondasi' hanya untuk TKLB; fase A-F
# mengikuti pola kode jenjang reguler. SMKLB tidak ada di dokumen.
_SPECIAL_SCHOOLS = {
    'TKLB': {
        'TKLB_fondasi': ('Fondasi',
                         'Taman Kanak-Kanak Luar Biasa, Fase Fondasi'),
    },
    'SDLB': {
        'SDLB_1': ('A', 'SDLB Kelas I, Fase A (usia mental < 7 tahun)'),
        'SDLB_2': ('A', 'SDLB Kelas II, Fase A (usia mental < 7 tahun)'),
        'SDLB_3': ('B', 'SDLB Kelas III, Fase B (usia mental ± 7 tahun)'),
        'SDLB_4': ('B', 'SDLB Kelas IV, Fase B (usia mental ± 7 tahun)'),
        'SDLB_5': ('C', 'SDLB Kelas V, Fase C (usia mental ± 8 tahun)'),
        'SDLB_6': ('C', 'SDLB Kelas VI, Fase C (usia mental ± 8 tahun)'),
    },
    'SMPLB': {
        'SMPLB_7': ('D', 'SMPLB Kelas VII, Fase D (usia mental ± 9 tahun)'),
        'SMPLB_8': ('D', 'SMPLB Kelas VIII, Fase D (usia mental ± 9 tahun)'),
        'SMPLB_9': ('D', 'SMPLB Kelas IX, Fase D (usia mental ± 9 tahun)'),
    },
    'SMALB': {
        'SMALB_10': ('E', 'SMALB Kelas X, Fase E (usia mental ± 10 tahun)'),
        'SMALB_11': ('F', 'SMALB Kelas XI, Fase F (usia mental ± 10 tahun)'),
        'SMALB_12': ('F', 'SMALB Kelas XII, Fase F (usia mental ± 10 tahun)'),
    },
}


def build() -> dict:
    m = json.loads(MAPPINGS_PATH.read_text(encoding='utf-8'))

    # ---- master phases (Fondasi dipakai TKLB_fondasi dan CP Fondasi
    # BSKAP 046; tanpanya validasi phase gagal. A-F tidak diubah.) ----
    phases = m.get('phases', [])
    if not any(p.get('code') == 'Fondasi' for p in phases):
        phases = ([{'code': 'Fondasi', 'name': 'Fase Fondasi', 'order': 0,
                    'description': 'Fase fondasi (TKLB)'}]
                  + list(phases))
        m['phases'] = phases

    # ---- otoritas (nama kementerian sesuai kop dokumen 046) ------------
    dikdasmen = m['education_systems']['KEMENDIKDASMEN']
    dikdasmen['name'] = 'Kementerian Pendidikan Dasar dan Menengah'
    dikdasmen['description'] = ('Sistem pendidikan di bawah Kementerian '
                                'Pendidikan Dasar dan Menengah')
    # SMKLB tidak disebut 046 sama sekali. Buang bila tersisa dari
    # versi mapping lama, jangan hanya menahan diri menambahkannya.
    types = [t for t in dikdasmen['institution_types'] if t != 'SMKLB']
    for level in _SPECIAL_SCHOOLS:
        if level not in types:
            types.append(level)
    dikdasmen['institution_types'] = types

    # ---- jenjang -> fase (pendidikan khusus, Diktum KELIMA 046) --------
    grades = m['grade_to_phase_mappings']['KEMENDIKDASMEN']
    grades.pop('SMKLB', None)
    for level, classes in _SPECIAL_SCHOOLS.items():
        grades[level] = {
            code: {'phase': phase, 'description': desc}
            for code, (phase, desc) in classes.items()
        }

    # ---- subjects -----------------------------------------------------
    kemenag = _madrasah_subjects(['MI', 'MTs', 'MA', 'MAK'])
    # RA: satu mapel (PAI RA) dengan tiga elemen stimulasi resmi.
    kemenag['RA'] = [_subj('PAB-RA', 'PAI RA', _RA_ELEMENTS)]
    # MAPK hanya di jenjang MA (Madrasah Aliyah Program Keagamaan).
    kemenag['MA'].extend(_mapk_subjects())
    dikdasmen = _school_subjects()
    reguler = [_subj('PAB', 'Pendidikan Agama dan Budi Pekerti',
                     _PAB_ELEMENTS)] + [
        _subj(code, name, elements)
        for code, name, elements in _RELIGION_SUBJECTS
        if not code.startswith('PK-')]
    for level in ('SD', 'SMP', 'SMA', 'SMK'):
        dikdasmen[level] = reguler + dikdasmen.get(level, [])
    for level in ('TKLB', 'SDLB', 'SMPLB', 'SMALB'):
        for code, name, elements in _RELIGION_SUBJECTS:
            if not code.startswith('PK-'):
                continue
            dikdasmen.setdefault(level, []).append(
                _subj(code, name, elements))
    m['subjects'] = {'KEMENAG': kemenag, 'KEMENDIKDASMEN': dikdasmen}

    # ---- curriculum_versions (tanggal dari bukti PDF) ------------------
    m['curriculum_versions'] = [
        {
            'id': 'KMA-1503-2025',
            'name': 'Kurikulum Madrasah KMA 1503 Tahun 2025',
            'system': 'KEMENAG',
            'year': 2025,
            'regulation_id': 'REG-KEMENAG-1503-2025',
            # "Keputusan ini mulai berlaku pada tanggal ditetapkan"
            # ditetapkan 22 September 2025 (KMA 1503/2025, hlm. 5).
            'effective_date': '2025-09-22',
            'effective_evidence': {
                'basis': 'Keputusan ini mulai berlaku pada tanggal '
                         'ditetapkan; ditetapkan 22 September 2025.',
                'source_document': 'REG-KEMENAG-1503-2025',
                'page': 5,
            },
            'status': 'active',
            'applicable_to': ['RA', 'MI', 'MTs', 'MA', 'MAK'],
            'notes': ('CP PAI dan Bahasa Arab dari Kepdirjen Pendis '
                      '9941/2025 (termasuk jalur MAPK).'),
        },
        {
            'id': 'KEMENDIKDASMEN-2025',
            'name': 'Kurikulum Nasional Kemendikdasmen (CP BSKAP 046/2025 '
                    'jo. BKPDM 020/2026)',
            'system': 'KEMENDIKDASMEN',
            'year': 2025,
            'regulation_id': 'REG-KEMENDIKDASMEN-BSKAP-046-2025',
            'amendment_regulation_id': 'REG-KEMENDIKDASMEN-BKPDM-020-2026',
            # 046: "mulai berlaku sejak tanggal ditetapkan", ditetapkan
            # 16 Juli 2025; amandemen CP PAB oleh BKPDM 020 berlaku
            # 11 Juni 2026 (dokumen masing-masing).
            'effective_date': '2025-07-16',
            'amendment_effective_date': '2026-06-11',
            'effective_evidence': {
                'basis': 'Mulai berlaku sejak tanggal ditetapkan; '
                         'ditetapkan 16 Juli 2025 (BSKAP 046, hlm. 6). '
                         'Amandemen CP PAB: berlaku pada tanggal '
                         'ditetapkan, 11 Juni 2026 (BKPDM 020, hlm. 3).',
                'source_document': 'REG-KEMENDIKDASMEN-BSKAP-046-2025',
                'page': 6,
            },
            'status': 'active',
            # TKLB/SDLB/SMPLB/SMALB disebut eksplisit di Diktum KESATU
            # huruf e dan Diktum KELIMA Kepka BSKAP 046 (hal. 3-5).
            # SMKLB TIDAK disebut dokumen itu, jadi tidak dimasukkan.
            'applicable_to': ['SD', 'SMP', 'SMA', 'SMK',
                              'TKLB', 'SDLB', 'SMPLB', 'SMALB'],
            'notes': ('CP mapel umum dari BSKAP 046/H/KR/2025; CP '
                      'Pendidikan Agama dan Budi Pekerti dari amandemen '
                      'BKPDM 020/2026 (relasi amendemen - 046 tetap '
                      'berlaku untuk mapel lain).'),
        },
    ]

    # ---- validation rules tambahan (MAPK & provenance) ------------------
    rules = m.setdefault('validation_rules', {})
    rules['mapk_separation'] = (
        'CP MAPK (program_type=MAPK) tidak boleh tercampur dengan CP '
        'reguler pada subject yang sama; lookup CP default hanya jalur '
        'reguler.')
    rules['element_official_only'] = (
        'Elemen hanya dari item bernomor resmi per fase pada dokumen '
        'sumber (9941/2025 / BKPDM 020/2026); cakupan materi disimpan '
        'sebagai sub_element.')
    rules['cp_provenance'] = (
        'Setiap CP wajib membawa provenance: source_document, '
        'source_fragment_id, source_page (CP -> fragment -> document -> '
        'PDF Hukum/).')
    m['version'] = '2.0'

    return m


def main():
    m = build()
    MAPPINGS_PATH.write_text(
        json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
    n_sub = sum(len(v) for v in m['subjects']['KEMENAG'].values())
    n_sub2 = sum(len(v) for v in m['subjects']['KEMENDIKDASMEN'].values())
    print(f"✅ {MAPPINGS_PATH.name}: version {m['version']}, "
          f"KEMENAG {n_sub} entri mapel (termasuk MAPK), "
          f"KEMENDIKDASMEN {n_sub2} entri")
    for cv in m['curriculum_versions']:
        print(f"   {cv['id']}: berlaku {cv['effective_date']} "
              f"(reg {cv['regulation_id']})")


if __name__ == '__main__':
    main()
