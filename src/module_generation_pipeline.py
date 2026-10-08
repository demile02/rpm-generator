#!/usr/bin/env python3
"""
PHASE C: Real AI Module Generation Pipeline with Full Validation
Complete end-to-end module generation using 9Router with comprehensive validation

Pipeline stages:
1.  Curriculum Validation (CurriculumEngine - real CP retrieval from DB)
2.  Build Module Metadata
3.  AI Generation (9Router - TP, KKTP, materials, activities, assessments)
4.  Structure Validation
5.  Curriculum Protection Validation (CP/phase/subject/element immutable)
6.  Rule Engine Validation (C3+ via RuleEngine + KKO keyword extraction)
7.  Pedagogical Validation (FATAL on failure)
8.  Anti-Slop Processing (protected fields untouched)
9.  Final Completeness & Alignment Validation (FATAL on failure)
10. Conditional success: status == "success" only if every stage passed

Invalid modules can NEVER return SUCCESS.
"""

import json
import functools
import hashlib
import logging
import re
import sqlite3
import time
import uuid
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from nine_router_client import NineRouterClient, NineRouterConfig, NineRouterError
from nine_router_client import AuthenticationError, ValidationError
from module_store import GenerationLogStore
from curriculum_engine import CurriculumEngine
from rule_engine import RuleEngine
from curriculum_context import (
    CurriculumContext,
    CPEntry,
    ATPEntry,
    CurriculumContextGenerator,
    ContextValidator,
    TPEntry as CurriculumTPEntry,
)

logger = logging.getLogger(__name__)


def resolve_grade_key(institution_type: str, grade: str) -> str:
    """Normalize grade to the 'MTs_7' style key used by curriculum mappings.

    Accepts either grade='7' (with institution_type='MTs') or the
    fully-qualified grade='MTs_7'.
    """
    grade = str(grade)
    prefix = f"{institution_type}_"
    if grade.lower().startswith(prefix.lower()):
        return grade
    return f"{institution_type}_{grade}"


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class TPEntry:
    """Learning Objective (Tujuan Pembelajaran)."""
    id: str
    text: str
    cognitive_level: str  # C1-C6
    cp_reference: str
    source_type: str = "ai_generated"


@dataclass
class KKTPEntry:
    """Success Criteria (Kriteria Ketercapaian TP)."""
    id: str
    tp_id: str
    criteria: List[str]
    cognitive_level: str
    source_type: str = "ai_generated"


@dataclass
class ActivityEntry:
    """Aktivitas/pengalaman belajar.

    experience = pengalaman belajar Pembelajaran Mendalam
    (memahami | mengaplikasi | merefleksi) - atribut pedagogis.
    stage = struktur langkah pembelajaran (Pembuka | Inti | Penutup).
    meeting = indeks pertemuan (1-based) bila RPM disusun per pertemuan,
    0 bila tidak terikat pertemuan (hasil lama).
    Ketiganya independen: tidak ada mapping kaku tahap = pengalaman.
    """
    id: str
    name: str
    description: str
    duration: int
    tp_linked: str
    type: str
    resources: List[str] = field(default_factory=list)
    experience: str = ""  # memahami | mengaplikasi | merefleksi
    stage: str = ""  # Pembuka | Inti | Penutup (mode pertemuan)
    meeting: int = 0  # 1-based bila mode pertemuan, 0 bila tidak ada


@dataclass
class AssessmentItem:
    """Assessment item."""
    id: str
    question: str
    type: str
    tp_linked: Optional[str] = None
    kktp_linked: Optional[str] = None
    points: int = 0


@dataclass
class ValidationResult:
    """Validation result for a stage."""
    stage_name: str
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ============================================================
# RPM NORMATIVE CONSTANTS (deterministic, per authority)
#
# 8 Dimensi Profil Lulusan (Permendikdasmen No. 10 Tahun 2025) adalah
# sasaran profil lulusan untuk KEDUA sistem pendidikan. Untuk madrasah
# (KEMENAG), Kurikulum Berbasis Cinta / Panca Cinta (Kepdirjen Pendis
# No. 6077 Tahun 2025) adalah LAYER TAMBAHAN — BUKAN pengganti dan
# BUKAN dimensi ke-9/10 dari Profil Lulusan.
# ============================================================

# 8 Dimensi Profil Lulusan — Permendikdasmen No. 10 Tahun 2025.
PROFILE_DIMENSIONS_8 = [
    "Keimanan dan Ketakwaan kepada Tuhan YME",
    "Kewargaan",
    "Penalaran Kritis",
    "Kreativitas",
    "Kolaborasi",
    "Kemandirian",
    "Kesehatan",
    "Komunikasi",
]

# Panca Cinta / lima tema KBC — Kepdirjen Pendis No. 6077 Tahun 2025.
# HANYA untuk konteks madrasah (KEMENAG), sebagai layer tambahan.
KBC_THEMES = [
    "Cinta Allah dan Rasul-Nya",
    "Cinta Ilmu",
    "Cinta Lingkungan",
    "Cinta Diri dan Sesama",
    "Cinta Tanah Air",
]

KBC_SOURCE_DOCUMENT = "Kepdirjen Pendis No. 6077 Tahun 2025"

# Frasa meta/arsitektur generator yang tidak boleh muncul dalam teks KBC
# untuk guru (temuan audit Batch 7). Daftar sempit dan harfiah — bukan
# keyword matching topik (dilarang); hanya gema instruksi arsitektur.
KBC_META_PHRASES = (
    "layer tambahan",
    "lapisan tambahan",
    "lapisan nilai tambahan",
    "arsitektur",
)


def _contains_kbc_meta_language(text: str) -> bool:
    """True bila teks memuat frasa meta generator (case-insensitive)."""
    lowered = (text or '').lower()
    return any(phrase in lowered for phrase in KBC_META_PHRASES)

# ============================================================
# KONTEKS REGULASI (amandemen/pedoman CP) — deterministik, per
# sistem pendidikan. Dokumen-dokumen ini MENGUBAH/menerangkan CP
# (bukan sumber CP: CP tetap dari SK-Dirjen-Pendis-9941-2025) dan
# WAJIB dikonsultasikan ke AI saat generate agar TP/desain memakai
# ketentuan TERBARU. Fragmen diambil langsung dari
# db/rpm_generator.db dengan provenance utuh (doc id + halaman +
# fragment id) — AI tidak dapat mengubahnya.
# ============================================================
REGULATORY_CONTEXT_DOC_IDS = {
    # BKPDM 020/2026 mengubah CP PAI dan Budi Pekerti dari BSKAP
    # 046/H/KR/2025 (Kurikulum 2026).
    'KEMENDIKDASMEN': ['DOC-REG-KEMENDIKDASMEN-BKPDM-020-2026'],
    # KMA 1503/2025: pedoman implementasi kurikulum madrasah +
    # Pembelajaran Mendalam (panduan CP dan kerangka pembelajaran).
    'KEMENAG': ['DOC-REG-KEMENAG-1503-2025'],
}

REGULATORY_CONTEXT_ROLES = {
    'DOC-REG-KEMENDIKDASMEN-BKPDM-020-2026':
        'amandemen CP Pendidikan Agama dan Budi Pekerti (Kurikulum 2026)',
    'DOC-REG-KEMENAG-1503-2025':
        'pedoman implementasi kurikulum dan Pembelajaran Mendalam madrasah',
}

# Basis kata-kunci seleksi fragmen (diperluas dengan nama mapel).
AMENDMENT_KEYWORDS = [
    'capaian pembelajaran', 'pembelajaran mendalam', 'kurikulum',
    'pendidikan agama', 'budi pekerti', 'profil lulusan',
]

# Mapel -> kata-kunci tambahan (normalisasi nama panjang).
_SUBJECT_KEYWORD_MAP = {
    'pendidikan agama dan budi pekerti': ['pendidikan agama', 'budi pekerti'],
    'pai dan bahasa arab': ['pendidikan agama', 'bahasa arab'],
}

# Anchor klausul kunci per dokumen (frasa literal, dicocokkan
# case-insensitive): fragmen yang memuat frasa DIJAMIN masuk seleksi
# lewat query TERPISAH (di luar LIKE kata-kunci + LIMIT) — klausul
# yang mendefinisikan/mengubah CP tidak boleh terpotong oleh batas
# kandidat maupun kalah oleh fragmen lain yang lebih kaya kata kunci.
KEY_CLAUSE_ANCHORS = {
    'DOC-REG-KEMENDIKDASMEN-BKPDM-020-2026': [
        'mengubah ketentuan mengenai capaian pembelajaran',
        'capaian pembelajaran pendidikan agama dan budi',
    ],
    'DOC-REG-KEMENAG-1503-2025': [
        'capaian pembelajaran adalah',
    ],
}


def _subject_keywords(subject: str) -> List[str]:
    """Kata-kunci seleksi tambahan dari nama mapel (lowercase)."""
    s = re.sub(r'\s+', ' ', (subject or '').lower()).strip()
    return list(_SUBJECT_KEYWORD_MAP.get(s, [s] if s else []))


