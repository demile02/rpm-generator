#!/usr/bin/env python3
"""
Curriculum Engine - PHASE 3
AI RPP/RPM Generator (Pembelajaran Mendalam)

Manages curriculum data:
- Education systems (Kemenag, Kemendikdasmen)
- Grades and phases (deterministic mapping)
- Subjects and elements
- Learning outcomes (CP) extraction and storage
- Subject-system validation
"""

import sqlite3
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class PhaseMapping:
    """Grade to phase mapping."""
    grade: str
    phase: str
    education_system: str
    institution_type: str


@dataclass
class Subject:
    """Subject definition."""
    code: str
    name: str
    system: str
    elements: List[str]


@dataclass
class LearningOutcome:
    """Capaian Pembelajaran (CP)."""
    id: str
    subject: str
    phase: str
    element: str
    text: str
    source_page: int
    source_document: str
    # Halaman lain yang memuat teks CP yang sama (item menyeberang
    # halaman). Pencocokan provenance mencoba semuanya.
    source_pages: List[int] = None
    # Provenance & identitas penuh (AGENTS.md §9/§27): setiap CP dapat
    # ditelusuri CP -> source_fragment -> source_document -> PDF Hukum/.
    education_system: str = ''
    institution_type: str = ''
    education_level: str = ''
    curriculum_version_id: str = ''
    subject_id: str = None
    phase_id: str = None
    element_id: str = None
    # Cakupan/substansi di bawah elemen (mis. Tajwid, Ibadah) - BUKAN
    # elemen; elemen resmi adalah item bernomor per fase.
    sub_element: str = None
    # 'reguler' | 'MAPK' - memisahkan jalur Madrasah Aliyah Program
    # Keagamaan dari mata pelajaran reguler (AGENTS.md §8).
    program_type: str = 'reguler'
    track: str = None
    source_fragment_id: str = None
    source_section: str = None
    version: str = '1.0'
    status: str = 'active'