def build_regulatory_context(
    education_system: str,
    subject: str,
    phase: str,
    db_path: Optional[str] = None,
    max_fragments_per_doc: int = 6,
    max_chars_per_doc: int = 2400,
) -> Dict:
    """Konteks regulasi deterministik untuk satu permintaan generate.

    Memilih fragmen paling relevan (kata-kunci amandemen/pedoman + nama
    mapel) dari dokumen regulasi yang mengubah/menerangkan CP untuk
    sistem pendidikan terkait. Semua fragmen membawa provenance lengkap
    (document_id, halaman, fragment id) sehingga konsultasi regulasi
    tetap telusuri ke Hukum/. Kegagalan DB adalah FATAL (fail closed):
    generasi tanpa konteks amandemen/pedoman berisiko memakai CP
    kedaluwarsa, jadi result membawa 'fatal': True dan pemanggil wajib
    menghentikan generate.
    """
    doc_ids = REGULATORY_CONTEXT_DOC_IDS.get(education_system or '', [])
    result: Dict = {
        'enabled': False,
        'sources': [],
        'note': ('Konteks regulasi amandemen/pedoman CP terlampir; '
                 'fragmen resmi, provenance terjaga, tidak dapat diubah.'),
    }
    if not doc_ids:
        result['note'] = ('Tidak ada dokumen amandemen/pedoman CP yang '
                          'terdaftar untuk sistem pendidikan ini.')
        return result
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / 'db' / 'rpm_generator.db')
    keywords = AMENDMENT_KEYWORDS + _subject_keywords(subject)
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.row_factory = sqlite3.Row
            for doc_id in doc_ids:
                like_parts = ' OR '.join(
                    ["lower(text) LIKE ?"] * len(keywords))
                args: List[Any] = [doc_id] + [f'%{k}%' for k in keywords]
                rows = conn.execute(
                    f'SELECT id, page_number, text FROM source_fragments '
                    f'WHERE document_id = ? AND ({like_parts}) '
                    f'ORDER BY page_number, id LIMIT ?',
                    args + [max_fragments_per_doc * 10],
                ).fetchall()
                # --- Slot anchor klausul kunci (query terpisah) ------
                # Anchor tidak lewat LIKE kata-kunci maupun LIMIT:
                # kandidatnya diambil langsung per frasa sehingga klausul
                # definisi/amandemen CP selalu terwakili. Bebas budget
                # karakter (harus masuk), maksimum satu fragmen per
                # frasa anchor (yang pertama by page/id).
                anchor_phrases = KEY_CLAUSE_ANCHORS.get(doc_id, [])
                anchors_lower = [p.lower() for p in anchor_phrases]
                picked: List[Dict] = []
                used_chars = 0
                anchored_ids: set = set()
                if anchors_lower:
                    like_parts = ' OR '.join(
                        ["lower(text) LIKE ?"] * len(anchors_lower))
                    arows = conn.execute(
                        f'SELECT id, page_number, text FROM source_fragments '
                        f'WHERE document_id = ? AND ({like_parts}) '
                        f'ORDER BY page_number, id',
                        [doc_id] + [f'%{p}%' for p in anchors_lower],
                    ).fetchall()
                    seen_phrase: set = set()
                    for r in arows:
                        text = (r['text'] or '').strip()
                        low = text.lower()
                        hit = next((p for p in anchors_lower if p in low),
                                   None)
                        if hit is None or hit in seen_phrase:
                            continue
                        seen_phrase.add(hit)
                        anchored_ids.add(r['id'])
                        picked.append({
                            'fragment_id': r['id'],
                            'source_document_id': doc_id,
                            'page': r['page_number'],
                            'text': text,
                        })
                        used_chars += len(text)
                # --- Slot scoring biasa ------------------------------
                # Scoring deterministik: fragmen substantif (bukan kop
                # surat/halaman formal) didahulukan. Bobot: kecocokan
                # kata-kunci > panjang teks (min 120 char) > halaman awal
                # (konsisten antar-run). Fragmen anchor dilewati di sini
                # (sudah masuk lewat slot anchor).
                scored: List[tuple] = []
                for r in rows:
                    if r['id'] in anchored_ids:
                        continue
                    text = (r['text'] or '').strip()
                    if len(text) < 80:
                        continue
                    low = text.lower()
                    score = sum(1 for k in keywords if k in low)
                    score += 1 if len(text) >= 120 else 0
                    score += max(0, 5 - r['page_number'] // 10) * 0.1
                    scored.append((-score, r['page_number'], r['id'], text))
                scored.sort()
                for _score, page, frag_id, text in scored:
                    if len(picked) >= max_fragments_per_doc:
                        break
                    if used_chars + len(text) > max_chars_per_doc:
                        continue
                    picked.append({
                        'fragment_id': frag_id,
                        'source_document_id': doc_id,
                        'page': page,
                        'text': text,
                    })
                    used_chars += len(text)
                if not picked:
                    logger.warning(
                        "Regulatory context: no fragments matched for %s",
                        doc_id)
                    continue
                title_row = conn.execute(
                    'SELECT title FROM source_documents WHERE id = ?',
                    (doc_id,)).fetchone()
                result['sources'].append({
                    'document_id': doc_id,
                    'document_title': (
                        title_row['title'] if title_row else doc_id),
                    'role': REGULATORY_CONTEXT_ROLES.get(doc_id, ''),
                    'fragments': picked,
                })
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.error("Regulatory context unavailable: %s", exc)
        result['sources'] = []
        result['enabled'] = False
        result['error'] = str(exc)
        # Fail closed: callers must stop generation when the regulatory
        # consultation cannot be built (stale-CP risk).
        result['fatal'] = True
        return result
    result['enabled'] = bool(result['sources'])
    return result


def format_buku_ajar_for_prompt(
    fragmen: list,
    judul: str = '',
) -> str:
    """Serialisasi fragmen buku ajar ke blok prompt materi (R-43).

    Tiap fragmen membawa id + halaman agar AI bisa merujuk sumbernya
    dan validator bisa mengecek struktur output lawan sumber.
    """
    if not fragmen:
        return ''
    baris = '\n'.join(
        f"  [{f.get('id')} · hal. {f.get('page_number')}] "
        f"{(f.get('text') or '')[:1200]}"
        for f in fragmen
    )
    return (
        "\n\nSUMBER BUKU AJAR (fragmen buku user, IKUTI HIERARKI "
        "APA ADANYA, DILARANG membuat struktur/kategori sendiri):\n"
        f"{judul}\n{baris}\n"
        "ATURAN MATERI: tulis main_content mengikuti hierarki sumber di "
        "atas (jumlah aspek + turunannya sama persis). Setiap klaim "
        "faktual (jumlah aspek, definisi, contoh) WAJIB mencantumkan id "
        "fragmen sumber dalam tanda kurung, contoh: [BUKU-xxx-H47-1]. "
        "Klaim tanpa rujukan = DITOLAK."
    )


def format_regulatory_context_for_prompt(
    regulatory_context: Optional[Dict],
) -> str:
    """Serialisasi konteks regulasi ke blok teks prompt (atau string
    kosong bila tidak ada sumber). Provenance ditampilkan eksplisit
    agar jejak konsultasi tetap dapat diaudit dari prompt mana pun."""
    if not regulatory_context:
        return ''
    sources = regulatory_context.get('sources') or []
    if not sources:
        return ''
    blocks = []
    for src in sources:
        frag_lines = '\n'.join(
            f"  [{f['source_document_id']} · hal. {f['page']}] {f['text']}"
            for f in src.get('fragments') or []
        )
        role = src.get('role') or 'dokumen regulasi'
        blocks.append(
            f"{src.get('document_id', '')} "
            f"({src.get('document_title', '')} — {role}):\n{frag_lines}"
        )
    return (
        "\n\nKONTEKS REGULASI (fragmen resmi, provenance terlampir — "
        "kutip apa adanya, DILARANG mengubah CP/fase/mapel):\n"
        + '\n\n'.join(blocks)
    )

# Prinsip pembelajaran Pembelajaran Mendalam (Permendikdasmen No. 13
# Tahun 2025). Ketiganya adalah PRINSIP, bukan tiga tahap kegiatan
# yang wajib berurutan.
DEEP_LEARNING_PRINCIPLES = ["Berkesadaran", "Bermakna", "Menggembirakan"]

# Tiga pengalaman belajar Pembelajaran Mendalam. BUKAN padanan
# kegiatan awal-inti-penutup.
LEARNING_EXPERIENCES = ["Memahami", "Mengaplikasi", "Merefleksi"]

# Prompt policy: concrete school-document language, not invented activity branding.
ANTI_SLOP_GENERATION_RULES = (
    "ATURAN BAHASA DAN AKTIVITAS: Tulis aktivitas sebagai tindakan nyata "
    "murid dengan pola tindakan + objek + output. Gunakan kata kerja biasa "
    "seperti membaca, mengamati, menyimak, menjawab pertanyaan, bertanya, "
    "berdiskusi, menganalisis, mengidentifikasi, membandingkan, "
    "mengelompokkan, menafsirkan, mencari informasi, mengerjakan soal, "
    "mempresentasikan, menyimpulkan, menulis, merefleksikan, melakukan "
    "latihan, atau mengerjakan kuis. JANGAN mengarang nama khusus, branding, "
    "label kreatif, metafora, nama permainan, akronim, jargon, framework, "
    "atau istilah bahasa Inggris untuk aktivitas. Jangan gunakan model/metode "
    "yang tidak diminta. Jika pengguna atau sumber memang meminta model/metode, "
    "pertahankan nama resminya tanpa membuat kombinasi baru. Hindari contoh "
    "pola seperti Jigsaw Sumber, Claim-Evidence-Reasoning, Gallery Walk, "
    "Think-Pair-Share, Learning Lab, Exit Ticket, Jelajah, Laboratorium, "
    "Misi, Eksplorasi, Tiket, Safari, Challenge, atau Station bila tidak "
    "diminta. Ubah label menjadi deskripsi konkret yang mudah dipahami guru. "
    "Gunakan istilah murid, bukan peserta didik atau siswa."
)

# Struktur langkah pembelajaran per pertemuan. Independen dari
# pengalaman belajar: satu aktivitas membawa keduanya sekaligus.
MEETING_STAGES = ["Pembuka", "Inti", "Penutup"]

# Durasi 1 JP (menit) per satuan pendidikan + fase/kelas, dari tabel
# struktur kurikulum pada dokumen regulasi (diverifikasi visual
# langsung dari PDF Hukum/, bukan dari OCR/memory):
#
# Reguler (fase -> menit):
# - Fase A/B/C = 35 (SD/MI kelas I-VI; 13/2025 Tab SD/MI; KMA Tab 1-2 MI)
# - Fase D = 40 (SMP/MTs kelas VII-IX; 13/2025 Tab SMP; KMA Tab 6-7 MTs)
# - Fase E/F = 45 (SMA/MA/SMK/MAK kelas X-XII/XIII; 13/2025 Tab 8 dst;
#   KMA Tab 10-14). Berlaku untuk TK? TIDAK (tanpa bukti) -> fail closed.
#   Berlaku untuk RA? TIDAK (tanpa bukti) -> fail closed.
# SLB (per satuan + fase; per-grade overrides bila tabel membedakan):
# - SDLB Fase A/B/C = 30 (13/2025 Tab 16 SDLB+MILB kelas I, hlm. PDF
#   cetak -34-; KMA Tab 15 MILB kelas I, 1 JP = 30 menit)
# - SMPLB/MTsLB Fase D = 35 (13/2025 Tab 21 kelas VII, 1 JP = 35 menit;
#   KMA Tab 20 MTsLB kelas VII)
# - SMALB/MALB Fase E/F = 40 (13/2025 Tab 24 kelas X, 1 JP = 40 menit)
# - MILB kelas VI = 33 (KMA Tab 19, 1 JP = 33 menit — terverifikasi
#   visual, bukan salah OCR). MILB/MTsLB/MALB bukan identifier resmi
#   mapping aplikasi (yang ada SDLB/SMPLB/SMALB), sehingga nilai 33
#   tercatat di sini sebagai bukti tanpa mapping aktif.
# - TKLB/Fondasi: TIDAK ADA angka di sumber -> fail closed.
JP_MENIT_REGULER = {
    'A': 35, 'B': 35, 'C': 35, 'D': 40, 'E': 45, 'F': 45,
}
REGULER_INSTITUTIONS = {
    'SD', 'SMP', 'SMA', 'SMK', 'MI', 'MTs', 'MA', 'MAK',
}
# Satuan LB resmi mapping aplikasi -> {fase: menit} + override per
# kelas {'grades': {grade_key: menit}} bila tabel membedakan kelas.
JP_MENIT_SLB = {
    'SDLB': {'default': {'A': 30, 'B': 30, 'C': 30}, 'grades': {}},
    'SMPLB': {'default': {'D': 35}, 'grades': {}},
    'SMALB': {'default': {'E': 40, 'F': 40}, 'grades': {}},
}

# Alias lawas (phase saja): dipertahankan untuk kompatibilitas baca,
# JANGAN dipakai untuk SLB (reguler vs SLB berbeda pada fase sama).
JP_MENIT_PER_FASE = dict(JP_MENIT_REGULER)


def resolve_jp_menit(institution_type: str, phase: str,
                     grade=None, mapping=None) -> tuple:
    """Resolusi deterministik durasi 1 JP (menit).

    Key: (satuan pendidikan, fase[, kelas]) memakai identifier resmi.
    Return (menit, None) bila terverifikasi; (None, error) bila tidak
    ada bukti (fail closed — tanpa tebak, tanpa fallback reguler,
    tanpa default 45). ``mapping`` opsional untuk menguji mekanisme
    override per-kelas tanpa menyentuh konfigurasi produksi.
    """
    config = mapping if mapping is not None else {
        'reguler_institutions': REGULER_INSTITUTIONS,
        'reguler': JP_MENIT_REGULER,
        'slb': JP_MENIT_SLB,
    }
    inst = (institution_type or '').strip()
    ph = (phase or '').strip()
    slb = (config.get('slb') or {})
    if inst in slb:
        entry = slb[inst] or {}
        grades = entry.get('grades') or {}
        if grade is not None and str(grade) in grades:
            return grades[str(grade)], None
        minutes = (entry.get('default') or {}).get(ph)
        if minutes is None:
            return None, (
                f"Alokasi waktu belum tersedia untuk kombinasi satuan "
                f"pendidikan {inst!r} dan fase {ph!r}.")
        return minutes, None
    if inst in (config.get('reguler_institutions') or set()):
        minutes = (config.get('reguler') or {}).get(ph)
        if minutes is None:
            return None, (
                f"Alokasi waktu belum tersedia untuk kombinasi satuan "
                f"pendidikan {inst!r} dan fase {ph!r}.")
        return minutes, None
    return None, (
        f"Alokasi waktu belum tersedia untuk kombinasi satuan "
        f"pendidikan {inst!r} dan fase {ph!r}.")


def validate_time_budget(activities, n_meetings: int,
                         minutes_per_meeting: int,
                         tp_ids) -> List[str]:
    """Validator deterministik alokasi waktu pertemuan (fail closed).

    Aturan: setiap aktivitas memakai tahap valid, nomor pertemuan
    valid, TP valid, dan durasi bilangan bulat positif; jumlah durasi
    per pertemuan PERSIS sama dengan budget; total PERSIS sama dengan
    n_meetings x budget. Tanpa toleransi, tanpa silent fix. Setiap
    error memakai kode TIME_BUDGET_INVALID.
    """
    errors = []
    tp_ids = set(tp_ids or [])

    def fail(message: str):
        errors.append(f"TIME_BUDGET_INVALID: {message}")

    for act in activities or []:
        name = act.get('id', '?') if isinstance(act, dict) else '?'
        stage = act.get('stage') if isinstance(act, dict) else None
        meeting = act.get('meeting') if isinstance(act, dict) else None
        duration = act.get('duration') if isinstance(act, dict) else None
        tp = act.get('tp_linked') if isinstance(act, dict) else None
        if stage not in MEETING_STAGES:
            fail(f"{name}: tahap {stage!r} invalid "
                 f"(harus salah satu dari {', '.join(MEETING_STAGES)})")
        if not isinstance(meeting, int) or isinstance(meeting, bool) \
                or not (1 <= meeting <= n_meetings):
            fail(f"{name}: pertemuan {meeting!r} invalid "
                 f"(harus 1..{n_meetings})")
        if tp not in tp_ids:
            fail(f"{name}: TP {tp!r} invalid (tidak ada pada TP generation)")
        if not isinstance(duration, int) or isinstance(duration, bool) \
                or duration <= 0:
            fail(f"{name}: durasi {duration!r} invalid "
                 f"(bilangan bulat positif menit)")
    per_meeting: Dict[int, int] = {}
    for act in activities or []:
        meeting = act.get('meeting') if isinstance(act, dict) else None
        duration = act.get('duration') if isinstance(act, dict) else None
        if isinstance(meeting, int) and not isinstance(meeting, bool) \
                and isinstance(duration, int) \
                and not isinstance(duration, bool) and duration > 0:
            per_meeting[meeting] = per_meeting.get(meeting, 0) + duration
    for meeting in range(1, n_meetings + 1):
        used = per_meeting.get(meeting, 0)
        if used != minutes_per_meeting:
            fail(f"Pertemuan {meeting}: total {used} menit != "
                 f"budget {minutes_per_meeting} menit")
    total = sum(per_meeting.values())
    expected_total = n_meetings * minutes_per_meeting
    if total != expected_total:
        fail(f"Total {total} menit != alokasi {expected_total} menit")
    return errors


def build_meetings(activities, n_meetings: int, jp_per_meeting: int,
                   minutes_per_jp: int) -> List[Dict]:
    """Susun D berdasarkan pertemuan dari aktivitas tervalidasi.

    Deterministik: grup aktivitas per (pertemuan, tahap); total per
    pertemuan dihitung dari durasi (bukan dari AI).
    """
    per_meeting = minutes_per_jp * jp_per_meeting
    meetings = []
    for meeting in range(1, n_meetings + 1):
        stages = {stage: [] for stage in MEETING_STAGES}
        for act in activities or []:
            if not isinstance(act, dict):
                continue
            if act.get('meeting') == meeting \
                    and act.get('stage') in stages:
                stages[act['stage']].append(act)
        used = sum(
            a.get('duration', 0) for bucket in stages.values() for a in bucket
            if isinstance(a.get('duration'), int))
        meetings.append({
            'index': meeting,
            'jp': jp_per_meeting,
            'minutes_per_jp': minutes_per_jp,
            'minutes': per_meeting,
            'used_minutes': used,
            'stages': stages,
        })
    return meetings


def attach_meeting_principles(meetings, principles) -> List[Dict]:
    """Tempel prinsip per pertemuan (Batch 8.5 §6) ke meetings.

    Deterministik berdasarkan nomor pertemuan; entri tak cocok
    diabaikan (tidak ada karangan). Dipakai generate(), regen, dan
    recompute versi.
    """
    lookup = {}
    for entry in principles or []:
        if not isinstance(entry, dict):
            continue
        meeting = entry.get('meeting')
        if isinstance(meeting, int) and not isinstance(meeting, bool):
            lookup[meeting] = {
                key: str(entry.get(key) or '').strip()
                for key in ('berkesadaran', 'bermakna', 'menggembirakan')
            }
    out = []
    for meeting in meetings or []:
        if not isinstance(meeting, dict):
            out.append(meeting)
            continue
        entry = dict(meeting)
        prin = lookup.get(entry.get('index'))
        if prin and all(prin.values()):
            entry['principles'] = prin
        out.append(entry)
    return out

# Kurikulum versi per sistem (deterministik; lihat AGENTS.md §4).
CURRICULUM_VERSION_BY_SYSTEM = {
    "KEMENAG": "KMA-1503-2025",
    "KEMENDIKDASMEN": "KEMENDIKDASMEN-2025",
}


def _to_positive_int(value) -> Optional[int]:
    """Koersi input hitung guru: int >= 1 valid, selain itu None."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None
    if isinstance(value, bool):
        return None
    return number if number >= 1 else None


def resolve_meetings_spec(params: Dict, phase: str,
                          institution_type: str = None):
    """Tentukan mode pertemuan dari input guru (deterministik).

    Return (spec, error): spec None berarti mode lama (tanpa
    pertemuan). Mode pertemuan aktif bila jumlah_pertemuan ATAU
    jp_per_pertemuan diisi — keduanya wajib valid bila salah satu
    ada; durasi JP diambil dari konfigurasi (satuan pendidikan +
    fase[/kelas]) yang sudah tervalidasi (tanpa input bebas, tanpa
    default diam-diam, tanpa fallback antar-satuan).
    """
    raw_n = params.get('jumlah_pertemuan')
    raw_jp = params.get('jp_per_pertemuan')
    has_n = raw_n is not None and str(raw_n).strip() != ''
    has_jp = raw_jp is not None and str(raw_jp).strip() != ''
    if not has_n and not has_jp:
        return None, None
    n = _to_positive_int(raw_n) if has_n else None
    jp = _to_positive_int(raw_jp) if has_jp else None
    if n is None or jp is None:
        return None, (
            "Input alokasi waktu invalid: 'jumlah_pertemuan' dan "
            "'jp_per_pertemuan' wajib bilangan bulat >= 1 bila salah "
            "satu diisi.")
    minutes_per_jp, jp_error = resolve_jp_menit(
        institution_type if institution_type is not None
        else params.get('institution_type'),
        phase, params.get('grade'))
    if minutes_per_jp is None:
        return None, f"Input alokasi waktu invalid: {jp_error}"
    per_meeting = jp * minutes_per_jp
    return {
        'n_meetings': n,
        'jp_per_meeting': jp,
        'minutes_per_jp': minutes_per_jp,
        'minutes_per_meeting': per_meeting,
        'total_minutes': n * per_meeting,
    }, None


def normalize_mc_item(item: Dict, where: str) -> Dict:
    """Kontrak Pilihan Ganda: question + options (>=4, label A.. valid)
    + correct answer yang cocok salah satu opsi (Batch 4).

    Normalisasi yang aman (bukan karangan): opsi string diberi label
    A, B, C, ... sesuai urutan; correct_answer berupa teks opsi
    dinormalisasi ke labelnya. Selain itu -> ValueError (fail-closed
    via recovery stage yang sudah ada; tanpa silent fallback).
    Item non-MC dikembalikan apa adanya.
    """
    if not isinstance(item, dict):
        raise ValueError(f"{where}: item asesmen bukan object")
    item_type = str(item.get('type') or '').strip().lower()
    if item_type != 'multiple_choice':
        return item
    question = str(item.get('question') or '').strip()
    if not question:
        raise ValueError(f"{where}: multiple_choice tanpa question")
    options = item.get('options')
    if not isinstance(options, list) or len(options) < 4:
        raise ValueError(
            f"{where}: multiple_choice wajib >= 4 options "
            f"(dapat {len(options) if isinstance(options, list) else 0})")
    normalized = []
    for i, opt in enumerate(options):
        want = chr(ord('A') + i)
        if isinstance(opt, dict):
            label = str(opt.get('label') or '').strip().upper()
            text = str(opt.get('text', opt.get('option', '')) or '').strip()
            if not text:
                raise ValueError(
                    f"{where}: option {want} tanpa teks jawaban")
            if label and label != want:
                raise ValueError(
                    f"{where}: label option rusak ({label!r}, harus {want})")
            normalized.append({'label': want, 'text': text})
        elif isinstance(opt, str) and opt.strip():
            normalized.append({'label': want, 'text': opt.strip()})
        else:
            raise ValueError(f"{where}: option {want} invalid")
    answer = item.get('correct_answer', item.get('answer_key',
                                                 item.get('answer')))
    key = None
    if isinstance(answer, str) and answer.strip():
        answer = answer.strip()
        if len(answer) == 1 and answer.upper() in [
                o['label'] for o in normalized]:
            key = answer.upper()
        else:
            for opt in normalized:
                if opt['text'].strip().lower() == answer.lower():
                    key = opt['label']
                    break
    if key is None:
        raise ValueError(
            f"{where}: correct_answer tidak cocok salah satu option")
    item = dict(item)
    item['options'] = normalized
    item['correct_answer'] = key
    return item


def _normalize_kbc_insertion(item, themes) -> Dict:
    """Normalisasi satu materi insersi KBC (Batch 4).

    Field 'tema' (bila diisi AI) harus persis salah satu tema
    terpilih; selain itu -> None (fallback pairing presentasi,
    bukan fail — reliabilitas generation tidak dikorbankan).
    Tidak mengarang tema/insersi baru.
    """
    if not isinstance(item, dict):
        return {'text': str(item), 'tema': None}
    tema = item.get('tema')
    if not isinstance(tema, str) or tema.strip() not in (themes or []):
        tema = None
    else:
        tema = tema.strip()
    out = dict(item)
    out['tema'] = tema
    return out


def _readiness_stage_block(student_readiness) -> str:
    """Blok konteks kesiapan murid untuk prompt stage (Batch 11).

    Readiness adalah fakta observasi guru: boleh mewarnai scaffolding,
    bantuan, contoh, kompleksitas, strategi, dan konteks asesmen; tidak
    boleh mengubah CP/TP/KKTP, tidak boleh melahirkan diagnosis baru,
    dan tidak dianggap fakta bila kosong (string kosong = generik).
    """
    text = str(student_readiness or '').strip()
    if not text:
        return ''
    return (
        "\n\nKesiapan murid menurut observasi guru "
        "(fakta, bukan asumsi): "
        f"{text}\n"
        "Gunakan FAKTA di atas hanya untuk menyesuaikan CARA "
        "pembelajaran dirancang (scaffolding, tingkat bantuan, "
        "contoh/konteks, kompleksitas, strategi pelaksanaan, "
        "bentuk/konteks asesmen) agar selaras TP/KKTP. DILARANG: "
        "membuat diagnosis baru tentang murid, menginfer kemampuan di "
        "luar fakta di atas, atau mengubah target TP/KKTP."
    )


def build_kbc_layer(education_system: str) -> Dict:
    """KBC layer metadata: aktif HANYA untuk madrasah (KEMENAG).

    Panca Cinta tidak pernah masuk daftar Dimensi Profil Lulusan; ia
    hidup di layer kbc terpisah (tema + materi insersi) sesuai AGENTS.md
    §14/§15.
    """
    enabled = education_system == 'KEMENAG'
    return {
        "enabled": enabled,
        "themes": list(KBC_THEMES) if enabled else [],
        "insertion_material": [],
        "source": KBC_SOURCE_DOCUMENT if enabled else None,
    }


def resolve_kbc_insertions(kbc: Dict, activities) -> List[Dict]:
    """Traceability eksplisit insersi KBC -> aktivitas (deterministik).

    Setiap item insersi (string lama atau dict {text/materi,
    tp_ids/tp_terkait}) dinormalisasi menjadi
    {id, text, tp_ids, activity_ids, active}. Linkage memakai TP yang
    sudah tervalidasi (aktivitas membawa tp_linked) — tanpa keyword
    matching. TP tanpa aktivitas valid menghasilkan activity_ids kosong
    dan active False (tidak dirender sebagai insersi aktif). Tidak ada
    insersi/aktivitas yang dibuat di sini.
    """
    raw_items = (kbc or {}).get('insertion_material') or []
    if not isinstance(raw_items, list):
        return []
    tp_to_acts: Dict[str, List[str]] = {}
    for act in activities or []:
        if isinstance(act, dict):
            aid, tp = act.get('id'), act.get('tp_linked')
        else:
            aid, tp = getattr(act, 'id', None), getattr(act, 'tp_linked', None)
        if aid and tp:
            tp_to_acts.setdefault(str(tp), []).append(str(aid))
    resolved = []
    seq = 0
    for item in raw_items:
        if isinstance(item, dict):
            text = item.get('text', item.get('materi', ''))
            tp_ids = item.get('tp_ids', item.get('tp_terkait', []))
        else:
            text, tp_ids = item, []
        text = str(text or '').strip()
        if not text:
            continue
        if not isinstance(tp_ids, list):
            tp_ids = []
        tp_ids = [str(t).strip() for t in tp_ids
                  if isinstance(t, str) and str(t).strip()]
        activity_ids = []
        for tp in tp_ids:
            for aid in tp_to_acts.get(tp, []):
                if aid not in activity_ids:
                    activity_ids.append(aid)
        seq += 1
        tema = (item.get('tema') if isinstance(item, dict) else None)
        if not isinstance(tema, str) or \
                tema.strip() not in ((kbc or {}).get('themes') or []):
            tema = None
        else:
            tema = tema.strip()
        resolved.append({
            'id': f'kbc-ins-{seq:02d}',
            'text': text,
            'tema': tema,
            'tp_ids': tp_ids,
            'activity_ids': activity_ids,
            'active': bool(activity_ids),
        })
    return resolved


KEMENAG_APPROACH = {
    "approach": "Pembelajaran Mendalam",
    "source": "Permendikdasmen No. 13 Tahun 2025; KMA No. 1503 Tahun 2025",
    "principles": list(DEEP_LEARNING_PRINCIPLES),
    "deep_learning": {
        "characteristics": ["berkesadaran (mindful)", "bermakna (meaningful)", "menggembirakan (joyful)"],
        "role": "kerangka kerja pembelajaran dan asesmen",
    },
    # 8 Dimensi Profil Lulusan — bukan nilai KBC.
    "values": list(PROFILE_DIMENSIONS_8),
    "profile_dimensions_source": "Permendikdasmen No. 10 Tahun 2025",
    # KBC sebagai layer tambahan madrasah (bukan pengganti dimensi).
    "kbc": build_kbc_layer('KEMENAG'),
}

KEMENDIKDASMEN_APPROACH = {
    "approach": "Pembelajaran Mendalam",
    "source": "Permendikdasmen No. 13 Tahun 2025; PPA Edisi Revisi 2025 (BSKAP Kemendikdasmen)",
    "principles": list(DEEP_LEARNING_PRINCIPLES),
    "deep_learning": {
        "characteristics": ["berkesadaran (mindful)", "bermakna (meaningful)", "menggembirakan (joyful)"],
        "role": "kerangka kerja pembelajaran dan asesmen",
    },
    "values": list(PROFILE_DIMENSIONS_8),
    "profile_dimensions_source": "Permendikdasmen No. 10 Tahun 2025",
    "kbc": build_kbc_layer('KEMENDIKDASMEN'),
}

# Deterministic scoring intervals (PPA 2025 p53)
SCORING_INTERVALS = [
    {"interval": "81-100", "follow_up": "Sudah mencapai tujuan pembelajaran, perlu tantangan lebih (pengayaan)"},
    {"interval": "61-80", "follow_up": "Sudah mencapai tujuan pembelajaran"},
    {"interval": "41-60", "follow_up": "Hampir mencapai tujuan pembelajaran, perlu remedial dengan mempelajari kembali kriteria yang diperlukan"},
    {"interval": "0-40", "follow_up": "Belum mencapai tujuan pembelajaran, perlu remedial menyeluruh"},
]

# C.5 rubric levels (audit finding RUBRIC_DESCRIPTOR_WEAK: labels alone are
# not sufficient — every level must carry an observable descriptor).
RUBRIC_LEVELS = ['Kurang', 'Cukup', 'Baik', 'Sangat Baik']


def _normalize_b4_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace (used by the
    rubric-descriptor checks and formerly the B.4-vs-L.1 gate)."""
    return " ".join(
        re.sub(r"[^\w\s]", " ", (text or "").lower()).split()
    )

def build_approach_principles(education_system: str) -> Dict:
    """Deterministic approach/principles metadata per authority.

    Keduanya memakai kerangka Pembelajaran Mendalam; KEMENAG membawa
    layer KBC tambahan (madrasah), KEMENDIKDASMEN tidak.
    """
    if education_system == 'KEMENAG':
        return json.loads(json.dumps(KEMENAG_APPROACH))
    return json.loads(json.dumps(KEMENDIKDASMEN_APPROACH))


def allowed_profile_values(education_system: str) -> List[str]:
    """8 Dimensi Profil Lulusan (normatif, sama untuk kedua sistem).

    Panca Cinta / tema KBC TIDAK pernah ada di daftar ini.
    """
    return list(PROFILE_DIMENSIONS_8)


def default_curriculum_version(education_system: str) -> str:
    """Versi kurikulum deterministik per sistem pendidikan.

    KEMENAG (madrasah) -> KMA-1503-2025;
    KEMENDIKDASMEN (sekolah umum) -> KEMENDIKDASMEN-2025.
    Sistem tidak dikenal adalah ERROR, bukan silent fallback - mencegah
    versi kurikulum madrasah menempel pada sekolah umum (atau sebaliknya).
    """
    try:
        return CURRICULUM_VERSION_BY_SYSTEM[education_system]
    except KeyError:
        raise ValueError(
            f"Unknown education_system {education_system!r}; expected one "
            f"of {sorted(CURRICULUM_VERSION_BY_SYSTEM)}"
        ) from None


@dataclass
class Module:
    """Complete validated learning module."""
    id: str
    title: str
    subject: str
    grade: str
    phase: str
    curriculum_version: str

    # Metadata
    module_identity: Dict
    facilities: List[str]
    target_students: Dict
    learning_model: str
    methods: List[str]

    # Core content
    learning_objectives: List[TPEntry]
    success_criteria: List[KKTPEntry]
    essential_understanding: Dict
    guiding_questions: List[str]
    learning_activities: List[ActivityEntry]

    # Assessment
    assessments: Dict

    # Supplementary
    reflection: List[Dict] = field(default_factory=list)
    remedial: Optional[Dict] = None
    enrichment: Optional[Dict] = None
    references: List[Dict] = field(default_factory=list)
    appendices: Dict = field(default_factory=dict)

    # -------------------------------------------------------------
    # MASTER OUTLINE fields (additive; Master Module Outline spec).
    # All have defaults -> backward compatible with legacy constructors.
    # -------------------------------------------------------------
    initial_competence: Optional[Dict] = None          # A.2 Kompetensi Awal
    profile_dimensions: List[str] = field(default_factory=list)  # A.3
    approach_principles: Dict = field(default_factory=dict)      # A.7 (deterministic)
    learning_phases: Dict = field(default_factory=dict)          # B.6: introduction/core/closing
    blueprint: List[Dict] = field(default_factory=list)          # C.4 Kisi-kisi (deterministic)
    rubric: Dict = field(default_factory=dict)                   # C.5 Rubrik & penskoran
    lkpd: List[Dict] = field(default_factory=list)               # Lampiran: LKPD
    glosarium: List[Dict] = field(default_factory=list)          # Lampiran: Glosarium
                                                                 # [{istilah, definisi}] — kosong
                                                                 # bila belum dibuat (via
                                                                 # regen/edit guru), bukan
                                                                 # karangan sistem.
    instrument_recap: Dict = field(default_factory=dict)         # Lampiran: rekap instrumen
    # RPM Pembelajaran Mendalam (AGENTS.md §12):
    # B Identifikasi - kesiapan murid + karakteristik materi.
    # Strukturnya deterministik (selalu ada); isinya diisi AI/konteks.
    learner_readiness: Optional[Dict] = None          # B.1 Kesiapan murid
    material_characteristics: Optional[Dict] = None   # B.2 Karakteristik materi
    # C Desain - kerangka pembelajaran
    pedagogical_practices: List[str] = field(default_factory=list)  # praktik pedagogis
    learning_partnerships: List[str] = field(default_factory=list)  # kemitraan
    learning_environment: Optional[Dict] = field(default_factory=lambda: {})  # lingkungan
    digital_use: Optional[Dict] = field(default_factory=lambda: {})  # pemanfaatan digital
    # Unit pembelajaran (AGENTS.md §11): kesatuan pembelajaran, bukan
    # 1 bab = 1 dokumen.
    unit: Optional[Dict] = None
    # Konsultasi regulasi (AGENTS.md §3/§7): fragmen resmi dokumen yang
    # mengubah/menerangkan CP (BKPDM 020/2026 utk School, KMA 1503/2025
    # utk Madrasah) yang dikonsultasikan ke AI saat generate. Struktur
    # deterministik; konten fragmen dari DB dengan provenance utuh.
    regulatory_consultation: Optional[Dict] = None

    # Validation & Metadata
    curriculum_context: Optional[Any] = None
    validation_results: Dict = field(default_factory=dict)
    generation_id: str = ""
    generated_at: str = ""
    generated_by: str = "9router-rpm"
    # Authoritative user topic (BLOCKER 1 lineage): carried from the
    # generation request into the serialized module JSON so the API/UI
    # read it as a first-class field, never re-derived from the title.
    topic: str = ""
    # Batch 8.5 §5: input topik mentah guru (topic_seed) vs formulasi
    # formal hasil refinement AI (topic). Render memakai topic; seed
    # disimpan sebagai provenance input (immutable pasca-generate).
    topic_seed: str = ""
    # Batch 8.5 §2: alasan relevansi per dimensi Profil Lulusan yang
    # dipilih AI ({dimensi: deskripsi}). Selalu berpasangan dengan
    # profile_dimensions; tidak pernah dikarang untuk dimensi lain.
    profile_dimension_notes: Dict = field(default_factory=dict)
    # Input guru eksplisit (tanpa silent default): penyusun, kesiapan
    # murid, dan D terstruktur per pertemuan. Defaults kosong menjaga
    # kompatibilitas hasil lama.
    penyusun: str = ""
    student_readiness: str = ""
    meetings: List[Dict] = field(default_factory=list)

    def build_master_outline(self) -> Dict:
        """Master Outline view (A-E + Lampiran) over the existing fields.

        View adapter: the flat dataclass fields remain the source of
        truth; this view only re-groups them per the Master Outline.
        """
        ctx = self.curriculum_context
        cp = ctx.cp if ctx is not None else None
        ap = self.approach_principles or {}
        return {
            'general_information': {
                'identity': {
                    'id': self.id, 'title': self.title,
                    'subject': self.subject, 'grade': self.grade,
                    'phase': self.phase,
                    'curriculum_version': self.curriculum_version,
                    'module_identity': self.module_identity,
                    'unit': self.unit,
                },
                'initial_competence': self.initial_competence,
                # 8 Dimensi Profil Lulusan (Permendikdasmen 10/2025).
                'profile_dimensions_values': self.profile_dimensions,
                # KBC: layer tambahan madrasah; selalu None/empty untuk
                # KEMENDIKDASMEN.
                'kbc': ap.get('kbc') or build_kbc_layer(
                    (ctx.education_system if ctx is not None else '') or ''),
                'facilities_infrastructure': self.facilities,
                'target_students': self.target_students,
                'learning_model': self.learning_model,
                'approach_principles': self.approach_principles,
            },
            # B. IDENTIFIKASI (AGENTS.md §12 B / §17)
            'identification': {
                'learner_readiness': self.learner_readiness,
                'material_characteristics': self.material_characteristics,
                'profile_dimensions': self.profile_dimensions,
                # Batch 8.5 §2: alasan relevansi per dimensi terpilih.
                'profile_dimension_notes': self.profile_dimension_notes,
            },
            # C. DESAIN PEMBELAJARAN (AGENTS.md §12 C / §16)
            'design': {
                'cp': cp.text if cp is not None else None,
                'cp_provenance': ({
                    'source_document_id': cp.source_document_id,
                    'source_fragment_id': cp.source_fragment_id,
                    'source_page': cp.source_page,
                    'phase': cp.phase,
                    'element': cp.element,
                    'curriculum_version': self.curriculum_version,
                } if cp is not None else None),
                'tp': [asdict(t) for t in self.learning_objectives],
                'atp': ({'tp_ids': [t.id for t in self.learning_objectives]}
                        if self.learning_objectives else None),
                'kktp': [asdict(k) for k in self.success_criteria],
                'topic_context': self.topic,
                'pedagogical_practices': self.pedagogical_practices,
                'learning_partnerships': self.learning_partnerships,
                'learning_environment': self.learning_environment,
                'digital_use': self.digital_use,
                'meaningful_understanding': self.essential_understanding,
                'triggering_questions': self.guiding_questions,
                # Jejak konsultasi regulasi (amandemen/pedoman CP) yang
                # dikonsultasikan ke AI — provenance telusuri ke Hukum/.
                'regulatory_consultation': self.regulatory_consultation,
            },
            # D. PENGALAMAN BELAJAR / LANGKAH PEMBELAJARAN
            # (memahami / mengaplikasi / merefleksi, AGENTS.md §13)
            'learning_experience': {
                'experiences': self.learning_phases,
                'principles': DEEP_LEARNING_PRINCIPLES,
            },
            # E. ASESMEN (awal / proses / akhir; AGENTS.md §12 E / §18)
            'assessment': {
                'awal': self.assessments.get('diagnostic'),
                'proses': self.assessments.get('formative'),
                'akhir': self.assessments.get('summative'),
                'blueprint': self.blueprint,
                'rubric_scoring': self.rubric,
            },
            'remedial_enrichment': {
                'remedial': self.remedial,
                'enrichment': self.enrichment,
            },
            'reflection': {
                'student': [r for r in self.reflection if r.get('role') == 'student'],
                'teacher': [r for r in self.reflection if r.get('role') == 'teacher'],
            },
            'attachments': {
                'lkpd': self.lkpd,
                'glosarium': self.glosarium,
                'instrument_recap': self.instrument_recap,
                'supporting': self.appendices,
            },
        }

    def to_dict(self) -> Dict:
        """Convert to dictionary (legacy keys preserved + master_outline view)."""
        data = asdict(self)
        data['master_outline'] = self.build_master_outline()
        return data

    @classmethod
    def from_stored_dict(cls, data: Dict,
                         context: Optional[Any]) -> 'Module':
        """Rebuild a Module from persisted JSON (restart-safe reload).

        Uses ONLY storage data — no in-memory dependency. Typed list
        entries are reconstructed so dataclass validators operate on
        real objects.
        """
        tp_fields = {f for f in TPEntry.__dataclass_fields__}
        kk_fields = {f for f in KKTPEntry.__dataclass_fields__}
        act_fields = {f for f in ActivityEntry.__dataclass_fields__}
        return cls(
            id=data.get('id', ''),
            title=data.get('title', ''),
            subject=data.get('subject', ''),
            grade=data.get('grade', ''),
            phase=data.get('phase', ''),
            curriculum_version=data.get('curriculum_version', ''),
            module_identity=data.get('module_identity', {}),
            facilities=data.get('facilities', []),
            target_students=data.get('target_students', {}),
            learning_model=data.get('learning_model', ''),
            methods=data.get('methods', []),
            learning_objectives=[
                TPEntry(**{k: tp.get(k) for k in tp_fields})
                for tp in data.get('learning_objectives') or []
                if isinstance(tp, dict)
            ],
            success_criteria=[
                KKTPEntry(**{k: kk.get(k) for k in kk_fields})
                for kk in data.get('success_criteria') or []
                if isinstance(kk, dict)
            ],
            essential_understanding=data.get('essential_understanding', {}),
            guiding_questions=data.get('guiding_questions', []),
            learning_activities=[
                ActivityEntry(**{k: a.get(k) for k in act_fields})
                for a in data.get('learning_activities') or []
                if isinstance(a, dict)
            ],
            assessments=data.get('assessments', {}),
            reflection=data.get('reflection', []),
            remedial=data.get('remedial'),
            enrichment=data.get('enrichment'),
            references=data.get('references', []),
            appendices=data.get('appendices', {}),
            initial_competence=data.get('initial_competence'),
            profile_dimensions=data.get('profile_dimensions', []),
            approach_principles=data.get('approach_principles', {}),
            learning_phases=data.get('learning_phases', {}),
            blueprint=data.get('blueprint', []),
            rubric=data.get('rubric', {}),
            lkpd=data.get('lkpd', []),
            glosarium=data.get('glosarium', []),
            instrument_recap=data.get('instrument_recap', {}),
            learner_readiness=data.get('learner_readiness'),
            material_characteristics=data.get('material_characteristics'),
            pedagogical_practices=data.get('pedagogical_practices', []),
            learning_partnerships=data.get('learning_partnerships', []),
            learning_environment=data.get('learning_environment', {}),
            digital_use=data.get('digital_use', {}),
            unit=data.get('unit'),
            regulatory_consultation=data.get('regulatory_consultation'),
            curriculum_context=context,
            validation_results=data.get('validation_results', {}),
            generation_id=data.get('generation_id', ''),
            generated_at=data.get('generated_at', ''),
            generated_by=data.get('generated_by', ''),
            topic=data.get('topic', ''),
            topic_seed=data.get('topic_seed', ''),
            profile_dimension_notes=data.get(
                'profile_dimension_notes', {}),
            penyusun=data.get('penyusun', ''),
            student_readiness=data.get('student_readiness', ''),
            meetings=data.get('meetings', []),
        )

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str, ensure_ascii=False, indent=2)


# ============================================================
# STAGE VALIDATORS
# ============================================================

class CurriculumValidator:
    """STAGE 1: Curriculum Validation (real CP retrieval)."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / 'db' / 'rpm_generator.db')
        self.db_path = db_path
        self.curriculum_engine = CurriculumEngine(db_path)
        self.curriculum_engine.connect()
        # Curriculum context resolved by the most recent successful validate()
        self.last_context: Optional[CurriculumContext] = None

    def close(self):
        """Close the underlying database connection."""
        self.curriculum_engine.close()

    def validate(self, params: Dict) -> Tuple[bool, Optional[CurriculumContext], List[str]]:
        """Validate curriculum context and retrieve CP from the database."""
        errors = []

        # Validate required fields ('element' is optional: resolved
        # deterministically when omitted - see BLOCKER 3 fix)
        required = ['education_system', 'institution_type', 'grade', 'subject']
        for field_name in required:
            if field_name not in params:
                errors.append(f"Missing required field: {field_name}")

        if errors:
            return False, None, errors

        # Validate education system
        if params['education_system'] not in ['KEMENAG', 'KEMENDIKDASMEN']:
            errors.append(f"Invalid education_system: {params['education_system']}")

        # Validate grade-phase mapping (phase is derived, never free-text)
        grade_key = resolve_grade_key(params['institution_type'], params['grade'])
        is_valid, phase, error = self.curriculum_engine.validate_grade_phase(
            params['education_system'],
            grade_key
        )
        if not is_valid:
            errors.append(f"Invalid grade-phase mapping: {error}")
            return False, None, errors

        # Validate subject-system mapping
        if not self.curriculum_engine.validate_subject_system(
            params['subject'],
            params['education_system']
        ):
            errors.append(
                f"Subject {params['subject']} not valid for {params['education_system']}"
            )
            return False, None, errors

        # Retrieve CP from the real database. Element resolution is
        # deterministic and EXPLICIT: a user-requested element must match
        # the authoritative CP exactly (no silent fallback), otherwise the
        # generation fails with ELEMENT_NOT_FOUND. Without an explicit
        # element, a unique match is resolved deterministically and the
        # resolution is recorded on the context metadata.
        try:
            expected_version = default_curriculum_version(
                params['education_system'])
            cp_list = self.curriculum_engine.get_cp_by_subject_phase(
                params['subject'], phase,
                education_system=params['education_system'],
                institution_type=params['institution_type'],
                curriculum_version_id=expected_version,
            )
            requested_element = (params.get('element') or '').strip()
            cp_row = None
            element_resolution = None
            if requested_element:
                for candidate in cp_list:
                    if candidate.element == requested_element:
                        cp_row = candidate
                        break
                if cp_row is None:
                    available = sorted({c.element for c in cp_list})
                    errors.append(
                        f"ELEMENT_NOT_FOUND: no CP for element "
                        f"'{requested_element}' in {params['subject']} "
                        f"phase {phase}. Available elements: {available}"
                    )
                    return False, None, errors
            elif cp_list:
                unique_elements = {c.element for c in cp_list}
                if len(unique_elements) == 1:
                    cp_row = cp_list[0]
                    element_resolution = (
                        f"element '{cp_row.element}' resolved uniquely from "
                        f"subject/phase (no explicit request)"
                    )
                else:
                    errors.append(
                        f"ELEMENT_NOT_FOUND: multiple elements available "
                        f"{sorted(unique_elements)} for {params['subject']} "
                        f"phase {phase}; an explicit 'element' is required"
                    )
                    return False, None, errors
            if cp_row is None:
                errors.append(
                    f"CP not found for {params['subject']}/{params.get('element')} phase {phase}"
                )
                return False, None, errors

            # Build immutable CP entry with real provenance. The DB
            # source_fragment_id is authoritative and retained verbatim;
            # a missing fragment id fails closed (no synthesized
            # page-derived id) so provenance can never be silently
            # weakened.
            if not (cp_row.source_fragment_id or '').strip():
                errors.append(
                    "CP_PROVENANCE_INVALID: CP row "
                    f"{cp_row.id!r} has no source_fragment_id "
                    "(fail closed — provenance must be complete)"
                )
                return False, None, errors
            cp = CPEntry(
                id=cp_row.id,
                text=cp_row.text,
                source_document_id=cp_row.source_document,
                source_fragment_id=cp_row.source_fragment_id,
                source_page=cp_row.source_page,
                phase=cp_row.phase,
                element=cp_row.element
            )
        except Exception as e:
            errors.append(f"Error retrieving CP: {str(e)}")
            return False, None, errors

        # Audit note: 'element' in the generated context mirrors the CP's
        # own element (authoritative). If resolution differed from the raw
        # request (unique-match path), the difference is recorded in
        # element_resolution_note below instead of being applied silently.

        # Build CurriculumContext via the official context generator
        # (immutable CP/ATP entries, hash, curriculum rules)
        try:
            context_gen = CurriculumContextGenerator()
            # curriculum_version is deterministic per education_system
            # (default_curriculum_version). A caller-supplied
            # 'curriculum_version' is FORBIDDEN: silently accepting it
            # would let a madrasah version attach to a school module
            # (or vice versa). Fail closed instead.
            if (params.get('curriculum_version') or '').strip():
                errors.append(
                    "CURRICULUM_VERSION_OVERRIDE_FORBIDDEN: "
                    "'curriculum_version' is derived deterministically "
                    "from education_system and must not be supplied"
                )
                return False, None, errors
            context = context_gen.generate(
                education_system=params['education_system'],
                institution_type=params['institution_type'],
                grade=str(params['grade']),
                phase=phase,
                subject=params['subject'],
                element=cp.element,  # authoritative CP element (not raw request)
                cp_text=cp.text,
                cp_source_doc=cp.source_document_id,
                cp_source_frag=cp.source_fragment_id,
                cp_page=cp.source_page,
                tp_list=[],
                atp_tp_ids=[],
                curriculum_version=expected_version
            )
            if context is None:
                errors.extend(
                    context_gen.validation_errors
                    or ["Curriculum context generation failed"]
                )
                return False, None, errors
            # Explicit, non-silent element resolution record (BLOCKER 3):
            # the context always carries the CP's authoritative element;
            # when it differs from the raw user request, the difference is
            # logged and stored on the context metadata.
            resolved_note = (
                element_resolution
                or f"element '{cp.element}' matched explicit request"
            )
            if element_resolution or cp.element != requested_element:
                logger.info("Element resolution: %s", resolved_note)
            context.element_resolution_note = resolved_note
            # BLOCKER 1 fix: carry the authoritative user topic on the
            # validated context so every downstream stage reads one source.
            context.topic = str(params.get('topic') or '').strip()
            self.last_context = context
            return True, context, []
        except Exception as e:
            errors.append(f"Error building CurriculumContext: {str(e)}")
            return False, None, errors


class StructureValidator:
    """STAGE 4: JSON Parsing & Structure Validation."""

    @staticmethod
    def validate_json(response_text: str) -> Tuple[bool, Optional[Dict], str]:
        """Parse and validate JSON response."""
        try:
            data = json.loads(response_text)
            if not isinstance(data, dict):
                return False, None, "Response must be JSON object"
            return True, data, ""
        except json.JSONDecodeError as e:
            return False, None, f"Invalid JSON: {str(e)}"

    @staticmethod
    def validate_tp_structure(tp_list: List) -> Tuple[bool, List[str]]:
        """Validate TP list structure."""
        errors = []
        if not isinstance(tp_list, list):
            return False, ["TP must be list"]
        if len(tp_list) == 0:
            return False, ["TP list is empty"]
        if len(tp_list) > 6:
            return False, ["Too many TP (max 6)"]
        return True, []

    @staticmethod
    def validate_kktp_structure(kktp_list: List) -> Tuple[bool, List[str]]:
        """Validate KKTP list structure."""
        errors = []
        if not isinstance(kktp_list, list):
            return False, ["KKTP must be list"]
        if len(kktp_list) == 0:
            return False, ["KKTP list is empty"]
        for i, kktp in enumerate(kktp_list):
            if not isinstance(kktp, KKTPEntry):
                errors.append(f"KKTP[{i}] must be KKTPEntry")
                continue
            if not kktp.criteria:
                errors.append(f"KKTP[{i}] missing 'criteria'")
            if kktp.tp_id != f"TP-{i + 1}":
                errors.append(
                    f"KKTP[{i}] references '{kktp.tp_id}' but is aligned to TP-{i + 1}"
                )
        return len(errors) == 0, errors


class ProtectionValidator:
    """STAGE 5: Curriculum Protection Validation.

    Verifies AI output cannot change CP, phase, subject, element,
    education_system, curriculum version, or provenance.
    """

    PROTECTED_FIELDS = {
        'cp', 'phase', 'element', 'subject', 'education_system', 'grade',
        'curriculum_version'
    }

    def validate(
        self, original: CurriculumContext, module: Module
    ) -> Tuple[bool, List[str]]:
        """Verify protected fields unchanged in the generated module."""
        errors = []

        ctx = module.curriculum_context
        if ctx is None:
            return False, ["Module has no curriculum context"]

        # CP text must be byte-identical
        if original.cp.text != ctx.cp.text:
            errors.append("CP text was modified (protected field)")
        if original.cp.id != ctx.cp.id:
            errors.append("CP id was modified (protected field)")
        # Provenance must be intact
        if original.cp.source_document_id != ctx.cp.source_document_id:
            errors.append("CP source document was modified (protected field)")
        if original.cp.source_fragment_id != ctx.cp.source_fragment_id:
            errors.append("CP source fragment was modified (protected field)")
        if original.cp.source_page != ctx.cp.source_page:
            errors.append("CP source page was modified (protected field)")

        if original.phase != ctx.phase:
            errors.append("Phase was modified (protected field)")
        if original.subject != ctx.subject:
            errors.append("Subject was modified (protected field)")
        if original.element != ctx.element:
            errors.append("Element was modified (protected field)")
        if original.education_system != ctx.education_system:
            errors.append("Education system was modified (protected field)")
        if original.grade != ctx.grade:
            errors.append("Grade was modified (protected field)")
        if original.curriculum_version != ctx.curriculum_version:
            errors.append("Curriculum version was modified (protected field)")

        # Module top-level mirrors must match too
        if module.subject != original.subject:
            errors.append("Module subject differs from context (protected field)")
        if module.phase != original.phase:
            errors.append("Module phase differs from context (protected field)")
        if module.grade != original.grade:
            errors.append("Module grade differs from context (protected field)")
        if module.curriculum_version != original.curriculum_version:
            errors.append("Module curriculum version differs (protected field)")

        return len(errors) == 0, errors

    def validate_ai_output(
        self, original: CurriculumContext, ai_data: Dict
    ) -> Tuple[bool, List[str]]:
        """Verify AI JSON output does not attempt to override protected fields."""
        errors = []
        protected_keys = {
            'cp', 'phase', 'subject', 'element', 'education_system',
            'curriculum_version', 'grade',
            # Indonesian aliases used by AI responses
            'capaian_pembelajaran', 'fase', 'mata_pelajaran', 'elemen',
            'sistem_pendidikan', 'jenjang',
        }
        for key in protected_keys:
            if key in ai_data:
                errors.append(
                    f"AI output attempted to define protected field '{key}'"
                )
        return len(errors) == 0, errors


class RuleValidator:
    """STAGE 6: Rule Engine Validation (C3+ cognitive levels)."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / 'db' / 'rpm_generator.db')
        self.db_path = db_path
        self.rule_engine = RuleEngine(db_path)

    def validate_tp_cognitive_level(self, tp_text: str) -> Tuple[bool, str, str]:
        """Validate TP meets minimum C3 cognitive level (KKO keyword extraction)."""
        c_level = self._extract_cognitive_level(tp_text)

        level_order = {'C1': 1, 'C2': 2, 'C3': 3, 'C4': 4, 'C5': 5, 'C6': 6}

        if c_level not in level_order:
            return False, c_level, "Could not determine cognitive level"

        if level_order[c_level] < 3:  # C3 is minimum
            return False, c_level, f"TP cognitive level {c_level} below minimum C3"

        return True, c_level, ""

    def validate_kktp_cognitive_level(self, kktp_text: str) -> Tuple[bool, str, str]:
        """Validate KKTP meets minimum C3 cognitive level."""
        return self.validate_tp_cognitive_level(kktp_text)

    @staticmethod
    def _extract_cognitive_level(text: str) -> str:
        """Extract cognitive level from text (KKO keyword heuristic, C6→C1).

        Daftar KKO adalah data normatif dari tabel cognitive_operators
        (87 kata kerja operasional C1-C6 dari user) + 'menganalisis' (C4)
        dan 'menerapkan' (C3) yang dipakai AI/test tapi tidak ada di
        daftar user. 'memahami' TIDAK didaftarkan (tidak ada di daftar
        user) -> UNKNOWN/ditolak. Multi-kata dicocokkan sebagai frasa agar 'membaca'
        saja tidak terangkat jadi C1 dan 'menyusun daftar' tidak
        tertelan 'menyusun kembali' (frasa panjang dulu).
        """
        text_lower = text.lower()

        c6_keywords = ['menyusun kembali', 'membangun', 'merencanakan',
                       'memproduksi', 'mengkombinasikan', 'merancang',
                       'merekonstruksi', 'membuat', 'menciptakan',
                       'mengabstraksi', 'mengkategorikan', 'mengarang',
                       'mendesain', 'merangkaikan']
        c5_keywords = ['memberi argumentasi', 'memberi saran', 'mengecek',
                       'mengkritik', 'mempertahankan', 'memvalidasi',
                       'mendukung', 'memproyeksikan', 'memperbandingkan',
                       'menilai', 'mengevaluasi', 'menafsirkan',
                       'merekomendasi']
        c4_keywords = ['menganalisis', 'mendiferensiasikan',
                       'mengorganisasikan', 'mengatribusikan', 'mendiagnosis',
                       'memerinci', 'menelaah', 'mendeteksi', 'mengaitkan',
                       'memecahkan', 'memisahkan', 'menyeleksi',
                       'mempertentangkan', 'membagi']
        c3_keywords = ['menerapkan', 'melaksanakan', 'mengimplementasikan',
                       'menggunakan', 'mengonsepkan', 'menentukan',
                       'memproseskan', 'mendemonstrasikan', 'menghitung',
                       'menghubungkan', 'melakukan', 'membuktikan',
                       'menghasilkan', 'memperagakan', 'melengkapi',
                       'menyesuaikan', 'menemukan']
        c2_keywords = ['memberi contoh', 'menjelaskan', 'mengartikan',
                       'menginterpretasikan', 'menceritakan', 'menampilkan',
                       'merangkum', 'menyimpulkan', 'membandingkan',
                       'mengklasifikasikan', 'menunjukkan', 'menguraikan',
                       'membedakan', 'menyadur', 'meramalkan',
                       'memperkirakan', 'menerangkan', 'menggantikan']
        c1_keywords = ['mengingat kembali', 'menyusun daftar',
                       'memberi definisi', 'menemukenali', 'membaca',
                       'menyebutkan', 'melafalkan', 'menuliskan',
                       'menghafal', 'menggarisbawahi', 'menjodohkan',
                       'memilih', 'menyatakan']

        for kw in c6_keywords:
            if kw in text_lower:
                return 'C6'
        for kw in c5_keywords:
            if kw in text_lower:
                return 'C5'
        for kw in c4_keywords:
            if kw in text_lower:
                return 'C4'
        for kw in c3_keywords:
            if kw in text_lower:
                return 'C3'
        for kw in c2_keywords:
            if kw in text_lower:
                return 'C2'
        for kw in c1_keywords:
            if kw in text_lower:
                return 'C1'

        return 'UNKNOWN'


class PedagogicalValidator:
    """STAGE 7: Pedagogical Validation (fatal on failure)."""

    @staticmethod
    def validate_activity_alignment(
        activities: List[ActivityEntry], tp_count: int
    ) -> Tuple[bool, List[str]]:
        """Validate every TP has at least one LINKED activity.

        Count alone is weak: N activities for N TPs still fails when a
        TP has no activity carrying its tp_linked. Each TP id must be
        referenced by >= 1 activity (unlinked shared-experience
        activities never satisfy coverage).
        """
        errors = []

        if len(activities) < tp_count:
            errors.append(
                f"Only {len(activities)} activities for {tp_count} TP (need 1+ per TP)"
            )

        linked = set()
        for act in activities or []:
            ref = getattr(act, 'tp_linked', None)
            if isinstance(ref, str) and ref.strip():
                linked.add(ref.strip())
        for i in range(1, (tp_count or 0) + 1):
            if f"TP-{i}" not in linked:
                errors.append(
                    f"TP-{i} has no linked activity (tp_linked coverage)"
                )

        return len(errors) == 0, errors

    @staticmethod
    def validate_assessment_alignment(
        assessments: Dict, tp_count: int, kktp_count: int
    ) -> Tuple[bool, List[str]]:
        """Validate assessment covers diagnostic, formative, summative.

        Buckets alone are weak: every TP must be traceable to >= 1
        assessment item via an explicit tp_linked. Items without a link
        never satisfy coverage. R-42: bucket kosong (tidak digenerate)
        dilewati; hubungan hanya dicek untuk bucket yang ada.
        """
        errors = []

        if not isinstance(assessments, dict) or not assessments:
            return False, ["Assessments missing entirely"]

        ada = [b for b in ('diagnostic', 'formative', 'summative')
               if assessments.get(b)]
        if not ada:
            return False, ["Assessments missing entirely"]

        linked_tps = set()

        def _collect(items):
            for item in items or []:
                if isinstance(item, dict):
                    ref = item.get('tp_linked')
                    if isinstance(ref, str) and ref.strip():
                        linked_tps.add(ref.strip())

        _collect(assessments.get('diagnostic'))
        _collect(assessments.get('formative'))
        summative = assessments.get('summative')
        if isinstance(summative, dict):
            _collect(summative.get('items'))
        elif isinstance(summative, list):
            _collect(summative)
        for i in range(1, (tp_count or 0) + 1):
            if f"TP-{i}" not in linked_tps:
                errors.append(
                    f"TP-{i} is not traceable to any assessment item "
                    "(tp_linked coverage)"
                )

        return len(errors) == 0, errors


# ============================================================
# ANTI-SLOP SKILL ADAPTER (runtime enforcement of
# skills/antislop/SKILL.md + skills/antislop-copywriting/SKILL.md)
#
# The Markdown skill files are agent instructions, NOT executable
# code. This adapter is the explicit runtime implementation: it
# encodes the transferable prose rules as deterministic transforms
# (rewrite) and detectors (report-only), each citing its skill rule.
# Rules that only make sense for coding-agent/UI output (icons,
# layouts, CTAs, testimonials scaffolding, themes, responsiveness,
# keyboard, FAQ, navigation, patching, dark mode, etc.) are
# deliberately NOT applied to RPM content; they are listed as
# excluded with reasons so the mapping stays auditable.
# Version the policy: bump ANTISLOP_SKILL_VERSION whenever this
# table or the transforms below change.
# ============================================================

ANTISLOP_SKILL_VERSION = '1.1'

# (rule_id, name, enforcement, note)
# enforcement: 'rewrite' = deterministic safe transform applied;
#   'detect' = reported in the anti-slop report, never rewritten
#   (rewriting would risk meaning drift in teacher-facing prose).
ANTISLOP_SKILL_RULES = (
    ('R-02', 'em-dash', 'rewrite',
     'Spaced em/en/double hyphens become commas; digit ranges kept.'),
    ('R-36-chatbot-closer', 'chatbot-closer', 'rewrite',
     'Whole information-free closer sentences are dropped.'),
    ('R-36-signposting', 'signposting', 'rewrite',
     'Whole meta-commentary sentences are dropped.'),
    ('R-36-filler', 'filler-phrase', 'rewrite',
     'Unambiguous English filler phrases get plain equivalents.'),
    ('R-36-informal-id', 'informal-construction-id', 'rewrite',
     'ID informal fillers (dan lain-lain/dll/dsb/dst/etc) are dropped.'),
    ('R-16', 'empty-ai-vocabulary', 'detect',
     'Buzzwords are flagged; deletion would break sentences.'),
    ('R-36-fake-candid', 'fake-candid-opener', 'detect',
     'Theatrical honesty openers are flagged.'),
    ('R-36-authority-trope', 'persuasive-authority-trope', 'detect',
     'Ceremonial authority phrases are flagged.'),
    ('R-36-caps', 'all-caps-emphasis', 'detect',
     'Re-casing would damage proper nouns; flagged instead.'),
    ('R-36-staccato', 'staccato-drama', 'detect',
     'Runs of clipped fragments are flagged.'),
    ('R-36-quotes', 'excessive-quotation', 'detect',
     'Quote-dense fields are flagged; real citations keep quotes.'),
    ('R-36-inline-header', 'inline-header-list', 'detect',
     'Bold-header list items are flagged.'),
)


class SkillDrivenNormalizer:
    """Deterministic prose filter implementing the transferable
    skills/antislop rules for Indonesian teacher-facing narrative.

    Only information-preserving transforms are applied; everything
    else is reported as findings. Quoted spans ("..." / "...") are
    never rewritten, so dalil quotations stay byte-identical.
    """

    _BUZZWORDS = (
        'unlock', 'elevate', 'empower', 'delve', 'showcase', 'testament',
        'landscape', 'journey', 'robust', 'game-changer', 'next-level',
        'seamless', 'cutting-edge', 'revolutionary', 'revolutionizing',
    )
    # Full-sentence closers (EN from the skill + ID adapter extensions
    # marked [ID]; same R-36 rule, operative language of RPM output).
    _CLOSERS_FULL = frozenset([
        "i hope this helps",
        "you're welcome",
        "semoga membantu",  # [ID]
        "semoga bermanfaat",  # [ID]
        "selamat mengajar",  # [ID]
    ])
    # Konstruksi informal yang dilarang di dokumen RPM formal [ID]:
    # singkatan malas (dll/dst/etc) dan frasa tak-tuntas
    # (dan lain-lain, dsb). Dihapus deterministik; bila kalimat jadi
    # kosong, kalimat asli dipertahankan caller (fail safe).
    _INFORMAL_PATTERNS = (
        # "dan lain-lain" / "dan lain sebagainya" (variasi tanda baca).
        re.compile(
            r'\s*,?\s*\bdan\s+lain(?:-lain|nya| sebagainya)\b\s*[.;]?',
            re.IGNORECASE),
        # Singkatan malas: dll. / dsb. / dst. / etc. (dengan/tanpa titik).
        re.compile(r'\s*,?\s*\b(dll|dsb|dst|etc)\b\.?', re.IGNORECASE),
    )
    _CLOSERS_PREFIX = (
        "let me know if",
        "feel free to",
        "would you like me to",
        "beri tahu saya jika",  # [ID]
        "silakan bertanya jika",  # [ID]
    )
    _SIGNPOSTS = (
        "let's dive in",
        "here's what you need to know",
        "in this article",
        "without further ado",
        "mari kita selami",  # [ID]
        "mari kita bahas",  # [ID]
        "pada artikel ini",  # [ID]
        "tanpa berlama-lama",  # [ID]
    )
    _FILLERS = (
        (re.compile(r'\bin order to\b', re.IGNORECASE), 'to'),
        (re.compile(r'\bdue to the fact that\b', re.IGNORECASE),
         'because'),
        (re.compile(r'\bat this point in time\b', re.IGNORECASE), 'now'),
        (re.compile(r'\bit is important to note that\b', re.IGNORECASE),
         ''),
    )
    _FAKE_CANDID = re.compile(
        r"^(honestly|let'?s be honest|here'?s the thing|real talk)\b",
        re.IGNORECASE)
    _AUTHORITY = re.compile(
        r"\b(at its core|the real question is|what really matters|"
        r"fundamentally|the deeper issue|the heart of the matter)\b",
        re.IGNORECASE)
    _BUZZWORD_RE = None  # built lazily, keeps import light
    _QUOTE_SPAN = re.compile(
        '"[^"]*"|\\u201c[^\\u201d]*\\u201d')
    _SENT_SPLIT = re.compile(r'(?<=[.!?…])\s+')
    _INLINE_HEADER = re.compile(r'^-\s*\*\*.+?\*\*:')

    @classmethod
    def _buzzword_re(cls):
        if cls._BUZZWORD_RE is None:
            cls._BUZZWORD_RE = re.compile(
                r'\b(' + '|'.join(re.escape(w) for w in cls._BUZZWORDS)
                + r')\b', re.IGNORECASE)
        return cls._BUZZWORD_RE

    @classmethod
    def _split_quoted(cls, text):
        """Split into (is_quoted, segment) parts; quoted spans are
        protected from every rewrite."""
        parts, last = [], 0
        for match in cls._QUOTE_SPAN.finditer(text):
            if match.start() > last:
                parts.append((False, text[last:match.start()]))
            parts.append((True, match.group(0)))
            last = match.end()
        if last < len(text):
            parts.append((False, text[last:]))
        return parts or [(False, text)]

    @classmethod
    def _normalize_plain(cls, segment, counts):
        """Apply rewrite rules to one unquoted segment."""
        out = segment
        # R-02: spaced em/en/double hyphens -> comma. Digit ranges
        # (10-12) and hyphenated compounds are never touched: only
        # whitespace-flanked runs or letter-flanked em dashes qualify.
        new = re.sub(r'\s+(?:—|–|--)\s+', ', ', out)
        new = re.sub(r'(?<=[A-Za-z])—(?=[A-Za-z])', ', ', new)
        if new != out:
            counts['R-02'] = counts.get('R-02', 0) + 1
            out = new
        # R-36 filler phrases (English, unambiguous).
        for pattern, replacement in cls._FILLERS:
            new = pattern.sub(replacement, out)
            if new != out:
                counts['R-36-filler'] = counts.get('R-36-filler', 0) + 1
                out = new
        # [ID] Konstruksi informal RPM: hapus deterministik. Kutipan
        # sudah dipisah sebelum fungsi ini dipanggil, jadi dalil aman.
        for pattern in cls._INFORMAL_PATTERNS:
            new = pattern.sub('', out)
            if new != out:
                counts['R-36-informal-id'] = counts.get(
                    'R-36-informal-id', 0) + 1
                out = new
        return out

    @classmethod
    def _is_closer_or_signpost(cls, sentence):
        norm = sentence.strip().lower().rstrip('.!?')
        if norm in cls._CLOSERS_FULL:
            return 'R-36-chatbot-closer'
        if any(norm == p or norm.startswith(p + ' ')
               for p in cls._CLOSERS_PREFIX):
            return 'R-36-chatbot-closer'
        if any(norm == s or norm.startswith(s + ' ') or norm.startswith(s + ',')
               for s in cls._SIGNPOSTS):
            return 'R-36-signposting'
        return None

    @classmethod
    def normalize(cls, text):
        """Normalize prose; returns (new_text, {rule_id: count}).

        Quote spans are split FIRST on the whole text (so abbreviations
        like "QS." can never shatter a protected quotation), then each
        unquoted part is processed sentence by sentence. Quoted parts
        are always kept verbatim. Never returns an empty string for
        non-empty input (the caller keeps the original instead).
        """
        counts: Dict[str, int] = {}
        if not isinstance(text, str) or not text.strip():
            return text, counts
        kept = []
        for quoted, seg in cls._split_quoted(text):
            if quoted:
                kept.append(seg)
                continue
            for sentence in cls._SENT_SPLIT.split(seg):
                if not sentence.strip():
                    continue
                hit = cls._is_closer_or_signpost(sentence)
                if hit:
                    counts[hit] = counts.get(hit, 0) + 1
                    continue
                kept.append(cls._normalize_plain(sentence, counts))
        out = re.sub(r'[ \t]{2,}', ' ', ' '.join(kept)).strip()
        return (out if out else text), counts

    @classmethod
    def scan(cls, text, limit=25):
        """Detect skill violations without rewriting.

        Returns [{rule, excerpt}]; excerpts capped for log hygiene.
        """
        findings = []

        def add(rule, excerpt):
            if len(findings) < limit:
                excerpt = str(excerpt).strip().replace('\n', ' ')
                findings.append({'rule': rule, 'excerpt': excerpt[:120]})

        if not isinstance(text, str) or not text.strip():
            return findings
        for match in cls._buzzword_re().finditer(text):
            start = max(0, match.start() - 40)
            add('R-16', text[start:match.end() + 40])
        for sentence in cls._SENT_SPLIT.split(text):
            stripped = sentence.strip()
            if cls._FAKE_CANDID.match(stripped):
                add('R-36-fake-candid', stripped)
            if cls._AUTHORITY.search(stripped):
                add('R-36-authority-trope', stripped)
            letters = re.sub(r'[^A-Za-z]', '', stripped)
            if len(stripped) > 20 and letters and not re.search(
                    r'[a-z]', stripped):
                add('R-36-caps', stripped)
        shorts, run = 0, 0
        for sentence in cls._SENT_SPLIT.split(text):
            if sentence.strip() and len(sentence.strip()) <= 25:
                run += 1
                shorts = max(shorts, run)
            else:
                run = 0
        if run >= 3 or shorts >= 3:
            add('R-36-staccato', text)
        if text.count('"') + text.count('"') + text.count('"') > 6:
            add('R-36-quotes', text)
        for line in text.splitlines():
            if cls._INLINE_HEADER.match(line.strip()):
                add('R-36-inline-header', line.strip())
        return findings