class CurriculumEngine:
    """Manages curriculum data and validation."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.connection = None
        self.cursor = None
        self.mappings = self._load_mappings()
        
    def connect(self):
        """Connect to database.

        The connection may be used from multiple worker threads (the async
        generation endpoint runs each job on its own thread while the
        pipeline singleton persists). All engine access is serialized by the
        app's generation lock, so ``check_same_thread=False`` is required
        and safe: without it, every job after the first raised a
        cross-thread ProgrammingError that surfaced as an empty CP list.
        """
        if self.connection is not None:
            return
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        
    def close(self):
        """Close connection (idempotent; safe to call twice)."""
        if self.connection:
            try:
                self.connection.close()
            finally:
                self.connection = None
                self.cursor = None
    
    def _load_mappings(self) -> Dict:
        """Load curriculum mappings from JSON."""
        mappings_path = self.db_path.parent / 'curriculum_mappings.json'
        try:
            with open(mappings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Could not load mappings: {e}")
            return {}
    
    def validate_grade_phase(self, system: str, grade: str) -> Tuple[bool, Optional[str], str]:
        """
        Validate and determine phase from grade.
        Returns: (is_valid, phase, error_message)
        """
        try:
            system_mappings = self.mappings.get('grade_to_phase_mappings', {}).get(system, {})
            
            # Find institution type that contains this grade
            for inst_type, grades in system_mappings.items():
                if grade in grades:
                    phase = grades[grade].get('phase')
                    return True, phase, ""
            
            return False, None, f"Grade {grade} tidak ditemukan dalam sistem {system}"
            
        except Exception as e:
            return False, None, str(e)
    
    def get_subjects_for_system(self, system: str, institution_type: str = None) -> List[Subject]:
        """Get subjects available for system."""
        try:
            subjects_data = self.mappings.get('subjects', {}).get(system, {})
            subjects = []
            
            for inst_type, subj_list in subjects_data.items():
                if institution_type and inst_type != institution_type:
                    continue
                    
                for subj in subj_list:
                    subject = Subject(
                        code=subj.get('code'),
                        name=subj.get('name'),
                        system=system,
                        elements=subj.get('elements', [])
                    )
                    subjects.append(subject)
            
            return subjects
            
        except Exception as e:
            print(f"❌ Error getting subjects: {e}")
            return []
    
    # ------------------------------------------------------------------
    # Parser CP dari SK Dirjen Pendis 9941/2025 (sumber CP madrasah,
    # AGENTS.md §4) — parser v2 berbasis PETA BAGIAN dokumen.
    #
    # Struktur asli dokumen (terverifikasi dari fragmen, provenance
    # halaman pada tiap bagian):
    #   I.    RA (p5-8)                          — mode 'ra'
    #   II.   AQH MI, MTs, MA/MAK (p9-18)        — mode 'std'
    #   III.  AQH MAPK (p19-37)                  — mode 'std', program MAPK;
    #         sub-mapel 3.1 AQH (Tafsir), 3.2 AQH (Hadis), 3.3 Ilmu Tafsir,
    #         3.4 Ilmu Hadis (heading di p19/p25/p30/p34)
    #   IV.   Akidah Akhlak MI, MTs, MA/MAK (p38-53) — mode 'std'
    #   V.    Akidah Akhlak MAPK (p54-65)        — sub-mapel 5.1 Ilmu Kalam
    #         (p54), 5.2 Akhlak Tasawuf (p60)
    #   VI.   Fikih MI, MTs, MA/MAK (p66-75)     — mode 'std'
    #   VII.  Fikih jenjang MAPK (p76-84)        — sub-mapel 7.1 Fikih
    #         (p76), 7.2 Ushul Fikih (p80)
    #   VIII. SKI MI, MTs, MA/MAK (p85-94)       — mode 'std'
    #   IX.   Bahasa Arab MI, MTs, MA/MAK (p95-102) — mode 'std', reguler;
    #         9.1 Bahasa Arab Program Keagamaan (p103-106) — sub-mapel MAPK,
    #         program_type disetel 'MAPK' oleh _cp_apply_mapk_sub
    #
    # ELEMEN RESMI vs CAKUPAN (mengikuti dokumen): elemen resmi adalah
    # item bernomor per fase ("X.1 Pemahaman Konsep" / "X.2 Keterampilan
    # Proses"; BA: "Komponen Bahasa" / "Keterampilan Bahasa"). Label
    # Tajwid, Ilmu Al-Qur'an, Ilmu Hadis, Al-Qur'an, Hadis, Akidah,
    # Akhlak, Adab, Kisah Keteladanan, Ibadah, Muamalah adalah
    # CAKUPAN/SUBSTANSI di bawah elemen Pemahaman — disimpan sebagai
    # sub_element, BUKAN element. CP MAPK terpisah dari reguler lewat
    # program_type ('MAPK') + track (nama sub-mapel per dokumen).
    # ------------------------------------------------------------------

    _CP_DOC_ID = 'DOC-REG-KEMENAG-PENDIS-9941-2025'
    _CP_SOURCE_LABEL = 'SK-Dirjen-Pendis-9941-2025'
    _CP_SYSTEM = 'KEMENAG'
    _CP_INSTITUTION = 'madrasah'
    # ID versi kurikulum (curriculum_versions di curriculum_mappings.json),
    # BUKAN id regulasi/dokumen sumber. 9941/2025 adalah sumber CP-nya,
    # tetapi CP itu hidup di bawah kurikulum KMA 1503/2025.
    _CP_CURRICULUM_VERSION = 'KMA-1503-2025'

    # Peta heading bagian (romawi) -> konteks parser bagian tersebut.
    # phase_start = huruf fase pertama bagian itu (untuk resolusi fase
    # yang terpotong OCR lewat nomor urutnya, mis. "4. Fa" di SKI = fase E
    # karena bagian VIII mulai di fase B).
    _CP_SECTIONS = (
        (re.compile(r"^I\.\s+CAPAIAN\s+PEMBELAJARAN\s+RAUDLATUL\s+ATHFAL", re.I),
         dict(subject='PAI RA', mode='ra', program_type='reguler',
              education_level='RA', track=None, phase_start='A')),
        (re.compile(r"^II\.\s+CAPAIAN\s+PEMBELAJARAN\s+AL-QUR", re.I),
         dict(subject="Al-Qur'an Hadis", mode='std', program_type='reguler',
              education_level='MI, MTs, MA/MAK', track=None, phase_start='A')),
        (re.compile(r"^III\.\s+CAPAIAN\s+PEMBELAJARAN\s+AL-QUR", re.I),
         dict(subject="Al-Qur'an Hadis (Tafsir)", mode='std',
              program_type='MAPK', education_level='MA Program Keagamaan',
              track='Tafsir', phase_start='E')),
        (re.compile(r"^IV\.\s+CAPAIAN\s+PEMBELAJARAN\s+AKIDAH\s+AKHLAK", re.I),
         dict(subject='Akidah Akhlak', mode='std', program_type='reguler',
              education_level='MI, MTs, MA/MAK', track=None, phase_start='A')),
        (re.compile(r"^V\.\s+CAPAIAN\s+PEMBELAJARAN\s+AKIDAH\s+AKHLAK", re.I),
         dict(subject='Ilmu Kalam', mode='std', program_type='MAPK',
              education_level='MA Program Keagamaan', track='Ilmu Kalam',
              phase_start='E')),
        (re.compile(r"^VI\.\s+CAPAIAN\s+PEMBELAJARAN\s+FIKIH", re.I),
         dict(subject='Fikih', mode='std', program_type='reguler',
              education_level='MI, MTs, MA/MAK', track=None, phase_start='A')),
        (re.compile(r"^VII\.\s+CAPAIAN\s+PEMBELAJARAN\s+FIKIH\s+JENJANG\s+MAPK", re.I),
         dict(subject='Fikih', mode='std', program_type='MAPK',
              education_level='MA Program Keagamaan', track='Fikih',
              phase_start='E')),
        (re.compile(r"^VIII\.\s+CAPAIAN\s+PEMBELAJARAN\s+SEJARAH", re.I),
         dict(subject='Sejarah Kebudayaan Islam', mode='std',
              program_type='reguler', education_level='MI, MTs, MA/MAK',
              track=None, phase_start='B')),
        (re.compile(r"^IX\.\s+CAPAIAN\s+PEMBELAJARAN\s+BAHASA\s+ARAB", re.I),
         dict(subject='Bahasa Arab', mode='std', program_type='reguler',
              education_level='MI, MTs, MA/MAK', track=None, phase_start='A')),
    )

    # Sub-mapel MAPK (heading bernomor di dalam bagian MAPK) — mengganti
    # subject/track bagian induknya. Spasi OCR pada "5. 1." ditangani.
    _CP_MAPK_SUBS = (
        (re.compile(r"^3\s*\.\s*2\.?\s+CAPAIAN.*HADIS", re.I),
         dict(subject="Al-Qur'an Hadis (Hadis)", track='Hadis',
              phase_start='E')),
        (re.compile(r"^3\s*\.\s*3\.?\s+CAPAIAN\s+PEMBELAJARAN\s+ILMU\s+TAFSIR", re.I),
         dict(subject='Ilmu Tafsir', track='Ilmu Tafsir', phase_start='E')),
        (re.compile(r"^3\s*\.\s*4\.?\s+CAPAIAN", re.I),
         dict(subject='Ilmu Hadis', track='Ilmu Hadis', phase_start='E')),
        (re.compile(r"^5\s*\.\s*2\.?\s+CAPAIAN.*AKHLAK\s+TASAWUF", re.I),
         dict(subject='Akhlak Tasawuf', track='Akhlak Tasawuf',
              phase_start='E')),
        (re.compile(r"^7\s*\.\s*2\.?\s+CAPAIAN.*USHUL\s+FIKIH", re.I),
         dict(subject='Ushul Fikih', track='Ushul Fikih', phase_start='E')),
        (re.compile(r"^9\s*\.\s*1\.?\s+CAPAIAN\s+PEMBELAJARAN\s+BAHASA\s+ARAB", re.I),
         dict(subject='Bahasa Arab', track='Bahasa Arab', phase_start='E')),
    )

    # Cakupan/substansi (label tabel elemen) per mapel — nama kanonik
    # = label persis di dokumen (bukan konflasi lama seperti
    # Tajwid -> "Pemahaman Al-Qur'an"). Kunci = label lowercase.
    _CP_TABLE_SUBELEMENTS = {
        "Al-Qur'an Hadis": {
            'tajwid': 'Tajwid',
            "al-qur'an": "Al-Qur'an",
            "ilmu al-qur'an": "Ilmu Al-Qur'an",
            'hadis': 'Hadis',
            'ilmu hadis': 'Ilmu Hadis',
        },
        'Akidah Akhlak': {
            'akidah': 'Akidah',
            'akhlak': 'Akhlak',
            'adab': 'Adab',
            'kisah keteladanan': 'Kisah Keteladanan',
        },
        'Fikih': {
            'ibadah': 'Ibadah',
            'muamalah': 'Muamalah',
        },
    }

    # Label cakupan yang menempel INLINE di awal baris (layout tabel PDF:
    # "Tajwid Mengenal dan menulis huruf hijaiyah ..."). Hanya aktif untuk
    # mapel yang memang memuat label tersebut di tabel elemennya.
    _CP_TABLE_LABELS = {
        "Al-Qur'an Hadis": (
            (re.compile(r"^Tajwid\b"), 'Tajwid'),
            (re.compile(r"^Ilmu\s+Al-Qur[’']an\b"), "Ilmu Al-Qur'an"),
            (re.compile(r"^Al-Qur[’']an\b(?!\s+Hadis\b)"), "Al-Qur'an"),
            (re.compile(r"^Ilmu\s+Hadis\b"), 'Ilmu Hadis'),
            (re.compile(r"^Hadis\b"), 'Hadis'),
        ),
        'Akidah Akhlak': (
            (re.compile(r'^Akidah\b'), 'Akidah'),
            (re.compile(r'^Akhlak\b'), 'Akhlak'),
            (re.compile(r'^Adab\b'), 'Adab'),
            (re.compile(r'^Kisah\s+Keteladanan\b'), 'Kisah Keteladanan'),
        ),
        'Fikih': (
            (re.compile(r'^Ibadah\b'), 'Ibadah'),
            (re.compile(r'^Muamalah\b'), 'Muamalah'),
        ),
    }

    # Elemen resmi item bernomor per fase ("1.1 Pemahaman Konsep",
    # "1.2 Keterampilan Proses", BA: "1.1 Komponen Bahasa").
    _CP_NUMBERED_ELEMENT = re.compile(
        r'^(Pemahaman\s+Konsep|Keterampilan\s+Proses|'
        r'Komponen\s+Bahasa|Keterampilan\s+Bahasa)\b', re.I)

    # Item elemen lengkap dengan nomornya — tiga format di dokumen:
    #   "1.1 Pemahaman Konsep"   (reguler, item bernomor fase)
    #   "1. Pemahaman Konsep"    (sub-mapel MAPK fase tunggal)
    #   "1.1 Pemahamankonsep"    (varian OCR: spasi label tertelan)
    _CP_NUM_ELEM_FULL = re.compile(
        r'^\d+\.\s*(?:\d+[.\s]*)?(Pemahaman\s*[Kk]onsep|Keterampilan\s*'
        r'[Pp]roses|'
        r'Komponen\s*[Bb]ahasa|Keterampilan\s*[Bb]ahasa)\b[.:]*\s*')
    _CP_NUM_ELEM_MID = re.compile(
        r'\d+\.\s*(?:\d+[.\s]*)?(Pemahaman\s*[Kk]onsep|Keterampilan\s*'
        r'[Pp]roses|'
        r'Komponen\s*[Bb]ahasa|Keterampilan\s*[Bb]ahasa)\b[.:]*\s*')

    # Baris kepala sub-bab struktur (Rasional/Tujuan/Karakteristik/CP).
    _CP_STRUCT_HEADING = re.compile(
        r'^[A-F]\.\s*(Rasional|Tujuan|Karakteristik|Capaian\s+Pembelajaran)\s*$',
        re.I)

    # RA: label elemen pada baris tabel "No | Elemen | CP" ("1. Nilai Agama
    # dan Murid mengenal ..."). Elemen RA = tiga elemen stimulasi resmi.
    _CP_RA_ELEMENT_ROWS = (
        (re.compile(r'^(?:\d+\.\s*)?Nilai\s+Agama', re.I),
         'Nilai Agama dan Budi Pekerti'),
        (re.compile(r'^(?:\d+\.\s*)?Jati\s+Diri\b', re.I), 'Jati Diri'),
        (re.compile(r'^(?:\d+\.\s*)?Dasar-Dasar\b', re.I),
         'Dasar-Dasar Literasi, Matematika, Sains, Teknologi, Rekayasa, dan Seni'),
    )

    # RA: lanjutan label kolom elemen yang ter-wrap ke baris berikutnya
    # ("Budi Pekerti", "Literasi,", "Matematika, Sains,", ...). DIPOTONG
    # tanpa flush - sisa baris tetap konten item yang sedang berjalan.
    _CP_RA_STRIP_RE = re.compile(
        r'^(?:Budi\s+Pekerti|Pekerti|Literasi|Matematika|Sains|Teknologi|'
        r'Rekayasa|Seni)\b[,.]?',
        re.IGNORECASE,
    )

    # Regex bersama.
    _CP_PHASE_RE = re.compile(r'^(?:(\d+)\.\s*)?[Ff]a+a?se\s+([A-F])\b')
    _CP_PHASE_TRUNCATED_RE = re.compile(r'^(?:(\d+)\.\s*)?Fa+a?se?\s*$')
    _CP_NUMBERED_ITEM_RE = re.compile(r'^(\d+)\.\s*(\d+)[.\s]+')
    _CP_BULLET_RE = re.compile(r'^[•●\-]\s+')
    _CP_PRINTED_PAGE_RE = re.compile(r'^-\s*\d+\s*-$')
    # Baris harakat/tanda baca Arab (contoh pola kalimat pada mapel
    # Bahasa Arab) - bukan CP. Menghapus hanya bila baris didominasi
    # karakter Arab dengan sedikit sekali huruf Latin.
    _CP_ARABIC_JUNK_RE = re.compile(
        r'^(?![A-Za-z]{6,})[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\s'
        r'\u064B-\u065F.,؛؟,:;()\-]*$')

    # Baris kepala SK / metadata instansi - tidak pernah konten CP.
    _CP_SKIP_PREFIXES = (
        'kementerian agama', 'direktur jenderal', 'keputusan direktur',
        'nomor ', 'tentang ', 'salinan', 'lampiran', 'menetapkan',
        'diktum ', 'www.', 'elemen deskripsi',
    )
    # CATATAN: kalimat pengantar item Keterampilan Proses/ilmiah (mis.
    # "Keterampilan ilmiah yang digunakan dalam pembelajaran elemen
    # pemahaman fikih.") adalah ISI item KP di dokumen - JANGAN di-skip.
    # Me-skip-nya membuat baris wrap lanjutan ("pemahaman fikih.")
    # membuka segmen lowercase dan seluruh CP KP terbuang di filter
    # flush. Deskripsi tabel elemen di bagian C. Karakteristik aman:
    # di sana fase belum diset sehingga flush tidak pernah emit.

    # Sel tabel elemen yang berdiri sendiri (layout tabel PDF: kolom
    # "Elemen | Deskripsi" ter-OCR sebagai baris terpisah). Struktur
    # tabel - bukan konten CP.
    _CP_TABLE_CELL_LABELS = {
        'elemen', 'deskripsi', 'elemen deskripsi', 'pemahaman',
        'keterampilan', 'pemahaman konsep', 'keterampilan proses',
        'komponen bahasa', 'keterampilan bahasa',
    }

    # Kata kerja pembuka CP - validasi label cakupan generik (mapel
    # MAPK tanpa kamus label): label selalu DIIKUTI kalimat CP yang
    # berawalan kata kerja ini di dokumen.
    _CP_CP_VERBS = (
        'Menganalisis', 'Merefleksikan', 'Memahami', 'Membandingkan',
        'Menerapkan', 'Mengidentifikasi', 'Menjelaskan', 'Membedakan',
        'Menyebutkan', 'Menghafal', 'Mengenal', 'Membaca', 'Menulis',
        'Membuat', 'Menyajikan', 'Mengklasifikasikan',
        'Mendeskripsikan', 'Menghubungkan', 'Meniru', 'Menyimak',
        'Menggunakan', 'Menyimpulkan', 'Mengomunikasikan',
        'Mempertanyakan', 'Merencanakan', 'Mengevaluasi', 'Mengamati',
        'Mengumpulkan', 'Menceritakan', 'Memecahkan', 'Menghindari',
        'Membiasakan', 'Menyusun', 'Mengkaji', 'Mengeksplorasi',
        'Memprediksi', 'Menanya', 'Membaca',
    )

    def _cp_numbered_element_name(self, line: str):
        """Nama elemen resmi bila baris adalah label item elemen bernomor
        ("1.1 Pemahaman Konsep" / BA "1.2 Keterampilan Bahasa")."""
        m = self._CP_NUM_ELEM_FULL.match(line)
        if not m:
            return None
        # Normalisasi varian OCR ("Pemahamankonsep", "PEMAHAMAN KONSEP",
        # "Pemahaman  konsep") ke nama kanonik.
        key = re.sub(r'\s+', '', m.group(1)).lower()
        return {'pemahamankonsep': 'Pemahaman Konsep',
                'keterampilanproses': 'Keterampilan Proses',
                'komponenbahasa': 'Komponen Bahasa',
                'keterampilanbahasa': 'Keterampilan Bahasa'}.get(key, key)

    def _cp_apply_mapk_sub(self, line: str, sec: dict) -> bool:
        """Terapkan sub-mapel MAPK (heading bernomor 3.x/5.x/7.x/9.x) pada
        konteks bagian. Return True bila line adalah heading tersebut.

        Heading ini hanya muncul di dalam bagian Program Keagamaan, jadi
        program_type ikut dipastikan 'MAPK'. Tanpa itu, bagian 9.1 (Bahasa
        Arab, hal. 103) mewarisi program_type='reguler' dari bagian IX dan
        4 CP-nya tersimpan di jalur yang salah."""
        for pat, upd in self._CP_MAPK_SUBS:
            if pat.match(line):
                sec['subject'] = upd['subject']
                sec['track'] = upd['track']
                sec['program_type'] = 'MAPK'
                sec['education_level'] = 'MA Program Keagamaan'
                sec['fase'] = None
                if upd.get('phase_start'):
                    sec['phase_start'] = upd['phase_start']
                return True
        return False

    def _cp_extract(self, fragments) -> List[LearningOutcome]:
        """Parser v2: state machine atas alur baris fragmen 9941 berbasis
        PETA BAGIAN (_CP_SECTIONS). Subjek, fase, program (reguler/MAPK),
        dan track berasal dari heading bagian/sub-mapel; elemen HANYA dari
        item bernomor resmi per fase (cakupan materi masuk sub_element).
        Semua CP membawa provensi halaman."""
        sec = {'subject': None, 'fase': None, 'element': None,
               'sub_element': None, 'mode': None, 'program_type': None,
               'education_level': None, 'track': None, 'phase_start': None}
        seg_lines: List[str] = []
        seg_page = None
        seg_state = dict(sec)
        segments: List[dict] = []

        def flush():
            nonlocal seg_lines, seg_page, seg_state
            _dbg = os.environ.get('CP_DEBUG')
            if seg_lines and seg_state['subject'] and seg_state['fase']:
                text = '\n'.join(seg_lines).strip()
                # RA: hanya item "Murid ..." yang merupakan CP - deskripsi
                # tabel elemen ("Mencakup ...") tidak dianggap CP.
                if seg_state['subject'] == 'PAI RA' \
                        and not text.startswith('Murid'):
                    if _dbg:
                        print(f'      [flush-drop RA] {text[:60]!r}')
                    seg_lines, seg_page, seg_state = [], None, dict(sec)
                    return
                # CP asli di dokumen SELALU berawalan huruf kapital.
                # Segmen yang berawalan huruf kecil/tanda baca adalah ekor
                # kalimat pengantar atau kurung fase yang ter-wrap antar
                # baris/fragmen ("ah Aliyah Program Keagamaan)",
                # "berbahasa Arab, murid ...", ", mustahil, dan jaiz") -
                # bukan CP.
                if text and not (text[0].isalpha() and text[0].isupper()):
                    if _dbg:
                        print(f'      [flush-drop lower] {text[:60]!r}')
                    seg_lines, seg_page, seg_state = [], None, dict(sec)
                    return
                if len(text) >= 40:
                    segments.append({
                        'page': seg_page,
                        'subject': seg_state['subject'],
                        'fase': seg_state['fase'],
                        'element': seg_state['element'] or 'Umum',
                        'sub_element': seg_state.get('sub_element'),
                        'program_type': seg_state.get('program_type'),
                        'education_level': seg_state.get('education_level'),
                        'track': seg_state.get('track'),
                        'text': text,
                    })
            seg_lines, seg_page, seg_state = [], None, dict(sec)

        # Rekonstruksi aliran baris per halaman. Fragmen 9941 dipotong
        # pada batas 1000 karakter di posisi SEMBARANG - bisa di tengah
        # kata ("Menganali|sis", "Madras|ah", "kosa ka|ta") sehingga
        # heading bagian/fase/elemen yang jatuh di titik potong tidak
        # pernah tampak sebagai baris utuh dan seluruh bagian bisa
        # lolos dari parser. Gabungkan fragmen per halaman TANPA
        # pemisah untuk memulihkan baris asli dokumen (potong di tengah
        # kata tersambung kembali; potong tepat di '\n' tetap
        # menghasilkan baris terpisah).
        page_texts: Dict[int, List[str]] = {}
        page_order: List[int] = []
        for row in fragments:
            p = row['page_number']
            if p not in page_texts:
                page_texts[p] = []
                page_order.append(p)
            page_texts[p].append(row['text'] or '')

        for page in page_order:
            lines = [l.strip()
                     for l in ''.join(page_texts[page]).split('\n')]
            lines = [l for l in lines if l]
            i = 0
            while i < len(lines):
                line = lines[i]
                # --- Penanda bagian (heading romawi). Konteks bagian
                # diambil dari peta; konten heading tidak diproses lagi.
                # Heading bisa menempel di TENGAH baris hasil rekonstruksi
                # (prosa karakteristik mengalir tanpa baris baru sebelum
                # "III. CAPAIAN ...") - pecah dan proses keduanya.
                sec_hit = next(((mm, cfg) for _pat, cfg
                                in self._CP_SECTIONS
                                if (mm := _pat.search(line))), None)
                if sec_hit:
                    flush()
                    m, cfg = sec_hit
                    prefix = line[:m.start()].rstrip()
                    if prefix:
                        lines[i] = prefix
                    else:
                        i += 1
                    sec.update(subject=cfg['subject'], mode=cfg['mode'],
                               program_type=cfg['program_type'],
                               education_level=cfg['education_level'],
                               track=cfg['track'], element=None,
                               sub_element=None,
                               phase_start=cfg['phase_start'],
                               # RA: satu fase fondasi tanpa heading
                               # "Fase X" eksplisit di dokumen.
                               fase=('A' if cfg['mode'] == 'ra' else None))
                    # Heading bisa ter-wrap: "VIII. ... SEJARAH KEBUDAYAAN
                    # ISLAM MI," + "MTs, MA/MAK" - buang baris lanjutannya.
                    j = i + 1
                    while (j < len(lines)
                           and not self._CP_PHASE_RE.match(lines[j])
                           and not any(p.match(lines[j])
                                       for p, _c in self._CP_MAPK_SUBS)
                           and not re.match(r'^[A-F]\.\s', lines[j])):
                        j += 1
                    i = j
                    continue
                # --- Sub-mapel MAPK (3.x/5.x/7.x/9.x).
                mapk_hit = next(((mm, upd) for _pat, upd
                                 in self._CP_MAPK_SUBS
                                 if (mm := _pat.search(line))), None)
                if mapk_hit:
                    flush()
                    p, upd = mapk_hit
                    prefix = line[:p.start()].rstrip()
                    if prefix:
                        lines[i] = prefix
                    else:
                        i += 1
                    self._cp_apply_mapk_sub(line, sec)
                    continue
                # --- Penanda fase: "1. Fase A (Kelas ...)" / "2. FASE F (...)".
                # Bisa menempel di tengah baris hasil rekonstruksi
                # ("... kehidupan. 1. Fase A (...)") - pecah dan proses
                # keduanya.
                m = self._CP_PHASE_RE.search(line)
                if m and m.start() > 0:
                    flush()
                    prefix = line[:m.start()].rstrip()
                    if prefix:
                        lines[i] = prefix
                        continue
                    line = line[m.start():]
                    m = self._CP_PHASE_RE.match(line)
                if m:
                    flush()
                    sec['fase'] = m.group(2).upper()
                    sec['element'] = None
                    sec['sub_element'] = None
                    rest = line[m.end():].strip()
                    # Buang keterangan fase dalam kurung ("(Kelas I dan II
                    # Madrasah Ibtidaiyah)"). Kurung bisa ter-wrap antar
                    # baris, bahkan ANTAR-FRAGMEN (contoh nyata: "2. Fase F
                    # (Kelas XI dan XII Madras" di akhir fragmen p59, sisa
                    # "ah Aliyah Program Keagamaan)" membuka fragmen
                    # berikutnya) - maka penanganan kurung memakai kursor
                    # global (posisi halaman+indeks baris dokumen).
                    #
                    # PENTING: jika kurung penutupnya tidak ada (OCR
                    # menggugurkan ')' - contoh nyata fase E AA p49: "5. Fase
                    # E (Kelas X Madrasah Aliyah/Madrasah Aliyah Kejuruan"
                    # tanpa ')'), JANGAN melahap baris berikutnya sampai
                    # ketemu ')' yang tidak akan pernah datang - itu yang
                    # membuat item CP fase berikutnya hilang. Cukup SATU
                    # baris lanjutan dilihat; jika tidak ada ')' di sana,
                    # kurung dianggap selesai dan sisa baris diproses.
                    if rest.startswith('('):
                        if ')' in rest:
                            rest = rest[rest.find(')') + 1:].strip()
                        elif i + 1 < len(lines) and ')' in lines[i + 1]:
                            i += 1
                            rest = lines[i]
                            rest = rest[rest.find(')') + 1:].strip()
                        else:
                            # Kurung tak tertutup (OCR kehilangan ')'):
                            # buang seluruh ekornya - itu anotasi kelas
                            # fase ("Kelas X Madrasah Aliyah/...") yang
                            # jika dipertahankan menjadi CP junk.
                            rest = ''
                    elif not rest:
                        # Kurung sudah terputus dari baris fasenya.
                        j = i + 1
                        while j < len(lines) and lines[j].startswith('('):
                            if ')' in lines[j]:
                                j += 1
                                break
                            j += 1
                        i = j
                        continue
                    if not rest:
                        i += 1
                        continue
                    line = rest  # konten setelah kurung fase
                # --- "4. Fa" (fase terpotong OCR): resolusi via nomor urut
                # + phase_start bagian (bagian VIII mulai di fase B -> "4."
                # = fase E).
                m_tr = self._CP_PHASE_TRUNCATED_RE.match(line)
                if m_tr and sec['phase_start'] and m_tr.group(1):
                    letter = chr(ord(sec['phase_start'])
                                 + int(m_tr.group(1)) - 1)
                    if 'A' <= letter <= 'F':
                        flush()
                        sec['fase'] = letter
                        sec['element'] = None
                        sec['sub_element'] = None
                        i += 1
                        continue
                # --- Item elemen bernomor ("1.1 Pemahaman Konsep" atau
                # "1. Pemahaman Konsep" pada sub-mapel fase tunggal):
                # PEMISAH CP + penanda elemen resmi. Jika nomor item
                # menempel di TENGAH baris konsolidasi ("... berikut. 1.2
                # Keterampilan ..."), pecah dan proses sisa barisnya.
                elem_name = self._cp_numbered_element_name(line)
                if elem_name is None:
                    m_mid = self._CP_NUM_ELEM_MID.search(line)
                    if m_mid and m_mid.start() > 0:
                        flush()
                        line = line[m_mid.start():]
                        elem_name = self._cp_numbered_element_name(line)
                if elem_name:
                    flush()
                    sec['element'] = elem_name
                    sec['sub_element'] = None
                    rest = self._CP_NUM_ELEM_FULL.sub('', line, count=1).strip()
                    # Label elemen duplikat yang tertanam mid-line
                    # ("2. Fase F (Kelas XI...)\n2.1 Pemahaman konsep\nMenganalisis...")
                    # sudah jadi penanda elemen - jangan diakumulasi ulang
                    # sebagai konten CP.
                    if rest.lower().rstrip('.') in (
                            'pemahaman konsep', 'keterampilan proses',
                            'komponen bahasa', 'keterampilan bahasa'):
                        rest = ''
                    if rest:
                        lines[i] = rest
                        continue
                    i += 1
                    continue
                # --- Struktur bernomor lain (di luar item elemen) - skip.
                if re.match(r'^\d+\.\d+', line):
                    flush()
                    i += 1
                    continue
                # --- Label cakupan inline di awal baris (layout tabel:
                # "Tajwid Mengenal dan menulis huruf hijaiyah ...").
                labels = self._CP_TABLE_LABELS.get(sec['subject'] or '', ())
                label_hit = next(((m, lab) for pat, lab in labels
                                  if (m := pat.match(line))), None)
                if label_hit and sec.get('element') == 'Pemahaman Konsep':
                    m, label = label_hit
                    flush()
                    sec['sub_element'] = label
                    line = line[m.end():].strip()
                    if not line:
                        i += 1
                        continue
                # --- Baris cakupan berdiri sendiri ("Tajwid", "Ibadah").
                low = line.lower().rstrip('.')
                # --- Sel tabel elemen berdiri sendiri ("Elemen",
                # "Deskripsi", ...) - struktur tabel, bukan CP.
                if low in self._CP_TABLE_CELL_LABELS:
                    flush()
                    i += 1
                    continue
                table_sub = self._CP_TABLE_SUBELEMENTS.get(
                    sec['subject'] or '', {}).get(low)
                if table_sub and len(line) <= 45 \
                        and sec.get('element') == 'Pemahaman Konsep':
                    flush()
                    sec['sub_element'] = table_sub
                    i += 1
                    continue
                # --- Label cakupan generik (mapel MAPK tanpa kamus
                # label): baris pendek, berawalan kapital, tanpa tanda
                # baca kalimat, dan DIIKUTI baris berawalan kata kerja
                # CP - pola konsisten tabel CP MAPK ("Sumber Hukum
                # Islam" -> "Menganalisis fungsi, kedudukan ...").
                if (sec.get('element') in ('Pemahaman Konsep',
                                           'Komponen Bahasa')
                        and sec['subject'] not in self._CP_TABLE_SUBELEMENTS
                        and len(line) <= 45
                        and line[0].isupper()
                        and ';' not in line and ',' not in line
                        and not line.rstrip().endswith(':')
                        and i + 1 < len(lines)
                        and lines[i + 1].split(' ')[0].split(',')[0]
                        in self._CP_CP_VERBS):
                    flush()
                    sec['sub_element'] = line
                    i += 1
                    continue
                # --- Penomoran halaman cetak.
                if self._CP_PRINTED_PAGE_RE.match(line):
                    i += 1
                    continue
                # --- Baris harakat/tanda baca Arab (contoh pola kalimat BA)
                # - bukan CP.
                if self._CP_ARABIC_JUNK_RE.match(line):
                    flush()
                    i += 1
                    continue
                # --- Langkah inkuiri ber-bullet ("● Mengamati ..."):
                # bagian dari item Keterampilan Proses yang sedang
                # berjalan - TIDAK memecah CP (satu CP per elemen per
                # fase, sesuai struktur item di dokumen). Marker bullet
                # dibuang, isinya tetap terakumulasi.
                if self._CP_BULLET_RE.match(line):
                    line = self._CP_BULLET_RE.sub('', line, count=1).strip()
                    if not line:
                        i += 1
                        continue
                if low := line.lower().rstrip('.'):
                    # Prefix metadata SK hanya berlaku bila baris diawali
                    # huruf kapital (header SK ditulis kapital). Tanpa
                    # syarat ini, lanjutan CP seperti "tentang kebesaran
                    # ..." (baris wrap) ikut ter-skip dan memotong CP.
                    if line[0].isupper() and any(
                            low.startswith(p)
                            for p in self._CP_SKIP_PREFIXES):
                        flush()
                        i += 1
                        continue
                    if low.startswith('pada akhir fase'):
                        flush()
                        i += 1
                        continue
                if self._CP_STRUCT_HEADING.match(line):
                    flush()
                    i += 1
                    continue
                # --- RA: tabel "No | Elemen | CP".
                if sec['subject'] == 'PAI RA':
                    m_strip = self._CP_RA_STRIP_RE.match(line)
                    if m_strip:
                        line = line[m_strip.end():].strip()
                        if not line:
                            i += 1
                            continue
                    ra_hit = next(((mm, elem) for pat, elem
                                   in self._CP_RA_ELEMENT_ROWS
                                   if (mm := pat.match(line))), None)
                    if ra_hit:
                        flush()
                        sec['element'] = ra_hit[1]
                        line = line[ra_hit[0].end():].strip()
                        if not line:
                            i += 1
                            continue
                # --- Akumulasi konten item CP yang sedang berjalan.
                # Segmen BARU hanya boleh dimulai dari baris valid dengan
                # konteks (subjek+fase) lengkap - kalau tidak, baris
                # di-skip. Tanpa ini, baris noise bisa membuka segmen
                # tanpa halaman (source_page=None) dan tanpa konteks.
                if not seg_lines:
                    starts_ok = (
                        not self._cp_is_noise_line(line)
                        and sec['subject'] and sec['fase']
                        and (sec['subject'] != 'PAI RA'
                             or line.startswith('Murid')))
                    if not starts_ok:
                        i += 1
                        continue
                    flush()
                    seg_page = page
                    seg_state = dict(sec)
                seg_lines.append(line)
                i += 1
        flush()

        # Emit dengan identitas & provensi penuh (AGENTS.md §9/§27):
        # setiap CP membawa jalur telusur CP -> source_fragment ->
        # source_document -> PDF Hukum/.
        seen = set()
        counters: Dict[tuple, int] = {}
        results: List[LearningOutcome] = []
        for seg in segments:
            norm = re.sub(r'\s+', ' ', seg['text']).strip().lower()[:400]
            # Kunci dedup menyertakan subjek+fase+element: dokumen 9941
            # sengaja MENGULANG teks langkah KP yang sama antar fase
            # (mis. KP AQH fase D vs E, p16 vs p17) - dedup teks-saja
            # membuang CP fase berikutnya yang sah.
            dedup_key = (seg['subject'], seg['fase'], seg['element'], norm)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            key = (seg['subject'], seg['fase'], seg['page'])
            counters[key] = counters.get(key, 0) + 1
            slug = seg['subject'].replace(' ', '-').replace("'", '')
            results.append(LearningOutcome(
                id=f"CP-{slug}-{seg['fase']}-{seg['page']}-{counters[key]}",
                subject=seg['subject'],
                phase=seg['fase'],
                element=seg['element'],
                text=seg['text'][:600],
                source_page=seg['page'],
                source_document=self._CP_SOURCE_LABEL,
                education_system='KEMENAG',
                institution_type='madrasah',
                education_level=seg.get('education_level') or '',
                curriculum_version_id=self._CP_CURRICULUM_VERSION,
                subject_id=None,
                phase_id=None,
                element_id=None,
                sub_element=seg.get('sub_element'),
                program_type=seg.get('program_type') or 'reguler',
                track=seg.get('track'),
                version='1.0',
                status='active',
            ))
        return results

    def _cp_is_noise_line(self, line: str) -> bool:
        """Baris yang TIDAK boleh memulai segmen fallback."""
        low = line.lower().rstrip('.')
        return any(low.startswith(p) for p in self._CP_SKIP_PREFIXES)

    # ------------------------------------------------------------------
    # Parser CP School (Pendidikan Agama dan Budi Pekerti) dari BKPDM
    # No. 020 Tahun 2026 (amandemen CP PAI-BP nasional atas BSKAP
    # 046/H/KR/2025 — per AGENTS.md §3/§4, CP PAI-BP sekolah diambil dari
    # sini, bukan dari 046 yang tetap berlaku untuk mapel lain).
    #
    # Lampiran BKPDM menyusun CP PAI-BP reguler sebagai bagian
    #   "1.1 CAPAIAN PEMBELAJARAN PENDIDIKAN AGAMA ISLAM DAN BUDI PEKERTI"
    #     "D. Capaian Pembelajaran"
    #       "1. Fase A (Umumnya untuk Kelas I dan II SD/MI/...)"  <- penanda fase
    #         "1.1. Al-Qur'an Hadis Membaca ..."                  <- item bernomor
    #     ... sampai "1.2 CAPAIAN PEMBELAJARAN ... KRISTEN ..."    <- akhir window
    #
    # Parser bekerja HANYA di dalam window bagian 1.1 (bagian agama lain
    # dan Pendidikan Khusus 2.x sengaja di luar scope — mapelnya berbeda).
    # OCR menghasilkan dua gaya penulisan item yang keduanya ditangani:
    #   (a) item bernomor + label inline: "6.1. Al-Qur'an Hadis Membaca ..."
    #   (b) label berdiri sendiri lalu badan CP di baris-baris berikutnya
    # Label elemen yang menempel di AKHIR baris lanjutan (layout dua kolom
    # PDF: "... malaikat. Akhlak") dipisahkan sebagai elemen item
    # BERIKUTNYA, bukan bagian badan CP. Elemen resmi (hal. 6): Al-Qur'an
    # Hadis, Akidah, Akhlak, Fikih, Sejarah Peradaban Islam. Pemilihan
    # label case-sensitive (label selalu kapital; kata yang sama di badan
    # CP huruf kecil) agar badan CP tidak salah potong. Provensi: halaman
    # fragmen pertama setiap item.
    # ------------------------------------------------------------------

    _CP_SCHOOL_DOC_ID = 'DOC-REG-KEMENDIKDASMEN-BKPDM-020-2026'
    _CP_SCHOOL_SOURCE_LABEL = 'BKPDM-020-2026'
    _CP_SCHOOL_SUBJECT = 'Pendidikan Agama dan Budi Pekerti'

    # Window bagian CP PAI-BP reguler (anchor nomor bagian "1.1"/"1.2"
    # agar tidak tertukar dengan bagian agama lain atau Pendidikan Khusus
    # "2.x" di dokumen yang sama).
    _CP_SCHOOL_WINDOW_START = re.compile(
        r'^1\.1\s+CAPAIAN\s+PEMBELAJARAN\s+PENDIDIKAN\s+AGAMA\s+ISLAM\b',
        re.IGNORECASE)
    _CP_SCHOOL_WINDOW_END = re.compile(
        r'^1\.2\s+CAPAIAN\s+PEMBELAJARAN\s+PENDIDIKAN\s+AGAMA\s+KRISTEN\b',
        re.IGNORECASE)
    # Gerbang konten CP di dalam window (setelah narasi rasional/karakteristik).
    _CP_SCHOOL_CP_GATE = re.compile(r'^d\.\s*capaian\s+pembelajaran\b', re.IGNORECASE)
    # Penanda fase: awal baris "Fase X (...)" / "1. Fase X (...)".
    _CP_SCHOOL_PHASE = re.compile(r'^(?:\d+\.\s*)?Fase\s+([A-F])\b')
    # Item CP bernomor "X.Y." — item valid HANYA bila diikuti label elemen.
    _CP_SCHOOL_ITEM = re.compile(r'^\d+\.\d+\.?\s*')

    # Label elemen (case-sensitive, kapital) — varian OCR "Al-Our'an/
    # Al-Qur'an/Al-Ouran" ditangani kelas karakter [QO] + apostrof opsional.
    _CP_SCHOOL_ELEMENT_START = (
        (re.compile(r"Al[-\s]*[QO]ur['’ʼ]?an\s+Hadis\b"), "Al-Qur'an Hadis"),
        (re.compile(r'\bAkidah\b'), 'Akidah'),
        (re.compile(r'\bAkhlak\b'), 'Akhlak'),
        (re.compile(r'\bFikih\b'), 'Fikih'),
        (re.compile(r'\bSejarah\s+Peradaban\s+Islam\b'), 'Sejarah Peradaban Islam'),
    )

    # Baris narasi pengantar fase — bukan CP.
    _CP_SCHOOL_NARRATIVE = ('pada akhir fase', 'kemampuan sebagai berikut',
                            'elemen dan deskripsi', 'elemen deskripsi')

    @staticmethod
    def _cp_school_match_element(text: str):
        """Cocokkan label elemen di AWAL teks (case-sensitive).
        Return (canonical_element, end_index) atau None."""
        for pat, canon in CurriculumEngine._CP_SCHOOL_ELEMENT_START:
            m = pat.match(text)
            if m:
                return canon, m.end()
        return None

    @staticmethod
    def _cp_school_split_trailing(line: str):
        """Pisahkan label elemen yang menempel di AKHIR baris lanjutan
        (layout dua kolom: "... malaikat. Akhlak"). Return (body, element)."""
        stripped = line.strip()
        for pat, canon in CurriculumEngine._CP_SCHOOL_ELEMENT_START:
            m = pat.search(stripped)
            if m and m.end() == len(stripped.rstrip('. ').rstrip()):
                body = stripped[:m.start()].strip().rstrip('.,')
                return body, canon
        return stripped, None

    def _extract_school_cp(self, fragments) -> List[LearningOutcome]:
        """State machine atas alur baris fragmen BKPDM 020 (window 1.1)."""
        in_window = False
        cp_started = False
        fase = None
        element = None
        page = None
        cur = None  # {'fase','element','page','lines'} — snapshot saat dibuka
        segments: List[dict] = []

        def flush():
            nonlocal cur
            if cur:
                text = ' '.join(cur['lines']).strip()
                if cur['fase'] and cur['element'] and len(text) >= 40:
                    segments.append({
                        'page': cur['page'], 'fase': cur['fase'],
                        'element': cur['element'], 'text': text,
                    })
                cur = None

        def process_line(line: str):
            nonlocal fase, element, cur
            # (1) Penanda fase di awal baris.
            m = self._CP_SCHOOL_PHASE.match(line)
            if m:
                flush()
                fase = m.group(1).upper()
                line = line[m.end():].strip()
                # Buang keterangan fase dalam kurung "(Umumnya untuk ...)":
                # layout OCR kadang memecahnya ke baris sendiri, dan tanpa
                # ini sisa kurung lolos jadi item CP. Konten sesungguhnya
                # SETELAH kurung tetap diproses (narrasi fase / item).
                if line.startswith('('):
                    close = line.find(')')
                    line = (line[close + 1:].strip() if close != -1 else '')
                if not line:
                    return
            # (2) Item bernomor yang tertanam di tengah baris konsolidasi
            # ("... berikut: 1.1. Al-Qur'an Hadis Membaca ...") — hanya
            # dianggap item bila nomornya langsung diikuti label elemen.
            # Hanya nomor di TENGAH baris yang di-redirect; nomor di posisi
            # 0 jatuh ke penangan item (4) — hindari rekursi tanpa ujung.
            m = self._CP_SCHOOL_ITEM.search(line)
            if m and m.start() > 0:
                after = line[m.end():].lstrip()
                if self._cp_school_match_element(after):
                    pre = line[:m.start()].strip()
                    if pre:
                        flush()  # narasi antar-item — bukan CP
                    return process_line(line[m.start():])
            # (3) Narasi pengantar fase — bukan CP.
            low = line.lower()
            if any(p in low for p in self._CP_SCHOOL_NARRATIVE):
                flush()
                return
            # (4) Item bernomor di awal baris.
            if self._CP_SCHOOL_ITEM.match(line):
                flush()
                rest = self._CP_SCHOOL_ITEM.sub('', line, count=1).strip()
                hit = self._cp_school_match_element(rest)
                if hit:
                    element, end = hit
                    body = rest[end:].strip()
                    body, next_elem = self._cp_school_split_trailing(body) \
                        if body else (body, None)
                    if body:
                        cur = {'fase': fase, 'element': element,
                               'page': page, 'lines': [body]}
                    if next_elem:
                        flush()
                        element = next_elem
                else:
                    element = None  # item tanpa label — jangan akumulasi
                return
            # (5) Label elemen berdiri sendiri.
            stripped = line.strip().rstrip('.')
            hit = self._cp_school_match_element(stripped)
            if hit and hit[1] == len(stripped):
                flush()
                element = hit[0]
                return
            # (6) Label elemen inline + badan CP satu baris.
            hit = self._cp_school_match_element(line)
            if hit:
                flush()
                element, end = hit
                rest = line[end:].strip()
                if rest:
                    body, next_elem = self._cp_school_split_trailing(rest)
                    if body:
                        cur = {'fase': fase, 'element': element,
                               'page': page, 'lines': [body]}
                    if next_elem:
                        flush()
                        element = next_elem
                return
            # (7) Baris lanjutan; mungkin diakhiri label item berikutnya.
            body, next_elem = self._cp_school_split_trailing(line)
            if not body and next_elem:
                flush()
                element = next_elem
                return
            if cur is None:
                if body and element:
                    cur = {'fase': fase, 'element': element,
                           'page': page, 'lines': [body]}
                # else: baris nyasar di luar item — buang
            else:
                cur['lines'].append(body or line)
            if next_elem:
                flush()
                element = next_elem

        for row in fragments:
            page = row['page_number']
            for raw in (row['text'] or '').split('\n'):
                line = raw.strip()
                if not line:
                    continue
                if self._CP_SCHOOL_WINDOW_START.match(line):
                    flush()
                    in_window = True
                    cp_started = False
                    continue
                if self._CP_SCHOOL_WINDOW_END.match(line):
                    flush()
                    in_window = False
                    cp_started = False
                    continue
                if not in_window:
                    continue
                if re.match(r'^-\s*\d+\s*-$', line):
                    continue  # penomoran halaman cetak
                if not cp_started:
                    m = self._CP_SCHOOL_CP_GATE.match(line)
                    if m:
                        cp_started = True
                        rest = line[m.end():].strip()
                        if rest:
                            process_line(rest)
                    continue
                process_line(line)
        flush()

        # Dedup + emit dengan provensi halaman.
        seen = set()
        counters: Dict[tuple, int] = {}
        results: List[LearningOutcome] = []
        for seg in segments:
            norm = re.sub(r'\s+', ' ', seg['text']).strip().lower()[:400]
            dedup_key = (seg['fase'], seg['element'], norm)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            key = (seg['fase'], seg['page'])
            counters[key] = counters.get(key, 0) + 1
            results.append(LearningOutcome(
                id=f"CP-PAI-BP-{seg['fase']}-{seg['page']}-{counters[key]}",
                subject=self._CP_SCHOOL_SUBJECT,
                phase=seg['fase'],
                element=seg['element'],
                text=seg['text'][:600],
                source_page=seg['page'],
                source_document=self._CP_SCHOOL_SOURCE_LABEL,
                education_system='KEMENDIKDASMEN',
                institution_type='sekolah',
                education_level='SD/MI s.d. SMA/MA (Fase A-F)',
                # BKPDM 020/2026 hanya amendemen CP PAB di dalam kurikulum
                # KEMENDIKDASMEN-2025, bukan versi kurikulum tersendiri.
                curriculum_version_id='KEMENDIKDASMEN-2025',
                program_type='reguler',
                version='1.0',
                status='active',
            ))
        return results

    # ------------------------------------------------------------------
    # CP agama selain PAI-BP di BKPDM 020/2026.
    #
    # Diktum KESATU mengubah CP Pendidikan Agama dan Budi Pekerti serta
    # Pendidikan Khusus Pendidikan Agama dan Budi Pekerti. Lampiran memuat
    # enam agama, masing-masing jalur reguler (1.2-1.6) dan pendidikan
    # khusus (2.1-2.6). PAI-BP reguler (1.1) ditangani _extract_school_cp
    # di atas; agama lain bentuk itemnya seragam ("1.1. Kitab Suci Weda
    # Mengenali ...") sehingga satu parser cukup.
    #
    # OCR memecah item di batas fragmen: nomor di akhir satu fragmen,
    # label di fragmen berikutnya ("2.2. Ritual" + "Etika"). Keduanya
    # disambung sebelum diparse. Item yang nomornya hilang sama sekali
    # (label tanpa nomor) tidak bisa dipastikan milik fase mana, jadi
    # tidak diambil — lebih baik kurang daripada salah pasang.
    # ------------------------------------------------------------------

    _CP_RELIGION_SECTIONS = (
        ('1.2', 'Pendidikan Agama Kristen dan Budi Pekerti', 'sekolah'),
        ('1.3', 'Pendidikan Agama Katolik dan Budi Pekerti', 'sekolah'),
        ('1.4', 'Pendidikan Agama Hindu dan Budi Pekerti', 'sekolah'),
        ('1.5', 'Pendidikan Agama Buddha dan Budi Pekerti', 'sekolah'),
        ('1.6', 'Pendidikan Agama Khonghucu dan Budi Pekerti', 'sekolah'),
        ('2.1', 'Pendidikan Khusus Agama Islam dan Budi Pekerti',
         'pendidikan_khusus'),
        ('2.2', 'Pendidikan Khusus Agama Kristen dan Budi Pekerti',
         'pendidikan_khusus'),
        ('2.3', 'Pendidikan Khusus Agama Katolik dan Budi Pekerti',
         'pendidikan_khusus'),
        ('2.4', 'Pendidikan Khusus Agama Hindu dan Budi Pekerti',
         'pendidikan_khusus'),
        ('2.5', 'Pendidikan Khusus Agama Buddha dan Budi Pekerti',
         'pendidikan_khusus'),
        ('2.6', 'Pendidikan Khusus Agama Khonghucu dan Budi Pekerti',
         'pendidikan_khusus'),
    )

    _CP_RELIGION_HEAD = re.compile(
        r'^(\d+\.\d+)\s+CAPAIAN\s+PEMBELAJARAN\s+PENDIDIKAN', re.I)
    _CP_RELIGION_GATE = re.compile(r'^D\.\s*Capaian\s+Pembelajaran', re.I)
    _CP_RELIGION_PHASE = re.compile(r'^(?:\d+\.?\s*)?Fase\s+([A-F])\b')
    _CP_RELIGION_ITEM = re.compile(r'^(\d+)\.(\d+)\.?\s+(\S.*?)\s*$')
    # Nomor item yang kehilangan labelnya di batas fragmen.
    _CP_RELIGION_DANGLING = re.compile(r'\d+\.\d+\.?\s*$')
    _CP_RELIGION_LABEL = re.compile(r"^[A-ZÀ-ɏ][A-Za-zÀ-ɏ' \-]{1,40}$")
    _CP_RELIGION_NARRATIVE = (
        'pada akhir fase', 'capaian pembelajaran setiap elemen',
        'kemampuan sebagai berikut', 'murid memiliki kemampuan',
        'peserta didik memiliki kemampuan')

    @staticmethod
    def _religion_element(name: str) -> str:
        """Rapikan nama elemen yang dirusak OCR.

        Karakter Han di "Perilaku Junzi (君子)" terbaca sebagai simbol acak
        ("(#+", "(ET", "(2"). Semuanya satu elemen yang sama."""
        name = name.rstrip('.').strip()
        if name.startswith('Perilaku Junzi'):
            return 'Perilaku Junzi'
        # OCR membaca apostrof "Al-Qur'an" sebagai tanda kutip lain.
        name = name.replace('’', "'").replace('‘', "'")
        return name

    @staticmethod
    def _table_element_kind(prefix: str, subject: str):
        """Petakan awalan baris tabel ke elemen kanonik subject tersebut.

        Tabel CP Kristen/Katolik/PK-Kristen di BKPDM 020 tidak memakai
        nomor item ("1.1. ...") melainkan kolom Elemen | Subelemen | CP,
        sehingga parser bernomor (_extract_religion_cp) tidak pernah
        cocok di sini. Pencocokan memakai kata kunci awal kolom elemen
        / subelemen (case-insensitive); return nama kanonik persis
        seperti di curriculum_mappings.json, atau None."""
        low = (prefix or '').lower()
        if 'kristen' in subject.lower() or 'khusus agama kristen' in subject.lower():
            if low.startswith('allah') or low.startswith('| allah'):
                return 'Allah Berkarya'
            if (low.startswith('manusia') or low.startswith('hakikat')
                    or low.startswith('nilai')):
                return 'Manusia dan Nilai-nilai Kristiani'
            if (low.startswith('gereja') or low.startswith('masyarakat')
                    or low.startswith('tugas') or low.startswith('panggilan')):
                return 'Gereja dan Masyarakat Majemuk'
            if (low.startswith('alam') or low.startswith('lingkungan')
                    or low.startswith('tanggung') or low.startswith('ciptaan')):
                return 'Alam dan Lingkungan Hidup'
            # Subelemen tanpa label elemennya ("Allah Pencipta",
            # "Allah Pemelihara", ...): kata keduanya tetap menunjuk
            # elemen yang sama.
            if any(k in low for k in ('pencipta', 'pemelihara',
                                      'penyelamat', 'pembaru')):
                return 'Allah Berkarya'
            return None
        # Katolik: empat elemen terpisah.
        if low.startswith('pribadi'):
            return 'Pribadi Murid'
        if 'yesus' in low.split('|')[0][:30]:
            return 'Yesus Kristus'
        if low.startswith('gereja'):
            return 'Gereja'
        if low.startswith('masyarakat'):
            return 'Masyarakat'
        return None

    # Bagian tabel BKPDM 020 (kolom Elemen|Subelemen|CP, tanpa nomor
    # item): 1.2 Kristen reguler, 1.3 Katolik reguler, 2.2 Kristen
    # pendidikan khusus. Elemen persis mapping yang sudah ada.
    _CP_TABLE_SECTIONS = {
        '1.2': ('Pendidikan Agama Kristen dan Budi Pekerti', 'sekolah'),
        '1.3': ('Pendidikan Agama Katolik dan Budi Pekerti', 'sekolah'),
        '2.2': ('Pendidikan Khusus Agama Kristen dan Budi Pekerti',
                'pendidikan_khusus'),
    }

    _CP_TABLE_STARTER = re.compile(
        r'\b(Murid|Memahami|Menjelaskan|Menerapkan|Menganalisis|Memaknai|'
        r'Menyimpulkan|Mengevaluasi|Mewujudkan|Mengungkapkan|'
        r'Mempraktikkan|Mendeskripsikan|Mengidentifikasi|Menyebutkan|'
        r'Mengenal|Mensyukuri|Menghayati|Merefleksikan)\b')
    _CP_TABLE_JUNK = frozenset({
        'elemen', 'subelemen', 'capaian pembelajaran',
        'elemen subelemen', 'saas',
        'subelemen capaian pembelajaran',
        'elemen subelemen capaian pembelajaran',
    })

    # Elemen kanonik (urutan dokumen) per subject tabel. Kristen /
    # PK-Kristen: beberapa sub-baris per elemen (label kolom presque
    # selalu ada) -> elemen dari kata kunci label. Katolik: satu baris
    # per elemen tanpa label inline -> elemen dari urutan baris.
    _CP_TABLE_ELEMENTS = {
        'Pendidikan Agama Kristen dan Budi Pekerti': [
            'Allah Berkarya', 'Manusia dan Nilai-nilai Kristiani',
            'Gereja dan Masyarakat Majemuk', 'Alam dan Lingkungan Hidup'],
        'Pendidikan Agama Katolik dan Budi Pekerti': [
            'Pribadi Murid', 'Yesus Kristus', 'Gereja', 'Masyarakat'],
        'Pendidikan Khusus Agama Kristen dan Budi Pekerti': [
            'Allah Berkarya', 'Manusia dan Nilai-nilai Kristiani',
            'Gereja dan Masyarakat Majemuk', 'Alam dan Lingkungan Hidup'],
    }

    # Penanda fase tabel: OCR kadang menggugurkan nomornya (". Fase D"
    # di Katolik hal. 23) sehingga titik di depan ikut diterima.
    _CP_TABLE_PHASE = re.compile(r'^(?:[\d\.]+\s*)?Fase\s+([A-F])\b')
    # Kosakata label kolom tabel (elemen/subelemen/penghubung). Baris
    # yang hanya berisi kosakata ini adalah label murni; baris yang
    # memuat kata lain membawa badan CP sehingga teksnya wajib
    # dipertahankan (dibuang = CP terpotong dan provenance putus).
    _CP_TABLE_LABEL_VOCAB = frozenset({
        'allah', 'berkarya', 'pencipta', 'pemelihara', 'penyelamat',
        'pembaru', 'manusia', 'hakikat', 'nilai', 'kristiani',
        'gereja', 'masyarakat', 'majemuk', 'tugas', 'panggilan',
        'alam', 'lingkungan', 'hidup', 'ciptaan', 'tanggung', 'jawab',
        'terhadap', 'pribadi', 'murid', 'yesus', 'kristus', 'dan',
        'nilai-nilai', 'nilai–nilai',
    })

    @classmethod
    def _table_is_pure_label(cls, line: str) -> bool:
        """True bila baris hanya berisi label kolom (tanpa badan CP)."""
        tokens = re.findall(r'[A-Za-zÀ-ɏ]+', (line or '').lower())
        rest = [t for t in tokens if t not in cls._CP_TABLE_LABEL_VOCAB]
        return len(rest) <= 1
    # Sisa OCR batas kolom ("n i u ."): huruf tunggal berspasi.
    _CP_TABLE_LETTER_JUNK = re.compile(r'[A-Za-z]( [A-Za-z])+ *[.|\-]*')

    def _extract_table_religion_cp(self, fragments) -> List[LearningOutcome]:
        """CP tabel 1.2/1.3/2.2 BKPDM 020 (Kristen, Katolik, PK-Kristen).

        Satu baris tabel = satu CP. Baris tabel hanya diakui sesudah
        pengantar tabel fase itu ("Capaian Pembelajaran setiap elemen
        ..."/kepala kolom) sehingga narasi pengantar fase ("Pada akhir
        Fase ..., murid ...") tidak bocor menjadi CP atau konteks
        elemen. Baris baru dibuka oleh kalimat CP ("Murid ..."/kata
        kerja kapital); label elemen di awal baris menentukan elemennya
        (Kristen), baris Katolik tanpa label memakai urutan baris sesuai
        urutan empat elemen di dokumen. Baris lanjutan digabung ke CP
        berjalan. Label kolom yang menempel di tengah baris lanjutan
        hanya memutus CP bila CP berjalan sudah cukup panjang (batas
        80 karakter) - kalau tidak, itu pecahan kolom baris yang sama.
        Teks CP dipertahankan apa adanya dari fragmen."""
        subject = inst = None
        gate = False
        fase = None
        in_table = False
        element_ctx = None
        kat_idx = 0
        cur = None
        segments = []

        def flush():
            nonlocal cur
            if (cur and cur['element'] and cur['fase']
                    and len(cur['text']) >= 25):
                segments.append(cur)
            cur = None

        for row in fragments:
            page = row['page_number']
            frag_id = row['id']
            section = row['section']
            for raw in (row['text'] or '').split('\n'):
                line = raw.strip().strip('|').strip()
                if not line:
                    continue
                m = self._CP_RELIGION_HEAD.match(line)
                if m:
                    flush()
                    code = m.group(1)
                    if code in self._CP_TABLE_SECTIONS:
                        subject, inst = self._CP_TABLE_SECTIONS[code]
                    else:
                        subject = inst = None
                    gate = False
                    fase = None
                    in_table = False
                    element_ctx = None
                    kat_idx = 0
                    continue
                if subject is None:
                    continue
                if not gate:
                    if self._CP_RELIGION_GATE.match(line):
                        gate = True
                    continue
                m = self._CP_TABLE_PHASE.match(line)
                if m:
                    flush()
                    fase = m.group(1)
                    in_table = False
                    element_ctx = None
                    kat_idx = 0
                    continue
                low = line.lower().rstrip('.')
                if 'capaian pembelajaran setiap elemen' in low:
                    # Pengantar tabel fase itu; baris berikutnya adalah
                    # isi tabel. Baris ini sendiri bukan CP.
                    in_table = True
                    continue
                if any(p in low for p in self._CP_RELIGION_NARRATIVE):
                    continue
                if low in self._CP_TABLE_JUNK or (
                        'elemen' in low and 'capaian pembelajaran' in low):
                    # Kepala kolom tabel ("Elemen", "Subelemen",
                    # "Elemen Subelemen | Capaian Pembelajaran").
                    in_table = True
                    continue
                if not in_table or not fase:
                    continue
                if line.startswith('(') and 'yesus' in low:
                    # Pecahan label elemen ("(Yesus Kristus fT").
                    element_ctx = 'Yesus Kristus'
                    continue
                if self._CP_TABLE_LETTER_JUNK.fullmatch(line):
                    continue
                sm = self._CP_TABLE_STARTER.search(line)
                if sm:
                    prefix = line[:sm.start()]
                    body = line[sm.start():].strip()
                    elem = self._table_element_kind(prefix, subject)
                    if 'Katolik' in subject:
                        order = self._CP_TABLE_ELEMENTS[subject]
                        if elem:
                            element_ctx = elem
                            kat_idx = order.index(elem) + 1
                        else:
                            element_ctx = order[kat_idx % len(order)]
                            kat_idx += 1
                    else:
                        if elem:
                            element_ctx = elem
                        elif element_ctx is None:
                            # Kepala baris terpotong dari labelnya
                            # (batas fragmen): baris pertama fase
                            # selalu elemen pertama.
                            element_ctx = self._CP_TABLE_ELEMENTS[
                                subject][0]
                    flush()
                    cur = {'subject': subject, 'inst': inst, 'fase': fase,
                           'page': page, 'frag_id': frag_id,
                           'section': section,
                           'element': element_ctx, 'text': body,
                           'pages': [page]}
                    continue
                # Baris tanpa kalimat CP baru.
                elem = self._table_element_kind(line, subject)
                if elem and len(line) <= 60:
                    # Label kolom berdiri sendiri. Baris berjalan yang
                    # sudah utuh (>= 80 karakter) ditutup; yang masih
                    # pendek menandakan label pecahan kolom: label MURNI
                    # ("Allah Allah Pencipta") dibuang, tetapi baris
                    # campuran label + badan ("Nilai-nilai manusia
                    # adalah makhluk") wajib digabung karena memuat
                    # kata badan CP (dibuang = CP terpotong dan
                    # provenance putus). Konteks elemen tidak ditimpa
                    # selama baris berjalan belum selesai.
                    if cur is not None and len(cur['text']) >= 80:
                        flush()
                        element_ctx = elem
                    elif cur is None:
                        element_ctx = elem
                    elif not self._table_is_pure_label(line):
                        cur['text'] += ' ' + line
                        if page not in cur['pages']:
                            cur['pages'].append(page)
                        element_ctx = elem
                    continue
                if cur is not None:
                    if elem:
                        element_ctx = elem
                        cur['element'] = elem
                    cur['text'] += ' ' + line
                    if page not in cur['pages']:
                        cur['pages'].append(page)
                elif elem:
                    element_ctx = elem
        flush()

        seen = set()
        counters: Dict[tuple, int] = {}
        results: List[LearningOutcome] = []
        for seg in segments:
            text = re.sub(r'\s+', ' ', seg['text']).strip()
            norm = text.lower()[:400]
            key = (seg['subject'], seg['fase'], seg['element'], norm)
            if key in seen:
                continue
            seen.add(key)
            seq_key = (seg['subject'], seg['fase'], seg['page'])
            counters[seq_key] = counters.get(seq_key, 0) + 1
            slug = re.sub(r'[^a-z0-9]+', '-', seg['subject'].lower())
            slug = slug.strip('-')[:24]
            results.append(LearningOutcome(
                id=(f"CP-{slug}-{seg['fase']}-{seg['page']}-"
                    f"{counters[seq_key]}"),
                subject=seg['subject'],
                phase=seg['fase'],
                element=self._religion_element(seg['element']),
                text=text[:600],
                source_page=seg['page'],
                source_pages=seg['pages'],
                source_document=self._CP_SCHOOL_SOURCE_LABEL,
                education_system='KEMENDIKDASMEN',
                institution_type=seg['inst'],
                education_level='SD/MI s.d. SMA/MA (Fase A-F)',
                curriculum_version_id='KEMENDIKDASMEN-2025',
                program_type='reguler',
                version='1.0',
                status='active',
            ))
        return results

    def _extract_religion_cp(self, fragments) -> List[LearningOutcome]:
        """CP agama bernomor 1.4-1.6 dan 2.1/2.3-2.6 dari fragmen BKPDM 020.

        Bagian tabel (1.2 Kristen, 1.3 Katolik, 2.2 PK-Kristen) memakai
        kolom Elemen|Subelemen|CP tanpa nomor item sehingga tidak
        pernah cocok di sini; bagian itu ditangani
        _extract_table_religion_cp dan dilewati di sini agar tidak
        terjadi duplikasi."""
        by_code = {code: (name, inst)
                   for code, name, inst in self._CP_RELIGION_SECTIONS}

        # Sambung nomor item yang terpisah dari labelnya.
        merged = []
        for row in fragments:
            text = row['text'] or ''
            if merged and self._CP_RELIGION_LABEL.match(text.strip()) \
                    and self._CP_RELIGION_DANGLING.search(
                        merged[-1]['text'].rstrip()):
                prev = merged[-1]
                prev['text'] = (prev['text'].rstrip() + ' ' + text.strip())
            else:
                merged.append({'page': row['page_number'], 'text': text})

        subject = inst = None
        gate = False
        fase = None
        cur = None
        segments = []

        def flush():
            nonlocal cur
            if cur and cur['element'] and cur['fase'] \
                    and len(cur['text']) >= 25:
                segments.append(cur)
            cur = None

        for block in merged:
            for raw in block['text'].split('\n'):
                line = raw.strip()
                if not line:
                    continue
                m = self._CP_RELIGION_HEAD.match(line)
                if m:
                    flush()
                    if m.group(1) in self._CP_TABLE_SECTIONS:
                        # Bagian tabel (1.2/1.3/2.2) ditangani
                        # _extract_table_religion_cp.
                        subject, inst = None, None
                    else:
                        subject, inst = by_code.get(m.group(1), (None, None))
                    gate = False
                    fase = None
                    continue
                if subject is None:
                    continue
                if not gate:
                    if self._CP_RELIGION_GATE.match(line):
                        gate = True
                    continue
                m = self._CP_RELIGION_PHASE.match(line)
                if m:
                    flush()
                    fase = m.group(1)
                    continue
                low = line.lower()
                if any(p in low for p in self._CP_RELIGION_NARRATIVE):
                    continue
                m = self._CP_RELIGION_ITEM.match(line)
                if m and fase:
                    flush()
                    cur = {'subject': subject, 'inst': inst, 'fase': fase,
                           'page': block['page'], 'element': m.group(3),
                           'text': '', 'pages': [block['page']]}
                    continue
                if cur is not None and not self._CP_RELIGION_ITEM.match(line):
                    cur['text'] += (' ' if cur['text'] else '') + line
                    if block['page'] not in cur['pages']:
                        cur['pages'].append(block['page'])
        flush()

        seen = set()
        counters: Dict[tuple, int] = {}
        results: List[LearningOutcome] = []
        for seg in segments:
            norm = re.sub(r'\s+', ' ', seg['text']).strip().lower()[:400]
            key = (seg['subject'], seg['fase'], seg['element'], norm)
            if key in seen:
                continue
            seen.add(key)
            seq_key = (seg['subject'], seg['fase'], seg['page'])
            counters[seq_key] = counters.get(seq_key, 0) + 1
            slug = re.sub(r'[^a-z0-9]+', '-', seg['subject'].lower())
            slug = slug.strip('-')[:24]
            results.append(LearningOutcome(
                id=(f"CP-{slug}-{seg['fase']}-{seg['page']}-"
                    f"{counters[seq_key]}"),
                subject=seg['subject'],
                phase=seg['fase'],
                element=self._religion_element(seg['element']),
                text=re.sub(r'\s+', ' ', seg['text']).strip()[:600],
                source_page=seg['page'],
                source_pages=seg['pages'],
                source_document=self._CP_SCHOOL_SOURCE_LABEL,
                education_system='KEMENDIKDASMEN',
                institution_type=seg['inst'],
                education_level='SD/MI s.d. SMA/MA (Fase A-F)',
                curriculum_version_id='KEMENDIKDASMEN-2025',
                program_type='reguler',
                version='1.0',
                status='active',
            ))
        return results

    def extract_religion_cp_from_fragments(self) -> List[LearningOutcome]:
        """CP agama selain PAI-BP (Kristen, Katolik, Hindu, Buddha,
        Khonghucu, reguler dan pendidikan khusus) dari BKPDM 020/2026.

        Bagian bernomor (1.4-1.6, 2.1, 2.3-2.6) lewat _extract_religion_cp;
        bagian tabel (1.2 Kristen, 1.3 Katolik, 2.2 PK-Kristen) lewat
        _extract_table_religion_cp. Keduanya dari fragmen kanonik yang
        sama; tidak ada tumpang tindih bagian."""
        print("📚 Extracting CP agama lain (BKPDM 020/2026)...")
        try:
            self.cursor.execute("""
                SELECT sf.id, sf.page_number, sf.paragraph, sf.section, sf.text
                FROM source_fragments sf
                WHERE sf.document_id = ?
                ORDER BY sf.page_number, sf.paragraph
            """, (self._CP_SCHOOL_DOC_ID,))
            fragments = self.cursor.fetchall()
            entries = self._extract_religion_cp(fragments)
            table_entries = self._extract_table_religion_cp(fragments)
            seen = {(e.subject, e.phase, e.element,
                     re.sub(r'\s+', ' ', e.text).strip().lower()[:400])
                    for e in entries}
            for e in table_entries:
                key = (e.subject, e.phase, e.element,
                       re.sub(r'\s+', ' ', e.text).strip().lower()[:400])
                if key not in seen:
                    seen.add(key)
                    entries.append(e)
            self._cp_attach_fragment_provenance(entries, fragments)
            print(f"   ✅ Extracted {len(entries)} CP agama lain "
                  f"({len(table_entries)} dari tabel 1.2/1.3/2.2)")
            return entries
        except Exception as e:
            print(f"   ❌ Error extracting CP agama: {e}")
            return []

    def extract_school_cp_from_fragments(self) -> List[LearningOutcome]:
        """Extract CP Pendidikan Agama dan Budi Pekerti (sekolah) dari
        fragmen kanonik BKPDM 020/2026, dengan provensi halaman."""
        print("📚 Extracting CP School (BKPDM 020/2026, PAI-BP)...")
        try:
            self.cursor.execute("""
                SELECT sf.id, sf.page_number, sf.paragraph, sf.section, sf.text
                FROM source_fragments sf
                WHERE sf.document_id = ?
                ORDER BY sf.page_number, sf.paragraph
            """, (self._CP_SCHOOL_DOC_ID,))
            fragments = self.cursor.fetchall()
            entries = self._extract_school_cp(fragments)
            self._cp_attach_fragment_provenance(entries, fragments)
            print(f"   ✅ Extracted {len(entries)} CP School entries")
            return entries
        except Exception as e:
            print(f"   ❌ Error extracting CP School: {e}")
            return []

    # ------------------------------------------------------------------
    # Parser CP mapel umum dari Kepka BSKAP 046/H/KR/2025.
    #
    # CP Pendidikan Agama dan Budi Pekerti TIDAK diambil dari sini —
    # BKPDM 020/2026 mengamendemennya (parser _extract_school_cp).
    # 046 tetap sumber CP mapel lain (AGENTS.md §3).
    #
    # Setiap bab berheading "IV.1. CAPAIAN PEMBELAJARAN MATEMATIKA"
    # (atau "XVI. CAPAIAN PEMBELAJARAN SOSIOLOGI" tanpa nomor sub-bab),
    # lalu bagian "D. Capaian Pembelajaran", penanda fase, dan item CP.
    # Item ada dua bentuk: "1.1. Bilangan ..." (sub-nomor elemen, mapel
    # umum) dan "1. Wawasan Bidang Teknik Mesin ..." (mapel kejuruan).
    # Layout dua kolom memotong kata antar-baris; _cp046_merge_lines
    # menyambungnya sebelum parsing.
    # ------------------------------------------------------------------

    _CP046_DOC_ID = 'DOC-REG-KEMENDIKDASMEN-BSKAP-046-2025'
    _CP046_SOURCE_LABEL = 'BSKAP-046/H/KR/2025'
    _CP046_MIN_TEXT = 40

    # Heading bab. Butir diktum pembuka ("c. Capaian Pembelajaran pada")
    # diawali huruf kecil, jadi kode romawi wajib kapital. Titik setelah
    # romawi opsional ("X CAPAIAN PEMBELAJARAN" di pendidikan khusus),
    # tetapi romawi wajib diikuti pemisah — tanpa itu "V.2." yang pecah
    # jadi "IV" terbaca sebagai bab "IV".
    _CP046_BAB_RE = re.compile(
        r"(?:^|\. )([IVXLC]+)(?:\.| (?=[A-Z]))(?:(\d+)\.?)?\s*"
        r"(?:CAPAIAN|Capaian) (?:PEMBELAJARAN|Pembelajaran)"
        r"(?![A-Za-z])(.*)$")
    _CP046_GATE_RE = re.compile(r"^D\. Capaian Pembelajaran$")
    _CP046_GATE_BROKEN_RE = re.compile(r"^D\. Capa(ian)?$")
    _CP046_PHASE_RE = re.compile(
        r"^(?:\d+\.\s*)?(?:Pada akhir\s+)?Fase ([A-F]|Fondasi)\b", re.I)
    _CP046_PHASE_HANG_RE = re.compile(r"^(?:\d+\.\s*)?Pada akhir Fase$", re.I)
    _CP046_PHASE_CONT_RE = re.compile(r"^([A-F]|Fondasi)\b", re.I)
    _CP046_ITEM_SUB_RE = re.compile(r"^(\d+)\.(\d+)\.?\s+(\S.*)$")
    _CP046_ITEM_PLAIN_RE = re.compile(r"^(\d+)\.\s+([A-ZÀ-ɏ\"“].*)$")
    _CP046_NARRATIVE_RE = re.compile(
        r"^(Pada akhir [Ff]ase|Subelemen di dalam|Elemen dan deskripsi|"
        r"Capaian pembelajaran mata pelajaran|Rumusan Capaian|"
        r"berikut\.?:?$)", re.I)

    @staticmethod
    def _cp046_amended(subject: str) -> bool:
        """True bila mapel ini termasuk Pendidikan Agama yang
        diamendemen BKPDM 020/2026. Mencakup reguler dan Pendidikan
        Khusus; mapel lain tidak."""
        return 'AGAMA' in subject

    @staticmethod
    def _cp046_institution(subject: str) -> str:
        """Pendidikan Khusus dan Program Kebutuhan Khusus bukan satuan
        reguler. Selain itu satuan umum."""
        if subject.startswith('PENDIDIKAN KHUSUS') \
                or subject.startswith('PROGRAM KEBUTUHAN'):
            return 'pendidikan_khusus'
        return 'sekolah'

    @staticmethod
    def _cp046_split_word(prev: str, nxt: str) -> bool:
        """True bila prev berakhir di pecahan kata yang disambung nxt.

        Layout kolom memotong kata antar-baris ("Keterampil" + "an
        Proses", "Pada akhir F" + "ase F"). Lanjutan yang berupa kata
        utuh ("murid", "berikut") lebih panjang dari ambang dan tidak
        disambung, supaya item CP tidak ikut tersambung.
        """
        if not prev or not nxt or not prev[-1].isalpha():
            return False
        tail = prev.split()[-1]
        if tail == "Pada" and nxt.startswith("akhir"):
            return True
        if not nxt[:1].islower():
            return False
        return len(nxt.split()[0]) <= 12

    @classmethod
    def _cp046_merge_lines(cls, lines):
        """Sambung baris yang berakhir di pecahan kata.

        Tiap item lines = (halaman, teks, batas_fragmen). batas_fragmen
        True hanya di baris pertama sebuah fragmen. Pecahan kata huruf
        kapital ("KENDA" + "RAAN") hanya disambung di batas itu; di
        dalam fragmen baris kapital adalah item CP yang utuh.
        """
        merged = []
        i = 0
        while i < len(lines):
            page, s, boundary = lines[i][0], lines[i][1], lines[i][2]
            pages = [page]
            while i + 1 < len(lines) and cls._cp046_split_word(
                    s, lines[i + 1][1]):
                nxt_page, nxt = lines[i + 1][0], lines[i + 1][1]
                # "Pada" + "akhir" butuh spasi; "F" + "ase" pecahan di
                # tengah kata, disambung tanpa spasi.
                gap = " " if s.split()[-1][:1].isupper() and len(
                    s.split()[-1]) > 1 else ""
                i += 1
                s = s + gap + nxt
                pages.append(nxt_page)
            # Tanda batas fragmen dipertahankan: pecahan nama mapel
            # huruf kapital hanya terjadi di baris pertama fragmen.
            merged.append((page, s, pages, boundary))
            i += 1
        return merged

    @staticmethod
    def _cp046_join(parts) -> str:
        """Gabungkan baris badan CP; kata terpenggal disambung."""
        out = ""
        for p in parts:
            if out and out[-1].isalpha() and p[:1].islower():
                out += p
            else:
                out += (" " if out else "") + p
        return re.sub(r"\s+", " ", out).strip()

    def _cp046_chapters(self, lines):
        """Daftar (indeks, halaman, kode, judul) heading bab."""
        babs = []
        for i, (page, s, _pages, _boundary) in enumerate(lines):
            # "I" di ujung baris adalah pecahan dari "IV.2." di baris
            # berikutnya, bukan bab tersendiri.
            if re.fullmatch(r"[IVXLC]", s) and i + 1 < len(lines) \
                    and self._CP046_BAB_RE.search(s + lines[i + 1][1]):
                continue
            # "CAPAIAN" pecah antar-baris ("CA" + "PAIAN", "CAPAIAN PEMB"
            # + "ELAJARAN"). Pecahan nama mapel disambung di
            # _cp046_subject, bukan di sini.
            while i + 1 < len(lines) \
                    and (re.search(r'CAPAIAN( P+(EMB?)?)?$', s)
                         or s.endswith('CA')):
                nxt = lines[i + 1][1]
                head = nxt.split()[0]
                # Baris berikutnya yang sendiri heading bab bukan
                # lanjutan. Lanjutan sah: pecahan kata (tanpa vokal di
                # tiga huruf terakhir: "RAAN", "KNIK", "ENIHAN") atau
                # sisa kata "PEMBELAJARAN" yang terpotong ("P" +
                # "EMBELAJARAN", "PEMB" + "ELAJARAN", "PAIAN" +
                # "PEMBELAJARAN"). Kata utuh ("DAN", "BUDI") tidak.
                if self._CP046_BAB_RE.search(nxt):
                    break
                tail3 = head[-3:]
                fragment = head.isupper() and head.isalpha() \
                    and len(head) <= 12 \
                    and not re.search(r'[AEIOU]', tail3)
                pembelajaran = head in ('EMBELAJARAN', 'ELAJARAN',
                                        'PEMBELAJARAN', 'PAIAN')
                if not (fragment or pembelajaran):
                    break
                s = s + nxt
                i += 1
            # Ekstraksi menyisipkan spasi di tengah kata heading
            # ("VI.89. CA PAIAN PEMBELAJARAN ...", "... CAPAIAN PEMB
            # ELAJARAN ..."). Hanya pola yang benar-benar pecah;
            # heading utuh tidak boleh ikut berubah.
            s = re.sub(r"CA PAIAN", "CAPAIAN", s)
            s = re.sub(r"PEMB ELAJARAN", "PEMBELAJARAN", s)
            m = self._CP046_BAB_RE.search(s)
            if m is None and i + 1 < len(lines):
                nxt = lines[i + 1][1]
                tail = re.sub(r"[A-Z]+$", "", s)
                # Heading pecah antar-baris: di tengah kata ("... TE" +
                # "KNIK"), di spasi (kedua baris kapital), atau di tengah
                # kata "PEMBELAJARAN" ("CAPAIAN PEMB" + "ELAJARAN").
                # "CAPAIAN PEMBELAJARAN" yang pecah di mana pun:
                # "CAPAIAN PEMB" + "ELAJARAN" atau "CAPAIAN" + "EMBELAJARAN".
                glued = s + nxt if re.search(
                    r"CAPAIAN( P+(EM[A-Z]*)?)?$", s) else ""
                spaced = s + " " + nxt if s.isupper() and nxt.isupper() \
                    else ""
                for cand in (tail + nxt, glued, spaced):
                    # Penyambung baris menyisipkan spasi di tengah kata
                    # heading ("CA PAIAN", "CAPAIAN P" + "EMBELAJARAN").
                    cand = re.sub(r"C[A ]*PAIAN", "CAPAIAN", cand)
                    cand = re.sub(r"CAPAIAN P+E", "CAPAIAN PE", cand)
                    cand = re.sub(r"P[E ]*MBELAJARAN", "PEMBELAJARAN", cand)
                    if cand and self._CP046_BAB_RE.search(cand):
                        m = self._CP046_BAB_RE.search(cand)
                        break
            if m:
                num = m.group(2)
                code = f"{m.group(1)}.{num}" if num else m.group(1)
                babs.append((i, page, code, m.group(3).strip(), s))
        return babs

    def _cp046_subject(self, window) -> str:
        """Nama mapel satu bab: judul heading plus lanjutan yang kapital
        semua, berhenti di "A. Rasional" atau gerbang CP."""
        # heading_line = baris heading yang sudah disambung dan
        # dinormalisasi di _cp046_chapters. Nama mapel diambil dari
        # situ, bukan dari baris mentah yang masih pecah.
        # Pemanggil menaruh heading ternormalisasi di elemen terakhir
        # baris pertama. Elemen ketiga adalah daftar halaman, bukan
        # heading — jangan dibaca sebagai heading.
        heading_line = window[0][-1] if len(window[0]) > 3 else window[0][1]
        # Penyambung pecahan menyatukan tanpa spasi ("CA" + "PAIAN"
        # jadi "CAPAIAN"). Kembalikan ke bentuk baku sebelum dipotong.
        heading_line = re.sub(r'CA\s*PAIAN', 'CAPAIAN', heading_line)
        name_parts = [re.sub(r'^.*?CAPAIAN PEMBELAJARAN\s*', '',
                             heading_line)]
        # Nama mapel pecah antar-fragmen, seluruhnya kapital ("TEKNIK
        # KENDA" + "RAAN RINGAN"). _cp046_merge_lines hanya menyambung
        # lanjutan huruf kecil agar tidak menelan badan CP, jadi
        # penyambungan nama dilakukan di sini.
        # Pemanggil menimpa window[0] dengan heading ternormalisasi, jadi
        # baris itu tidak pernah cocok dengan heading_line. Baris pecahan
        # ("RAAN RINGAN") ada persis sesudahnya — mulai dari situ, bukan
        # dari 0, supaya baris itu tidak terlewat.
        head_idx = next((j for j, row in enumerate(window)
                         if row[1] == heading_line), None)
        if head_idx is None:
            head_idx = 0 if len(window) > 1 else -1
        for row in window[head_idx + 1:]:
            s = row[1]
            if not s.isupper() or self._CP046_GATE_RE.match(s):
                break
            # Baris di dalam fragmen yang sama selalu lanjutan nama.
            # Baris pertama fragmen baru bisa lanjutan nama yang patah
            # ("TEKNIK" + "GRAFIKA", tetap berspasi lewat _cp046_join)
            # atau pecahan kata ("KENDA" + "RAAN RINGAN", disambung tanpa
            # spasi). Pembeda ada di token pertama baris lanjutan, lihat
            # bawah.
            if row[3]:
                if not s.split()[0].isalpha():
                    break
                # Pecahan kata dikenali dari token PERTAMA baris lanjutan.
                # Ekor tidak bisa dipakai: "KENDA" dan "PEMBEL" pecahan
                # tapi punya vokal, sama seperti kata utuh. Vokal juga
                # tidak membedakan — "RAAN" pecahan tapi punya vokal.
                # Yang membedakan: pecahan selalu pendek ("RAAN", "KNIK",
                # "ENIHAN", "L", "N", "USUS", paling panjang 6 huruf),
                # lanjutan nama yang utuh ("GRAFIKA") lebih panjang.
                kepala = s.split()[0]
                if name_parts and name_parts[-1] and len(kepala) <= 6:
                    name_parts[-1] = name_parts[-1] + s
                    continue
            # Sisa heading bab yang pecah ("EMBELAJARAN ...") bukan
            # lanjutan nama. Lewati, jangan hentikan perakitan.
            if 'PEMBELAJARAN' in s or 'EMBELAJARAN' in s:
                continue
            name_parts.append(s)
        subject = self._cp046_join(name_parts).rstrip(' .')
        # Ekstraksi menyisipkan spasi di tengah kata nama mapel
        # ("PENDIDIKA N KHUSUS"). Satukan token pendek yang diawali
        # huruf kapital ke token sebelumnya.
        subject = re.sub(r'([A-Z]) ([A-Z]{1,2})(?= )', r'\1\2', subject)
        # Spasi yang tersisip di tengah kata heading ("CAPAIANP
        # EMBELAJARAN", "PEMB ELAJARAN"). "CA" hanya disatukan bila
        # lanjutan tanpa vokal ("CA PAIAN"); "CA PERIKANAN" utuh.
        subject = re.sub(r'CAPAIANP\s*EMBELAJARAN', 'CAPAIAN PEMBELAJARAN',
                         subject)
        subject = re.sub(r'PEMB\s+ELAJARAN', 'PEMBELAJARAN', subject)
        subject = re.sub(
            r'\bCA (\S+)',
            lambda m: 'CA' + m.group(1) if not re.search(r'[AEIOU]', m.group(1))
            else m.group(0), subject)
        # Heading bab yang terulang karena patah halaman membawa salinan
        # nama kedua. Buang heading beserta nomor bab di depannya
        # ("IX. CAPAIAN PEMBELAJARAN PRAKTIK ..." -> "PRAKTIK ..."),
        # baik yang dipisah spasi maupun yang tersambung langsung.
        subject = re.sub(r'^.*?CAPAIAN PEMBELAJARAN\s*', '', subject,
                         count=1, flags=re.S)
        subject = re.split(r'\s*CAPAIAN PEMBELAJARAN', subject, maxsplit=1)[0]
        return subject.strip(' .')

    def _extract_046_cp(self, fragments) -> List[LearningOutcome]:
        """CP seluruh bab BSKAP 046, dengan provensi halaman."""
        lines = []
        prev_id = None
        for row in fragments:
            # Baris pertama tiap fragmen ditandai: potongan kata antar
            # fragmen ("KENDA" + "RAAN") hanya terjadi di batas ini.
            first = True
            for raw in (row['text'] or '').split('\n'):
                s = raw.strip()
                if s:
                    boundary = first and prev_id is not None \
                        and row['id'] != prev_id
                    lines.append((row['page_number'], s, boundary))
                    first = False
            prev_id = row['id']
        lines = self._cp046_merge_lines(lines)
        babs = self._cp046_chapters(lines)

        results: List[LearningOutcome] = []
        self._cp046_seq: Dict[tuple, int] = {}
        for k, (start, page, code, title, heading) in enumerate(babs):
            end = babs[k + 1][0] if k + 1 < len(babs) else len(lines)
            if isinstance(end, tuple):
                end = end[0]
            window = lines[start:end]
            # Baris heading diganti versi yang sudah disambung dan
            # dinormalisasi, plus penanda agar _cp046_subject tahu.
            subject = self._cp046_subject(
                [(window[0][0], window[0][1], window[0][2], heading)]
                + window[1:])

            gate_at = next(
                (j for j, (_, s, _, _) in enumerate(window)
                 if self._CP046_GATE_RE.match(s)
                 or self._CP046_GATE_BROKEN_RE.match(s)), None)
            if gate_at is None:
                continue
            body = window[gate_at + 1:]

            fase = None
            element = None
            buf: List[str] = []
            buf_pages: List[int] = []
            phase_hang = False

            def flush():
                nonlocal buf, buf_pages
                if buf and element and fase:
                    text = self._cp046_join(buf)
                    if len(text) >= self._CP046_MIN_TEXT:
                        # Kunci mencakup kode bab: elemen bernama sama
                        # ("Geometri") muncul di banyak mapel. Counter
                        # disimpan di self — increment pada dict lokal
                        # tidak tersimpan dari dalam flush.
                        key = (code, fase, element, buf_pages[0])
                        # Nomor urut lewat self: dict lokal tidak tersimpan
                        # dari dalam flush, dan nama variabel di sini
                        # bertabrakan dengan variabel loop _extract_046_cp.
                        self._cp046_seq[key] = self._cp046_seq.get(key, 0) + 1
                        # Slug elemen wajib masuk ID. Elemen berbeda di bab
                        # dan halaman yang sama ("Akidah" dan "Akhlak")
                        # akan bentrok, lalu INSERT OR IGNORE membuangnya.
                        cp_id = "CP-046-{}-{}-{}-{}-{}".format(
                            code, fase, buf_pages[0],
                            self._element_slug(element),
                            self._cp046_seq[key])
                        # BKPDM 020/2026 mengamendemen CP Pendidikan Agama.
                        # CP agama di 046 tetap disimpan sebagai riwayat,
                        # bukan current. Mapel lain tidak terpengaruh.
                        amended = self._cp046_amended(subject)
                        results.append(LearningOutcome(
                            id=cp_id,
                            subject=subject,
                            phase=fase,
                            element=element,
                            text=text[:600],
                            source_page=buf_pages[0],
                            source_pages=list(buf_pages),
                            source_document=self._CP046_SOURCE_LABEL,
                            education_system='KEMENDIKDASMEN',
                            institution_type=self._cp046_institution(subject),
                            education_level='SD s.d. SMA/SMK (Fase A-F)',
                            curriculum_version_id='KEMENDIKDASMEN-2025',
                            program_type='reguler',
                            version='1.0',
                            status='superseded' if amended else 'active',
                        ))
                buf, buf_pages = [], []

            idx = 0
            while idx < len(body):
                pg, s, pages, _boundary = body[idx]
                nxt = body[idx + 1][1] if idx + 1 < len(body) else ''
                idx += 1
                if phase_hang:
                    phase_hang = False
                    cm = self._CP046_PHASE_CONT_RE.match(s)
                    if cm:
                        flush()
                        fase = cm.group(1).upper()
                        if fase == 'FONDASI':
                            fase = 'Fondasi'
                        continue
                pm = self._CP046_PHASE_RE.match(s)
                if pm:
                    flush()
                    fase = pm.group(1).upper()
                    if fase == 'FONDASI':
                        fase = 'Fondasi'
                    continue
                if self._CP046_PHASE_HANG_RE.match(s):
                    phase_hang = True
                    continue
                # Sisa keterangan fase yang pecah antar-baris
                # ("tuk Kelas III dan IV SD/Program Paket A)").
                if 'Paket' in s and re.search(r'Paket [ABC]\)?\s*$', s) \
                        and not re.match(r'^\d', s):
                    continue
                sm = self._CP046_ITEM_SUB_RE.match(s)
                lm = self._CP046_ITEM_PLAIN_RE.match(s)
                if sm or (lm and not re.match(r'^\d+\.\s+Fase\b', s)):
                    flush()
                    element = (sm or lm).group(3 if sm else 2).strip()
                    element = element.rstrip('.')
                    # Label elemen pecah antar-baris ("Keterampil" +
                    # "an Proses Mampu ..."): sambungkan, sisanya badan CP.
                    if element and self._cp046_split_word(element, nxt) \
                            and idx < len(body):
                        cont = nxt.split(None, 1)
                        element = (element + cont[0]).rstrip('.')
                        cont_pages = body[idx][2]
                        idx += 1
                        if len(cont) > 1 and fase:
                            buf_pages = list(cont_pages)
                            buf.append(cont[1])
                    buf_pages = buf_pages or [pg]
                    continue
                if self._CP046_NARRATIVE_RE.match(s):
                    continue
                if element and fase:
                    for p in pages:
                        if p not in buf_pages:
                            buf_pages.append(p)
                    buf.append(s)
            flush()
        return results

    def extract_046_cp_from_fragments(self) -> List[LearningOutcome]:
        """Extract CP mapel umum dari fragmen kanonik BSKAP 046/H/KR/2025."""
        print("📚 Extracting CP BSKAP 046 (mapel umum)...")
        try:
            self.cursor.execute("""
                SELECT sf.id, sf.page_number, sf.paragraph, sf.section, sf.text
                FROM source_fragments sf
                WHERE sf.document_id = ?
                ORDER BY sf.page_number, sf.paragraph
            """, (self._CP046_DOC_ID,))
            fragments = self.cursor.fetchall()
            entries = self._extract_046_cp(fragments)
            self._cp_attach_fragment_provenance(entries, fragments)
            print(f"   ✅ Extracted {len(entries)} CP BSKAP 046")
            return entries
        except Exception as e:
            print(f"   ❌ Error extracting CP 046: {e}")
            return []

    def extract_all_cp(self) -> List[LearningOutcome]:
        """Seluruh CP: madrasah (9941/2025) + sekolah PAI-BP (BKPDM
        020/2026) + mapel umum sekolah (BSKAP 046/H/KR/2025). Sistem
        pendidikan terpisah — tidak ada pemetaan silang antar jalur."""
        entries = (self.extract_cp_from_fragments()
                   + self.extract_school_cp_from_fragments()
                   + self.extract_religion_cp_from_fragments()
                   + self.extract_046_cp_from_fragments())
        self._assign_registry_ids(entries)
        return entries

    @staticmethod
    def _element_slug(name: str) -> str:
        """Slug deterministik nama elemen: huruf kecil, spasi jadi tanda
        hubung, tanda baca dibuang. Hasil sama untuk input sama."""
        slug = re.sub(r"[^a-z0-9]+", '-', (name or '').lower()).strip('-')
        return slug

    def _assign_registry_ids(self, entries: List[LearningOutcome]):
        """Isi subject_id, phase_id, element_id, dan source_document_id
        dari registry/mapping yang SUDAH ada. Tidak mengarang: kolom
        dibiarkan kosong bila padanannya tidak ada di mapping atau di
        tabel source_fragments.

        subject_id = code mapel (name + program_type harus cocok, supaya
        BA reguler dan BA-MAPK tidak tertukar). element_id =
        "{subject_id}-{slug elemen}" dan hanya diisi bila elemen itu ada
        di daftar elemen mapel. phase_id = huruf fase bila fase itu
        dipakai sistem pendidikan CP. source_document_id =
        source_fragments.document_id dari source_fragment_id CP."""
        subjects = self.mappings.get('subjects', {})
        by_key: Dict[tuple, dict] = {}
        for system, levels in subjects.items():
            for subs in levels.values():
                for subj in subs:
                    by_key.setdefault(
                        (system, subj.get('name'),
                         subj.get('program_type') or 'reguler'),
                        subj)

        phases_by_system: Dict[str, set] = {}
        for system, insts in self.mappings.get(
                'grade_to_phase_mappings', {}).items():
            phases_by_system[system] = {
                meta.get('phase')
                for grades in insts.values()
                for meta in grades.values()
                if meta.get('phase')}
        # Fase Fondasi dipakai TKLB (Diktum KELIMA BSKAP 046) tetapi
        # tidak muncul di pemetaan kelas -> fase.
        phases_by_system.setdefault('KEMENDIKDASMEN', set()).add('Fondasi')

        frag_ids = [e.source_fragment_id for e in entries
                    if e.source_fragment_id]
        doc_by_frag: Dict[str, str] = {}
        if frag_ids:
            placeholders = ','.join('?' for _ in frag_ids)
            self.cursor.execute(
                f"SELECT id, document_id FROM source_fragments "
                f"WHERE id IN ({placeholders})", frag_ids)
            doc_by_frag = {row['id']: row['document_id']
                           for row in self.cursor.fetchall()}

        for e in entries:
            e.source_document_id = doc_by_frag.get(e.source_fragment_id)
            subj = by_key.get(
                (e.education_system, e.subject, e.program_type or 'reguler'))
            if subj and subj.get('code'):
                e.subject_id = subj['code']
                if e.element in (subj.get('elements') or []):
                    e.element_id = (f"{subj['code']}-"
                                    f"{self._element_slug(e.element)}")
            if e.phase in phases_by_system.get(e.education_system, ()):
                e.phase_id = e.phase

    def refresh_cp_registry_ids(self) -> int:
        """Sinkron ulang subject_id/phase_id/element_id/source_document_id
        seluruh CP dari mapping file TERBARU (UPDATE kolom ID saja).

        Dipakai rebuild sesudah mappings 046 selesai dibangun dari CP
        yang sudah ter-populate: tanpa ini CP 046 aktif tidak resolve
        karena langkah mappings berjalan saat tabel masih kosong.
        Deterministik; teks, provenance, status, dan versi CP tidak
        diubah. Return jumlah baris yang di-UPDATE."""
        self.mappings = self._load_mappings()
        rows = self.cursor.execute(
            'SELECT id, subject, phase, element, education_system, '
            'program_type, source_fragment_id FROM learning_outcomes'
        ).fetchall()
        entries = [
            LearningOutcome(
                id=r['id'], subject=r['subject'], phase=r['phase'],
                element=r['element'], text='', source_page=0,
                source_document='',
                education_system=r['education_system'] or '',
                program_type=r['program_type'] or 'reguler',
                source_fragment_id=r['source_fragment_id'],
            )
            for r in rows
        ]
        self._assign_registry_ids(entries)
        for e in entries:
            self.cursor.execute(
                'UPDATE learning_outcomes SET subject_id = ?, '
                'phase_id = ?, element_id = ?, source_document_id = ? '
                'WHERE id = ?',
                (e.subject_id, e.phase_id, e.element_id,
                 e.source_document_id, e.id))
        self.connection.commit()
        return len(entries)

    def _cp_attach_fragment_provenance(self, entries, fragments):
        """Hubungkan setiap CP ke fragmen sumbernya (CP -> source_fragment
        -> source_document -> PDF Hukum/). Fragmen dipilih per (page,
        paragraph) pertama yang memuat awal teks CP (normalisasi spasi) —
        tanpa mengubah teks CP maupun fragmen."""
        by_page: Dict[int, List] = {}
        for row in fragments:
            by_page.setdefault(row['page_number'], []).append(row)

        def _norm(s: str) -> str:
            return re.sub(r'\s+', ' ', s or '').strip().lower()

        def _tight(s: str) -> str:
            # Cadangan: ekstraksi kadang menyisipkan spasi di tengah
            # kata ("Mem ahami"). Dipakai hanya bila pencocokan biasa
            # gagal, supaya tidak menggeser kecocokan yang sudah benar.
            return re.sub(r' (?=[a-z])', '', s)

        for e in entries:
            head = _norm(e.text)[:120]
            if not head:
                continue
            pages = e.source_pages or [e.source_page]
            rows = [r for p in pages for r in by_page.get(p, [])]
            for row in rows:
                ftext = _norm(row['text'])
                if not ftext:
                    continue
                # Item CP bisa mulai di TENGAH fragmen atau MENYEBRANG
                # fragmen: cocokkan prefix dua arah — toleran terhadap
                # pemenggalan kata antar-fragmen ("Madras\nah" ->
                # "madrasah") dengan mencoba beberapa panjang prefix.
                matched = False
                for plen in (60, 45, 30):
                    if len(head) < plen:
                        continue
                    probe = head[:plen]
                    if probe in ftext or ftext[:plen] in head:
                        matched = True
                        break
                    # Prefix pemenggalan kata: buang token akhir yang
                    # terpotong lalu cocokkan.
                    cut = probe.rsplit(' ', 1)[0]
                    if len(cut) >= 25 and cut in ftext:
                        matched = True
                        break
                if not matched:
                    # Cadangan untuk spasi tersisip di tengah kata.
                    thead = _tight(head)
                    tftext = _tight(ftext)
                    n = min(40, len(thead), len(tftext))
                    matched = n >= 18 and (
                        thead[:n] in tftext or tftext[:n] in thead)
                    if not matched and len(head) >= 18:
                        # Kata terpecah di batas chunk fragmen
                        # ("Menerapka" + "n produksi"). Dibentuk dari teks
                        # asli, bukan dari _tight yang sudah membuang spasi.
                        # Jendela digeser: huruf awal bisa terpotong di
                        # chunk sebelumnya ("Menerapka" + "n ...").
                        flat = re.sub(r'\s+', '', head)
                        target = re.sub(r'\s+', '', ftext)
                        # Mulai dari 0, 10, dan 20: kata pertama bisa
                        # hampir seluruhnya terpotong di chunk sebelumnya.
                        matched = any(flat[i:i + 22] in target
                                      for i in (0, 10, 20)
                                      if i + 22 <= len(flat))
                if matched:
                    e.source_fragment_id = row['id']
                    e.source_section = row['section'] or None
                    # source_page mengikuti fragmen yang cocok. CP yang
                    # menyeberang halaman tercatat di halaman awal,
                    # padahal teksnya ada di fragmen halaman berikutnya.
                    e.source_page = row['page_number']
                    break

    def extract_cp_from_fragments(self) -> List[LearningOutcome]:
        """
        Extract Capaian Pembelajaran dari fragmen kanonik SK-Dirjen-Pendis-9941.
        Parser state machine: fase diwarisi dari heading bagian (bukan hanya
        kolokasi dalam fragmen yang sama), item dipecah per-baris penanda,
        elemen hanya dari label eksplisit. Semua CP membawa provensi
        (source_document + source_page yang terhubung fragmen).
        """
        print("📚 Extracting Capaian Pembelajaran (parser state machine)...")

        try:
            self.cursor.execute("""
                SELECT sf.id, sf.page_number, sf.paragraph, sf.section, sf.text
                FROM source_fragments sf
                JOIN source_documents sd ON sf.document_id = sd.id
                WHERE sd.id = ?
                ORDER BY sf.page_number, sf.paragraph
            """, (self._CP_DOC_ID,))

            fragments = self.cursor.fetchall()
            entries = self._cp_extract(fragments)
            self._cp_attach_fragment_provenance(entries, fragments)
            n_unknown = sum(1 for e in entries if e.phase == 'Unknown')
            print(f"   ✅ Extracted {len(entries)} CP entries "
                  f"({n_unknown} tanpa fase)")
            return entries

        except Exception as e:
            print(f"   ❌ Error extracting CP: {e}")
            return []
    
    def populate_cp_table(self, outcomes: List[LearningOutcome]):
        """Populate learning_outcomes table dari daftar CP hasil parser."""
        print("📝 Populating learning outcomes (CP)...")
        
        try:
            # Create table if not exists (kolom inti; kolom provenance
            # lengkap dibuat oleh db_initialization).
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS learning_outcomes (
                    id TEXT PRIMARY KEY,
                    subject TEXT,
                    phase TEXT,
                    element TEXT,
                    text TEXT,
                    source_page INTEGER,
                    source_document TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            inserted = 0
            for cp in outcomes:
                try:
                    self.cursor.execute("""
                        INSERT OR IGNORE INTO learning_outcomes
                        (id, subject, phase, element, text, source_page,
                         source_document, education_system, institution_type,
                         education_level, curriculum_version_id, subject_id,
                         phase_id, element_id, sub_element, program_type,
                         track, source_document_id, source_fragment_id,
                         source_section, version, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (cp.id, cp.subject, cp.phase, cp.element, cp.text,
                          cp.source_page, cp.source_document,
                          cp.education_system, cp.institution_type,
                          cp.education_level, cp.curriculum_version_id,
                          cp.subject_id, cp.phase_id, cp.element_id,
                          cp.sub_element, cp.program_type, cp.track,
                          cp.source_document_id, cp.source_fragment_id,
                          cp.source_section, cp.version, cp.status))
                    inserted += 1
                except Exception as e:
                    print(f"   ⚠️  Error inserting CP: {e}")
            
            self.connection.commit()
            print(f"   ✅ Inserted {inserted} learning outcomes")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            self.connection.rollback()
    
    def get_system_for_institution(self, institution_type: str) -> str:
        """Get education system for institution type."""
        systems = self.mappings.get('education_systems', {})
        
        for system, data in systems.items():
            if institution_type in data.get('institution_types', []):
                return system
        
        return None
    
    def validate_subject_system(self, subject: str, system: str) -> bool:
        """Validate subject exists in system."""
        subjects = self.get_subjects_for_system(system)
        return any(s.name == subject for s in subjects)
    
    def get_cp_by_subject_phase(self, subject: str, phase: str,
                                program_type: str = 'reguler',
                                education_system: str = None,
                                institution_type: str = None,
                                curriculum_version_id: str = None) -> List[LearningOutcome]:
        """Get CP for subject and phase. Default hanya jalur reguler agar
        CP MAPK (program_type='MAPK') tidak tercampur dengan CP reguler
        yang ber-subject sama (mis. Fikih fase E/F).

        Fail-closed filters: only ``status='active'`` rows are returned.
        Optional ``education_system`` / ``institution_type`` /
        ``curriculum_version_id`` narrow the query to the requesting
        context so a cross-system or superseded-version CP can never leak
        into another system's generation.
        """
        try:
            query = ("""
                SELECT * FROM learning_outcomes
                WHERE subject = ? AND phase = ?
                  AND COALESCE(program_type, 'reguler') = ?
                  AND COALESCE(status, 'active') = 'active'
            """)
            args: list = [subject, phase, program_type]
            if education_system:
                query += " AND education_system = ?"
                args.append(education_system)
            if institution_type:
                # DB institution_type is the system family ('madrasah' /
                # 'sekolah' / 'pendidikan_khusus'), NOT the school unit
                # ('MTs', 'SMP', 'SDLB'). Map the requesting unit to its
                # family and filter on that only: education_level is
                # free text (CSV or ranges like 'SD s.d. SMA/SMK
                # (Fase A-F)') with no reliable per-unit token, so
                # unit-level matching would silently drop valid CP rows
                # (SDLB/SMPLB/SMALB fail closed for the wrong reason).
                # Cross-system leakage stays impossible: education_system
                # + curriculum_version_id + status filters above still
                # bind every row to the requesting context.
                family = ('madrasah' if institution_type in (
                    'MI', 'MTs', 'MA', 'MAK', 'RA') else (
                    'pendidikan_khusus' if institution_type in (
                        'SDLB', 'SMPLB', 'SMALB') else (
                        'sekolah' if institution_type in (
                            'SD', 'SMP', 'SMA', 'SMK', 'TK') else
                        institution_type)))
                if family == 'pendidikan_khusus':
                    query += (" AND (institution_type = ?"
                              " OR institution_type = 'sekolah'"
                              " OR COALESCE(institution_type, '') = '')")
                    args.append(family)
                else:
                    query += (" AND (institution_type = ? OR "
                              "COALESCE(institution_type, '') = '')")
                    args.append(family)
            if curriculum_version_id:
                query += " AND curriculum_version_id = ?"
                args.append(curriculum_version_id)
            query += " ORDER BY source_page"
            self.cursor.execute(query, tuple(args))
            
            rows = self.cursor.fetchall()
            return [
                LearningOutcome(
                    id=row['id'],
                    subject=row['subject'],
                    phase=row['phase'],
                    element=row['element'],
                    text=row['text'],
                    source_page=row['source_page'],
                    source_document=row['source_document'],
                    education_system=row['education_system']
                    if 'education_system' in row.keys() else '',
                    institution_type=row['institution_type']
                    if 'institution_type' in row.keys() else '',
                    education_level=row['education_level']
                    if 'education_level' in row.keys() else '',
                    curriculum_version_id=row['curriculum_version_id']
                    if 'curriculum_version_id' in row.keys() else '',
                    subject_id=row['subject_id']
                    if 'subject_id' in row.keys() else None,
                    phase_id=row['phase_id']
                    if 'phase_id' in row.keys() else None,
                    element_id=row['element_id']
                    if 'element_id' in row.keys() else None,
                    sub_element=row['sub_element']
                    if 'sub_element' in row.keys() else None,
                    program_type=row['program_type']
                    if 'program_type' in row.keys() else 'reguler',
                    track=row['track'] if 'track' in row.keys() else None,
                    source_fragment_id=row['source_fragment_id']
                    if 'source_fragment_id' in row.keys() else None,
                    source_section=row['source_section']
                    if 'source_section' in row.keys() else None,
                    version=row['version'] if 'version' in row.keys() else '1.0',
                    status=row['status'] if 'status' in row.keys() else 'active',
                )
                for row in rows
            ]
            
        except Exception as e:
            print(f"❌ Error retrieving CP: {e}")
            return []
    
    def print_statistics(self):
        """Print curriculum statistics."""
        print("\n📊 Curriculum Statistics:")
        print("─" * 60)
        
        try:
            self.cursor.execute("SELECT COUNT(*) as count FROM learning_outcomes")
            cp_count = self.cursor.fetchone()['count']
            
            self.cursor.execute("""
                SELECT subject, COUNT(*) as count
                FROM learning_outcomes
                GROUP BY subject
            """)
            
            print(f"Total Learning Outcomes: {cp_count}")
            print("\nBy Subject:")
            for row in self.cursor.fetchall():
                print(f"  {row['subject']}: {row['count']}")
            
        except Exception as e:
            print(f"Error: {e}")


class GradePhaseValidator:
    """Validates and maps grades to phases."""
    
    def __init__(self, mappings: Dict):
        self.mappings = mappings
    
    def validate_and_get_phase(self, system: str, institution_type: str, grade: str) -> Tuple[bool, str, str]:
        """
        Validate grade and return phase.
        Returns: (is_valid, phase, error_message)
        """
        try:
            grade_phase_map = self.mappings.get('grade_to_phase_mappings', {}).get(system, {})
            
            if institution_type not in grade_phase_map:
                return False, None, f"Jenis institusi {institution_type} tidak dikenal dalam {system}"
            
            inst_grades = grade_phase_map[institution_type]
            
            if grade not in inst_grades:
                valid_grades = ', '.join(inst_grades.keys())
                return False, None, f"Kelas {grade} tidak valid. Pilih dari: {valid_grades}"
            
            phase = inst_grades[grade]['phase']
            return True, phase, ""
            
        except Exception as e:
            return False, None, str(e)


if __name__ == '__main__':
    PROJECT_ROOT = Path(__file__).parent.parent
    DB_PATH = PROJECT_ROOT / 'db' / 'rpm_generator.db'
    
    print("\n" + "="*60)
    print("🎓 CURRICULUM ENGINE - PHASE 3")
    print("="*60 + "\n")
    
    engine = CurriculumEngine(str(DB_PATH))
    engine.connect()
    
    # Extract CP from fragments (parser state machine):
    # madrasah (9941) + sekolah PAI-BP (BKPDM 020) — jalur terpisah.
    cp_entries = engine.extract_all_cp()
    
    # Populate CP table
    engine.populate_cp_table(cp_entries)
    
    # Print statistics
    engine.print_statistics()
    
    engine.close()
    
    print("\n✅ CURRICULUM ENGINE PHASE 3 COMPLETE")