class AntiSlopProcessor:
    """STAGE 8: Anti-Slop Processing (Humanization).

    Protected fields (CP, TP, phase, subject, element, citations,
    references, dates) are NEVER modified. Only whitelisted narrative
    fields may be humanized.
    """

    PROTECTED_FIELDS = {
        'cp', 'tp', 'kktp', 'phase', 'element', 'subject',
        'education_system', 'citations', 'references', 'dates',
        'cognitive_level', 'curriculum_version'
    }

    HUMANIZABLE_FIELDS = {
        'activity_description', 'material_narrative',
        'assessment_instruction', 'reflection'
    }

    # Runtime skill policy: subset of ANTISLOP_SKILL_RULES actually
    # enforced by the adapter above (rule id -> short name). UI-only
    # skill rules (icons, layout, themes, keyboard, FAQ, navigation,
    # testimonials scaffolding, etc.) are intentionally absent here.
    ANTISLOP_SKILL_VERSION = ANTISLOP_SKILL_VERSION
    SKILL_RULES = tuple(
        {'id': rule_id, 'name': name, 'enforcement': enforcement}
        for rule_id, name, enforcement, _note in ANTISLOP_SKILL_RULES
    )

    # Module-field routing for skill normalization. Keys are report
    # labels; values are the legacy humanize_section field names
    # (behavior of the legacy path is preserved exactly). The
    # 'generated_narrative' route covers every other AI-authored
    # narrative dict walked by _normalize_generated_dicts.
    SKILL_FIELD_ROUTES = {
        'activity_description': 'activity_description',
        'pedagogical_practices': 'material_narrative',
        'triggering_questions': 'material_narrative',
        'reflection': 'reflection',
        'remedial_description': 'material_narrative',
        'enrichment_description': 'material_narrative',
        'material_summary': 'material_narrative',
        'assessment_question': 'assessment_instruction',
        'generated_narrative': 'material_narrative',
    }

    @staticmethod
    def _field_value(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def snapshot_protected(module: Module) -> Dict:
        """Capture every protected/normative value anti-slop must not
        touch. Humanizable NARRATIVE text is excluded by design (it is
        the only thing allowed to change); everything structural or
        normative is captured verbatim."""
        def tp_snapshot(items):
            out = []
            for entry in items or []:
                out.append((
                    AntiSlopProcessor._field_value(entry, 'id'),
                    AntiSlopProcessor._field_value(entry, 'text'),
                    AntiSlopProcessor._field_value(entry, 'cognitive_level'),
                ))
            return out

        def kktp_snapshot(items):
            out = []
            for entry in items or []:
                criteria = AntiSlopProcessor._field_value(
                    entry, 'criteria') or []
                out.append((
                    AntiSlopProcessor._field_value(entry, 'id'),
                    AntiSlopProcessor._field_value(entry, 'tp_id'),
                    tuple(criteria) if isinstance(criteria, list)
                    else criteria,
                    AntiSlopProcessor._field_value(
                        entry, 'cognitive_level'),
                ))
            return out

        def assessment_structure(assessments):
            """Full item structure minus humanizable question text."""
            out = {}
            for bucket, items in (assessments or {}).items():
                if isinstance(items, dict):
                    items = items.get('items', [])
                normalized = []
                for item in items or []:
                    if not isinstance(item, dict):
                        normalized.append(item)
                        continue
                    normalized.append({
                        key: value for key, value in item.items()
                        if key != 'question'
                    })
                out[bucket] = normalized
            return out

        def str_list(values):
            return [v for v in (values or []) if isinstance(v, str)]

        material = module.material_characteristics or {}
        characteristics = {
            key: value for key, value in material.items()
            if key != 'summary'
        } if isinstance(material, dict) else material
        context = module.curriculum_context
        cp_text = None
        try:
            if context is not None:
                cp_text = context.cp.text
        except AttributeError:
            cp_text = None
        learner = module.learner_readiness
        return {
            'cp': cp_text,
            'phase': module.phase,
            'subject': module.subject,
            'element': AntiSlopProcessor._field_value(
                context, 'element') if context is not None else None,
            'grade': module.grade,
            'curriculum_version': module.curriculum_version,
            'title': module.title,
            'topic': module.topic,
            'topic_seed': module.topic_seed,
            'tp': tp_snapshot(module.learning_objectives),
            'kktp': kktp_snapshot(module.success_criteria),
            'student_readiness': module.student_readiness,
            'penyusun': module.penyusun,
            'learner_readiness': learner,
            'material_lists': characteristics,
            'assessment_structure': assessment_structure(
                module.assessments),
            'references': module.references,
            'regulatory_consultation':
                module.regulatory_consultation,
            'approach_principles': module.approach_principles,
            'glosarium': module.glosarium,
            'lkpd': module.lkpd,
        }

    @staticmethod
    def validate_antislop_snapshot(before: Dict, after: Dict):
        """Fail when any protected value changed across anti-slop."""
        errors = []
        for key in before:
            if key not in after or before[key] != after[key]:
                errors.append(
                    f"AntiSlop changed protected field: {key}")
        for key in after:
            if key not in before:
                errors.append(
                    f"AntiSlop introduced unexpected field: {key}")
        return len(errors) == 0, errors

    @staticmethod
    def _normalize_text(text, legacy_field, label, report):
        """Legacy humanize_section + skill normalize one string."""
        if not isinstance(text, str) or not text:
            return text
        for finding in SkillDrivenNormalizer.scan(text):
            entry = dict(finding)
            entry['field'] = label
            report['findings'].append(entry)
        legacy = AntiSlopProcessor.humanize_section(text, legacy_field)
        normalized, counts = SkillDrivenNormalizer.normalize(legacy)
        for rule_id, count in counts.items():
            report['rewrites'][rule_id] = \
                report['rewrites'].get(rule_id, 0) + count
        return normalized

    @staticmethod
    def _normalize_str_list(values, legacy_field, label, report):
        changed = 0
        out = []
        for value in values or []:
            if isinstance(value, str):
                new_value = AntiSlopProcessor._normalize_text(
                    value, legacy_field, label, report)
                out.append(new_value)
                if new_value != value:
                    changed += 1
            else:
                out.append(value)
        report['fields_processed'][label] = \
            report['fields_processed'].get(label, 0) + len(out)
        return out, changed

    @staticmethod
    def _normalize_generated_dicts(module: Module, report) -> None:
        """Normalize every remaining AI-authored narrative dict.

        Covers outline fields the legacy path never touched
        (initial_competence, material_characteristics free text,
        essential_understanding/B.4, learner_readiness summary,
        learning_environment, digital_use, KBC notes, LKPD text,
        profile_dimension_notes): 'murid' baku + informal-filler
        removal apply. Protected/normative structures (CP/TP/KKTP,
        links, points, provenance, glosarium terms, references) are
        never walked here.
        """
        routes = AntiSlopProcessor.SKILL_FIELD_ROUTES
        legacy_field = routes['generated_narrative']
        label = 'generated_narrative'

        def walk(node, depth=0):
            if depth > 6 or not isinstance(node, dict):
                return
            for key, value in list(node.items()):
                if key in ('source', 'provenance',
                           'source_document_id', 'source_fragment_id',
                           'source_page', 'cp', 'tp_linked',
                           'kktp_linked', 'tp_reference', 'tp_terkait',
                           'points', 'options', 'correct_answer',
                           'answer_key', 'answer', 'levels',
                           'descriptors', 'criteria', 'themes',
                           'tema', 'enabled'):
                    continue
                if isinstance(value, str) and value.strip():
                    node[key] = AntiSlopProcessor._normalize_text(
                        value, legacy_field, label, report)
                elif isinstance(value, dict):
                    walk(value, depth + 1)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            walk(item, depth + 1)

        for container in (
                getattr(module, 'initial_competence', None),
                getattr(module, 'material_characteristics', None),
                getattr(module, 'essential_understanding', None),
                getattr(module, 'learner_readiness', None),
                getattr(module, 'learning_environment', None),
                getattr(module, 'digital_use', None),
                getattr(module, 'profile_dimension_notes', None)):
            if isinstance(container, dict):
                walk(container)
        kbc = (getattr(module, 'approach_principles', None) or {}).get(
            'kbc')
        if isinstance(kbc, dict):
            note = kbc.get('integration_note')
            if isinstance(note, str) and note.strip():
                kbc['integration_note'] = (
                    AntiSlopProcessor._normalize_text(
                        note, legacy_field, label, report))
        for sheet in getattr(module, 'lkpd', None) or []:
            if isinstance(sheet, dict):
                walk(sheet)

    @staticmethod
    def humanize_with_report(module: Module):
        """Skill-driven humanize; returns (module, report).

        Only whitelisted AI narrative is processed; quoted spans
        (dalil quotations) are never rewritten; protected fields are
        structurally unreachable here (verified by snapshot gate in
        the pipeline).
        """
        report: Dict[str, Any] = {
            'skill_version': AntiSlopProcessor.ANTISLOP_SKILL_VERSION,
            'fields_processed': {},
            'rewrites': {},
            'findings': [],
        }
        routes = AntiSlopProcessor.SKILL_FIELD_ROUTES
        # Activity descriptions (legacy behavior preserved).
        for activity in module.learning_activities or []:
            description = AntiSlopProcessor._field_value(
                activity, 'description')
            if isinstance(description, str) and description:
                new_description = AntiSlopProcessor._normalize_text(
                    description, routes['activity_description'],
                    'activity_description', report)
                report['fields_processed']['activity_description'] = \
                    report['fields_processed'].get(
                        'activity_description', 0) + 1
                try:
                    activity.description = new_description
                except AttributeError:
                    pass
                if isinstance(activity, dict):
                    activity['description'] = new_description
        # Pedagogical practices + triggering questions (plain lists).
        module.pedagogical_practices, _ = \
            AntiSlopProcessor._normalize_str_list(
                module.pedagogical_practices,
                routes['pedagogical_practices'],
                'pedagogical_practices', report)
        module.guiding_questions, _ = \
            AntiSlopProcessor._normalize_str_list(
                module.guiding_questions,
                routes['triggering_questions'],
                'triggering_questions', report)
        # Reflection entries: dicts with question lists, or strings.
        reflection = module.reflection or []
        for pos, entry in enumerate(reflection):
            if isinstance(entry, dict):
                questions = entry.get('questions')
                if isinstance(questions, list):
                    entry['questions'], _ = \
                        AntiSlopProcessor._normalize_str_list(
                            questions, routes['reflection'],
                            'reflection', report)
            elif isinstance(entry, str) and entry:
                reflection[pos] = AntiSlopProcessor._normalize_text(
                    entry, routes['reflection'], 'reflection', report)
        if isinstance(module.reflection, list):
            report['fields_processed']['reflection'] = \
                report['fields_processed'].get('reflection', 0) + len(
                    [e for e in reflection if isinstance(e, (dict, str))])
        # Remedial / enrichment descriptions only (linkage untouched).
        for attr, label in (('remedial', 'remedial_description'),
                            ('enrichment', 'enrichment_description')):
            container = getattr(module, attr, None)
            if isinstance(container, dict):
                description = container.get('description')
                if isinstance(description, str) and description:
                    container['description'] = \
                        AntiSlopProcessor._normalize_text(
                            description, routes[label], label, report)
                    report['fields_processed'][label] = \
                        report['fields_processed'].get(label, 0) + 1
        # Material summary only (prerequisite/misconception lists stay).
        material = module.material_characteristics
        if isinstance(material, dict):
            summary = material.get('summary')
            if isinstance(summary, str) and summary:
                material['summary'] = AntiSlopProcessor._normalize_text(
                    summary, routes['material_summary'],
                    'material_summary', report)
                report['fields_processed']['material_summary'] = \
                    report['fields_processed'].get('material_summary', 0) + 1
        # Assessment question text only (keys/options/scores untouched).
        assessments = module.assessments or {}
        for bucket, items in assessments.items():
            rows = items.get('items', []) if isinstance(items, dict) \
                else items
            for item in rows or []:
                if not isinstance(item, dict):
                    continue
                question = item.get('question')
                if isinstance(question, str) and question:
                    item['question'] = AntiSlopProcessor._normalize_text(
                        question, routes['assessment_question'],
                        'assessment_question', report)
                    report['fields_processed']['assessment_question'] = \
                        report['fields_processed'].get(
                            'assessment_question', 0) + 1
        # Remaining AI narrative dicts (outline/B.4/learner/KBC/LKPD):
        # same murid-baku + informal cleanup, protected structures
        # excluded by construction.
        AntiSlopProcessor._normalize_generated_dicts(module, report)
        return module, report

    @staticmethod
    def humanize(module: Module) -> Module:
        """Apply humanization only to whitelisted narrative fields.

        Protected fields (CP text, TP text, phase, subject, element,
        KKTP criteria, references) pass through byte-identical.
        Delegates to the skill-driven adapter; report discarded here
        (use humanize_with_report when the report is needed).
        """
        module, _report = AntiSlopProcessor.humanize_with_report(module)
        return module

    @staticmethod
    def humanize_section(section: str, field_name: str) -> str:
        """Humanize a section only if the field is whitelisted."""
        if field_name in AntiSlopProcessor.PROTECTED_FIELDS:
            return section  # Unchanged
        if field_name in AntiSlopProcessor.HUMANIZABLE_FIELDS:
            # Conservative humanization; structure and meaning preserved.
            # Istilah baku RPM = "murid" (sumber hukum memakai Murid;
            # bukan "peserta didik"/"siswa").
            out = section.replace('peserta didik', 'murid')
            out = out.replace('Peserta didik', 'Murid')
            out = re.sub(r'\bsiswa\b', 'murid', out)
            out = re.sub(r'\bSiswa\b', 'Murid', out)
            return out
        return section


class FinalValidator:
    """STAGE 9: Final validation before returning the module."""

    @staticmethod
    def validate_immutability(before: Dict, after: Dict) -> Tuple[bool, List[str]]:
        """Verify normative data hasn't changed."""
        errors = []

        protected = ['cp', 'tp', 'phase', 'element', 'subject']

        for field_name in protected:
            if before.get(field_name) != after.get(field_name):
                errors.append(f"Protected field changed: {field_name}")

        return len(errors) == 0, errors

    @staticmethod
    def _generated_texts(module: Module) -> List[Tuple[str, str]]:
        """All AI-generated narrative fields the murid/formal validator
        scans (FactualityValidator._ai_authored_texts minus glossary
        terms, which quote source vocabulary verbatim)."""
        out: List[Tuple[str, str]] = []
        try:
            texts = FactualityValidator._ai_authored_texts(module)
        except Exception:
            texts = []
        for label, text in texts:
            if label.startswith('glosarium'):
                continue
            out.append((label, text))
        return out

    @staticmethod
    def validate_murid_formal(module: Module) -> List[str]:
        """Istilah baku RPM = 'murid' across ALL generated fields.

        'peserta didik' / 'siswa' (any case) in AI-authored narrative is
        an error (MURID_TERM_INVALID); informal dangling fillers
        (dan lain-lain/dll/dsb/dst/etc) are an error
        (FORMAL_LANGUAGE_INVALID). Quoted dalil spans ("...") are
        exempt — quotations stay byte-identical. CP text, TP text, KKTP
        criteria and other protected/normative fields are never scanned
        here (they are immutable by design).
        """
        errors: List[str] = []
        quote_span = re.compile('"[^"]*"|\u201c[^\u201d]*\u201d')
        bad_term = re.compile(r'\bpeserta\s+didik\b|\bsiswa\b',
                              re.IGNORECASE)
        bad_informal = re.compile(
            r'\bdan\s+lain(?:-lain|nya| sebagainya)\b'
            r'|\b(dll|dsb|dst|etc)\b', re.IGNORECASE)
        for label, text in FinalValidator._generated_texts(module):
            if not isinstance(text, str) or not text.strip():
                continue
            unquoted = quote_span.sub(' ', text)
            m = bad_term.search(unquoted)
            if m:
                errors.append(
                    f"MURID_TERM_INVALID: {label} uses "
                    f"{m.group(0).strip()!r} — baku RPM = 'murid'")
            m2 = bad_informal.search(unquoted)
            if m2:
                errors.append(
                    f"FORMAL_LANGUAGE_INVALID: {label} uses informal "
                    f"filler {m2.group(0).strip()!r}")
        return errors

    @staticmethod
    def validate_topic_preserved(module: Module) -> List[str]:
        """Topic preserved: refined topic must share content with seed.

        topic_seed (teacher input, immutable provenance) vs topic
        (formal refinement). An empty refined topic with a non-empty
        seed, or a refined topic sharing zero content tokens with the
        seed, is TOPIC_DRIFT (fail closed). Empty seed = no topic
        claimed (no fabrication check needed).
        """
        errors: List[str] = []
        seed = (getattr(module, 'topic_seed', '') or '').strip()
        topic = (getattr(module, 'topic', '') or '').strip()
        if not seed:
            return errors
        if not topic:
            return ["TOPIC_DRIFT: refined topic empty while "
                    f"teacher seed is {seed!r}"]
        stop = {'yang', 'dan', 'dengan', 'untuk', 'dalam', 'pada',
                'dari', 'sebagai', 'adalah', 'secara', 'serta',
                'atau', 'kepada', 'tentang', 'oleh', 'ini', 'itu',
                'para', 'siswa', 'murid'}
        seed_toks = {w for w in re.findall(r'[a-z]+', seed.lower())
                     if len(w) > 3 and w not in stop}
        topic_toks = {w for w in re.findall(r'[a-z]+', topic.lower())
                      if len(w) > 3 and w not in stop}
        if seed_toks and topic_toks and not (seed_toks & topic_toks):
            errors.append(
                f"TOPIC_DRIFT: refined topic {topic!r} shares no "
                f"content with teacher seed {seed!r}")
        return errors

    @staticmethod
    def validate_completeness(module: Module) -> Tuple[bool, List[str]]:
        """Validate module completeness (all core components present)."""
        errors = []

        if not module.title:
            errors.append("Module title missing")

        if not module.learning_objectives:
            errors.append("Learning objectives (TP) missing")

        if not module.success_criteria:
            errors.append("Success criteria (KKTP) missing")

        if not module.learning_activities:
            errors.append("Learning activities missing")

        # R-42: asesmen boleh kosong seluruhnya (tidak digenerate).
        # Bila ada sebagian, hubungan dicek validator lain.

        if not module.curriculum_context:
            errors.append("Curriculum context missing")

        if not module.generation_id:
            errors.append("Generation ID missing")

        return len(errors) == 0, errors

    @staticmethod
    def validate_relationships(module: Module) -> Tuple[bool, List[str]]:
        """Validate explicit TP -> KKTP -> Activity -> Assessment links.

        Every KKTP must reference an existing TP, every activity must
        link to an existing TP, and every summative/formative assessment
        item must reference an existing TP (tp_linked) when provided.
        """
        errors = []
        tp_ids = {tp.id for tp in module.learning_objectives}
        kktp_ids = {kktp.id for kktp in module.success_criteria}

        # KKTP -> TP relationship
        for kktp in module.success_criteria:
            if kktp.tp_id not in tp_ids:
                errors.append(
                    f"{kktp.id} references non-existent TP '{kktp.tp_id}'"
                )

        # Activity -> TP relationship: mengaplikasi activities MUST link to a
        # real TP; shared-experience activities (memahami/merefleksi) may be
        # unlinked, but a wrong TP id is always an error.
        shared_experience_types = {
            'memahami', 'merefleksi',
            # legacy tags (pre-RPM stored modules)
            'pendahuluan', 'introduction', 'pembuka', 'apersepsi',
            'penutup', 'closing',
        }
        for activity in module.learning_activities:
            act_type = (activity.type or '').strip().lower()
            if not activity.tp_linked:
                if act_type in shared_experience_types:
                    continue
                errors.append(f"{activity.id} has no TP linkage")
            elif activity.tp_linked not in tp_ids:
                errors.append(
                    f"{activity.id} references non-existent TP '{activity.tp_linked}'"
                )

        # Assessment items -> TP relationship (where linkage provided)
        def check_items(items: Any, bucket: str):
            if not isinstance(items, list):
                return
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    linked = item.get('tp_linked')
                    if linked is not None and linked not in tp_ids:
                        errors.append(
                            f"{bucket}[{i}] references non-existent TP '{linked}'"
                        )
                    kk = item.get('kktp_linked')
                    if kk is not None and kk not in kktp_ids:
                        errors.append(
                            f"{bucket}[{i}] references non-existent KKTP '{kk}'"
                        )

        assessments = module.assessments or {}
        check_items(assessments.get('diagnostic'), 'diagnostic')
        check_items(assessments.get('formative'), 'formative')
        summative = assessments.get('summative')
        if isinstance(summative, dict):
            check_items(summative.get('items'), 'summative')

        return len(errors) == 0, errors


# ============================================================
# MASTER OUTLINE DETERMINISTIC BUILDERS + VALIDATOR
# ============================================================

def build_learning_phases(activities: List[ActivityEntry]) -> Dict:
    """D. Pengalaman Belajar: group flat activities into the three
    canonical experiences (memahami / mengaplikasi / merefleksi).
    Compatibility adapter: the flat per-TP list stays untouched; groups
    are derived deterministically from activity.experience (fallback:
    activity.type for entries stored before the RPM migration).
    """
    phases = {'memahami': [], 'mengaplikasi': [], 'merefleksi': []}
    legacy_map = {
        'pendahuluan': 'memahami', 'introduction': 'memahami',
        'pembuka': 'memahami', 'apersepsi': 'memahami',
        'inti': 'mengaplikasi', 'core': 'mengaplikasi',
        'penutup': 'merefleksi', 'closing': 'merefleksi',
        'refleksi': 'merefleksi', 'penilaian': 'merefleksi',
    }
    for act in activities:
        exp = (getattr(act, 'experience', '') or '').strip().lower()
        if exp not in phases:
            exp = legacy_map.get((act.type or '').strip().lower())
        if exp in phases:
            phases[exp].append(asdict(act))
        else:
            phases['mengaplikasi'].append(asdict(act))
    return phases


def build_blueprint(tp_list: List[str], assessments: Dict) -> List[Dict]:
    """C.4 Kisi-kisi: deterministic-derived from validated TP + summative
    assessment items. Only real data; never invented.

    Links are EXPLICIT only: a blueprint row lists question forms from
    summative items carrying the matching tp_linked. No positional
    inference (items[i-1]) — an unlinked TP yields an empty row that
    the MasterOutlineValidator rejects (BLUEPRINT_ERROR) instead of a
    fabricated link.
    """
    blueprint = []
    summative = (assessments or {}).get('summative') or {}
    items = summative.get('items', []) if isinstance(summative, dict) else []
    for i, tp in enumerate(tp_list, 1):
        linked = [item for item in items
                  if isinstance(item, dict) and item.get('tp_linked') == f'TP-{i}']
        blueprint.append({
            'tp_id': f'TP-{i}',
            'tp_text': tp,
            'cognitive_level': None,  # filled by pipeline after rule stage
            'question_form': [it.get('type') for it in linked if isinstance(it, dict)],
            'item_count': len(linked),
            'points': sum(int(it.get('points', 0) or 0)
                          for it in linked if isinstance(it, dict)),
        })
    return blueprint


def build_rubric(kktp_list: List[KKTPEntry],
                 descriptor_map: Optional[Dict[str, List[str]]] = None
                 ) -> Dict:
    """C.5: rubric derived from KKTP criteria + deterministic scoring
    intervals (PPA 2025 p53).

    Audit finding RUBRIC_DESCRIPTOR_WEAK: label-only levels ("4 = Sangat
    Baik") are not sufficient. ``descriptor_map`` carries the AI-generated
    observable performance descriptors per KKTP id — a list of exactly one
    descriptor per RUBRIC_LEVELS entry. When the AI contract fails to
    deliver them the level labels remain but the MasterOutlineValidator
    rejects the rubric, so a label-only rubric can never reach SUCCESS.
    """
    descriptors = descriptor_map or {}
    rows = []
    for kktp in kktp_list:
        row = {
            'kktp_id': kktp.id,
            'tp_id': kktp.tp_id,
            'criteria': kktp.criteria,
            'levels': list(RUBRIC_LEVELS),
        }
        d = descriptors.get(kktp.id)
        if isinstance(d, list) and d:
            row['descriptors'] = [str(x) for x in d]
        rows.append(row)
    return {
        'kktp_rubric': rows,
        'scoring_intervals': SCORING_INTERVALS,
    }


def build_instrument_recap(assessments: Dict) -> Dict:
    """L.3: deterministic recap of assessment instruments."""
    def count(items: Any) -> int:
        return len(items) if isinstance(items, list) else 0
    summative = (assessments or {}).get('summative') or {}
    s_items = summative.get('items', []) if isinstance(summative, dict) else []
    return {
        'diagnostic_count': count((assessments or {}).get('diagnostic')),
        'formative_count': count((assessments or {}).get('formative')),
        'summative_count': count(s_items),
        'summative_rubric': (summative.get('rubric')
                             if isinstance(summative, dict) else None),
    }


def validasi_struktur_materi(main_content: str,
                               fragmen: list) -> list:
    """Cek materi lawan fragmen buku sumber (R-43, deterministik).

    Return list error (kosong = lolos). Cek:
    1. Setiap klaim faktual (pola jumlah: "N aspek", "terdiri dari N",
       "dibagi menjadi N", "N turunan/bagian/jenis") wajib ada id
       fragmen [BUKU-...] di kalimat yang sama.
    2. Jumlah aspek yang diklaim harus muncul di teks fragmen sumber
       (angka N ada di fragmen yang dirujuk).
    Tanpa fragmen = tidak dicek (bukan jalur R-43).
    """
    import re as _re
    if not fragmen:
        return []
    teks_sumber = ' '.join((f.get('text') or '') for f in fragmen).lower()
    ids = {str(f.get('id') or '') for f in fragmen if f.get('id')}
    errors = []
    kalimat = _re.split(r'(?<=[.!?])\s+', main_content or '')
    kata_angka = {'satu': '1', 'dua': '2', 'tiga': '3', 'empat': '4',
                  'lima': '5', 'enam': '6', 'tujuh': '7'}
    pola_jumlah = _re.compile(
        r'(\d+|dua|tiga|empat|lima|satu|enam|tujuh)\s*'
        r'(aspek|turunan|bagian|jenis|macam|kategori|kelompok)',
        _re.IGNORECASE)
    pola_id = _re.compile(r'\[(BUKU-[A-Za-z0-9]+(?:-H\d+-\d+)?)\]')
    for k in kalimat:
        for m in pola_jumlah.finditer(k):
            mentah = m.group(1).lower()
            angka = kata_angka.get(mentah, mentah)
            rujuk = pola_id.findall(k)
            if not rujuk:
                errors.append(
                    f"MATERI_TANPA_RUJUKAN: klaim '{m.group(0)}' tanpa id "
                    f"fragmen sumber.")
                continue
            if not any(r in ids for r in rujuk):
                errors.append(
                    f"MATERI_RUJUKAN_ASING: id fragmen tidak dikenal.")
                continue
            if angka not in teks_sumber:
                errors.append(
                    f"MATERI_STRUKTUR_BEDA: jumlah '{m.group(0)}' tidak "
                    f"ditemukan di fragmen sumber.")
    return errors


class MasterOutlineValidator:
    """STAGE 7b: Master Outline structure + alignment validation.
    Errors use structured codes (see task spec section 20)."""

    @staticmethod
    def validate(module: Module) -> Tuple[bool, List[Dict]]:
        errors: List[Dict] = []

        def err(code: str, message: str):
            errors.append({'code': code, 'message': message,
                           'stage': 'master_outline'})

        # B.6: three learning experiences must exist and each be non-empty
        phases = module.learning_phases or {}
        for phase_name in ('memahami', 'mengaplikasi', 'merefleksi'):
            if not phases.get(phase_name):
                err('ACTIVITY_ERROR',
                    f"Pengalaman belajar '{phase_name}' kosong")

        # Mengaplikasi activities must still link to real TPs (TP -> activity)
        tp_ids = {tp.id for tp in module.learning_objectives}
        for act in phases.get('mengaplikasi', []):
            if act.get('tp_linked') not in tp_ids:
                err('TP_ALIGNMENT_ERROR',
                    f"Aktivitas mengaplikasi {act.get('id')} tidak menautkan TP valid")

        # TP -> KKTP traceability (every TP must have a KKTP)
        kktp_tp_ids = {k.tp_id for k in module.success_criteria}
        for tp in module.learning_objectives:
            if tp.id not in kktp_tp_ids:
                err('KKTP_ERROR', f"{tp.id} has no KKTP")

        # TP -> assessment traceability: hanya untuk bucket yang ada
        # (R-42: bucket tidak digenerate tidak menuntut traceability).
        assessments = module.assessments or {}
        ada_bucket = [b for b in ('diagnostic', 'formative', 'summative')
                      if assessments.get(b)]
        linked_tps = set()
        for bucket in ('diagnostic', 'formative'):
            if bucket not in ada_bucket:
                continue
            for item in assessments.get(bucket) or []:
                if isinstance(item, dict) and item.get('tp_linked'):
                    linked_tps.add(item['tp_linked'])
        if 'summative' in ada_bucket:
            summative = assessments.get('summative')
            if isinstance(summative, dict):
                for item in summative.get('items') or []:
                    if isinstance(item, dict) and item.get('tp_linked'):
                        linked_tps.add(item['tp_linked'])
        if ada_bucket:
            for tp in module.learning_objectives:
                if tp.id not in linked_tps:
                    err('ASSESSMENT_ERROR',
                        f"{tp.id} is not traceable to any assessment item")

        # C.4 blueprint coverage: bila sumatif ada, satu baris per TP
        # dengan question form. R-42: tanpa sumatif, blueprint boleh
        # kosong (tidak ada kisi-kisi yang bisa diturunkan).
        ada_sumatif = bool((module.assessments or {}).get('summative'))
        if ada_sumatif and len(module.blueprint) < len(
                module.learning_objectives):
            err('BLUEPRINT_ERROR', 'Kisi-kisi does not cover all TP')
        if ada_sumatif:
            for row in module.blueprint:
                if not row.get('question_form'):
                    err('BLUEPRINT_ERROR',
                        f"Kisi-kisi row {row.get('tp_id')} has no question form")

        # C.5 rubric <-> KKTP consistency
        rubric_rows = (module.rubric or {}).get('kktp_rubric') or []
        rubric_kktp = {r.get('kktp_id') for r in rubric_rows}
        for kktp in module.success_criteria:
            if kktp.id not in rubric_kktp:
                err('RUBRIC_ERROR',
                    f"Rubric missing for {kktp.id}")
        if not (module.rubric or {}).get('scoring_intervals'):
            err('RUBRIC_ERROR', 'Scoring intervals missing')

        # C.5 descriptors (audit finding RUBRIC_DESCRIPTOR_WEAK): every
        # declared level needs an observable, criterion-specific descriptor.
        # Labels like "4 = Sangat Baik" alone are rejected.
        for row in rubric_rows:
            rid = row.get('kktp_id')
            desc = row.get('descriptors')
            criteria_txt = ' '.join(
                c for c in (row.get('criteria') or []) if isinstance(c, str)
            )
            if not isinstance(desc, list) or not desc:
                err('RUBRIC_DESCRIPTOR_WEAK',
                    f"Rubric for {rid} has no level descriptors "
                    f"(labels only are not sufficient)")
                continue
            levels = row.get('levels') or []
            if len(levels) > 1 and len(desc) < len(levels):
                err('RUBRIC_DESCRIPTOR_WEAK',
                    f"Rubric for {rid} declares {len(levels)} levels but "
                    f"only {len(desc)} descriptors")
                continue
            # Label-only check: descriptor must carry more than the bare
            # level label / a short adjective, and say something observable.
            for lv, d in zip(levels, desc):
                if not isinstance(d, str) or len(d.strip()) < 10:
                    err('RUBRIC_DESCRIPTOR_WEAK',
                        f"Rubric for {rid}: level '{lv}' descriptor is a "
                        f"label or too short to be observable")
                    break
            # Identical descriptors: every level must differ.
            uniq = {d.strip().lower() for d in desc if isinstance(d, str)}
            if len(uniq) != len(desc):
                err('RUBRIC_DESCRIPTOR_WEAK',
                    f"Rubric for {rid}: descriptors are identical across "
                    f"levels (not a progression)")
                continue
            # Generic-unrelated check: after stripping shared pedagogical
            # vocabulary, the descriptors must carry content words tied to
            # the criterion (observable acts), not only generic adjectives.
            generic = {'baik', 'sangat', 'cukup', 'kurang', 'sekali', 'lebih',
                       'peserta', 'didik', 'siswa', 'dapat', 'belum', 'dalam',
                       'dengan', 'secara', 'menunjukkan', 'memperlihatkan'}
            desc_tokens = {
                t for d in desc
                for t in _normalize_b4_text(d).split()
                if t not in generic and len(t) > 3
            }
            if criteria_txt:
                crit_tokens = {
                    t for t in _normalize_b4_text(criteria_txt).split()
                    if len(t) > 3
                }
            else:
                crit_tokens = set()
            if desc_tokens and crit_tokens and not (desc_tokens & crit_tokens):
                err('RUBRIC_DESCRIPTOR_WEAK',
                    f"Rubric for {rid}: descriptors are generic and not "
                    f"related to the assessed criteria")

        # A.3 profile/values: the normative list is the 8 Dimensi Profil
        # Lulusan (Permendikdasmen No. 10 Tahun 2025). Empty A.3 is an
        # accidental pipeline omission because a deterministic source
        # ALWAYS exists. Non-normative values (mis. tema Panca Cinta
        # bocor sebagai "dimensi") DITOLAK - Panca Cinta bukan dimensi.
        if not module.profile_dimensions:
            err('A3_EMPTY',
                "A.3 Dimensi Profil Lulusan kosong although a "
                "deterministic normative source exists (pipeline omission)")
        invalid_dims = [
            d for d in module.profile_dimensions
            if d not in PROFILE_DIMENSIONS_8
        ]
        if invalid_dims:
            err('A3_NON_NORMATIVE_DIMENSION',
                f"A.3 contains non-normative profile dimensions "
                f"{invalid_dims}; only the 8 Dimensi Profil Lulusan "
                f"(Permendikdasmen No. 10 Tahun 2025) are allowed")

        # KBC gating (AGENTS.md §15): enabled HANYA untuk KEMENAG.
        kbc = (module.approach_principles or {}).get('kbc')
        if module.curriculum_context is not None:
            system = module.curriculum_context.education_system
            if system == 'KEMENAG':
                if not (isinstance(kbc, dict) and kbc.get('enabled')):
                    err('KBC_LAYER_ERROR',
                        "KBC layer missing for a KEMENAG (madrasah) module")
            elif isinstance(kbc, dict) and kbc.get('enabled'):
                err('KBC_LAYER_ERROR',
                    "KBC layer must not be enabled outside KEMENAG")

        # RPM section B (Identifikasi): struktur harus ada. Isi boleh
        # jujur menyatakan data belum tersedia, tapi field-nya wajib.
        if not isinstance(module.learner_readiness, dict):
            err('SCHEMA_ERROR',
                "B.1 kesiapan murid (learner_readiness) missing")
        if not isinstance(module.material_characteristics, dict):
            err('SCHEMA_ERROR',
                "B.2 karakteristik materi (material_characteristics) missing")

        # RPM section C (Desain): kerangka pembelajaran.
        if not module.pedagogical_practices:
            err('SCHEMA_ERROR',
                "C praktik pedagogis (pedagogical_practices) kosong")
        if not isinstance(module.learning_environment, dict):
            err('SCHEMA_ERROR',
                "C lingkungan pembelajaran (learning_environment) missing")

        # B.4: a concise synthesis, never a copy of longer narrative text.
        eu = module.essential_understanding or {}
        b4_has_text = any(
            isinstance(v, str) and v.strip() for v in eu.values()
        ) or (isinstance(eu.get('main_content'), str)
              and eu.get('main_content').strip())
        if not b4_has_text:
            err('SCHEMA_ERROR',
                "B.4 essential understanding is empty")

        # D: conditional content must still reference a TP
        for section, name in ((module.remedial, 'remedial'),
                              (module.enrichment, 'enrichment')):
            if section:
                refs = section.get('tp_reference')
                valid_refs = isinstance(refs, list) and all(r in tp_ids for r in refs)
                if not valid_refs:
                    err('TP_ALIGNMENT_ERROR',
                        f"{name} content does not reference valid TP")

        # E: reflection must exist for both roles
        roles = {r.get('role') for r in module.reflection}
        if 'student' not in roles:
            err('ACTIVITY_ERROR', 'Student reflection missing')
        if 'teacher' not in roles:
            err('ACTIVITY_ERROR', 'Teacher reflection missing')

        # Lampiran LKPD must link to TP and have a task
        for sheet in module.lkpd:
            if sheet.get('tp_linked') not in tp_ids:
                err('TP_ALIGNMENT_ERROR',
                    f"LKPD {sheet.get('id')} has no valid TP link")
            if not sheet.get('task'):
                err('SCHEMA_ERROR',
                    f"LKPD {sheet.get('id')} has no task")

        # A.7 approach principles must be the normative metadata
        if not module.approach_principles:
            err('CONTEXT_ERROR', 'Approach/principles metadata missing')

        return len(errors) == 0, errors


class FactualityValidator:
    """Batch 2: gerbang faktualitas + provenance output (fail closed).

    Memastikan RPM final tidak mengklaim data regulatif tanpa provenance
    valid di database kanonik:

    1. CP/provenance: id CP harus ada + aktif, teks byte-identik, dokumen
       sumber terdaftar di source_documents, halaman cocok, sistem
       pendidikan cocok, dan routing dokumen benar (9941 hanya PAI/Bahasa
       Arab madrasah; 020 hanya PABP; 046 untuk mapel umum).
    2. Klaim regulasi dalam teks AI: setiap kutipan nomor regulasi harus
       merujuk pada 9 dokumen kanonik terdaftar; sisanya ditolak
       (REGULATORY_CLAIM_UNVERIFIED) — tanpa pengecualian diam-diam.

    Tidak membuat registry baru: keanggotaan dokumen dibaca dari tabel
    source_documents yang sudah ada. Tidak melonggarkan validator lain.
    """

    # Pola kutipan regulasi yang dianggap klaim normatif.
    _AUTHORITY_PATTERN = re.compile(
        r'(Permendikdasmen|Permendikbudristek|Permendikbud|Kepka\s+BSKAP'
        r'|BSKAP|BKPDM|KMA|Kepdirjen\s+Pendis|Kepdirjen|Kepmen|PP|UU'
        r'|Permen[A-Za-z ]*|Keputusan)\s*(No\.?|Nomor)\s*(\d+[A-Za-z/]*)'
        r'[^\n.]{0,40}?(Tahun\s*(\d{4}))',
        re.IGNORECASE,
    )
    _BARE_CODE_PATTERN = re.compile(
        r'\b(\d{2,5}(?:/[A-Za-z0-9]+)*/\d{4})\b'
    )
    _BARE_NUMBER_YEAR_PATTERN = re.compile(
        r'\bNo\.?\s*(\d+[A-Za-z/]*)\s*Tahun\s*(\d{4})'
    )

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / 'db' / 'rpm_generator.db')
        self.db_path = db_path

    # -- dokumen kanonik (dibaca dari registry existing) -----------------

    def _registered_docs(self) -> List[Dict]:
        """Daftar dokumen kanonik: (doc_id, number, year, authority_key)."""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                'SELECT id, title FROM source_documents').fetchall()
        finally:
            conn.close()
        docs = []
        for doc_id, title in rows:
            number, year = self._number_year_from_title(title)
            docs.append({
                'id': doc_id,
                'number': number,
                'year': year,
                'authority': self._authority_key(title),
            })
        return docs

    @staticmethod
    def _number_year_from_title(title: str) -> Tuple[Optional[str], Optional[str]]:
        m = re.search(r'Nomor\s+(\d+).*?(\d{4})', title or '')
        if not m:
            return None, None
        return m.group(1).lstrip('0') or '0', m.group(2)

    @staticmethod
    def _authority_key(title: str) -> str:
        t = (title or '').lower()
        if 'bkpdm' in t:
            return 'bkpdm'
        if 'bskap' in t or 'kepka' in t:
            return 'bskap'
        if 'kepdirjen' in t or 'pendis' in t:
            return 'kepdirjen'
        if 'kma' in t:
            return 'kma'
        if 'permendikdasmen' in t:
            return 'permendikdasmen'
        return 'other'

    @staticmethod
    def _claim_authority_key(authority: str) -> str:
        a = (authority or '').lower()
        if 'bkpdm' in a:
            return 'bkpdm'
        if 'bskap' in a or 'kepka' in a:
            return 'bskap'
        if 'kepdirjen' in a or 'pendis' in a:
            return 'kepdirjen'
        if re.search(r'\bkma\b', a):
            return 'kma'
        if 'permendikdasmen' in a:
            return 'permendikdasmen'
        return 'other'

    def _matches_registered(self, docs: List[Dict], number: str,
                            year: str, authority: Optional[str] = None) -> bool:
        number = (number or '').lstrip('0') or '0'
        for doc in docs:
            if doc['number'] != number or doc['year'] != year:
                continue
            if authority is None:
                return True
            if self._claim_authority_key(authority) == doc['authority']:
                return True
            # Kode telanjang tanpa otoritas: nomor+tahun cocok cukup.
            if authority == '':
                return True
        return False

    # -- gerbang 1: CP/provenance ----------------------------------------

    def validate_cp(self, module: Module) -> List[str]:
        """CP output harus cocok dengan baris aktif di database.

        Catatan: CPEntry.id pipeline (`CP-<Mapel>-<Fase>`) adalah id
        agregat, BUKAN primary key learning_outcomes (yang berbentuk
        `CP-...-<halaman>-<index>`). Karena itu kecocokan dibuktikan
        lewat konten: teks + provenance harus sama persis dengan salah
        satu baris aktif untuk triple (subject, phase, element).
        """
        errors = []
        ctx = module.curriculum_context
        if ctx is None or getattr(ctx, 'cp', None) is None:
            return ['CP_PROVENANCE_INVALID: module has no curriculum CP']
        cp = ctx.cp
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                'SELECT id, subject, phase, element, text, '
                'source_document, source_document_id, source_page, '
                'education_system, status FROM learning_outcomes '
                'WHERE subject = ? AND phase = ? AND element = ? '
                'AND status = ?',
                (ctx.subject, ctx.phase, ctx.element, 'active')).fetchall()
        finally:
            conn.close()
        if not rows:
            return [f'CP_PROVENANCE_INVALID: no active curriculum row '
                    f'for {ctx.subject}/{ctx.phase}/{ctx.element}']
        matched = None
        for row in rows:
            (_rid, _subj, _phase, _elem, text, src_label, src_id,
             src_page, _edu, _status) = row
            if text != cp.text:
                continue
            if (src_label != cp.source_document_id
                    and src_id != cp.source_document_id):
                continue
            if src_page != cp.source_page:
                continue
            matched = row
            break
        if matched is None:
            return [f'CP_PROVENANCE_INVALID: module CP text/provenance '
                    f'does not match any active registered row for '
                    f'{ctx.subject}/{ctx.phase}/{ctx.element}']
        (_rid, subject, _phase, _elem, _text, _src_label, src_id,
         _src_page, edu_system, _status) = matched
        if edu_system != ctx.education_system:
            errors.append(
                f'CP_PROVENANCE_INVALID: CP belongs to '
                f'{edu_system!r}, not {ctx.education_system!r}')
        if src_id is None or not self._doc_registered(src_id):
            errors.append(
                f'CP_PROVENANCE_INVALID: CP source document '
                f'{src_id!r} is not a registered canonical document')
        # Routing dokumen: 9941 hanya madrasah; 020 hanya PABP; 046
        # untuk mapel umum (distinction Batch 2 §1).
        doc_id = src_id or ''
        if '9941' in doc_id and ctx.education_system != 'KEMENAG':
            errors.append(
                'CP_PROVENANCE_INVALID: 9941/2025 CP used outside KEMENAG')
        if '020' in doc_id and 'agama' not in (subject or '').lower():
            errors.append(
                f'CP_PROVENANCE_INVALID: BKPDM 020/2026 CP used for '
                f'non-PABP subject {subject!r}')
        if '046' in doc_id and 'agama' in (subject or '').lower():
            errors.append(
                f'CP_PROVENANCE_INVALID: BSKAP 046/2025 CP used for '
                f'religion subject {subject!r} (superseded by 020/2026)')
        return errors

    def _doc_registered(self, doc_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                'SELECT 1 FROM source_documents WHERE id = ?',
                (doc_id,)).fetchone()
        finally:
            conn.close()
        return row is not None

    # -- gerbang 2: klaim regulasi dalam teks AI --------------------------

    def validate_claims(self, module: Module) -> List[str]:
        """Setiap kutipan regulasi dalam teks AI harus merujuk dokumen
        kanonik terdaftar."""
        errors = []
        try:
            docs = self._registered_docs()
        except Exception:
            return ['REGULATORY_CLAIM_UNVERIFIED: canonical document '
                    'registry unavailable (fail closed)']
        if not docs:
            return ['REGULATORY_CLAIM_UNVERIFIED: canonical document '
                    'registry empty (fail closed)']
        for label, text in self._ai_authored_texts(module):
            for m in self._AUTHORITY_PATTERN.finditer(text):
                authority, number = m.group(1), m.group(3)
                year = m.group(5)
                if not self._matches_registered(docs, number, year, authority):
                    errors.append(
                        'REGULATORY_CLAIM_UNVERIFIED: '
                        f'{label} cites {m.group(0).strip()!r} which is not '
                        'a registered canonical document')
            for m in self._BARE_CODE_PATTERN.finditer(text):
                code = m.group(1)
                parts = code.split('/')
                number, year = parts[0], parts[-1]
                if not self._matches_registered(docs, number, year, ''):
                    errors.append(
                        'REGULATORY_CLAIM_UNVERIFIED: '
                        f'{label} cites code {code!r} which is not a '
                        'registered canonical document')
            for m in self._BARE_NUMBER_YEAR_PATTERN.finditer(text):
                # Sudah tercakup pola otoritas di atas bila ada nama
                # regulasi di depannya; cek mandiri hanya bila tidak.
                start = max(0, m.start() - 40)
                window = text[start:m.start()]
                if re.search(r'(Permen|Kepka|Kepdirjen|KMA|BKPDM|BSKAP|PP|UU|Keputusan)',
                             window, re.IGNORECASE):
                    continue
                number, year = m.group(1), m.group(2)
                if not self._matches_registered(docs, number, year, ''):
                    errors.append(
                        'REGULATORY_CLAIM_UNVERIFIED: '
                        f'{label} cites {m.group(0).strip()!r} which is not '
                        'a registered canonical document')
        return errors

    @staticmethod
    def _ai_authored_texts(module: Module) -> List[Tuple[str, str]]:
        """Hanya field yang ditulis AI (bukan metadata deterministik,
        bukan CP/provenance, bukan input guru)."""
        out: List[Tuple[str, str]] = []

        def add(label, value):
            if isinstance(value, str) and value.strip():
                out.append((label, value))

        mat = module.material_characteristics if isinstance(
            module.material_characteristics, dict) else {}
        add('material_characteristics.summary', mat.get('summary'))
        for key in ('description', 'prerequisites'):
            ic = module.initial_competence
            if isinstance(ic, dict):
                add(f'initial_competence.{key}', ic.get(key))
        eu = module.essential_understanding
        if isinstance(eu, dict):
            for key, value in eu.items():
                add(f'essential_understanding.{key}', value)
        for q in module.guiding_questions or []:
            add('guiding_question', q)
        for act in module.learning_activities or []:
            add(f'activity.{act.id}.name', act.name)
            add(f'activity.{act.id}.description', act.description)
        assessments = module.assessments if isinstance(
            module.assessments, dict) else {}
        FactualityValidator._walk_strings(
            assessments, 'assessments', out, add)
        for sheet in module.lkpd or []:
            if isinstance(sheet, dict):
                for key in ('title', 'instructions', 'task'):
                    add(f'lkpd.{sheet.get("id")}.{key}', sheet.get(key))
        for section in (module.remedial, module.enrichment):
            if isinstance(section, dict):
                add('followup.description', section.get('description'))
        for refl in module.reflection or []:
            if isinstance(refl, dict):
                for q in refl.get('questions') or []:
                    add('reflection', q)
        kbc = (module.approach_principles or {}).get('kbc') or {}
        if isinstance(kbc, dict):
            add('kbc.integration_note', kbc.get('integration_note'))
            for ins in kbc.get('insertions') or []:
                if isinstance(ins, dict):
                    add(f'kbc.{ins.get("id")}', ins.get('text'))
            for item in kbc.get('insertion_material') or []:
                add('kbc.insertion_material', item)
        for i, entry in enumerate(module.glosarium or []):
            if isinstance(entry, dict):
                add(f'glosarium[{i}].istilah', entry.get('istilah'))
                add(f'glosarium[{i}].definisi', entry.get('definisi'))
        return out

    @staticmethod
    def _walk_strings(node, label, out, add):
        if isinstance(node, str):
            add(label, node)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key in ('source', 'provenance', 'source_document_id',
                           'source_fragment_id', 'source_page', 'cp'):
                    continue
                FactualityValidator._walk_strings(
                    value, f'{label}.{key}', out, add)
        elif isinstance(node, (list, tuple)):
            for i, value in enumerate(node):
                FactualityValidator._walk_strings(
                    value, f'{label}[{i}]', out, add)

    # -- entry point -------------------------------------------------------

    def validate(self, module: Module) -> List[str]:
        """Kedua gerbang; list kosong berarti PASS (fail closed)."""
        return self.validate_cp(module) + self.validate_claims(module)


# ============================================================
# MAIN PIPELINE ORCHESTRATOR
# ============================================================

def _record_generation_log(fn):
    """Decorator: audit trail generation di sekitar generate().

    Mengumpulkan record attempt dari _ai_stage_call (self._gen_records),
    menambahkan record final dari result, menempelkannya sebagai
    result["generation_log"], dan mempersist best-effort via
    GenerationLogStore. Body generate() tidak diubah. Persistence yang
    gagal TIDAK menggagalkan generation (try/except), dan tidak pernah
    menyimpan secret (record hanya metadata + hash prompt).
    """
    @functools.wraps(fn)
    def wrapper(self, params):
        self._gen_records = []
        t0 = time.perf_counter()
        result = None
        try:
            result = fn(self, params)
            return result
        finally:
            try:
                self._finalize_generation_log(result, t0)
            except Exception:
                pass
    return wrapper


class ModuleGenerationPipeline:
    """Complete PHASE C module generation pipeline with all validation stages."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / 'db' / 'rpm_generator.db')
        self.db_path = db_path
        self.curriculum_validator = CurriculumValidator(db_path)
        self.structure_validator = StructureValidator()
        self.protection_validator = ProtectionValidator()
        self.rule_validator = RuleValidator(db_path)
        self.pedagogical_validator = PedagogicalValidator()
        self.anti_slop = AntiSlopProcessor()
        self.final_validator = FinalValidator()
        self.factuality_validator = FactualityValidator(db_path)
        self.context_validator = ContextValidator(db_path)
        # Topic is attached to the validated context after STAGE 1 (see
        # generate()); typed as a plain attribute for all prompt builders.

        # Initialize 9Router client (real API)
        config = NineRouterConfig.from_environment()
        self.ai_client = NineRouterClient(config)
        logger.info("9Router client initialized (combo=%s)", config.combo)
        # Prinsip per pertemuan dari stage activities terakhir (dipakai
        # generate()/regen untuk ditempel ke meetings; [] bila N/A).
        self._last_meeting_principles: List[Dict] = []

    @_record_generation_log
    def generate(self, params: Dict) -> Dict:
        """Execute complete module generation pipeline."""
        # Batch 8.5: copy-on-entry — pipeline menulis kunci turunan
        # (topic_seed, topic hasil refinement, regulatory flag) ke params
        # selama generate; dict milik pemanggil tidak boleh termutasi
        # (regresi konkret: global VALID_PARAMS ikut tumbuh per generate).
        params = dict(params or {})
        generation_id = str(uuid.uuid4())
        logger.info("Starting module generation: %s", generation_id)

        result: Dict[str, Any] = {
            "status": "failed",  # Success must be EARNED at the final stage
            "generation_id": generation_id,
            "timestamp": datetime.now().isoformat(),
            "module": None,
            "validation": {},
            "errors": []
        }

        # BLOCKER 1 fix: normalize the topic once at the pipeline entry.
        # The topic is authoritative user input - it is never re-inferred by
        # the AI and never lost between stages; every AI prompt and the
        # module title read it from the validated context.
        params['topic'] = str(params.get('topic') or '').strip()

        # Konsultasi regulasi (deterministik, sebelum AI): fragmen resmi
        # dokumen yang mengubah/menerangkan CP utk sistem pendidikan
        # terkait (BKPDM 020/2026 utk School, KMA 1503/2025 utk Madrasah)
        # diambil dari DB dgn provenance utuh dan disuntikkan ke prompt
        # TP + outline. Kegagalan DB adalah FATAL (fail closed): tanpa
        # konteks amandemen/pedoman, CP bisa kedaluwarsa.
        regulatory_context = self.build_regulatory_context_for_generate(params)
        if regulatory_context.get('fatal'):
            result["errors"].append(
                "Regulatory context unavailable: "
                f"{regulatory_context.get('error')}; "
                "generation stopped (fail closed)")
            result["validation"]["regulatory_context"] = {
                "passed": False,
                "errors": [regulatory_context.get('error')],
            }
            return result
        params['regulatory_context_requested'] = bool(
            regulatory_context.get('enabled'))

        # R-43: buku ajar user opsional di pipeline (wajib di endpoint
        # generate UI). Tanpa buku = materi tanpa konteks sumber;
        # dengan buku = fragmen relevan disuntik + struktur divalidasi.
        buku_id = str(params.get('buku_document_id') or '').strip()
        if not buku_id:
            params['buku_fragmen'] = []
            params['buku_judul'] = ''
            result["validation"]["buku_ajar"] = {
                "passed": True, "errors": [],
                "document_id": None, "fragmen": []}
            logger.info("  - Buku ajar: tidak dipilih (materi tanpa sumber)")
        else:
            try:
                from buku_ajar import cari_fragmen, daftar_buku as _dbuku
                _judul = ''
                for _b in _dbuku(self.db_path):
                    if _b.get('document_id') == buku_id:
                        _judul = _b.get('judul') or ''
                buku_fragmen = cari_fragmen(
                    self.db_path, buku_id, params.get('topic') or '')
                if not buku_fragmen:
                    result["errors"].append(
                        "Buku tidak memuat fragmen relevan dengan topik; "
                        "pilih buku lain atau ubah topik.")
                    result["validation"]["buku_ajar"] = {
                        "passed": False,
                        "errors": ["tidak ada fragmen relevan"]}
                    return result
            except Exception as exc:
                result["errors"].append(f"Gagal membaca buku ajar: {exc}")
                result["validation"]["buku_ajar"] = {
                    "passed": False, "errors": [str(exc)]}
                return result
            params['buku_fragmen'] = buku_fragmen
            params['buku_judul'] = _judul
            params['buku_document_id_resolved'] = buku_id
            result["validation"]["buku_ajar"] = {
                "passed": True, "errors": [],
                "document_id": buku_id,
                "fragmen": [f.get('id') for f in buku_fragmen]}
            logger.info("  ✓ Buku ajar: %d fragmen relevan", len(buku_fragmen))

        # STAGE 1: Curriculum Validation
        logger.info("STAGE 1: Curriculum Validation")
        is_valid, curriculum_context, errors = self.curriculum_validator.validate(params)
        result["validation"]["curriculum"] = {"passed": is_valid, "errors": errors}

        if not is_valid:
            result["errors"].extend(errors)
            return result

        logger.info("  ✓ Curriculum context valid (phase %s)", curriculum_context.phase)

        # Batch 8.5 §5: topic_seed (input mentah guru) direfine menjadi
        # topik RPM formal memakai CP/elemen/fase/mapel. Downstream
        # (judul, semua prompt AI) memakai hasil refinement; seed mentah
        # disimpan sebagai provenance input (fail closed bila gagal).
        topic_seed = str(params.get('topic') or '').strip()
        params['topic_seed'] = topic_seed
        if not topic_seed:
            # Tanpa input topik: lewati refinement (perilaku lama:
            # judul tanpa topik). Tidak ada karangan topik.
            logger.info("  ✓ Topic kosong: refinement dilewati")
        else:
            try:
                refined_topic = self._ai_stage_call(
                    'topic',
                    lambda feedback: self._generate_topic(
                        topic_seed, curriculum_context, feedback=feedback),
                )
            except NineRouterError as e:
                result["errors"].append(f"AI generation failed: {str(e)}")
                result["validation"]["topic"] = {
                    "passed": False, "errors": [str(e)]}
                return result
            except (ValueError, KeyError, TypeError,
                    AttributeError) as e:
                result["errors"].append(f"AI response malformed: {str(e)}")
                result["validation"]["topic"] = {
                    "passed": False, "errors": [str(e)]}
                return result
            params['topic'] = refined_topic
            curriculum_context.topic = refined_topic
            logger.info("  ✓ Topic refined")

        # Input alokasi guru (deterministik, sebelum AI): bila mode
        # pertemuan diminta, validasi di sini dengan error jelas; bila
        # tidak ada input pertemuan, gunakan mode lama (tanpa fabrikasi
        # angka). Durasi JP dari konfigurasi satuan+phase tervalidasi
        # (tanpa input bebas, tanpa fallback antar-satuan).
        meetings_spec, meetings_error = resolve_meetings_spec(
            params, curriculum_context.phase,
            curriculum_context.institution_type)
        if meetings_error:
            result["errors"].append(meetings_error)
            result["validation"]["curriculum"] = {
                "passed": False, "errors": [meetings_error]}
            return result
        if meetings_spec is not None:
            logger.info(
                "  ✓ Alokasi waktu: %d pertemuan x %d JP x %d menit = %d menit",
                meetings_spec['n_meetings'],
                meetings_spec['jp_per_meeting'],
                meetings_spec['minutes_per_jp'],
                meetings_spec['total_minutes'])

        # Batch 8.5 §7: jumlah soal asesmen (default aplikasi, divalidasi
        # sebelum AI call; AI wajib memenuhi PERSIS).
        assessment_counts, counts_error = (
            ModuleGenerationPipeline.resolve_assessment_counts(
                params.get('assessment_counts')))
        if counts_error:
            result["errors"].append(counts_error)
            result["validation"]["curriculum"] = {
                "passed": False, "errors": [counts_error]}
            return result

        # STAGE 1b: Context Validation (ContextValidator - stop BEFORE any AI call)
        # Context is intentionally pre-AI: tp_list/atp are filled only after TP
        # generation, so here we enforce the CP-completeness invariants that must
        # hold before spending AI budget.
        logger.info("STAGE 1b: Context Validation")
        ctx_ok, ctx_error = self.context_validator.validate_context_completeness(
            curriculum_context
        )
        if not ctx_ok and "Tujuan Pembelajaran tidak ada" not in ctx_error:
            # TP-related failure is expected pre-generation (TPs are generated in
            # STAGE 3); every other context failure is fatal.
            result["errors"].append(f"Context validation failed: {ctx_error}")
            result["validation"]["context"] = {
                "passed": False, "errors": [ctx_error]
            }
            return result

        # STAGE 2: Build Module Metadata
        logger.info("STAGE 2: Build Module Metadata")
        module_id = (
            f"MOD-{curriculum_context.education_system[:3]}-"
            f"{curriculum_context.phase}-{uuid.uuid4().hex[:8]}"
        )
        module = Module(
            id=module_id,
            title=self._module_title(params),
            subject=params['subject'],
            grade=params['grade'],
            phase=curriculum_context.phase,
            curriculum_version=curriculum_context.curriculum_version,
            module_identity={
                "title": f"RPP/RPM {params['subject']}",
                "subject": params['subject'],
                "class": f"{params['institution_type']} {params['grade']}",
                # Metadata identitas di bawah ini TIDAK memiliki default:
                # hanya terisi bila user mengisi input (None = tidak
                # dirender, bukan angka/teks karangan).
                "semester": params.get('semester') or None,
                "year": params.get('year') or None,
                "satuan_pendidikan": (
                    str(params.get('satuan_pendidikan') or '').strip()
                    or None),
            },
            facilities=params.get('facilities', ['Papan tulis', 'Alat tulis']),
            target_students={"grade": params['grade'], "age_range": "12-14"},
            # learning_model TIDAK memiliki default formal: model formal
            # bukan bagian master outline (yang ada praktik pedagogis
            # dari AI) sehingga nilai kosong berarti tidak diklaim.
            learning_model=params.get('learning_model') or '',
            methods=params.get('methods', ['Diskusi', 'Studi Kasus']),
            learning_objectives=[],
            success_criteria=[],
            essential_understanding={},
            guiding_questions=[],
            learning_activities=[],
            assessments={},
            curriculum_context=curriculum_context,
            generation_id=generation_id,
            generated_at=datetime.now().isoformat(),
            topic=str(params.get('topic') or '').strip(),
            # Input guru eksplisit (tanpa default): penyusun dan kesiapan
            # murid diteruskan apa adanya ke output.
            topic_seed=params.get('topic_seed', ''),
            penyusun=str(params.get('penyusun') or '').strip(),
            student_readiness=str(
                params.get('student_readiness') or '').strip(),
            learner_readiness={
                'data_status': 'not-yet-collected',
                'note': ('Data kesiapan murid belum tersedia dalam sumber '
                         'kurikulum yang terdaftar.'),
            },
            material_characteristics={},
            pedagogical_practices=params.get(
                'pedagogical_practices',
                params.get('methods', ['Diskusi', 'Studi Kasus'])),
            learning_partnerships=params.get('learning_partnerships', []),
            learning_environment=params.get('learning_environment', {}),
            digital_use=params.get('digital_use', {}),
            unit={
                'name': str(params.get('topic') or '').strip(),
                'scope_note': (
                    'Satu unit pembelajaran: kesatuan tujuan, pengalaman '
                    'belajar, dan asesmen - tidak harus satu bab buku.'),
            },
        )
        logger.info("  ✓ Module metadata created: %s", module_id)

        # STAGE 3: AI Generation (9Router - all components)
        logger.info("STAGE 3: AI Generation (9Router, combo=rpm)")
        try:
            tp_list = self._ai_stage_call(
                'tp',
                lambda feedback: self._generate_tp(
                    curriculum_context, params.get('requested_tp_count', 3),
                    regulatory_context=regulatory_context,
                    feedback=feedback,
                ),
            )
            logger.info("  ✓ Generated %d TP", len(tp_list))

            kktp_list = self._ai_stage_call(
                'kktp',
                lambda feedback: self._generate_kktp(
                    tp_list, curriculum_context, feedback=feedback),
            )
            logger.info("  ✓ Generated %d KKTP", len(kktp_list))

            materials = self._ai_stage_call(
                'materials',
                lambda feedback: self._generate_materials(
                    tp_list, curriculum_context, feedback=feedback,
                    buku_fragmen=params.get('buku_fragmen'),
                    buku_judul=params.get('buku_judul') or ''),
            )
            activities = self._ai_stage_call(
                'activities',
                lambda feedback: self._generate_activities(
                    tp_list, curriculum_context, feedback=feedback,
                    meetings_spec=meetings_spec,
                    student_readiness=module.student_readiness),
            )
            assessments = self._ai_stage_call(
                'assessments',
                lambda feedback: self._generate_assessments(
                    tp_list, kktp_list, curriculum_context,
                    counts=assessment_counts,
                    feedback=feedback,
                    student_readiness=module.student_readiness),
            )
            outline_content = self._ai_stage_call(
                'outline',
                lambda feedback: self._generate_outline_content(
                    tp_list, kktp_list, curriculum_context,
                    regulatory_context=regulatory_context,
                    feedback=feedback,
                    student_readiness=module.student_readiness,
                ),
            )
            logger.info("  ✓ Generated all AI components (incl. outline content)")
        except NineRouterError as e:
            result["errors"].append(f"AI generation failed: {str(e)}")
            result["validation"]["ai_generation"] = {
                "passed": False, "errors": [str(e)]
            }
            return result
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            result["errors"].append(f"AI response malformed: {str(e)}")
            result["validation"]["ai_generation"] = {
                "passed": False, "errors": [str(e)]
            }
            return result

        # STAGE 4: JSON Parsing & Structure Validation
        logger.info("STAGE 4: Structure Validation")
        is_valid, struct_errors = self.structure_validator.validate_tp_structure(tp_list)
        if not is_valid:
            result["errors"].extend(struct_errors)
            result["validation"]["structure"] = {
                "passed": False, "errors": struct_errors
            }
            return result

        is_valid, kktp_struct_errors = self.structure_validator.validate_kktp_structure(
            kktp_list
        )
        if not is_valid:
            result["errors"].extend(kktp_struct_errors)
            result["validation"]["structure"] = {
                "passed": False, "errors": kktp_struct_errors
            }
            return result
        result["validation"]["structure"] = {"passed": True, "errors": []}
        logger.info("  ✓ Structure validation passed")

        # STAGE 5: Curriculum Protection Validation
        logger.info("STAGE 5: Protection Validation")
        is_valid, prot_errors = self.protection_validator.validate(
            curriculum_context, module
        )
        if not is_valid:
            result["errors"].extend(prot_errors)
            result["validation"]["protection"] = {
                "passed": False, "errors": prot_errors
            }
            return result
        result["validation"]["protection"] = {"passed": True, "errors": []}
        logger.info("  ✓ Protected fields verified")

        # STAGE 6: Rule Engine Validation (TP + KKTP cognitive levels)
        logger.info("STAGE 6: Rule Engine Validation")
        rule_errors = []
        for i, tp_text in enumerate(tp_list, 1):
            is_valid, c_level, error = self.rule_validator.validate_tp_cognitive_level(
                tp_text
            )
            if not is_valid:
                rule_errors.append(f"TP-{i}: {error}")

        # BLOCKER 2 fix: TP level vs KKTP declared-level compatibility.
        # A KKTP must not measure its TP below the TP's own cognitive level
        # (uses the shared KKO order, not string equality).
        level_order = {'C1': 1, 'C2': 2, 'C3': 3, 'C4': 4, 'C5': 5, 'C6': 6}

        for kktp in kktp_list:
            criteria_text = " ".join(kktp.criteria)
            declared = getattr(kktp, 'cognitive_level', None)
            if declared in level_order:
                # The declared level is the authoritative signal (the prompt
                # derives it from the validated TP level). Text-keyword
                # extraction is only a fallback: real KKTP wording often
                # uses valid KKO verbs outside the narrow keyword list.
                if level_order[declared] < 3:  # C3 is minimum
                    rule_errors.append(
                        f"{kktp.id}: cognitive level {declared} below minimum C3"
                    )
            else:
                is_valid, c_level, error = self.rule_validator.validate_kktp_cognitive_level(
                    criteria_text
                )
                if not is_valid:
                    rule_errors.append(f"{kktp.id}: {error}")

        tp_level_by_id = {
            f'TP-{i}': self.rule_validator._extract_cognitive_level(tp)
            for i, tp in enumerate(tp_list, 1)
        }
        for kktp in kktp_list:
            tp_level = tp_level_by_id.get(kktp.tp_id)
            kktp_level = getattr(kktp, 'cognitive_level', None)
            if tp_level not in level_order or kktp_level not in level_order:
                rule_errors.append(
                    f"KKTP_ERROR: {kktp.tp_id} (level {tp_level}) vs "
                    f"{kktp.id} (level {kktp_level}) - undetermined level"
                )
                continue
            if level_order[kktp_level] < level_order[tp_level]:
                rule_errors.append(
                    f"KKTP_ERROR: {kktp.id} declares {kktp_level} but measures "
                    f"{kktp.tp_id} at {tp_level} (tp_id={kktp.tp_id}, "
                    f"tp_level={tp_level}, kktp_level={kktp_level})"
                )

        # Run the full 5-rule RuleEngine on the generation data
        # (cognitive minimum, grade-phase, provenance, subject-system)
        first_level = self.rule_validator._extract_cognitive_level(tp_list[0])
        rule_data = {
            'tp_text': tp_list[0],
            'cognitive_level': first_level,
            'grade': resolve_grade_key(
                params['institution_type'], params['grade']
            ),
            'phase': curriculum_context.phase,
            'education_system': params['education_system'],
            'institution_type': params['institution_type'],
            'subject': params['subject'],
            'source_document_id': curriculum_context.cp.source_document_id,
            'source_fragment_id': curriculum_context.cp.source_fragment_id
        }
        rules_ok, rule_results = self.rule_validator.rule_engine.validate(rule_data)
        if not rules_ok:
            for r in rule_results:
                if not r.passed:
                    rule_errors.append(f"{r.rule_id}: {r.message}")

        if rule_errors:
            result["errors"].extend(rule_errors)
            result["validation"]["rules"] = {"passed": False, "errors": rule_errors}
            return result
        result["validation"]["rules"] = {"passed": True, "errors": []}
        logger.info("  ✓ All TP and KKTP meet minimum C3 cognitive level")

        # Sync generated TPs into the curriculum context (context stays the
        # single source of truth; ContextValidator re-runs on it in STAGE 6b).
        context_tp_list = [
            CurriculumTPEntry(
                id=f"TP-{i}",
                text=tp,
                cognitive_level=self.rule_validator._extract_cognitive_level(tp),
                source_type="ai_generated"
            )
            for i, tp in enumerate(tp_list, 1)
        ]
        curriculum_context.tp_list = context_tp_list
        curriculum_context.atp = ATPEntry(
            id=curriculum_context.atp.id,
            tp_ids=[tp.id for tp in context_tp_list]
        )

        # Populate module core content (after TP validation)
        module.learning_objectives = [
            TPEntry(
                id=f"TP-{i}",
                text=tp,
                cognitive_level=self.rule_validator._extract_cognitive_level(tp),
                cp_reference=curriculum_context.cp.id,
                source_type="ai_generated"
            )
            for i, tp in enumerate(tp_list, 1)
        ]
        module.success_criteria = kktp_list
        module.learning_activities = activities
        module.assessments = assessments
        # B.4 (audit finding DUPLICATED_CONTENT_B4_L1): the AI MUST return an
        # explicit synthesis - _generate_materials already enforces the
        # contract, so there is deliberately NO fallback that copies L.1
        # main_content into B.4.
        module.essential_understanding = materials['essential_understanding']

        module.regulatory_consultation = regulatory_context
        # Deterministic metadata first (never AI-authored):
        module.initial_competence = outline_content.get('initial_competence')
        module.profile_dimensions = self._resolve_profile_dimensions(
            outline_content, curriculum_context, params
        )
        # Batch 8.5 §2: catatan relevansi hanya untuk dimensi terpilih
        # yang tervalidasi (kontrak outline sudah menjamin isinya).
        _notes_out = outline_content.get('profile_dimension_notes') or {}
        _notes_norm = {k.strip(): v for k, v in _notes_out.items()
                       if isinstance(k, str)}
        module.profile_dimension_notes = {
            d: str(_notes_norm[d]).strip()
            for d in module.profile_dimensions
            if isinstance(_notes_norm.get(d), str)
            and _notes_norm[d].strip()
        }
        module.approach_principles = build_approach_principles(
            curriculum_context.education_system
        )
        # RPM section D: pengalaman belajar (memahami/mengaplikasi/
        # merefleksi) - bukan tahap awal/inti/penutup.
        module.learning_phases = build_learning_phases(activities)
        # RPM section B (IDENTIFIKASI) + C (DESAIN): struktur + isi dari
        # AI outline content (sudah divalidasi kontraknya di
        # _generate_outline_content).
        # Kesiapan murid adalah INPUT GURU, bukan fakta karangan AI:
        # bila guru mengisi, teks guru dipakai apa adanya TANPA tambahan
        # diagnosis AI (Batch 8.5 §1); bila kosong, nyatakan jujur belum
        # tersedia TANPA bullet inferensi AI (UAT FIX: aspects AI tidak
        # pernah dirender sebagai temuan; AGENTS.md §17).
        if module.student_readiness:
            module.learner_readiness = {
                'summary': module.student_readiness,
                'data_available': True,
                'aspects': [],
                'data_status': 'available',
                'note': ('Kesiapan murid berdasarkan observasi/asesmen awal '
                         'guru.'),
            }
        else:
            module.learner_readiness = {
                'summary': '',
                'data_available': False,
                'aspects': [],
                'data_status': 'not-yet-collected',
                # Jangan mengarang hasil asesmen awal (AGENTS.md §17).
                'note': ('Data kesiapan murid belum tersedia dalam sumber '
                         'kurikulum yang terdaftar.'),
            }
        module.material_characteristics = {
            'summary': str((outline_content.get('material_characteristics')
                            or {}).get('summary') or ''),
            'prerequisites': [
                str(p) for p in
                (outline_content.get('material_characteristics') or {})
                .get('prerequisites') or []
                if isinstance(p, (str, int, float))
            ],
            'potential_misconceptions': [
                str(m) for m in
                (outline_content.get('material_characteristics') or {})
                .get('potential_misconceptions') or []
                if isinstance(m, (str, int, float))
            ],
        }
        module.pedagogical_practices = [
            str(p) for p in outline_content.get('pedagogical_practices') or []
            if isinstance(p, (str, int, float))
        ]
        module.learning_partnerships = [
            str(p) for p in outline_content.get('learning_partnerships') or []
            if isinstance(p, (str, int, float))
        ]
        module.learning_environment = dict(
            outline_content.get('learning_environment') or {})
        module.digital_use = dict(outline_content.get('digital_use') or {})
        # KBC layer: di-merge ke approach_principles.kbc dengan tema yang
        # DIPILIH AI (subset Panca Cinta yang relevan) + materi insersi.
        if curriculum_context.education_system == 'KEMENAG' \
                and isinstance(outline_content.get('kbc'), dict):
            kbc_merged = dict(outline_content['kbc'])
            # Traceability eksplisit insersi -> aktivitas (deterministik
            # via TP yang sudah tervalidasi; tanpa keyword matching).
            kbc_merged['insertions'] = resolve_kbc_insertions(
                kbc_merged,
                [asdict(a) for a in module.learning_activities],
            )
            module.approach_principles['kbc'] = kbc_merged
        # Lampiran LKPD: Batch 8.5 §8 — LKPD bukan bagian default RPM,
        # sehingga generation utama tidak lagi mengisi/menimpa daftar
        # LKPD (data legacy pada modul lama tidak dihapus di tempat lain).
        module.lkpd = []
        # C.5: rubric with per-level descriptors (audit fix).
        module.rubric = build_rubric(
            kktp_list, assessments.get('rubric_descriptors')
        )
        module.instrument_recap = build_instrument_recap(assessments)
        module.blueprint = build_blueprint(tp_list, assessments)
        # Cognitive levels in the blueprint come from validated data only
        levels_by_tp = {
            f'TP-{i}': self.rule_validator._extract_cognitive_level(tp)
            for i, tp in enumerate(tp_list, 1)
        }
        for row in module.blueprint:
            row['cognitive_level'] = levels_by_tp.get(row.get('tp_id'))
        # Alignment traceability on assessments (TP -> KKTP -> Activity ->
        # Assessment): the AI items already carry tp_linked/kktp_linked;
        # fill kktp_linked for formative items deterministically when the
        # TP has exactly one KKTP (never invented when ambiguous).
        kktp_by_tp: Dict[str, List[str]] = {}
        for kktp in kktp_list:
            kktp_by_tp.setdefault(kktp.tp_id, []).append(kktp.id)
        for item in assessments.get('formative') or []:
            if isinstance(item, dict) and not item.get('kktp_linked'):
                candidates = kktp_by_tp.get(item.get('tp_linked'), [])
                if len(candidates) == 1:
                    item['kktp_linked'] = candidates[0]
        # Remedial/enrichment: conditional, only when AI provided content
        module.remedial = outline_content.get('remedial') or None
        module.enrichment = outline_content.get('enrichment') or None
        # Reflection: normalized to {role, questions}
        module.reflection = [
            {'role': 'student',
             'questions': outline_content.get('student_reflection', [])},
            {'role': 'teacher',
             'questions': outline_content.get('teacher_reflection', [])},
        ]
        # Deterministic derivation of learning phases already done above;
        # guiding questions (B.5) come from the AI outline content.
        module.guiding_questions = (
            outline_content.get('triggering_questions')
            or module.guiding_questions
        )

        # STAGE 1b (post-AI): full context validation with generated TPs + ATP
        # in place. Any failure here stops generation.
        logger.info("STAGE 6b: Context Validation (with generated TPs)")
        ctx_ok, ctx_error = self.context_validator.validate_context_completeness(
            curriculum_context
        )
        if not ctx_ok:
            result["errors"].append(f"Context validation failed: {ctx_error}")
            result["validation"]["context"] = {
                "passed": False, "errors": [ctx_error]
            }
            return result
        result["validation"]["context"] = {"passed": True, "errors": []}

        # STAGE 7: Pedagogical Validation (FATAL)
        logger.info("STAGE 7: Pedagogical Validation")
        is_valid, ped_errors = self.pedagogical_validator.validate_activity_alignment(
            activities, len(tp_list)
        )
        if not is_valid:
            result["errors"].extend(ped_errors)
            result["validation"]["pedagogical"] = {
                "passed": False, "errors": ped_errors
            }
            return result

        is_valid, ped_errors = self.pedagogical_validator.validate_assessment_alignment(
            assessments, len(tp_list), len(kktp_list)
        )
        if not is_valid:
            result["errors"].extend(ped_errors)
            result["validation"]["pedagogical"] = {
                "passed": False, "errors": ped_errors
            }
            return result
        result["validation"]["pedagogical"] = {"passed": True, "errors": []}
        logger.info("  ✓ Pedagogical validation passed")

        # STAGE 7b: Master Outline validation (fatal; structured error codes)
        logger.info("STAGE 7b: Master Outline Validation")
        mo_valid, mo_errors = MasterOutlineValidator.validate(module)
        if not mo_valid:
            result["errors"].extend(mo_errors)
            result["validation"]["master_outline"] = {
                "passed": False, "errors": mo_errors
            }
            return result
        result["validation"]["master_outline"] = {"passed": True, "errors": []}
        logger.info("  ✓ Master Outline validation passed")

        # R-43: buku ajar tercatat lolos (struktur sudah dicek + retry
        # di _generate_materials; tanpa buku generate berhenti di awal).
        if params.get('buku_fragmen'):
            result["validation"]["materi_sumber"] = {
                "passed": True, "errors": []}

        # STAGE 8: Anti-Slop Processing (protected fields untouched)
        logger.info("STAGE 8: Anti-Slop Processing")
        before_protected = AntiSlopProcessor.snapshot_protected(module)
        # Legacy 4-field check retained for trace continuity.
        before_legacy = {
            'cp': curriculum_context.cp.text,
            'phase': module.phase,
            'subject': module.subject,
            'element': curriculum_context.element,
        }
        module, antislop_report = self.anti_slop.humanize_with_report(
            module)
        after_protected = AntiSlopProcessor.snapshot_protected(module)
        after_legacy = {
            'cp': module.curriculum_context.cp.text,
            'phase': module.phase,
            'subject': module.subject,
            'element': module.curriculum_context.element,
        }
        is_valid, immut_errors = FinalValidator.validate_immutability(
            before_legacy, after_legacy
        )
        snap_valid, snap_errors = \
            AntiSlopProcessor.validate_antislop_snapshot(
                before_protected, after_protected)
        if not (is_valid and snap_valid):
            result["errors"].extend(immut_errors + snap_errors)
            result["validation"]["anti_slop"] = {
                "passed": False, "errors": immut_errors + snap_errors
            }
            return result
        finding_counts: Dict[str, int] = {}
        for finding in antislop_report.get('findings', []):
            rule_id = finding.get('rule', 'unknown')
            finding_counts[rule_id] = finding_counts.get(rule_id, 0) + 1
        result["validation"]["anti_slop"] = {
            "passed": True,
            "errors": [],
            "skill": antislop_report.get('skill_version'),
            "skill_rules": [rule['id'] for rule in
                            AntiSlopProcessor.SKILL_RULES],
            "fields_processed": antislop_report.get(
                'fields_processed', {}),
            "rewrite_counts": antislop_report.get('rewrites', {}),
            "finding_counts": finding_counts,
        }
        logger.info("  ✓ Anti-slop processing complete (protected fields intact)")

        # D terstruktur: susun meetings deterministik dari aktivitas
        # final (pasca Anti-Slop; durasi/link tidak diubah humanize).
        # Tanpa meetings_spec (hasil lama/API langsung): meetings kosong
        # dan D memakai pengelompokan pengalaman seperti sebelumnya.
        if meetings_spec is not None:
            module.meetings = attach_meeting_principles(
                build_meetings(
                    [asdict(a) for a in module.learning_activities],
                    meetings_spec['n_meetings'],
                    meetings_spec['jp_per_meeting'],
                    meetings_spec['minutes_per_jp'],
                ),
                self._last_meeting_principles,
            )

        # STAGE 9: Final Completeness & Relationship Validation (FATAL)
        logger.info("STAGE 9: Final Validation")
        is_complete, comp_errors = self.final_validator.validate_completeness(module)
        is_related, rel_errors = self.final_validator.validate_relationships(module)
        is_protected, prot2_errors = self.protection_validator.validate(
            curriculum_context, module
        )
        # Batch 2 §1: gerbang faktualitas (CP/provenance vs database +
        # klaim regulasi vs dokumen kanonik) — FATAL bila gagal.
        fact_errors = self.factuality_validator.validate(module)
        # Istilah baku RPM + bahasa formal di semua field AI (FATAL).
        murid_errors = FinalValidator.validate_murid_formal(module)
        # Topik guru dipertahankan (refinement wording saja) — FATAL.
        topic_errors = FinalValidator.validate_topic_preserved(module)
        # Slop findings must impact validation: detect-only findings
        # above the slop ceiling fail closed with a documented
        # regeneration path (bounded stage retry), never silent pass.
        slop_errors = self._slop_gate(antislop_report)
        final_errors = (comp_errors + rel_errors + prot2_errors
                        + fact_errors + murid_errors + topic_errors
                        + slop_errors)
        if final_errors:
            result["errors"].extend(final_errors)
            result["validation"]["final"] = {"passed": False, "errors": final_errors}
            return result
        result["validation"]["final"] = {"passed": True, "errors": []}
        logger.info("  ✓ Final validation passed")

        # STAGE 10: Only now may status become success
        module.validation_results = result["validation"]
        result["module"] = module.to_dict()
        result["status"] = "success"

        logger.info("✓ Module generation complete: %s", generation_id)
        return result

    # ------------------------------------------------------------
    # AI generation helpers (REAL 9Router calls, combo=rpm)
    # ------------------------------------------------------------
    # Detect-only slop findings (report-only rules) must still impact
    # validation: a module whose narrative trips more than
    # SLOP_FINDING_MAX detect-only findings fails closed at STAGE 9
    # with SLOP_THRESHOLD_EXCEEDED. Documented regeneration path: the
    # caller retries generate() (bounded: same AI_STAGE_MAX_ATTEMPTS
    # budget per AI stage applies on the fresh run); lowering the
    # ceiling or ignoring findings to raise the success rate is
    # forbidden — fix the prompts/content instead.
    SLOP_FINDING_MAX = 5

    def _slop_gate(self, antislop_report: Optional[Dict]) -> List[str]:
        """Fail closed when detect-only slop findings exceed ceiling."""
        try:
            findings = (antislop_report or {}).get('findings') or []
        except Exception:
            findings = []
        detect_rules = {r[0] for r in ANTISLOP_SKILL_RULES
                        if len(r) > 2 and r[2] == 'detect'}
        count = sum(1 for f in findings
                    if isinstance(f, dict)
                    and f.get('rule') in detect_rules)
        if count > self.SLOP_FINDING_MAX:
            return [
                f"SLOP_THRESHOLD_EXCEEDED: {count} detect-only slop "
                f"findings exceed ceiling {self.SLOP_FINDING_MAX} "
                f"(rules: {sorted(detect_rules)}); regenerate via a "
                f"fresh generate() run (bounded "
                f"{self.AI_STAGE_MAX_ATTEMPTS} attempts/stage) after "
                f"fixing prompts/content — do not weaken validators"
            ]
        return []
    # Bounded stage-level regeneration (maksimal AI_STAGE_MAX_ATTEMPTS
    # percobaan per stage AI: 1 + 2 regenerasi). Client sudah me-retry
    # transport/format di level HTTP/JSON; helper ini menangani
    # kegagalan level respons (root-shape salah, field hilang,
    # level semantik invalid) dengan meregenerasi stage YANG SAMA
    # memakai feedback ringkas — validator TIDAK PERNAH di-bypass:
    # setiap regenerasi divalidasi ulang oleh check stage itu sendiri,
    # dan kegagalan sesudah batas diteruskan jujur (gagal, bukan sukses
    # palsu). AuthenticationError tidak di-retry (fail fast).
    AI_STAGE_MAX_ATTEMPTS = 3

    # Prompt versions eksplisit per AI stage (deterministik, tersedia
    # runtime via get_prompt_version). Setiap perubahan isi prompt WAJIB
    # menaikkan versi stage terkait agar generation lama tetap traceable
    # ke versinya. Hash prompt efektif (termasuk feedback regenerasi)
    # selalu dicatat di log sebagai bukti konten yang dikirim.
    PROMPT_VERSIONS = {
        'tp': '1.0',
        'kktp': '1.0',
        'materials': '1.0',
        'activities': '1.1',
        'assessments': '1.1',
        'outline': '1.2',
        'glosarium': '1.1',
        'topic': '1.1',
    }

    @classmethod
    def get_prompt_version(cls, stage: str) -> str:
        """Versi prompt stage AI (KeyError bila stage tak dikenal)."""
        return cls.PROMPT_VERSIONS[stage]

    @staticmethod
    def _prompt_hash(*parts: str) -> str:
        """sha256 prompt efektif yang dikirim ke model."""
        h = hashlib.sha256()
        for p in parts:
            h.update((p or '').encode('utf-8'))
            h.update(b'\x00')
        return h.hexdigest()

    def _note_prompt(self, stage: str, system_prompt: str,
                     user_prompt: str) -> None:
        """Catat versi + hash prompt efektif untuk attempt berjalan."""
        self._active_prompt = {
            'version': self.get_prompt_version(stage),
            'hash': self._prompt_hash(system_prompt, user_prompt),
        }

    def _finalize_generation_log(self, result, t0: float) -> None:
        """Bangun record final, tempel ke result, persist best-effort."""
        records = list(getattr(self, '_gen_records', None) or [])
        gen_id = None
        status = 'failed'
        if isinstance(result, dict):
            gen_id = result.get('generation_id')
            if result.get('status') == 'success':
                status = 'success'
        if gen_id:
            for r in records:
                r['generation_id'] = gen_id
            records.append({
                'generation_id': gen_id,
                'stage': 'final',
                'attempt': 1,
                'prompt_version': None,
                'prompt_hash': None,
                'model': self.ai_client.config.combo,
                'provider': '9router',
                'status': status,
                'error_category': None,
                'error': None,
                'duration_ms': round((time.perf_counter() - t0) * 1000, 1),
                'response_chars': None,
                'empty_flag': None,
                'truncated_flag': None,
                'output_tokens': None,
                'is_retry': 0,
            })
            if isinstance(result, dict):
                result['generation_log'] = records
            try:
                GenerationLogStore(self.db_path).save_records(records)
            except Exception:
                pass

    @staticmethod
    def _categorize_ai_error(error: Exception) -> str:
        """Kategori failure untuk logging observability (transport /
        format / semantic). Hanya label; keputusan retry sama-sama
        bounded untuk ketiganya."""
        s = str(error).lower()
        if ('timeout' in s or 'connection' in s or 'rate limit' in s
                or 'server error' in s or 'empty content' in s):
            return 'transport'
        if ('not valid json' in s or 'extra data' in s
                or 'unterminated' in s or 'not a json object' in s
                or 'empty' in s):
            return 'format'
        return 'semantic'

    @staticmethod
    def _recovery_feedback(category: str, stage: str = '') -> str:
        """Feedback ringkas yang ditempel ke prompt regenerasi. String
        tetap (tidak memuat output model, tidak memuat marker dispatch
        mock 'tp_list'/'criteria'/'diagnostic'/lainnya). Bagian spesifik
        stage menarget mode gagal dominan yang terukur; generik bila
        stage tidak dikenal."""
        if category == 'transport':
            why = 'respons sebelumnya GAGAL diterima (gangguan koneksi/waktu)'
            extra = ''
        elif category == 'format':
            why = ('respons sebelumnya BUKAN JSON valid / terpotong / '
                   'bentuk root salah')
            extra = (' Root HARUS satu JSON object dengan key yang diminta, '
                     'bukan array.')
        else:
            why = 'respons sebelumnya DITOLAK kerangka validasi'
            extra = ''
        if stage == 'tp':
            extra += (' Setiap TP WAJIB memuat kata kerja operasional C3+ '
                      '(menerapkan, menggunakan, menganalisis, membandingkan, '
                      'mengevaluasi, menilai, merancang, menciptakan).')
        elif stage == 'kktp':
            extra += (" Nilai 'level' HANYA boleh C3, C4, C5, atau C6.")
        elif stage == 'assessments':
            extra += (' Setiap multiple_choice WAJIB membawa options '
                      '(minimal 4, label A, B, C, D) dan correct_answer '
                      'berupa label opsi yang cocok.')
        return (
            f"\n\nCATATAN PERBAIKAN: {why}. Ulangi SELURUH respons sesuai "
            f"skema yang diminta — HANYA JSON valid, object di level "
            f"teratas, tanpa markdown, tanpa teks tambahan.{extra}"
        )

    def _ai_stage_call(self, stage: str, call):
        """Jalankan satu stage AI dengan regenerasi terbatas.

        ``call`` menerima satu argumen ``feedback`` (str/None) yang
        ditempel ke prompt saat regenerasi. Setiap hasil (termasuk
        hasil regenerasi) melewati validasi stage yang sama; gagal
        sesudah batas -> error terakhir di-raise (jujur gagal).
        """
        last_error = None
        feedback = None
        for attempt in range(1, self.AI_STAGE_MAX_ATTEMPTS + 1):
            self._active_prompt = None
            t0 = time.perf_counter()
            try:
                outcome = call(feedback)
            except AuthenticationError:
                raise
            except (ValueError, ValidationError, NineRouterError,
                    AttributeError, TypeError, KeyError) as e:
                # Keluarga yang sama dengan yang generate() klasifikasikan
                # sebagai "AI response malformed": shape respons salah
                # (mis. top-level list -> .get AttributeError) adalah
                # failure respons, bukan bug program.
                last_error = e
                category = self._categorize_ai_error(e)
                self._log_attempt(
                    stage, attempt, 'failed', category, str(e)[:300],
                    round((time.perf_counter() - t0) * 1000, 1))
                if attempt < self.AI_STAGE_MAX_ATTEMPTS:
                    logger.warning(
                        "AI stage '%s' attempt %d/%d failed [%s]: %.200s; "
                        "regenerating stage",
                        stage, attempt, self.AI_STAGE_MAX_ATTEMPTS,
                        category, e,
                    )
                    feedback = self._recovery_feedback(category, stage)
                    continue
                logger.warning(
                    "AI stage '%s' attempt %d/%d failed [%s]: %.200s; "
                    "giving up",
                    stage, attempt, self.AI_STAGE_MAX_ATTEMPTS,
                    category, e,
                )
                raise
            else:
                self._log_attempt(
                    stage, attempt, 'success', None, None,
                    round((time.perf_counter() - t0) * 1000, 1))
                return outcome
        raise last_error

    def _log_attempt(self, stage: str, attempt: int, status: str,
                     error_category, error, duration_ms: float) -> None:
        """Satu record audit attempt (metadata saja, tanpa secret).

        Batch 2: metadata respons model (chars/empty/truncated) dibaca
        dari client dan dicatat apa adanya — tanpa raw prompt/response.
        """
        active = getattr(self, '_active_prompt', None) or {}
        try:
            model = self.ai_client.config.combo
        except Exception:
            model = None
        try:
            raw_meta = getattr(self.ai_client, 'last_response_meta', None)
            meta = raw_meta if isinstance(raw_meta, dict) else {}
        except Exception:
            meta = {}

        def _meta_int(key):
            value = meta.get(key)
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            return None
        records = getattr(self, '_gen_records', None)
        if records is None:
            return
        # generation_id di-backfill saat finalisasi (dibuat di body
        # generate); decorator menjamin konsistensi satu generation.
        records.append({
            'generation_id': None,
            'stage': stage,
            'attempt': attempt,
            'prompt_version': active.get('version'),
            'prompt_hash': active.get('hash'),
            'model': model,
            'provider': '9router',
            'status': status,
            'error_category': error_category,
            'error': error,
            'duration_ms': duration_ms,
            'response_chars': _meta_int('response_chars'),
            'empty_flag': _meta_int('empty'),
            'truncated_flag': _meta_int('truncated'),
            'output_tokens': _meta_int('output_tokens'),
            'is_retry': 1 if attempt > 1 else 0,
        })

    @staticmethod
    def _module_title(params: Dict) -> str:
        """A.1 title: topic is authoritative user input; 'None' must never
        leak into the title (audit blocker 1). Produk = RPP/RPM."""
        topic = str(params.get('topic') or '').strip()
        subject = params.get('subject', '')
        return (f"RPP/RPM {subject}: {topic}" if topic
                else f"RPP/RPM {subject}")

    # Stopwords untuk drift-guard topik (Batch 8.5 §5): kata fungsi yang
    # tidak membuktikan kesamaan substansi bila dibagi seed/refined.
    _TOPIC_STOPWORDS = frozenset({
        'yang', 'dan', 'dengan', 'untuk', 'dalam', 'pada', 'dari',
        'sebagai', 'adalah', 'secara', 'serta', 'atau', 'kepada',
        'tentang', 'oleh', 'ini', 'itu', 'para', 'siswa', 'murid',
    })

    @classmethod
    def _topic_content_tokens(cls, text: str) -> set:
        return {w for w in re.findall(r'[a-z]+', (text or '').lower())
                if len(w) > 3 and w not in cls._TOPIC_STOPWORDS}

    def _generate_topic(self, topic_seed: str,
                        context: CurriculumContext,
                        feedback: str = None) -> str:
        """Refine topic mentah guru menjadi topik RPM formal (Batch 8.5 §5).

        topic_seed (input guru) selalu dipertahankan sebagai provenance
        (module.topic_seed, immutable). Refinement HANYA memperbaiki
        wording formal di mana prompt menandai eksplisit (kapitalisasi,
        ejaan, tanda baca, imbuhan) — substansi, cakupan, dan istilah
        kunci milik guru tidak boleh ditambah/dikurangi/diubah.
        Kontrak: non-kosong, <= 150 karakter, berbagi >= 1 token konten
        dengan seed (drift guard, fail-closed via retry bounded).
        """
        seed = (topic_seed or '').strip()
        if not seed:
            raise ValueError("Topic seed kosong")
        cp_text = context.cp.text if context.cp is not None else ''
        system_prompt = (
            "Anda adalah ahli kurikulum. Formulasikan ulang topik "
            "pembelajaran menjadi judul topik RPM yang formal dan akademik. "
            "Respond dengan JSON ONLY, tanpa markdown: SATU object JSON "
            "(bukan array di level teratas)."
        )
        user_prompt = (
            f"Topik dari guru (TOPIK INI MILIK GURU — pertahankan "
            f"substansi, cakupan, dan istilah kuncinya; jangan tambah "
            f"subtopik baru, jangan mengarang isi):\n{seed}\n\n"
            f"Konteks: Subject {context.subject}, Element "
            f"{context.element}, Fase {context.phase}.\n"
            f"CP terkait: {cp_text}\n\n"
            f'Respond dengan JSON:\n{{"topik_rpm": "..."}}\n\n'
            f"WAJIB: perbaiki HANYA wording formal yang eksplisit "
            f"(kapitalisasi, ejaan, tanda baca, imbuhan); "
            f"substansi sama dengan input, "
            f"formulasikan ulang dengan kata-katamu sendiri (JANGAN "
            f"mengulang input guru secara verbatim), "
            f"maksimal 150 karakter."
        )
        if feedback:
            user_prompt += feedback

        self._note_prompt('topic', system_prompt, user_prompt)
        response = self.ai_client.generate_json(
            prompt=user_prompt, system_instruction=system_prompt
        )
        if not isinstance(response, dict):
            raise ValueError("Topic response is not a JSON object")
        refined = response.get('topik_rpm')
        if not isinstance(refined, str) or not refined.strip():
            raise ValueError("Topic response missing 'topik_rpm'")
        refined = refined.strip()
        if len(refined) > 150:
            raise ValueError(
                f"Refined topic too long ({len(refined)} chars, max 150)")
        if not (self._topic_content_tokens(seed)
                & self._topic_content_tokens(refined)):
            raise ValueError(
                "Refined topic drifts from teacher input "
                f"(seed={seed!r})")
        # UAT FIX: topik mentah tidak boleh di-echo verbatim — refinement
        # wajib memformulasi ulang (perbandingan ternormalisasi).
        norm = lambda s: re.sub(r'\s+', ' ', (s or '').strip().lower())
        if norm(refined) == norm(seed):
            raise ValueError(
                "Refined topic echoes teacher input verbatim "
                f"(seed={seed!r})")
        return refined

    def _generate_tp(self, context: CurriculumContext, count: int,
                     regulatory_context: Optional[Dict] = None,
                     feedback: str = None) -> List[str]:
        """Generate TP via 9Router."""
        system_prompt = (
            "Anda adalah ahli pendidikan Islam yang berpengalaman. "
            "Tugas Anda menghasilkan Tujuan Pembelajaran (TP) dengan tingkat "
            "kognitif minimum C3 (Menerapkan). "
            "HARUS menggunakan kata kerja operasional C3-C6: melaksanakan, "
            "mengimplementasikan, menggunakan, menentukan, mendemonstrasikan, "
            "menghitung, melakukan, membuktikan, mendiferensiasikan, "
            "mendiagnosis, menelaah, mendeteksi, mengaitkan, memecahkan, "
            "mengecek, mengkritik, memvalidasi, menilai, mengevaluasi, "
            "membangun, merencanakan, memproduksi, merancang, menciptakan, "
            "mendesain, menerapkan, menganalisis. "
            "Respond HANYA dengan JSON tanpa markdown."
        )

        user_prompt = (
            f"Hasilkan {count} TP untuk CP berikut:\n\n"
            f"CP: {context.cp.text}\n"
            f"Subject: {context.subject}\n"
            f"Phase: {context.phase}\n"
            f"Element: {context.element}\n"
            f"Topic/Materi: {context.topic}\n\n"
            f"TP harus spesifik terhadap Topic/Materi di atas.\n\n"
            f"Konsultasikan konteks regulasi terlampir (bila ada): CP yang "
            f"diamandemen/pedoman terbaru mengikat.\n"
            f'Respond dengan JSON: {{"tp_list": ["TP1", "TP2", ...]}}'
        )
        user_prompt += format_regulatory_context_for_prompt(regulatory_context)

        if feedback:
            user_prompt += feedback
        self._note_prompt('tp', system_prompt, user_prompt)
        response = self.ai_client.generate_json(
            prompt=user_prompt, system_instruction=system_prompt
        )
        self._assert_no_protected_override(response)
        tp_list = response.get("tp_list", [])
        # Real routers sometimes echo the list labels back into the text
        # ("TP1: ...", "2. ...") — mock responses never do, so normalize
        # here to keep stored TP text clean and single-sourced.
        tp_list = [re.sub(r'^\s*(?:TP\s*\d+|\d+)[\.\):]\s*', '', str(t)) for t in tp_list]
        tp_list = [t for t in tp_list if t.strip()]
        for i, tp_text in enumerate(tp_list, 1):
            # Fail fast dengan RULE YANG SAMA seperti STAGE 6: TP tanpa
            # level terukur (UNKNOWN) atau di bawah C3 tidak akan pernah
            # lolos validasi rules — menolak di sini memicu regenerasi
            # stage TP (level tepat) alih-alih mati KeyError di KKTP
            # atau gagal di STAGE 6 sesudah semua AI call. Bukan
            # pelonggaran: STAGE 6 tetap berjalan independen.
            is_valid, _, error = (
                self.rule_validator.validate_tp_cognitive_level(tp_text))
            if not is_valid:
                raise ValueError(f"TP-{i}: {error}")
        return tp_list

    def _generate_kktp(
        self, tp_list: List[str], context: CurriculumContext,
        feedback: str = None,
    ) -> List[KKTPEntry]:
        """Generate KKTP aligned to each TP via 9Router."""
        kktp_list = []

        for i, tp_text in enumerate(tp_list, 1):
            # The TP's cognitive level is DERIVED from validated KKO data,
            # not invented: we tell the AI the floor explicitly and still
            # validate its declared level afterwards (blocker 2).
            tp_level = self.rule_validator._extract_cognitive_level(tp_text)
            system_prompt = (
                ANTI_SLOP_GENERATION_RULES + " "
                "Anda ahli asesmen pembelajaran. Hasilkan Kriteria Ketercapaian TP "
                "(KKTP) yang setara level kognitif TP-nya. Respond JSON ONLY."
            )

            user_prompt = (
                f"Untuk TP: {tp_text}\n"
                f"Subject: {context.subject}\n"
                f"Level kognitif TP ini: {tp_level}. Deklarasikan 'level' "
                f"KKTP minimal {tp_level} (jangan lebih rendah).\n\n"
                f'Respond: {{"criteria": ["criteria 1", "criteria 2"], '
                f'"level": "{tp_level}"}}\n\n'
                f"Aturan 'level': tulis PERSIS salah satu dari C3, C4, C5, "
                f"C6 — tidak boleh C1, C2, atau teks lain, dan tidak boleh "
                f"lebih rendah dari {tp_level}."
            )
            if feedback:
                user_prompt += feedback

            self._note_prompt('kktp', system_prompt, user_prompt)
            response = self.ai_client.generate_json(
                prompt=user_prompt, system_instruction=system_prompt
            )
            self._assert_no_protected_override(response)

            # NO default-bypass: a missing/invalid declared level is fatal.
            kktp_level = response.get("level")
            if kktp_level not in ('C3', 'C4', 'C5', 'C6'):
                raise ValueError(
                    f"KKTP for TP-{i}: missing or invalid cognitive level "
                    f"(got {kktp_level!r}, need C3-C6)"
                )
            # Reject a KKTP that declares a level below the TP's own level
            # early (cheap fail before spending more AI calls).
            _order = {'C1': 1, 'C2': 2, 'C3': 3, 'C4': 4, 'C5': 5, 'C6': 6}
            tp_level = self.rule_validator._extract_cognitive_level(tp_text)
            if _order[kktp_level] < _order[tp_level]:
                raise ValueError(
                    f"KKTP for TP-{i} declares {kktp_level} but TP-{i} is "
                    f"{tp_level}: KKTP must not measure below its TP"
                )
            kktp_criteria = response.get("criteria")
            if not isinstance(kktp_criteria, list) or not kktp_criteria:
                raise ValueError(f"KKTP for TP-{i}: empty criteria")

            kktp_list.append(KKTPEntry(
                id=f"KKTP-{i}",
                tp_id=f"TP-{i}",
                criteria=kktp_criteria,
                cognitive_level=kktp_level,
                source_type="ai_generated"
            ))

        return kktp_list

    def _assert_no_protected_override(self, response: Any) -> None:
        """Reject AI responses that attempt to define protected fields."""
        if not isinstance(response, dict):
            return
        is_allowed, errors = self.protection_validator.validate_ai_output(
            None, response
        )
        if not is_allowed:
            raise NineRouterError(
                "AI output attempted to override protected fields: "
                + "; ".join(errors)
            )

    def build_regulatory_context_for_generate(
        self, params: Dict
    ) -> Dict:
        """Konteks regulasi untuk satu permintaan generate (helper publik;
        dipakai ulang app.py / test)."""
        return build_regulatory_context(
            education_system=params.get('education_system') or '',
            subject=params.get('subject') or '',
            phase=str(params.get('phase') or ''),
            db_path=self.db_path,
        )

    def _generate_glosarium(
        self, tp_list: List[str], context: CurriculumContext,
        materi_summary: str = None, feedback: str = None,
    ) -> List[Dict]:
        """Generate glosarium istilah materi via 9Router (regen target).

        Hanya dipanggil dari partial regeneration — generate() awal tidak
        membuat glosarium (kosong = belum dibuat, bukan karangan).
        Kontrak: {"glosarium": [{"istilah": ..., "definisi": ...}]},
        1..15 entri, string non-kosong, tanpa duplikat (fail-closed).
        """
        system_prompt = (
            "Anda adalah ahli pendidikan. Susun glosarium istilah kunci "
            "materi pembelajaran. Respond dengan JSON ONLY, tanpa markdown: "
            "SATU object JSON (bukan array di level teratas)."
        )
        tp_text = "\n".join([f"- {tp}" for tp in tp_list])
        user_prompt = (
            f"Susun glosarium untuk:\n"
            f"Subject: {context.subject}\n"
            f"Element: {context.element}\n"
            f"Topic: {context.topic}\n"
            f"Fase: {context.phase}\n\n"
            f"Tujuan Pembelajaran:\n{tp_text}\n\n"
        )
        if (materi_summary or '').strip():
            user_prompt += (
                f"Ringkasan materi:\n{materi_summary.strip()}\n\n")
        user_prompt += (
            f"Respond dengan JSON:\n"
            f'{{"glosarium": [{{"istilah": "...", '
            f'"definisi": "..."}}]}}\n\n'
            f"WAJIB: istilah adalah kata/frasa kunci yang benar-benar "
            f"muncul dalam materi di atas; definisi operasional singkat "
            f"(1-2 kalimat) sesuai fase; pilih 5 sampai 10 istilah paling "
            f"kunci (maksimal 15); tanpa duplikat; tanpa markdown."
        )
        if feedback:
            user_prompt += feedback

        self._note_prompt('glosarium', system_prompt, user_prompt)
        response = self.ai_client.generate_json(
            prompt=user_prompt, system_instruction=system_prompt
        )
        return self._validate_glosarium_contract(response)

    @staticmethod
    def _validate_glosarium_contract(response: Any) -> List[Dict]:
        """Kontrak output glosarium (fatal bila dilanggar)."""
        if not isinstance(response, dict):
            raise ValueError("Glosarium response is not a JSON object")
        items = response.get('glosarium')
        if not isinstance(items, list) or not items:
            raise ValueError("Glosarium response missing 'glosarium' list")
        if len(items) > 15:
            raise ValueError(
                f"Glosarium has {len(items)} entries (max 15)")
        seen = set()
        cleaned = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"Glosarium entry {i} is not an object")
            istilah = item.get('istilah')
            definisi = item.get('definisi')
            if not isinstance(istilah, str) or not istilah.strip():
                raise ValueError(
                    f"Glosarium entry {i} has empty 'istilah'")
            if not isinstance(definisi, str) or not definisi.strip():
                raise ValueError(
                    f"Glosarium entry {i} has empty 'definisi'")
            key = istilah.strip().lower()
            if key in seen:
                raise ValueError(
                    f"Glosarium has duplicate istilah {istilah!r}")
            seen.add(key)
            cleaned.append({'istilah': istilah.strip(),
                            'definisi': definisi.strip()})
        return cleaned

    def _generate_materials(
        self, tp_list: List[str], context: CurriculumContext,
        feedback: str = None, buku_fragmen: list = None,
        buku_judul: str = '',
    ) -> Dict:
        """Generate learning materials via 9Router.

        B.4 (essential_understanding) is a REQUIRED AI output: a concise
        synthesis of the transferable understanding, NOT a copy of the
        material. The old fallback (main_content duplicated as B.4) is gone;
        a missing or duplicating B.4 is rejected in STAGE 7b.
        R-43: materi WAJIB mengikuti hierarki fragmen buku ajar user
        dan merujuk id fragmen tiap klaim faktual.
        """
        system_prompt = (
            "Anda adalah ahli kurikulum dan pedagogi. Hasilkan materi pembelajaran "
            "yang bermakna. Respond dengan JSON ONLY, tanpa markdown: SATU "
            "object JSON (bukan array di level teratas)."
        )

        tp_text = "\n".join([f"- {tp}" for tp in tp_list])
        user_prompt = (
            f"Hasilkan materi pembelajaran untuk:\n"
            f"Subject: {context.subject}\n"
            f"Element: {context.element}\n"
            f"Topic: {context.topic}\n"
            f"Fase: {context.phase}\n\n"
            f"Tujuan Pembelajaran:\n{tp_text}\n\n"
            f"Materi harus fokus pada Topic di atas.\n\n" +
            format_buku_ajar_for_prompt(buku_fragmen, buku_judul) +
            f"\nRespond dengan JSON:\n"
            f'{{"introduction": "...", "main_content": "...", '
            f'"key_concepts": ["Konsep 1"], '
            f'"essential_understanding": {{"core_insight": "...", '
            f'"relationship": "...", "application": "...", "value": "..."}}}}\n\n'
            f"WAJIB: essential_understanding adalah SINTESIS ringkas "
            f"(total 3-5 kalimat) dari pemahaman utama yang tetap bermakna "
            f"setelah pembelajaran selesai - BUKAN salinan atau ringkasan "
            f"per-bagian dari main_content. Isi: core_insight (wawasan "
            f"konseptual inti), relationship (hubungan/sebab-akibat), "
            f"application (penerapan dalam kehidupan nyata murid), "
            f"value (makna/nilai bagi karakter)."
        )
        if feedback:
            user_prompt += feedback

        self._note_prompt('materials', system_prompt, user_prompt)
        try:
            response = self.ai_client.generate_json(
                prompt=user_prompt, system_instruction=system_prompt,
                # Batch 7 §10 (temuan audit teknis): jawaban materi valid
                # routinely 6-8 ribu karakter (~2500+ token) sehingga
                # budget default 2000 memotong object. Budget 4000 saja;
                # output terpotong tetap ditolak, retry tetap maks 3,
                # validasi tidak dilonggarkan.
                max_tokens=4000,
            )
        except Exception as exc:
            # Batch 2: respons terpotong dideteksi deterministik dari
            # metadata respons (tanpa raw) dan dilaporkan eksplisit —
            # kategori tetap 'format' sehingga recovery bounded yang
            # sudah ada (feedback + maks 3 attempt) yang menangani,
            # tanpa retry tambahan dan tanpa pelonggaran validasi.
            try:
                meta = getattr(self.ai_client, 'last_response_meta',
                               None) or {}
            except Exception:
                meta = {}
            if isinstance(meta, dict) and meta.get('truncated'):
                raise ValueError(
                    "Materials response is truncated (not valid JSON): "
                    f"respons terpotong pada {meta.get('response_chars')} "
                    "karakter; regenerasi stage yang sama diminta"
                ) from exc
            raise
        if not isinstance(response, dict) or not response:
            raise ValueError("Materials response is empty or not a JSON object")
        eu = response.get('essential_understanding')
        if not isinstance(eu, dict):
            raise ValueError(
                "AI materials response missing required section "
                "'essential_understanding' (B.4 synthesis)"
            )
        for key in ('core_insight', 'relationship', 'application', 'value'):
            if not isinstance(eu.get(key), str) or not eu.get(key, '').strip():
                raise ValueError(
                    f"essential_understanding.{key} is missing or empty"
                )
        # R-43: struktur materi lawan fragmen buku (ValueError = retry
        # bounded via _ai_stage_call, maks 3 attempt).
        if buku_fragmen:
            mat_errors = validasi_struktur_materi(
                str(response.get('main_content') or ''), buku_fragmen)
            if mat_errors:
                raise ValueError(
                    "Materi tidak sesuai sumber buku: " + mat_errors[0])
        return response

    def _generate_activities(
        self, tp_list: List[str], context: CurriculumContext,
        feedback: str = None, meetings_spec: Optional[Dict] = None,
        student_readiness: str = None,
    ) -> List[ActivityEntry]:
        """Generate pengalaman belajar via 9Router menjangkau tiga
        pengalaman Pembelajaran Mendalam (Memahami / Mengaplikasi /
        Merefleksi).

        AGENTS.md §13: tiga prinsip (berkesadaran/bermakna/menggembirakan)
        adalah PRINSIP yang menyertai pembelajaran, bukan tiga tahap
        kegiatan yang wajib berurutan.
        Bila meetings_spec diberikan (mode pertemuan): setiap aktivitas
        wajib membawa tahap (Pembuka/Inti/Penutup), nomor pertemuan,
        durasi menit, dan TP valid; budget waktu divalidasi deterministik.
        Tahap independen dari pengalaman (tidak ada mapping kaku).
        """
        """Generate pengalaman belajar via 9Router menjangkau tiga
        pengalaman Pembelajaran Mendalam (Memahami / Mengaplikasi /
        Merefleksi).

        AGENTS.md §13: tiga prinsip (berkesadaran/bermakna/menggembirakan)
        adalah PRINSIP yang menyertai pembelajaran, bukan tiga tahap
        kegiatan yang wajib berurutan - jadi tidak ada pemaksaan format
        awal-inti-penutup di sini.
        """
        system_prompt = (
            ANTI_SLOP_GENERATION_RULES + " "
            "Anda desainer pembelajaran berpengalaman. Rancang aktivitas "
            "pembelajaran interaktif untuk setiap TP. Gunakan bahasa "
            "Indonesia formal dokumen RPM: sebut peserta sebagai \"murid\" "
            "(bukan \"peserta didik\"/\"siswa\"); dilarang frasa tak-tuntas "
            "seperti \"dan lain-lain\"/\"dll\"/\"dsb\"/\"dst\"/\"etc\" — "
            "rinci materinya atau akhiri kalimatnya. "
            "Respond JSON ONLY: "
            "SATU object JSON dengan key activities (bukan array di level "
            "teratas)."
        )

        tp_text = "\n".join([f"{i}. {tp}" for i, tp in enumerate(tp_list, 1)])
        user_prompt = (
            f"Rancang pengalaman belajar untuk Subject: {context.subject}, "
            f"Fase: {context.phase}, Topic: {context.topic}.\n\n"
            f"Tujuan Pembelajaran:\n{tp_text}\n\n"
            f"Rancang aktivitas yang mencakup TIGA pengalaman belajar "
            f"Pembelajaran Mendalam:\n"
            f"- minimal 1 aktivitas pengalaman 'memahami'\n"
            f"- minimal {len(tp_list)} aktivitas pengalaman 'mengaplikasi' "
            f"(aktivitas mengaplikasi ke-i menautkan TP-i)\n"
            f"- minimal 1 aktivitas pengalaman 'merefleksi'\n\n"
        )
        if meetings_spec is not None:
            n = meetings_spec['n_meetings']
            mpm = meetings_spec['minutes_per_meeting']
            user_prompt += (
                f"STRUKTUR PERTEMUAN (wajib dipatuhi): RPM ini terdiri dari "
                f"{n} pertemuan; setiap pertemuan "
                f"{meetings_spec['jp_per_meeting']} JP x "
                f"{meetings_spec['minutes_per_jp']} menit = {mpm} menit. "
                f"Bagi SEMUA aktivitas ke pertemuan 1..{n}. Setiap aktivitas "
                f"WAJIB mencantumkan: 'meeting' (bilangan bulat 1..{n}), "
                f"'stage' (tepat salah satu: Pembuka, Inti, Penutup), "
                f"'duration' (menit, bilangan bulat positif), 'experience' "
                f"(memahami/mengaplikasi/merefleksi), dan 'tp_linked' "
                f"(tepat satu TP valid TP-1..TP-{len(tp_list)}). Jumlah "
                f"durasi per pertemuan HARUS tepat {mpm} menit dan total "
                f"semua pertemuan HARUS tepat "
                f"{meetings_spec['total_minutes']} menit. Sebar TP secara "
                f"pedagogis antarpertemuan; setiap TP minimal satu aktivitas. "
                f"Tahap (Pembuka/Inti/Penutup) independen dari pengalaman "
                f"belajar: aktivitas Inti boleh berpengalaman Memahami, "
                f"aktivitas Pembuka boleh berpengalaman Mengaplikasi, dst. "
                f"Prinsip berkesadaran/bermakna/menggembirakan menyertai "
                f"aktivitas, bukan menjadi tahap.\n\n"
                f"PRINSIP PER PERTEMUAN (wajib): untuk SETIAP pertemuan "
                f"1..{n}, tulis bagaimana aktivitas-aktivitas pertemuan "
                f"ITU mewujudkan ketiga prinsip — BUKAN penjelasan umum, "
                f"BUKAN mapping pengalaman-ke-prinsip (dilarang keras: "
                f"Memahami=Berkesadaran, Mengaplikasi=Bermakna, "
                f"Merefleksi=Menggembirakan). Porsi boleh berbeda antar "
                f"prinsip; deskripsi antarpertemuan harus berbeda karena "
                f"aktivitasnya berbeda.\n\n"
            )
        else:
            user_prompt += (
                f"JANGAN memformat sebagai kegiatan awal-inti-penutup; "
                f"prinsip berkesadaran/bermakna/menggembirakan menyertai "
                f"aktivitas, bukan menjadi tahap.\n\n"
            )
        user_prompt += (
            f"Respond dengan JSON:\n"
            f'{{"activities": [{{"name": "...", "description": "...", '
            f'"duration": 45, "experience": "memahami|mengaplikasi|merefleksi", '
            f'"tp_linked": "TP-1"'
        )
        if meetings_spec is not None:
            user_prompt += (
                f', "stage": "Pembuka|Inti|Penutup", "meeting": 1'
                f'}}], "meeting_principles": [{{"meeting": 1, '
                f'"berkesadaran": "...", "bermakna": "...", '
                f'"menggembirakan": "..."}}]}}'
            )
        else:
            user_prompt += ']}}'
        # Batch 11: readiness sebagai konteks pedagogis (bukan target).
        user_prompt += _readiness_stage_block(student_readiness)
        if feedback:
            user_prompt += feedback

        self._note_prompt('activities', system_prompt, user_prompt)
        response = self.ai_client.generate_json(
            prompt=user_prompt, system_instruction=system_prompt
        )
        raw_activities = response.get("activities", [])
        if not isinstance(raw_activities, list):
            raise ValueError("AI activities response is not a list")

        valid_experiences = {"memahami", "mengaplikasi", "merefleksi"}
        counts = {"memahami": 0, "mengaplikasi": 0, "merefleksi": 0}
        activities: List[ActivityEntry] = []
        for i, raw in enumerate(raw_activities, 1):
            if not isinstance(raw, dict):
                raise ValueError(f"Activity[{i - 1}] is not a JSON object")
            # NO template fallbacks: name/description/duration/experience must
            # come from the AI response; anything missing is a failure.
            name = str(raw.get("name", "")).strip()
            description = str(raw.get("description", "")).strip()
            duration = raw.get("duration")
            experience = str(raw.get("experience", "")).strip().lower()
            if not name:
                raise ValueError(f"Activity {i}: missing 'name' from AI")
            if not description:
                raise ValueError(f"Activity {i}: missing 'description' from AI")
            if not isinstance(duration, int) or duration <= 0:
                raise ValueError(
                    f"Activity {i}: invalid duration (got {duration!r})"
                )
            if experience not in valid_experiences:
                raise ValueError(
                    f"Activity {i}: invalid experience {experience!r} "
                    f"(must be one of {sorted(valid_experiences)})"
                )
            # TP linkage: normalize AI references. An applying activity must
            # link EXACTLY ONE TP (assigned sequentially when omitted);
            # shared-experience activities may reference one or many TPs, but
            # the schema stores a single primary link, so multi-TP shared
            # activities are treated as unlinked (allowed for shared
            # experiences). Anything unparseable is fatal.
            raw_tp = str(raw.get("tp_linked", "")).strip()
            tp_refs = [p.strip() for p in raw_tp.replace(";", ",").split(",")
                       if p.strip()]
            for ref in tp_refs:
                if not (ref.startswith("TP-") and ref[3:].isdigit()):
                    raise ValueError(
                        f"Activity {i}: invalid TP reference {ref!r}"
                    )
            counts[experience] += 1
            if experience == "mengaplikasi":
                if len(tp_refs) > 1:
                    raise ValueError(
                        f"Activity {i} (mengaplikasi) must link exactly one TP, "
                        f"got {tp_refs}"
                    )
                tp_linked = tp_refs[0] if tp_refs else f"TP-{counts['mengaplikasi']}"
            else:
                tp_linked = tp_refs[0] if len(tp_refs) == 1 else ""
            stage = ""
            meeting = 0
            if meetings_spec is not None:
                # Mode pertemuan: tahap + nomor pertemuan + TP wajib valid
                # (tidak ada auto-assign; semua diverifikasi budget).
                raw_stage = str(raw.get("stage", "")).strip()
                stage = raw_stage[:1].upper() + raw_stage[1:].lower() \
                    if raw_stage else ""
                if stage not in MEETING_STAGES:
                    raise ValueError(
                        f"Activity {i}: tahap {raw.get('stage')!r} invalid "
                        f"(harus salah satu dari "
                        f"{', '.join(MEETING_STAGES)})")
                raw_meeting = raw.get("meeting")
                if not isinstance(raw_meeting, int) \
                        or isinstance(raw_meeting, bool):
                    raise ValueError(
                        f"Activity {i}: pertemuan {raw_meeting!r} invalid "
                        f"(bilangan bulat 1.."
                        f"{meetings_spec['n_meetings']})")
                meeting = raw_meeting
                if len(tp_refs) != 1:
                    raise ValueError(
                        f"Activity {i}: mode pertemuan mewajibkan tepat satu "
                        f"TP valid (dapat {tp_refs})")
                tp_linked = tp_refs[0]
            activities.append(ActivityEntry(
                id=f"ACT-{i}",
                name=name,
                description=description,
                duration=duration,
                tp_linked=tp_linked,
                type=experience,  # pengalaman belajar (memahami/mengaplikasi/merefleksi)
                experience=experience,
                stage=stage,
                meeting=meeting,
            ))

        if counts["memahami"] < 1:
            raise ValueError("AI returned no 'memahami' experience activity")
        if counts["mengaplikasi"] < len(tp_list):
            raise ValueError(
                f"AI returned {counts['mengaplikasi']} mengaplikasi activities for "
                f"{len(tp_list)} TP"
            )
        if counts["merefleksi"] < 1:
            raise ValueError("AI returned no 'merefleksi' experience activity")
        if meetings_spec is not None:
            tp_ids = {f"TP-{i}" for i in range(1, len(tp_list) + 1)}
            budget_errors = validate_time_budget(
                [asdict(a) for a in activities],
                meetings_spec['n_meetings'],
                meetings_spec['minutes_per_meeting'],
                tp_ids,
            )
            if budget_errors:
                raise ValueError(
                    "Alokasi waktu invalid: " + "; ".join(budget_errors))
            self._last_meeting_principles = self._validate_meeting_principles(
                response.get('meeting_principles'),
                meetings_spec['n_meetings'],
            )
        else:
            self._last_meeting_principles = []
        return activities

    @staticmethod
    def _validate_meeting_principles(raw: Any,
                                     n_meetings: int) -> List[Dict]:
        """Validasi prinsip per pertemuan (Batch 8.5 §6, fail closed).

        Satu entri per pertemuan 1..n; tiap prinsip non-kosong (>=20
        chars), ketiganya berbeda dalam satu pertemuan, dan tidak ada
        dua pertemuan dengan teks gabungan identik (anti-generik).
        """
        if not isinstance(raw, list):
            raise ValueError(
                "AI response missing 'meeting_principles' list")
        by_meeting: Dict[int, Dict] = {}
        for entry in raw:
            if not isinstance(entry, dict):
                raise ValueError(
                    "meeting_principles entry is not an object")
            meeting = entry.get('meeting')
            if not isinstance(meeting, int) or isinstance(meeting, bool) \
                    or not (1 <= meeting <= n_meetings):
                raise ValueError(
                    f"meeting_principles entry has invalid meeting "
                    f"{meeting!r} (harus 1..{n_meetings})")
            if meeting in by_meeting:
                raise ValueError(
                    f"meeting_principles duplikat untuk pertemuan {meeting}")
            texts = {}
            for key in ('berkesadaran', 'bermakna', 'menggembirakan'):
                value = entry.get(key)
                if not isinstance(value, str) or len(value.strip()) < 20:
                    raise ValueError(
                        f"meeting_principles pertemuan {meeting}: '{key}' "
                        f"kosong atau terlalu pendek (min 20 karakter)")
                texts[key] = value.strip()
            lowered = {v.lower() for v in texts.values()}
            if len(lowered) != 3:
                raise ValueError(
                    f"meeting_principles pertemuan {meeting}: ketiga prinsip "
                    f"harus dideskripsikan berbeda")
            by_meeting[meeting] = texts
        if sorted(by_meeting) != list(range(1, n_meetings + 1)):
            raise ValueError(
                "meeting_principles harus mencakup pertemuan "
                f"1..{n_meetings}")
        combined = [
            ' | '.join(by_meeting[m][k] for k in
                       ('berkesadaran', 'bermakna', 'menggembirakan')).lower()
            for m in sorted(by_meeting)
        ]
        if len(set(combined)) != len(combined):
            raise ValueError(
                "meeting_principles identik antarpertemuan "
                "(deskripsi harus kontekstual per pertemuan)")
        return [{'meeting': m, **by_meeting[m]} for m in sorted(by_meeting)]

    # Jumlah soal asesmen default aplikasi (Batch 8.5 §7): setting
    # aplikasi, BUKAN klaim regulatif. Guru dapat mengubah via input
    # (1..ASSESSMENT_COUNT_MAX, divalidasi server).
    DEFAULT_ASSESSMENT_COUNTS = {
        'diagnostic': 10, 'formative': 10, 'summative': 5,
    }
    ASSESSMENT_COUNT_MAX = 30

    @classmethod
    def resolve_assessment_counts(cls, raw) -> Tuple[Dict, Optional[str]]:
        """Normalisasi jumlah soal: default bila absen; error bila invalid.

        Return (counts, error). Tanpa fallback diam-diam: None/absen ->
        default; non-int / < 0 / > MAX -> error jelas. R-42: 0 = bucket
        tidak digenerate (asesmen opsional per jenis); minimal satu
        bucket > 0 bila dict diberikan eksplisit.
        """
        counts = dict(cls.DEFAULT_ASSESSMENT_COUNTS)
        if raw is None:
            return counts, None
        if not isinstance(raw, dict):
            return counts, (
                "Input jumlah asesmen invalid: harus object "
                "{diagnostic, formative, summative}.")
        for key in ('diagnostic', 'formative', 'summative'):
            value = raw.get(key)
            if value is None or (isinstance(value, str)
                                 and not value.strip()):
                continue
            try:
                number = int(str(value).strip())
            except (TypeError, ValueError, AttributeError):
                return counts, (
                    f"Input jumlah asesmen invalid: '{key}' wajib bilangan "
                    f"bulat 0..{cls.ASSESSMENT_COUNT_MAX} (0 = tidak "
                    f"digenerate).")
            if isinstance(value, bool) or not (
                    0 <= number <= cls.ASSESSMENT_COUNT_MAX):
                return counts, (
                    f"Input jumlah asesmen invalid: '{key}' wajib bilangan "
                    f"bulat 0..{cls.ASSESSMENT_COUNT_MAX} (0 = tidak "
                    f"digenerate).")
            counts[key] = number
        if not any(counts[k] > 0
                   for k in ('diagnostic', 'formative', 'summative')):
            return counts, (
                "Input jumlah asesmen invalid: minimal satu jenis asesmen "
                "berjumlah >= 1.")
        return counts, None

    def _generate_assessments(
        self, tp_list: List[str], kktp_list: List[KKTPEntry],
        context: CurriculumContext, counts: Optional[Dict] = None,
        feedback: str = None, student_readiness: str = None,
    ) -> Dict:
        """Generate assessments via 9Router (diagnostic, formative, summative).

        Jumlah soal per bucket mengikuti counts (default aplikasi);
        kontrak memvalidasi jumlah PERSIS (fail/recovery, bukan
        pengurangan diam-diam). R-42: bucket 0 dilewati (tidak
        diminta ke AI, tidak divalidasi jumlah); rubric_descriptors
        tetap wajib untuk setiap KKTP.
        """
        counts = dict(counts) if isinstance(counts, dict) else dict(
            self.DEFAULT_ASSESSMENT_COUNTS)
        for key in ('diagnostic', 'formative', 'summative'):
            if key not in counts:
                counts[key] = self.DEFAULT_ASSESSMENT_COUNTS[key]
        aktif = [k for k in ('diagnostic', 'formative', 'summative')
                 if counts.get(k, 0) > 0]
        if not aktif:
            raise ValueError(
                "Tidak ada bucket asesmen diminta (semua counts 0)")
        system_prompt = (
            ANTI_SLOP_GENERATION_RULES + " "
            "Anda ahli asesmen pembelajaran. Rancang instrumen asesmen yang valid "
            "dan reliable. Respond JSON ONLY: SATU object JSON dengan key "
            "diagnostic, formative, summative, dan rubric_descriptors "
            "(bukan array/list di level teratas)."
        )

        tp_text = "\n".join([f"- {tp}" for tp in tp_list])
        kktp_text = "\n".join(
            [f"- {kktp.id} (untuk {kktp.tp_id})" for kktp in kktp_list]
        )
        levels_text = " / ".join(
            f"'{lv}'" for lv in RUBRIC_LEVELS
        )
        kktp_criteria_text = "\n".join(
            [f"- {kktp.id}: {'; '.join(kktp.criteria)}" for kktp in kktp_list]
        )
        user_prompt = (
            f"Rancang assessment untuk Subject: {context.subject}, "
            f"Topic: {context.topic}.\n\n"
            f"TP:\n{tp_text}\n\nKKTP:\n{kktp_text}\n\n"
            f"Kriteria KKTP (dasar rubrik):\n{kktp_criteria_text}\n\n"
            f"Respond dengan JSON:\n"
            f'{{"diagnostic": [{{"question": "...", "type": "multiple_choice", '
            f'"options": [{{"label": "A", "text": "..."}}, '
            f'{{"label": "B", "text": "..."}}, '
            f'{{"label": "C", "text": "..."}}, '
            f'{{"label": "D", "text": "..."}}], '
            f'"correct_answer": "B"}}], '
            f'"formative": [{{"question": "...", "type": "short_answer", '
            f'"tp_linked": "TP-1"}}], '
            f'"summative": {{"items": [{{"question": "...", "type": "essay", '
            f'"tp_linked": "TP-1", "kktp_linked": "KKTP-1", "points": 100}}], '
            f'"rubric": "..."}}, '
            f'"rubric_descriptors": {{"KKTP-1": [{{"level": "Kurang", '
            f'"descriptor": "..."}}, ...]}}}}\n\n'
            f"HANYA buat bucket ini (bucket lain JANGAN disertakan): "
            f"{', '.join(aktif)}. "
            f"JUMLAH SOAL WAJIB (jangan dikurangi, jangan dilebihkan): "
            + ", ".join(
                f"{b} PERSIS {counts[b]} soal" for b in aktif) + ". "
            f"SETIAP item WAJIB mencantumkan tp_linked ke TP yang diukur "
            f"(contoh: \"tp_linked\": \"TP-1\"); item tanpa tp_linked DITOLAK. "
            f"WAJIB: untuk SETIAP KKTP di atas sediakan rubric_descriptors "
            f"berisi PERSIS satu entri per level {levels_text}. "
            f"KONTRAK PILIHAN GANDA (fail-closed): setiap item "
            f"ber-type multiple_choice WAJIB memiliki options (minimal 4, "
            f"berlabel A, B, C, D, ...) dan correct_answer yang cocok "
            f"salah satu label opsi; tanpa itu respons DITOLAK. "
            f"Setiap descriptor harus perilaku yang DAPAT DIAMATI dan "
            f"SPESIFIK terhadap kriteria KKTP tersebut (bukan sekadar label "
            f"seperti 'sangat baik', bukan deskriptor generik yang sama untuk "
            f"semua kriteria). Urutkan dari level terendah ke tertinggi. "
            f"Jawab key rubric_descriptors plus bucket aktif "
            f"dalam SATU object JSON — jangan hanya "
            f"menjawab diagnostic saja, dan jangan kembalikan array."
        )
        # Batch 11: readiness sebagai konteks pedagogis (bukan target).
        user_prompt += _readiness_stage_block(student_readiness)
        if feedback:
            user_prompt += feedback

        self._note_prompt('assessments', system_prompt, user_prompt)
        response = self.ai_client.generate_json(
            prompt=user_prompt, system_instruction=system_prompt,
            # Skema asesmen besar (diagnostic+formative+summative+rubrik
            # per KKTP per level): budget token kecil memotong respons di
            # tengah object sehingga JSON tidak utuh. Budget, bukan
            # pelonggaran validasi — respons tetap harus object lengkap.
            max_tokens=6000,
        )

        if not isinstance(response, dict):
            raise ValueError("Assessment response is not a JSON object")

        assessments: Dict[str, Any] = {}
        for bucket in ('diagnostic', 'formative'):
            if bucket not in aktif:
                continue
            items = response.get(bucket)
            if not isinstance(items, list) or not items:
                raise ValueError(f"AI returned empty '{bucket}' assessment")
            if len(items) != counts[bucket]:
                raise ValueError(
                    f"AI returned {len(items)} '{bucket}' items, "
                    f"requested {counts[bucket]}")
            assessments[bucket] = items

        if 'summative' in aktif:
            summative = response.get("summative")
            if not isinstance(summative, dict) or not summative.get('items'):
                raise ValueError("AI returned empty 'summative' assessment")
            if len(summative['items']) != counts['summative']:
                raise ValueError(
                    f"AI returned {len(summative['items'])} 'summative' items, "
                    f"requested {counts['summative']}")
            assessments["summative"] = summative

        # Batch 4: kontrak Pilihan Ganda — setiap multiple_choice di
        # semua bucket wajib question + >=4 opsi berlabel + jawaban
        # benar yang cocok; selain itu ValueError -> recovery stage
        # yang sudah ada (bounded), lalu fail-closed jujur.
        for bucket in ('diagnostic', 'formative'):
            if bucket not in aktif:
                continue
            normalized_items = []
            for i, item in enumerate(assessments.get(bucket) or []):
                normalized_items.append(normalize_mc_item(
                    item, f"{bucket}[{i}]"))
            assessments[bucket] = normalized_items
        if 'summative' in aktif:
            summ_items = (assessments.get('summative') or {}).get('items', [])
            assessments['summative']['items'] = [
                normalize_mc_item(item, f"summative[{i}]")
                for i, item in enumerate(summ_items)]

        # C.5 rubric descriptors (RUBRIC_DESCRIPTOR_WEAK fix): normalize the
        # AI map into {kktp_id: [descriptor, ...]} ordered by RUBRIC_LEVELS.
        # Missing/short entries are tolerated here — the MasterOutlineValidator
        # later rejects any rubric row without a full descriptor set, so a
        # label-only rubric can never reach SUCCESS.
        raw_descriptors = response.get('rubric_descriptors')
        if not isinstance(raw_descriptors, dict):
            raw_descriptors = {}
        descriptor_map: Dict[str, List[str]] = {}
        for kktp in kktp_list:
            entries = raw_descriptors.get(kktp.id)
            if not isinstance(entries, list) or not entries:
                continue
            normalized: List[str] = []
            if all(isinstance(e, dict) and e.get('descriptor') for e in entries):
                by_level = {
                    str(e.get('level', '')).strip().lower():
                        str(e['descriptor']).strip()
                    for e in entries
                }
                for lv in RUBRIC_LEVELS:
                    d = by_level.get(lv.lower())
                    if d:
                        normalized.append(d)
            elif all(isinstance(e, str) for e in entries):
                # Positional form: lowest..highest level.
                normalized = [str(e).strip() for e in entries]
            if len(normalized) == len(RUBRIC_LEVELS):
                descriptor_map[kktp.id] = normalized
        if descriptor_map:
            assessments['rubric_descriptors'] = descriptor_map

        return assessments

    def _generate_outline_content(
        self, tp_list: List[str], kktp_list: List[KKTPEntry],
        context: CurriculumContext,
        regulatory_context: Optional[Dict] = None,
        feedback: str = None,
        student_readiness: str = None,
    ) -> Dict:
        """Generate the remaining RPM outline AI content via 9Router:
        triggering questions, reflections, initial competence, identifikasi
        (B), desain (C), conditional remedial/enrichment,
        KBC layer selection. Missing required sections are FATAL
        (AI_OUTPUT error). LKPD tidak diminta (Batch 8.5 §8)."""
        is_kemenag = context.education_system == 'KEMENAG'
        kbc_layer = build_kbc_layer(context.education_system)
        system_prompt = (
            ANTI_SLOP_GENERATION_RULES + " "
            "Anda ahli perencanaan pembelajaran (Pembelajaran Mendalam). "
            "Hasilkan konten outline RPM dalam JSON. DILARANG mengarang "
            "referensi atau mengubah CP/fase/mata pelajaran. "
            "Respond JSON ONLY tanpa markdown: SATU object JSON dengan "
            "key sesuai struktur yang diminta (bukan array di level teratas)."
        )
        tp_text = "\n".join([f"- {tp}" for tp in tp_list])
        kktp_text = "\n".join(
            [f"- {k.id} (untuk {k.tp_id}): {'; '.join(k.criteria)}"
             for k in kktp_list]
        )
        user_prompt = (
            f"Subject: {context.subject}\nElement: {context.element}\n"
            f"Fase: {context.phase}\nTopic: {context.topic}\n\n"
            f"Tujuan Pembelajaran:\n{tp_text}\n\nKKTP:\n{kktp_text}\n\n"
            f"Hasilkan JSON dengan struktur persis:\n"
            f'{{"triggering_questions": ["..."], '
            f'"initial_competence": {{"description": "...", '
            f'"prerequisites": ["..."]}}, '
            # B IDENTIFIKASI (AGENTS.md §17): kesiapan murid jujur,
            # karakteristik materi, dan pilihan dimensi profil lulusan.
            f'"learner_readiness": {{"summary": "...", '
            f'"data_available": false, "aspects": ["..."]}}, '
            f'"material_characteristics": {{"summary": "...", '
            f'"prerequisites": ["..."], "potential_misconceptions": ["..."]}}, '
            f'"profile_dimensions": ["nilai yang relevan"]'
            # Batch 8.5 §2: setiap dimensi terpilih wajib disertai alasan
            # relevansi yang spesifik terhadap topik (bukan sekadar nama).
            f', "profile_dimension_notes": {{"<nama dimensi persis>": '
            f'"alasan relevansi terhadap topik dan penerapannya dalam '
            f'aktivitas"}}'
            # C DESAIN (AGENTS.md §16): kerangka pembelajaran.
            f', "pedagogical_practices": ["strategi/model/metode yang '
            f'realistis"], '
            f'"learning_partnerships": ["pihak yang terlibat bila relevan '
            f'(boleh kosong)"], '
            f'"learning_environment": {{"physical": "...", '
            f'"virtual": "... atau null", "note": "..."}}, '
            f'"digital_use": {{"summary": "...", "tools": ["..."], '
            f'"note": "realistis terhadap konteks; boleh menyatakan tidak '
            f'diperlukan"}}, '
            f'"student_reflection": ["pertanyaan refleksi murid"], '
            f'"teacher_reflection": ["pertanyaan refleksi guru"], '
            # Batch 8.5 §8: LKPD BUKAN bagian default RPM — jangan
            # diminta, jangan digenerate otomatis.
            f'"remedial": {{"description": "...", "tp_reference": ["TP-1"]}} '
            f'atau null, '
            f'"enrichment": {{"description": "...", "tp_reference": ["TP-1"]}} '
            f'atau null'
        )
        # KBC layer (madrasah saja): AI MEMILIH tema yang relevan dari
        # Panca Cinta - TIDAK semua tema dipaksakan - dan mengusulkan
        # materi insersi. CP TIDAK diubah menjadi "CP berbasis cinta".
        if is_kemenag:
            themes_text = "\n".join(f"- {t}" for t in kbc_layer['themes'])
            user_prompt += (
                f"\n\nINTEGRASI KBC (Kurikulum Berbasis Cinta - layer "
                f"tambahan madrasah, sumber: {KBC_SOURCE_DOCUMENT}):\n"
                f"{themes_text}\n\n"
                f'"kbc": {{"themes": ["HANYA tema yang RELEVAN dengan CP, '
                f'tujuan, materi, dan konteks - pilih dari daftar di atas, '
                f'boleh satu atau lebih; jangan memaksa semua tema"], '
                f'"insertion_material": [{{"text": "materi insersi konkret '
                f'yang menghubungkan tema dengan pembelajaran", '
                f'"tema": "salah satu tema terpilih di atas (wajib diisi '
                f'dengan nama tema yang persis sama)", '
                f'"tp_terkait": ["TP-1", "TP-2"]}} atau string biasa], '
                f'"integration_note": "tulis PENERAPAN KONKRET di kelas '
                f'(kegiatan, momen, cara) - JANGAN menulis penjelasan '
                f'arsitektur seperti \'layer tambahan\', \'lapisan '
                f'tambahan\', atau \'bukan pengganti\'"}}. '
                f"KBC adalah layer TAMBAHAN di atas 8 Dimensi Profil "
                f"Lulusan, BUKAN penggantinya; CP tetap utuh."
            )
        else:
            user_prompt += (
                "\n\nSistem ini bukan madrasah: JANGAN menambahkan tema "
                "KBC/Panca Cinta apa pun."
            )
        # Konsultasi regulasi: fragmen BKPDM 020/2026 (School) atau KMA
        # 1503/2025 (Madrasah) masuk ke prompt — amandemen/pedoman CP
        # diikuti, bukan diabaikan (AGENTS.md §3/§7).
        user_prompt += format_regulatory_context_for_prompt(regulatory_context)
        if (student_readiness or '').strip():
            # Fakta observasi guru (bukan karangan AI): AI boleh
            # menggunakannya untuk merancang scaffolding/asesmen, bukan
            # untuk mengubah target TP.
            user_prompt += (
                "\n\nKesiapan murid menurut observasi guru "
                "(fakta, bukan asumsi): "
                f"{student_readiness.strip()}")
        # Batch 8.5 §1: kesiapan adalah input guru. AI DILARANG membuat
        # diagnosis baru, menambah fakta kemampuan murid, menginfer dari
        # CP/topik, atau mengarang hasil asesmen — baik di summary
        # maupun aspects learner_readiness.
        user_prompt += (
            "\n\nAturan kesiapan murid: JANGAN membuat diagnosis baru, "
            "JANGAN menambah fakta tentang kemampuan murid, JANGAN "
            "menginfer kemampuan dari CP/topik, JANGAN mengarang hasil "
            "asesmen yang tidak diberikan.")
        # closing the JSON template
        user_prompt += '}'
        if feedback:
            user_prompt += feedback

        self._note_prompt('outline', system_prompt, user_prompt)
        response = self.ai_client.generate_json(
            prompt=user_prompt, system_instruction=system_prompt,
            # Outline adalah respons terbesar (belasan section + LKPD +
            # KBC): budget kecil memotong object. Budget saja; validasi
            # kelengkapan section tetap fatal bila kurang.
            max_tokens=8000,
        )
        self._assert_no_protected_override(response)

        if not isinstance(response, dict):
            raise ValueError("Outline content response is not a JSON object")

        # Required sections (fatal if missing/malformed - no silent defaults)
        # NOTE: profile_dimensions may be an EMPTY list — AI silence is a
        # legitimate signal and _resolve_profile_dimensions() returns []
        # honestly (fail closed via A3_EMPTY, never auto full-8).
        for key, kind in (
            ('triggering_questions', list),
            ('student_reflection', list),
            ('teacher_reflection', list),
            ('pedagogical_practices', list),
        ):
            if not isinstance(response.get(key), kind) or not response.get(key):
                raise ValueError(
                    f"AI outline content missing required section '{key}'"
                )
        if not isinstance(response.get('profile_dimensions'), list):
            raise ValueError(
                "AI outline content missing required section 'profile_dimensions'"
            )
        # Batch 8.5 §2: setiap dimensi normatif yang dipilih wajib punya
        # deskripsi relevansi (spesifik, bukan sekadar nama). Fail closed.
        dim_notes = response.get('profile_dimension_notes')
        if not isinstance(dim_notes, dict):
            raise ValueError(
                "AI outline content missing required section "
                "'profile_dimension_notes'"
            )
        for dim in response['profile_dimensions']:
            if not isinstance(dim, str):
                raise ValueError(
                    "AI outline content has non-string profile dimension")
            if dim.strip() not in allowed_profile_values('KEMENAG'):
                continue  # non-normatif dibuang _resolve (bukan di sini)
            note = dim_notes.get(dim)
            if note is None:
                # Kunci ternormalisasi (UAT FIX whitespace).
                note = dim_notes.get(dim.strip())
            if not isinstance(note, str) or len(note.strip()) < 20:
                raise ValueError(
                    f"AI outline content missing relevance note "
                    f"for dimension {dim.strip()!r} (min 20 chars)")
            if note.strip().lower() == dim.strip().lower():
                raise ValueError(
                    f"AI relevance note for {dim!r} only repeats the name")
        for key in ('initial_competence', 'learner_readiness',
                    'material_characteristics', 'learning_environment',
                    'digital_use'):
            if not isinstance(response.get(key), dict):
                raise ValueError(
                    f"AI outline content missing required section '{key}'"
                )
        # Batch 8.5 §8: LKPD tidak digenerate/diabaikan bila AI
        # mengembalikannya (data lama tetap utuh di tempat lain).

        # KBC contract: untuk KEMENAG AI harus memilih tema DARI daftar
        # normatif (subset, bukan pengganti dimensi); untuk KEMENDIKDASMEN
        # KBC tidak boleh muncul.
        if is_kemenag:
            kbc = response.get('kbc')
            if not isinstance(kbc, dict) or not isinstance(kbc.get('themes'), list) \
                    or not kbc.get('themes'):
                raise ValueError(
                    "AI outline content missing 'kbc.themes' for a KEMENAG "
                    "(madrasah) module - pilih minimal satu tema yang relevan")
            bad = [t for t in kbc['themes'] if t not in KBC_THEMES]
            if bad:
                raise ValueError(
                    f"AI selected non-normative KBC themes: {bad}; "
                    f"allowed: {KBC_THEMES}")
            # Bahasa meta/arsitektur generator tidak boleh bocor ke teks
            # guru (temuan audit Batch 7: "layer tambahan" di
            # integration_note). Fail closed via retry bounded yang sama.
            meta_hits = [
                txt for txt in (
                    [kbc.get('integration_note')]
                    + [(x.get('text') if isinstance(x, dict) else x)
                       for x in (kbc.get('insertion_material') or [])])
                if isinstance(txt, str) and _contains_kbc_meta_language(txt)
            ]
            if meta_hits:
                raise ValueError(
                    "KBC_META_LANGUAGE: integration note / materi insersi "
                    "memuat penjelasan arsitektur generator "
                    f"({meta_hits[0][:80]!r}...); tulis penerapan konkret "
                    "di kelas")
            response['kbc'] = {
                'enabled': True,
                'themes': list(kbc['themes']),
                'insertion_material': [
                    _normalize_kbc_insertion(x, list(kbc['themes']))
                    for x in (kbc.get('insertion_material') or [])
                    if isinstance(x, (dict, str, int, float))
                ],
                'integration_note': str(kbc.get('integration_note') or ''),
                'source': KBC_SOURCE_DOCUMENT,
            }
        else:
            response.pop('kbc', None)

        return response

    def _resolve_profile_dimensions(
        self, outline_content: Dict, context: CurriculumContext, params: Dict
    ) -> List[str]:
        """A.3: DETERMINISTIC dari 8 Dimensi Profil Lulusan (Permendikdasmen
        No. 10 Tahun 2025) - never AI invented, dan BUKAN tema KBC.

        The normative list itself IS the authoritative source. AI suggestions
        can only narrow the selection to what the topic plausibly touches:
        intersections with the normative list are kept, non-normative
        suggestions are dropped. Bila AI tidak memberi yang usable, hasilnya
        KOSONG secara jujur (bukan klaim seluruh 8 relevan) dan validator
        A3_EMPTY menutup generation (fail closed) - tidak ada fallback
        otomatis ke daftar penuh.
        """
        allowed = allowed_profile_values(context.education_system)
        suggestions = outline_content.get('profile_dimensions') or []
        if not isinstance(suggestions, list):
            suggestions = []
        # UAT FIX: normalisasi whitespace agar lookup catatan tidak
        # meleset ('Kolaborasi ' != 'Kolaborasi').
        selected = []
        for s in suggestions:
            if isinstance(s, str) and s.strip() in allowed:
                name = s.strip()
                if name not in selected:
                    selected.append(name)
        return selected


def main():
    """CLI entry point (real generation)."""
    import sys
    import io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    logging.basicConfig(level=logging.INFO)

    params = {
        'education_system': 'KEMENAG',
        'institution_type': 'MTs',
        'grade': 'MTs_7',
        'subject': 'Akidah Akhlak',
        'element': 'Akhlak',
        'topic': 'Taubat',
        'requested_tp_count': 3
    }

    pipeline = ModuleGenerationPipeline()
    result = pipeline.generate(params)

    output_path = Path(__file__).parent.parent / 'db' / 'generated_module.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    print(f"Status: {result['status']}")
    print(f"Generation ID: {result['generation_id']}")
    if result['status'] != 'success':
        for err in result['errors']:
            print(f"ERROR: {err}")
        sys.exit(1)


if __name__ == '__main__':
    main()
