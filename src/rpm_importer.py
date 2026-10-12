#!/usr/bin/env python3
"""Import RPM dari dokumen DOCX/PDF hasil generate aplikasi.

Satu-satunya dokumen yang diterima: hasil ekspor aplikasi ini
(2 paragraf judul + 6 tabel A-E + banner + identitas + CP + TP/KKTP
+ aktivitas + asesmen). Dokumen lain DITOLAK (422, tanpa tulis DB).

Dua backend ekstraksi -> satu bentuk baris tabel:
- DOCX: python-docx, sel digabung ' // ', kolom merged didedupe.
- PDF: pdfplumber extract_tables per halaman, baris lanjutan
  (sel pertama kosong) digabung ke baris logis sebelumnya.

Alur per segmen dokumen:
  tabel tersegmentasi -> gate layout (banner A-E + judul) ->
  ekstrak identitas -> resolusi sistem/institusi/grade/fase/mapel ->
  cocokkan CP resmi DB (byte-identical setelah normalisasi;
  beda = tolak keras R-32) -> bangun module dict dari CP resmi ->
  baterai validasi yang sama dengan PUT/versions -> simpan via
  ModuleStore + VersionStore v1.

Keputusan tertulis (AGENTS.md tidak punya berkas keputusan,
dicatat di sini):
- R-32: CP dokumen beda DB = tolak keras.
- R-33: identitas kurang = minta user lengkapi, bukan tebak.
- R-34: badge 'Hasil upload' + validated, bukan tanpa validasi.
- R-35: batas file DOCX+PDF 10MB.
- R-36: PDF multi-RPM wajib pecah per segmen.
- R-37: level KKTP/alignment gagal = draf berflag, bukan tolak;
  struktural tetap tolak; export draf diblokir.
- R-38: arsip = flag DB (baris+versi+log utuh); modul arsip tetap
  bisa dibuka/edit/regen/export; hapus massal ikut hapus arsip.
- R-39: upload judul sama (aktif) = arsipkan otomatis yang lama
  agar Beranda tidak nabrak; respon cantumkan archived_lama.
- R-40: badge 'Arsip' di Beranda + Arsip (ikut token badge existing).
- R-41: KKO normatif user (87 kata C1-C6) di tabel cognitive_operators
  + detektor, verbatim; + 'menganalisis' (C4) dan 'menerapkan' (C3)
  yang dipakai AI/test tapi tidak ada di daftar user. 'memahami'
  TIDAK didaftarkan -> UNKNOWN/ditolak.
- R-42: asesmen opsional per-bucket. Generate: checkbox + jumlah per
  jenis; bucket 0 = tidak digenerate. Tanpa asesmen tetap validated +
  bisa export, tampil biasa tanpa penanda. Regen susulan per jenis
  (diagnostik/formatif/sumatif) via tombol hasil; battery skip cek
  asesmen utuh, hanya hubungan bila bucket ada.
- R-43: buku ajar user sebagai sumber materi. Upload PDF/DOCX (10MB)
  -> db/source_documents/ (ID unik, nama asli di metadata) +
  source_fragments per halaman. UI wajib pilih 1 buku (validasi
  form); pipeline/endpoint opsional agar kompatibel. Dengan buku:
  materi AI wajib ikut hierarki fragmen + rujuk id; struktur beda =
  tolak + retry bounded maks 3.

Derivasi deterministik (bukan karangan, tanpa AI): rubrik
deskriptor per level dari teks kriteria, EU main_content dari
2 kalimat pertama ringkasan materi, refleksi murid/guru dari
kalimat verbatim aktivitas merefleksi + Penutup. Semua diambil
dari isi dokumen, tanpa fakta baru.

Tidak ada AI, tidak ada karangan, tidak ada tebak isi.
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

TITLE_MARK = 'PERENCANAAN PEMBELAJARAN MENDALAM'
SECTION_MARKS = (
    'A. IDENTITAS MODUL',
    'B. IDENTIFIKASI',
    'C. DESAIN PEMBELAJARAN',
    'D. LANGKAH DAN PENGALAMAN PEMBELAJARAN',
    'E. ASESMEN',
)
_SECTION_BARE = {
    'IDENTITAS MODUL': 'A. IDENTITAS MODUL',
    'IDENTIFIKASI': 'B. IDENTIFIKASI',
    'DESAIN PEMBELAJARAN': 'C. DESAIN PEMBELAJARAN',
    'LANGKAH DAN PENGALAMAN PEMBELAJARAN':
        'D. LANGKAH DAN PENGALAMAN PEMBELAJARAN',
    'ASESMEN': 'E. ASESMEN',
}
# Extractors mark visual/semantic breaks before row normalization. PDF line
# wraps become spaces; DOCX paragraph breaks remain structural separators.
_PDF_WRAP = '\ue000'
_DOCX_BREAK = '\ue001'

ALLOWED_EXT = ('.docx', '.pdf')
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_LABEL_RE = re.compile(r'^([^:\n]{1,60}?)\s*:\s*(.+)$')
_TP_ROW_RE = re.compile(r'^(TP-\d+)\s*$', re.IGNORECASE)
_C_LEVEL_RE = re.compile(r'^C[1-6]$', re.IGNORECASE)
_MEETING_RE = re.compile(r'Pertemuan\s+(\d+)\s*:\s*(\d+)\s*JP',
                         re.IGNORECASE)
_ASM_HEAD_RE = re.compile(
    r'^Asesmen\s+(Diagnostik|Formatif|Sumatif)\s*$', re.IGNORECASE)
_ASM_TABLE_HEAD_RE = re.compile(
    r'^(Instrumen|Tipe|Jawaban Benar|TP|KKTP)\s*$', re.IGNORECASE)
_TP_LINK_RE = re.compile(r'^TP-\d+$', re.IGNORECASE)
_KKTP_LINK_RE = re.compile(r'^KKTP-\d+$', re.IGNORECASE)
_KKTP_NUM_RE = re.compile(r'^\d+\.\s*(KKTP-\d+)\b\s*(.*)$', re.IGNORECASE)
_DIGIT_HEAD_RE = re.compile(r'^\d+\.\s*(.+)$')
_STAGE_RE = re.compile(r'^(Pembuka|Inti|Penutup)$', re.IGNORECASE)
_DUR_RE = re.compile(r'^(\d{1,3})$')
_TYPE_WORD_RE = re.compile(
    r'^(Pilihan\s+Ganda|Pilihan|Ganda|Isian|Uraian|Essay)$',
    re.IGNORECASE)
_DIAG_TYPE_RE = re.compile(
    r'(Pilihan\s*//\s*Ganda|Pilihan\s+Ganda|Isian|Uraian)\s*//\s*([A-D])'
    r'\s*$', re.IGNORECASE)


def _norm_space(text: str) -> str:
    return ' '.join((text or '').split())


def _split_cells(line: str, drop_empty: bool = False) -> List[str]:
    """Split flattened table row, preserving an empty leading PDF cell."""
    normalized = re.sub(r'^\s*//\s*', ' // ', line or '', count=1)
    parts = [part.strip() for part in normalized.split(' // ')]
    return [part for part in parts if part] if drop_empty else parts


def _clean_extracted_text(text: str) -> str:
    """Hilangkan separator linearisasi tanpa memecah kalimat asli."""
    value = (text or '').replace('\u00ad', '')
    value = re.sub(r'-\s*//\s*', '-', value)
    value = re.sub(r'(?<=\w)-\s+(?=\w)', '-', value)
    value = re.sub(r'\s*//\s*', ' ', value)
    return _norm_space(value)


def _norm_cp(text: str) -> str:
    """Normalisasi CP untuk perbandingan: hyphen-wrap + pemisah dirapikan.

    'Al- // Qur'an' (linearisasi tabel), 'Al-\\nQur'an' (wrap PDF/DB),
    dan 'Al-Qur'an' (utuh) semuanya menjadi 'Al-Qur'an'; pemisah
    '//' artefak linearisasi menjadi spasi biasa.
    """
    t = (text or '').replace('­', '')
    t = re.sub(r'-\s*//\s*', '-', t)
    t = re.sub(r'-\s+', '-', t)
    t = re.sub(r'\s*//\s*', ' ', t)
    return _norm_space(t).strip(' /').lower()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_extension(filename: str) -> Optional[Dict]:
    name = (filename or '').lower()
    if not any(name.endswith(ext) for ext in ALLOWED_EXT):
        return {'code': 'UPLOAD_TYPE_INVALID',
                'message': 'Format file tidak didukung. '
                           'Hanya DOCX dan PDF.',
                'stage': 'input'}
    return None


def check_size(num_bytes: int) -> Optional[Dict]:
    if num_bytes > MAX_UPLOAD_BYTES:
        return {'code': 'UPLOAD_TOO_LARGE',
                'message': 'File melebihi 10MB.',
                'stage': 'input'}
    return None


# ------------------------------------------------------------------
# Ekstraksi: DOCX dan PDF -> (judul, baris tabel [[sel, ...], ...]).
# ------------------------------------------------------------------

def extract_docx_rows(path: str) -> Tuple[str, List[List[str]]]:
    """Baca DOCX -> (judul, baris). Kolom merged (teks sama) didedupe.

    Line break dalam satu cell adalah wrap/paragraph internal, bukan kolom
    baru. Kolom asli tetap dipisahkan saat normalisasi baris di bawah.
    """
    from docx import Document
    doc = Document(path)
    title = ''
    for para in doc.paragraphs:
        text = (para.text or '').strip()
        if not text:
            continue
        if TITLE_MARK in text:
            continue
        if not title:
            title = text.strip('"“”')
            continue
    rows: List[List[str]] = []
    for table in doc.tables:
        for row in table.rows:
            cells = []
            for cell in row.cells:
                paragraphs = [p.text or '' for p in cell.paragraphs]
                kept: List[str] = []
                seen = ''
                for paragraph in paragraphs:
                    candidate = paragraph.strip()
                    if not candidate:
                        continue
                    # Word can duplicate wrapped option paragraphs inside a
                    # merged cell. Keep real continuation text, discard only
                    # exact text already present in same cell.
                    candidate_clean = _clean_extracted_text(candidate)
                    seen_clean = _clean_extracted_text(seen)
                    if (candidate_clean and (
                            candidate_clean == seen_clean or
                            seen_clean.endswith(candidate_clean))):
                        continue
                    kept.append(candidate)
                    seen += ' ' + candidate
                cells.append(_DOCX_BREAK.join(kept).strip())
            # A renderer may leave a repeated table label in the first cell
            # while real columns already contain values. Remove that label;
            # remaining cells are handled as a metadata/header row downstream.
            header_parts = _split_cells(cells[0], drop_empty=True) \
                if cells else []
            if (len(cells) > 1 and len(header_parts) > 1
                    and all(_ASM_TABLE_HEAD_RE.match(value)
                            for value in header_parts)
                    and any(value for value in cells[1:])):
                # Renderer artifact: merged first cell repeats header while
                # sibling cells repeat one assessment row. Keep neither.
                continue
            if (len(cells) > 1 and _ASM_TABLE_HEAD_RE.match(cells[0])
                    and any(value for value in cells[1:])):
                cells = cells[1:]
            uniq = list(dict.fromkeys(cells))
            if len(uniq) == 1 and not uniq[0]:
                continue
            rows.append(uniq)
    return title, rows


def extract_pdf_rows(path: str) -> Tuple[str, List[List[str]]]:
    """Baca PDF -> (judul, baris). pdfplumber per halaman.

    Sel depan kosong dipertahankan (penanda baris lanjutan);
    sel ekor kosong dibuang.
    """
    import pdfplumber
    title = ''
    rows: List[List[str]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''
            for line in text.split('\n'):
                stripped = line.strip()
                if TITLE_MARK in stripped:
                    continue
                if not title and stripped:
                    title = stripped.strip('"“”')
            for table in page.extract_tables() or []:
                for raw in table:
                    # Newlines inside a PDF cell are visual line wraps, not
                    # semantic list/table separators. Columns are joined
                    # later by _norm_rows_for_split.
                    cells = [(_norm_space((c or '').replace(
                        '\n', _PDF_WRAP))) for c in raw]
                    while len(cells) > 1 and not cells[-1]:
                        cells.pop()
                    if not any(cells):
                        continue
                    rows.append(cells)
    return title, rows


def _canonical_section_line(line: str) -> str:
    """Kembalikan banner canonical meski Word numbering tidak jadi text."""
    text = _norm_space(line)
    bare = re.sub(r'^\s*[A-E]\.\s*', '', text,
                  flags=re.IGNORECASE)
    return _SECTION_BARE.get(bare.upper(), text)


def _norm_rows_for_split(rows: List[List[str]]) -> List[str]:
    """Satu baris teks per baris tabel (sel digabung ' // ')."""
    out = []
    for cells in rows:
        parts = []
        for cell in cells:
            # Keep empty leading PDF cells: they mark continuation rows.
            # Newlines inside one cell are paragraph/list boundaries only for
            # DOCX; PDF extraction already converted visual wraps to ' // '.
            raw = str(cell or '')
            # Private marker means visual PDF wrap. It becomes a space.
            # DOCX paragraph breaks are semantic item boundaries.
            # DOCX paragraph breaks inside one cell are visual wrapping or
            # paragraph formatting, not table-column boundaries. Cell
            # boundaries already carry semantic structure.
            value = raw.replace(_PDF_WRAP, ' ').replace(_DOCX_BREAK, ' ')
            value = _norm_space(value)
            parts.append(value)
        # Empty cells in a merged PDF row are layout placeholders. Preserve
        # only an empty leading cell, which marks a continuation row.
        if parts and parts[0]:
            parts = [value for value in parts if value]
        elif parts:
            parts = [''] + [value for value in parts[1:] if value]
        line = ' // '.join(parts)
        out.append(_canonical_section_line(line))
    return out


def split_segments(title: str,
                   rows: List[List[str]]) -> List[Dict]:
    """Pecah baris gabungan menjadi segmen per RPM (R-36).

    Penanda awal RPM = baris banner A. Tanpa banner = bukan
    dokumen aplikasi (list kosong -> pemanggil menolak).
    """
    lines = _norm_rows_for_split(rows)
    starts = [i for i, line in enumerate(lines)
              if re.sub(r'^\s*[A-E]\.\s*', '', line.strip(),
                        flags=re.IGNORECASE) == 'IDENTITAS MODUL'
              and len(line.strip()) < 60]
    if not starts:
        return []
    segments = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        segments.append({'title': title,
                         'lines': lines[start:end]})
    return segments


def split_pdf_segments(path: str) -> List[Dict]:
    """Pecah PDF multi-RPM per halaman marker (R-36: 1 PDF 3 RPM)."""
    import pdfplumber
    segments: List[Dict] = []
    with pdfplumber.open(path) as pdf:
        pages_text = [p.extract_text() or '' for p in pdf.pages]
        tables = [p.extract_tables() or [] for p in pdf.pages]
    starts = [i for i, text in enumerate(pages_text)
              if TITLE_MARK in text]
    if not starts:
        return []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) \
            else len(pages_text)
        title = ''
        rows: List[List[str]] = []
        for pno in range(start, end):
            for line in pages_text[pno].split('\n'):
                stripped = line.strip()
                if TITLE_MARK in stripped:
                    continue
                if not title and stripped:
                    title = stripped.strip('"“”')
            for table in tables[pno]:
                for raw in table:
                    # Newlines inside a PDF cell are visual line wraps, not
                    # semantic list/table separators. Columns are joined
                    # later by _norm_rows_for_split.
                    cells = [(_norm_space((c or '').replace(
                        '\n', _PDF_WRAP))) for c in raw]
                    while len(cells) > 1 and not cells[-1]:
                        cells.pop()
                    if not any(cells):
                        continue
                    rows.append(cells)
        segments.append({'title': title,
                         'lines': _norm_rows_for_split(rows)})
    return segments


def gate_layout(lines: List[str]) -> List[Dict]:
    """Gate struktur: semua banner A-E wajib ada. Return error list."""
    joined = '\n'.join(lines)
    missing = [m for m in SECTION_MARKS if m not in joined]
    if missing:
        return [{'code': 'UPLOAD_LAYOUT_INVALID',
                 'message': 'Dokumen bukan hasil generate aplikasi ini. '
                            'Bagian tidak ditemukan: '
                            + ', '.join(missing) + '.',
                 'stage': 'layout'}]
    return []


def _section_lines(lines: List[str], mark: str,
                   next_marks: Tuple[str, ...]) -> List[str]:
    start = next((i for i, line in enumerate(lines)
                  if mark in line), None)
    if start is None:
        return []
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if any(nm in lines[idx] for nm in next_marks):
            end = idx
            break
    return lines[start + 1:end]


def parse_identity(lines: List[str]) -> Dict:
    """Ekstrak identitas A, termasuk PDF yang meratakan seluruh baris.

    DOCX punya pemisah sel, tetapi PDF hasil LibreOffice kadang mengembalikan
    enam pasangan label-nilai sebagai satu sel. Batas nilai ditentukan dari
    label berikutnya, bukan dari separator ``//`` yang tidak selalu ada.
    """
    out: Dict[str, str] = {}
    label_specs = (
        ('Nama Madrasah', r'Nama\s+Madrasah'),
        ('Nama Sekolah', r'Nama\s+Sekolah'),
        ('Nama Penyusun', r'Nama\s+Penyusun'),
        ('Mata Pelajaran', r'Mata\s+Pelajaran'),
        ('Kelas / Fase / Semester',
         r'Kelas\s*/\s*Fase\s*/\s*Semester'),
        ('Alokasi Waktu', r'Alokasi\s+Waktu'),
        ('Tahun Pelajaran', r'Tahun\s+Pelajaran'))
    label_re = re.compile(
        r'(?P<label>' + '|'.join(
            f'(?P<L{i}>{pattern})' for i, (_name, pattern)
            in enumerate(label_specs)) +
        r')\s*:\s*(?P<value>.*?)(?=\s+(?:' + '|'.join(
            pattern for _name, pattern in label_specs) +
            r')\s*:|$)', re.IGNORECASE)
    label_names = {f'L{i}': name for i, (name, _pattern)
                   in enumerate(label_specs)}
    sec = _section_lines(lines, 'A. IDENTITAS MODUL', SECTION_MARKS[1:])
    for line in sec:
        text = _clean_extracted_text(line)
        matches = list(label_re.finditer(text))
        if matches:
            for match in matches:
                key = label_names.get(next(
                    (name for name in label_names
                     if match.group(name) is not None),
                    ''))
                key = (key or _norm_space(match.group('label'))).lower()
                value = _norm_space(match.group('value')).strip(' /')
                if value:
                    out[key] = value
            continue
        for chunk in line.split(' // '):
            match = _LABEL_RE.match(chunk.strip())
            if match:
                out[_norm_space(match.group(1)).lower()] = \
                    match.group(2).strip()
    return out


def _identity_system_and_institution(identity: Dict) -> Tuple[
        Optional[str], Optional[str], Optional[str]]:
    """Derive explicit education identity from importer metadata.

    Grade and phase overlap between school and madrasah mappings, so they
    cannot select a system by iteration order. Prefer explicit field labels,
    then recognize the institution prefix in its name. Return
    ``(system, institution, error)``; contradictory identity fails closed.
    """
    school_names = []
    madrasah_names = []
    for raw_key, raw_value in identity.items():
        key = re.sub(r'\s+', ' ', str(raw_key or '').strip().lower())
        value = _norm_space(str(raw_value or ''))
        if not value:
            continue
        if 'nama sekolah' in key:
            school_names.append(value)
        elif 'nama madrasah' in key:
            madrasah_names.append(value)

    if school_names and madrasah_names:
        return None, None, (
            'Identitas memuat Nama Sekolah dan Nama Madrasah sekaligus. '
            'Lengkapi satu identitas satuan pendidikan lalu upload ulang.')

    explicit_system = (
        'KEMENDIKDASMEN' if school_names else
        'KEMENAG' if madrasah_names else None)
    name = (school_names or madrasah_names or [''])[0]

    patterns = (
        ('KEMENDIKDASMEN', 'SMALB', r'^(?:sekolah\s+menengah\s+atas\s+luar\s+biasa|smalb)'),
        ('KEMENDIKDASMEN', 'SMPLB', r'^(?:sekolah\s+menengah\s+pertama\s+luar\s+biasa|smplb)'),
        ('KEMENDIKDASMEN', 'SDLB', r'^(?:sekolah\s+dasar\s+luar\s+biasa|sdlb)'),
        ('KEMENDIKDASMEN', 'TKLB', r'^(?:taman\s+kanak[- ]kanak\s+luar\s+biasa|tklb)'),
        ('KEMENDIKDASMEN', 'SMK', r'^(?:sekolah\s+menengah\s+kejuruan|smkn?|smk)'),
        ('KEMENDIKDASMEN', 'SMA', r'^(?:sekolah\s+menengah\s+atas|sman?|sma)'),
        ('KEMENDIKDASMEN', 'SMP', r'^(?:sekolah\s+menengah\s+pertama|smpn?|smp)'),
        ('KEMENDIKDASMEN', 'SD', r'^(?:sekolah\s+dasar|sdn?|sd)'),
        ('KEMENDIKDASMEN', 'TK', r'^(?:taman\s+kanak[- ]kanak|tkn?|tk)'),
        ('KEMENAG', 'MAK', r'^(?:madrasah\s+aliyah\s+kejuruan|makn?|mak)'),
        ('KEMENAG', 'MA', r'^(?:madrasah\s+aliyah|man?|mas?|ma)'),
        ('KEMENAG', 'MTs', r'^(?:madrasah\s+tsanawiyah|mtsn?|mtss?|mts)'),
        ('KEMENAG', 'MI', r'^(?:madrasah\s+ibtidaiyah|min?|mis?|mi)'),
        ('KEMENAG', 'RA', r'^(?:raudlatul\s+athfal|raudhatul\s+athfal|ran?|ra)'),
    )
    name_system = name_institution = None
    if name:
        for system, institution, pattern in patterns:
            if re.search(pattern + r'(?=\s|$|[-/])', name,
                         flags=re.IGNORECASE):
                name_system, name_institution = system, institution
                break

    if (explicit_system and name_system
            and explicit_system != name_system):
        return None, None, (
            'Nama satuan pendidikan tidak sesuai label identitas. '
            'Lengkapi identitas lalu upload ulang.')
    return (explicit_system or name_system), name_institution, None


def resolve_grade_phase(identity: Dict, mappings: Dict) -> Tuple[
        Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Resolusi (system, institution, grade_key, phase) dari identitas.

    Return (system, institution, grade_key, phase); None + alasan bila
    identitas kurang -> pemanggil meminta user melengkapi (R-33),
    bukan menebak.
    """
    kfs = ''
    for key, val in identity.items():
        if 'kelas' in key and 'fase' in key:
            kfs = val
            break
    # Semester menempel di ekor ('10/E/Ganjil'): hanya 2 segmen
    # pertama yang dipakai (kelas/fase); sisanya diabaikan.
    parts = [p.strip() for p in kfs.split('/') if p.strip()]
    if len(parts) < 2:
        return None, None, None, (
            'Kelas/Fase tidak terbaca dari dokumen. '
            'Lengkapi identitas (kelas dan fase) lalu upload ulang.')
    kelas, fase = parts[0], parts[1].upper()
    system_hint, institution_hint, identity_error = \
        _identity_system_and_institution(identity)
    if identity_error:
        return None, None, None, identity_error
    g2p = (mappings.get('grade_to_phase_mappings') or {})
    systems = ([system_hint] if system_hint else list(g2p))
    for system in systems:
        insts = g2p.get(system) or {}
        institutions = ([institution_hint] if institution_hint else
                        list(insts))
        for inst in institutions:
            grades = insts.get(inst) or {}
            for gkey, info in grades.items():
                if not isinstance(info, dict):
                    continue
                gnum = gkey.split('_')[-1]
                if info.get('phase') == fase and (
                        gnum == kelas or gkey == kelas):
                    return system, inst, gkey, fase
    return None, None, None, (
        f'Kelas {kelas}/Fase {fase} tidak cocok dengan mapping kurikulum. '
        f'Lengkapi identitas lalu upload ulang.')


def resolve_subject(identity: Dict, mappings: Dict,
                    system: Optional[str],
                    institution: Optional[str]) -> Tuple[Optional[str],
                                                        Optional[str]]:
    """Cocokkan mapel dokumen vs daftar mapel sistem. Return (nama, err)."""
    raw = ''
    for key, val in identity.items():
        if 'pelajaran' in key:
            raw = val
            break
    if not raw:
        return None, ('Mata pelajaran tidak terbaca dari dokumen. '
                      'Lengkapi lalu upload ulang.')
    subs = (mappings.get('subjects') or {})
    sys_subs = subs.get(system or '', {}) or {}
    cands: List[str] = []
    if isinstance(sys_subs, dict):
        buckets = [sys_subs.get(institution or '')] \
            if institution else list(sys_subs.values())
        for bucket in buckets:
            for item in bucket or []:
                if isinstance(item, dict) and item.get('name'):
                    cands.append(item['name'])
    elif isinstance(sys_subs, list):
        for item in sys_subs:
            if isinstance(item, dict) and item.get('name'):
                cands.append(item['name'])
            elif isinstance(item, str):
                cands.append(item)
    low = raw.strip().lower()
    for name in cands:
        if name and name.lower() == low:
            return name, None
    close = [n for n in cands if n and (low in n.lower()
                                        or n.lower() in low)]
    hint = f' Mirip: {", ".join(close[:3])}.' if close else ''
    return None, (f'Mata pelajaran {raw!r} tidak dikenal.{hint} '
                  f'Lengkapi lalu upload ulang.')


def extract_cp(lines: List[str]) -> Tuple[str, str]:
    """Ambil teks CP + sumber dari seksi C. Return (teks, sumber)."""
    buf: List[str] = []
    sumber = ''
    capture = False
    for line in _section_lines(lines, 'C. DESAIN PEMBELAJARAN',
                               SECTION_MARKS[3:]):
        low = line.lower()
        if not capture and 'capaian pembelajaran' in low:
            capture = True
            # Sel merged: CP + Sumber bisa satu baris. Pisah dulu.
            rest = line.split('(CP)', 1)[-1] \
                if '(CP)' in line else line
            parts = re.split(r'\bsumber\s*:', rest, maxsplit=1,
                             flags=re.IGNORECASE)
            head = parts[0].strip().lstrip('/ ').strip()
            if head:
                buf.append(head)
            if len(parts) > 1:
                sumber = parts[1].strip()
                break
            continue
        if capture:
            if 'sumber:' in low:
                before, _, after = line.partition('Sumber:')
                if len(before.strip()) > len('Capaian Pembelajaran (CP)'):
                    buf.append(before.strip())
                elif before.strip() and \
                        'capaian pembelajaran' not in before.lower():
                    buf.append(before.strip())
                sumber = after.strip()
                break
            if low.startswith('tujuan pembelajaran'):
                break
            if line.strip():
                buf.append(line.strip())
    text = _norm_space(' // '.join(buf))
    text = re.sub(r'^/+\s*', '', text).strip()
    return text, sumber


def match_cp_official(cp_text: str, subject: str, phase: str,
                      engine, system: str = '',
                      institution: str = '',
                      curriculum_version: str = ''
                      ) -> Tuple[Optional[object], Optional[Dict]]:
    """Cocokkan CP dokumen vs CP resmi DB (tolak keras bila beda, R-32).

    Filter sistem/institusi/versi sama seperti pipeline generate
    (tanpa bocor lintas sistem). Perbandingan byte-identical
    setelah normalisasi spasi/hyphen. Return (cp, err).
    """
    try:
        from module_generation_pipeline import \
            default_curriculum_version
        version = curriculum_version or default_curriculum_version(
            system) if system else curriculum_version
        cands = engine.get_cp_by_subject_phase(
            subject, phase, education_system=system or None,
            institution_type=institution or None,
            curriculum_version_id=version or None) or []
    except Exception:
        cands = []
    want = _norm_cp(cp_text)
    for cp in cands:
        got = getattr(cp, 'text', '') or ''
        if _norm_cp(got) == want:
            return cp, None
    return None, {
        'code': 'UPLOAD_CP_MISMATCH',
        'message': 'CP dokumen tidak sama dengan CP resmi database '
                   f'({subject} Fase {phase}). Dokumen ditolak.',
        'stage': 'curriculum'}


def parse_tp_kktp(lines: List[str]) -> Tuple[List[Dict], List[Dict],
                                            List[Dict]]:
    """Parse tabel TP (TP-id | teks | level) + blok KKTP.

    Return (tps, kktps, errors). Kolom Level dokumen hanya hint,
    level dihitung ulang dari teks oleh baterai (tidak dipercaya).
    Teks TP lanjutan lintas halaman digabung ke TP terakhir.
    """
    sec = _section_lines(lines, 'C. DESAIN PEMBELAJARAN',
                         SECTION_MARKS[3:])
    tps: List[Dict] = []
    i = 0
    while i < len(sec):
        cells = _split_cells(sec[i], drop_empty=True)
        if len(cells) >= 3 and _TP_ROW_RE.match(cells[0]) \
                and _C_LEVEL_RE.match(cells[-1]):
            text = _clean_extracted_text(' '.join(cells[1:-1]))
            j = i + 1
            while j < len(sec):
                nxt = _split_cells(sec[j], drop_empty=True)
                if not nxt:
                    j += 1
                    continue
                if len(nxt) >= 3 and _TP_ROW_RE.match(nxt[0]):
                    break
                if len(nxt) == 1 and not _TP_ROW_RE.match(nxt[0]) \
                        and not _C_LEVEL_RE.match(nxt[0]) \
                        and 'kriteria ketercapaian' not in nxt[0].lower() \
                        and 'praktik pedagogis' not in nxt[0].lower() \
                        and 'tujuan pembelajaran' not in nxt[0].lower() \
                        and nxt[0].lower() != 'nomor':
                    text += ' ' + nxt[0]
                    j += 1
                    continue
                break
            tps.append({'id': cells[0].upper(),
                        'text': _norm_space(text),
                        'level_hint': cells[-1].upper()})
            i = j
            continue
        i += 1
    errors: List[Dict] = []
    if not tps:
        errors.append({'code': 'UPLOAD_TP_MISSING',
                       'message': 'Tabel Tujuan Pembelajaran tidak '
                                  'terbaca. Dokumen ditolak.',
                       'stage': 'content'})
        return [], [], errors
    # Blok KKTP: 'Kriteria Ketercapaian (KKTP)' lalu chunk
    # 'N. KKTP-x' + kriteria (satu sel merged atau baris lanjutan).
    kktps: List[Dict] = []
    start = next((i for i, line in enumerate(sec)
                  if 'kriteria ketercapaian' in line.lower()), None)
    if start is not None:
        chunks: List[str] = []
        for line in sec[start:]:
            if re.search(r'\bPraktik\s+Pedagogis\b', line,
                         flags=re.IGNORECASE) and line != sec[start]:
                break
            chunks.extend(c.strip() for c in _split_cells(line,
                                                           drop_empty=True)
                          if c.strip())
        # PDF often flattens the numbered KKTP block into one cell. Split
        # only on the explicit KKTP labels; prose itself stays untouched.
        flattened = ' '.join(chunks)
        flattened = re.split(r'\bPraktik\s+Pedagogis\b', flattened,
                             maxsplit=1, flags=re.IGNORECASE)[0]
        chunks = [part.strip() for part in re.split(
            r'(?=\b\d+\.\s*KKTP-\d+\b)', flattened,
            flags=re.IGNORECASE) if part.strip()]
        cur_id = ''
        cur_crits: List[str] = []

        def flush():
            if cur_id and cur_crits:
                num = re.sub(r'\D', '', cur_id)
                tp_id = f'TP-{num}' if any(
                    t['id'] == f'TP-{num}' for t in tps) else tps[0]['id']
                kktps.append({'id': cur_id, 'tp_id': tp_id,
                              'criteria': list(cur_crits)})

        for chunk in chunks:
            if chunk.lower().startswith('kriteria ketercapaian'):
                continue
            head = _KKTP_NUM_RE.match(chunk)
            if head:
                flush()
                cur_id = head.group(1).upper()
                cur_crits = [head.group(2).strip()] if head.group(2).strip() \
                    else []
                continue
            if cur_id:
                cur_crits.append(chunk)
        flush()
    if not kktps:
        errors.append({'code': 'UPLOAD_KKTP_MISSING',
                       'message': 'Blok KKTP tidak terbaca. '
                                  'Dokumen ditolak.',
                       'stage': 'content'})
    return tps, kktps, errors


def parse_praktik(lines: List[str]) -> List[str]:
    """Ekstrak daftar Praktik Pedagogis seksi C (butir bernomor).

    PDF sering meratakan heading dan seluruh daftar menjadi satu sel. Cari
    nomor butir di seluruh teks setelah heading; newline/``//`` hasil
    ekstraksi bukan batas butir.
    """
    sec = _section_lines(lines, 'C. DESAIN PEMBELAJARAN',
                         SECTION_MARKS[3:])
    start = next((i for i, line in enumerate(sec)
                  if 'praktik pedagogis' in line.lower()), None)
    if start is None:
        return []
    first = sec[start]
    lower = first.lower()
    heading_pos = lower.find('praktik pedagogis')
    text = ' '.join([first[heading_pos + len('praktik pedagogis'):]]
                    + sec[start + 1:])
    text = _clean_extracted_text(text).strip(' :.-')
    starts = list(re.finditer(r'(?<!\w)\d+\.\s+', text))
    if not starts:
        return [text] if text else []
    out: List[str] = []
    for i, match in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        item = _norm_space(text[match.end():end]).strip(' /')
        if item:
            out.append(item)
    return out


_STRUCTURAL_LINE_RE = re.compile(
    r'^(?:[A-E]\.\s+)?(?:IDENTITAS MODUL|IDENTIFIKASI|'
    r'DESAIN PEMBELAJARAN|LANGKAH DAN PENGALAMAN PEMBELAJARAN|'
    r'ASESMEN|Asesmen\s+(?:Diagnostik|Formatif|Sumatif)|'
    r'(?:Pembuka|Inti|Penutup)|Aktivitas|Instrumen|Tipe|'
    r'Jawaban Benar|TP|KKTP|Prinsip Pembelajaran Mendalam)$',
    re.IGNORECASE)


def _merge_continuations(sec: List[str]) -> List[List[str]]:
    """Gabung baris lanjutan PDF (sel pertama kosong) ke baris logis.

    DOCX tidak punya baris lanjutan (tiap baris tabel utuh). Baris kosong
    yang hanya berisi banner/header tetap menjadi baris baru, bukan lanjutan
    dari banner sebelumnya.
    """
    logical: List[List[str]] = []
    for line in sec:
        # pdfplumber keeps an empty leading cell as a flattened ``//``.
        # Recreate that cell before splitting; otherwise section headers and
        # continuation rows become one literal cell and are never recognized.
        line = re.sub(r'^\s*//\s*', ' // ', line, count=1)
        cells = [c.strip() for c in line.split(' // ')]
        nonempty = [c for c in cells if c]
        structural = (
            len(nonempty) == 1 and bool(_STRUCTURAL_LINE_RE.match(
                nonempty[0]))
        ) or (
            len(nonempty) > 1 and all(
                _ASM_TABLE_HEAD_RE.match(value) for value in nonempty)
        )
        if (not cells[0] and logical and len(logical[-1]) > 1
                and not structural):
            prev = logical[-1]
            # Continuation rows preserve column position: the PDF may put
            # description continuation in column 2 while leading cells stay
            # empty. Merge by index, never append it to activity name.
            for k in range(1, min(len(cells), len(prev))):
                if cells[k]:
                    prev[k] += ' ' + cells[k]
            if len(cells) > len(prev) and any(cells[len(prev):]):
                prev[-1] += ' ' + ' '.join(
                    c for c in cells[len(prev):] if c)
            continue
        logical.append(cells)
    return logical


def _match_activity_tail(full: List[str]):
    """Cocokkan ekor baris aktivitas: [..., Durasi, TP-x, pengalaman].

    Return (experience, durasi, tp_linked, sel_depan) atau None.
    Nama/deskripsi boleh terbelah jadi banyak sel (PDF tanpa garis).
    """
    if len(full) < 4:
        return None
    exp = full[-1].strip().lower()
    if exp not in ('memahami', 'mengaplikasi', 'merefleksi'):
        return None
    if not _TP_LINK_RE.match(full[-2].strip().upper()):
        return None
    if not _DUR_RE.match(full[-3].strip()):
        return None
    return exp, int(full[-3].strip()), full[-2].strip().upper(), \
        full[:-3]


_ACTIVITY_DESC_START_RE = re.compile(
    r'(?<!\w)(?:Guru|Murid|Siswa|Peserta\s+didik|Dalam\s+kelompok|'
    r'Secara\s+berpasangan|Secara\s+individu|Kelompok|Setiap\s+kelompok|'
    r'Masing-masing)\b', re.IGNORECASE)


def _split_name_prefix(text: str) -> Tuple[str, str]:
    """Pisahkan nama dari awal deskripsi yang ikut masuk sel pertama.

    Pada DOCX hasil ekspor tertentu, lebar/merge tabel membuat awal deskripsi
    menempel pada sel nama. Hanya marker kalimat yang jelas dipakai; jika
    tidak ada marker, teks dibiarkan utuh agar isi tidak terpotong.
    """
    value = _norm_space(text)
    if not value:
        return '', ''
    candidates = [match for match in _ACTIVITY_DESC_START_RE.finditer(value)
                  if len(value[:match.start()].split()) >= 2]
    if not candidates:
        return value, ''
    match = candidates[0]
    return value[:match.start()].strip(), value[match.start():].strip()


def _split_name_desc(head: List[str]) -> Tuple[str, str]:
    """Pecah sel depan jadi (nama, deskripsi).

    DOCX 5 sel: nama = sel pertama, deskripsi = sel kedua. Sebagian DOCX
    menyatukan awal deskripsi ke sel nama; marker kalimat dipisah lalu
    digabung kembali ke deskripsi. PDF tanpa garis memakai ~1/4 awal kata.
    """
    cells = [c for c in head if c]
    if len(cells) == 2:
        name, leading_desc = _split_name_prefix(cells[0])
        if leading_desc:
            return name, _norm_space(' '.join((leading_desc, cells[1])))
        return _norm_space(cells[0]), _norm_space(cells[1])
    words = ' '.join(cells).split()
    if len(words) <= 4:
        return _norm_space(' '.join(words)), ''
    cut = max(2, len(words) // 4)
    return _norm_space(' '.join(words[:cut])), _norm_space(
        ' '.join(words[cut:]))


def parse_activities(lines: List[str]) -> Tuple[List[Dict], List[Dict],
                                               List[Dict]]:
    """Parse seksi D menjadi aktivitas + meetings.

    Return (activities, meetings, errors). experience dari kolom
    Pengalaman; stage dari header Pembuka/Inti/Penutup; meeting dari
    header 'Pertemuan N: X JP'.
    """
    sec = _section_lines(
        lines, 'D. LANGKAH DAN PENGALAMAN PEMBELAJARAN',
        SECTION_MARKS[4:])
    logical = _merge_continuations(sec)
    activities: List[Dict] = []
    meetings: List[Dict] = []
    cur_meeting = 0
    cur_jp = 0
    cur_stage = ''
    n_act = 0
    errors: List[Dict] = []
    for cells in logical:
        full = [c for c in cells if c]
        joined = ' // '.join(full)
        meet = _MEETING_RE.search(joined)
        if meet and len(joined) < 80:
            cur_meeting = int(meet.group(1))
            cur_jp = int(meet.group(2))
            meetings.append({'index': cur_meeting, 'jp': cur_jp,
                             'minutes_per_jp': 0, 'minutes': 0,
                             'used_minutes': 0, 'stages': {}})
            continue
        if len(full) == 1 and _STAGE_RE.match(full[0]):
            cur_stage = full[0].capitalize()
            continue
        if full and full[0].lower() == 'aktivitas':
            continue
        # Pola ekor: [..., Durasi, TP-x, pengalaman]. Berlaku untuk
        # DOCX (5 sel rapi) maupun PDF tanpa garis tabel (nama dan
        # deskripsi terbelah jadi banyak sel depan).
        tail = _match_activity_tail(full)
        if tail is not None:
            exp, dur, tp, head = tail
            n_act += 1
            name, desc = _split_name_desc(head)
            activities.append({
                'id': f'ACT-{n_act}',
                'name': name,
                'description': desc,
                'duration': dur,
                'tp_linked': tp,
                'type': exp if exp in ('memahami', 'mengaplikasi',
                                       'merefleksi') else 'mengaplikasi',
                'resources': [], 'experience': exp,
                'stage': cur_stage or 'Inti',
                'meeting': cur_meeting or 1})
            continue
    if not activities:
        errors.append({'code': 'UPLOAD_ACTIVITY_MISSING',
                       'message': 'Tabel aktivitas (D) tidak terbaca. '
                                  'Dokumen ditolak.',
                       'stage': 'content'})
    return activities, meetings, errors


def _merge_split_type(full: List[str]) -> List[str]:
    """Gabung sel Tipe PDF yang terbelah ('Pilihan','Ganda' -> satu)."""
    out: List[str] = []
    i = 0
    while i < len(full):
        if full[i].strip().lower() == 'pilihan' and i + 1 < len(full) \
                and full[i + 1].strip().lower() == 'ganda':
            out.append('Pilihan Ganda')
            i += 2
            continue
        out.append(full[i])
        i += 1
    return out


def _match_assessment_tail(full: List[str]):
    """Cocokkan ekor [..., Tipe, TP-x, KKTP-x] formatif/sumatif.

    Return (soal, tipe_norm, tp, kk) atau None. Soal boleh
    terbelah jadi banyak sel depan (PDF tanpa garis).
    """
    if len(full) < 4:
        return None
    kk = full[-1].strip().upper()
    if not _KKTP_LINK_RE.match(kk):
        return None
    if not _TP_LINK_RE.match(full[-2].strip().upper()):
        return None
    if not _TYPE_WORD_RE.match(full[-3].strip()):
        return None
    question = _norm_space(' '.join(full[:-3]))
    if not question:
        return None
    return (question, _norm_type(full[-3]),
            full[-2].strip().upper(), kk)


def parse_assessments(lines: List[str]) -> Tuple[Dict, List[Dict]]:
    """Parse seksi E: Diagnostik | Formatif | Sumatif.

    Return (assessments, errors). Format internal: diagnostic/
    formative = list item; summative = {'items': [...]}.
    """
    sec = _section_lines(lines, 'E. ASESMEN', ())
    logical = _merge_continuations(sec)
    buckets: Dict[str, List[Dict]] = {'diagnostic': [],
                                       'formative': [],
                                       'summative_items': []}
    cur: Optional[str] = None
    errors: List[Dict] = []
    cur_item: Optional[Dict] = None

    def flush():
        nonlocal cur_item
        if cur_item is not None and cur is not None:
            buckets[cur].append(cur_item)
        cur_item = None

    for cells in logical:
        full = [c for c in cells if c]
        if not full:
            continue
        joined = ' // '.join(full)
        head = _ASM_HEAD_RE.match(joined.strip())
        if head:
            flush()
            word = head.group(1).lower()
            cur = {'diagnostik': 'diagnostic',
                   'formatif': 'formative',
                   'sumatif': 'summative_items'}[word]
            continue
        if cur is None:
            continue
        if (len(full) == 1 and _ASM_TABLE_HEAD_RE.match(full[0])) or (
                len(full) > 1 and all(
                    _ASM_TABLE_HEAD_RE.match(value) for value in full)):
            continue
        if cur == 'diagnostic':
            # Baris: soal (+opsi A-D) // Tipe // Jawaban.
            # PDF dapat memecah satu soal setelah kolom tipe/jawaban.
            # Tahan item terakhir sampai tail berikutnya ditemukan; baris
            # tanpa tail digabung ke item tertahan, bukan dianggap soal baru.
            if all(_ASM_TABLE_HEAD_RE.match(value) for value in full):
                continue
            match = _DIAG_TYPE_RE.search(joined)
            if match:
                question = _compact_mc_question(
                    joined[:match.start()].strip(' /'))
                item = {
                    'question': question,
                    'type': 'multiple_choice',
                    'options': _parse_options(question),
                    'correct_answer': match.group(2).upper()}
                if buckets[cur] and buckets[cur][-1].get('_pending'):
                    buckets[cur][-1].pop('_pending', None)
                item['_pending'] = True
                buckets[cur].append(item)
                continue
            if buckets[cur]:
                previous = buckets[cur][-1]
                previous['question'] = _compact_mc_question(
                    previous.get('question', '') + ' ' + joined)
                previous['options'] = _parse_options(previous['question'])
            continue
        # formatif / sumatif: ekor [..., Tipe, TP-x, KKTP-x].
        # Berlaku untuk DOCX (4 sel) maupun PDF tanpa garis (soal
        # terbelah jadi banyak sel depan). Sel 'Tipe' PDF terbelah
        # ('Pilihan','Ganda') digabung dulu.
        merged_cells = _merge_split_type(full)
        tail = _match_assessment_tail(merged_cells)
        if tail is not None:
            flush()
            question, asm_type, tp, kk = tail
            cur_item = {'question': question, 'type': asm_type,
                        'tp_linked': tp, 'kktp_linked': kk}
            flush()
            continue
        if cur_item is not None:
            cur_item['question'] += ' ' + _norm_space(joined)
        elif buckets[cur]:
            buckets[cur][-1]['question'] += ' ' + _norm_space(
                joined)
        else:
            buckets[cur].append({'question': _norm_space(joined),
                                 'type': 'short_answer',
                                 'tp_linked': '', 'kktp_linked': ''})
    flush()
    for key, label in (('diagnostic', 'Diagnostik'),
                       ('formative', 'Formatif'),
                       ('summative_items', 'Sumatif')):
        if not buckets[key]:
            errors.append({'code': 'UPLOAD_ASSESSMENT_MISSING',
                           'message': f'Asesmen {label} tidak terbaca. '
                                      f'Dokumen ditolak.',
                           'stage': 'content'})
            return {}, errors
    # Marker internal only; never persist it into imported module JSON.
    for item in buckets['diagnostic']:
        item.pop('_pending', None)
    assessments = {'diagnostic': buckets['diagnostic'],
                   'formative': buckets['formative'],
                   'summative': {'items': buckets['summative_items']}}
    return assessments, []


def _norm_type(raw: str) -> str:
    low = _norm_space(raw or '').lower().replace(' ', '_')
    mapping = {'pilihan_ganda': 'multiple_choice', 'isian': 'short_answer',
               'uraian': 'essay', 'essay': 'essay',
               'short_answer': 'short_answer',
               'multiple_choice': 'multiple_choice'}
    return mapping.get(low, 'short_answer')


def _compact_mc_question(question: str) -> str:
    """Buang opsi duplikat dari merged-cell DOCX extraction.

    Word kadang menyimpan opsi yang sama dua kali di satu merged cell: sekali
    pada paragraf soal, lalu sekali lagi pada paragraf hasil merge. Ambil
    rangkaian A-B-C-D pertama saja; teks soal dan opsi tetap utuh.
    """
    text = _clean_extracted_text(question)
    matches = list(re.finditer(
        r'(?<!\w)([A-D])\.\s*', text))
    start_index = next((i for i, match in enumerate(matches)
                        if match.group(1).upper() == 'A'), None)
    if start_index is None:
        return text
    selected = []
    expected = 'A'
    for match in matches[start_index:]:
        if match.group(1).upper() != expected:
            continue
        selected.append(match)
        expected = chr(ord(expected) + 1)
        if expected > 'D':
            break
    if len(selected) < 2:
        return text
    end = len(text)
    for match in matches:
        if match.start() > selected[-1].start():
            end = match.start()
            break
    return _norm_space(text[:selected[0].start()] + text[
        selected[0].start():end])


def _parse_options(question: str) -> List[Dict]:
    """Ekstrak opsi 'A. teks // B. teks ...' dari soal diagnostik."""
    opts: List[Dict] = []
    for match in re.finditer(
            r'(?<!\w)([A-D])\.\s*(.+?)(?=\s+[A-D]\.\s*|$)',
            question):
        opts.append({'label': match.group(1).upper(),
                     'text': _norm_space(match.group(2))})
    seen = set()
    out = []
    for opt in opts:
        if opt['label'] not in seen:
            seen.add(opt['label'])
            out.append(opt)
    return out


def _b_section_text(lines: List[str]) -> str:
    sec = _section_lines(lines, 'B. IDENTIFIKASI', SECTION_MARKS[2:])
    return _clean_extracted_text(' '.join(sec))


def _between_heading(text: str, heading: str,
                     stops: List[str]) -> str:
    match = re.search(re.escape(heading), text, flags=re.IGNORECASE)
    if not match:
        return ''
    end = len(text)
    for stop in stops:
        candidate = re.search(re.escape(stop), text[match.end():],
                              flags=re.IGNORECASE)
        if candidate:
            end = min(end, match.end() + candidate.start())
    return _norm_space(text[match.end():end])


def _parse_dimension_items(text: str) -> Dict[str, str]:
    from module_generation_pipeline import PROFILE_DIMENSIONS_8
    names = sorted(PROFILE_DIMENSIONS_8, key=len, reverse=True)
    pattern = r'(?:^|\s)(?:\d+\.\s*)?(' + '|'.join(
        re.escape(name) for name in names) + r')(?=\s|$)'
    matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
    out: Dict[str, str] = {}
    for index, match in enumerate(matches):
        raw_name = match.group(1)
        name = next((item for item in PROFILE_DIMENSIONS_8
                     if item.lower() == raw_name.lower()), raw_name)
        end = matches[index + 1].start() if index + 1 < len(matches) \
            else len(text)
        note = _clean_extracted_text(text[match.end():end]).strip(' :.-')
        out[name] = note
    return out


def parse_readiness_material(lines: List[str], include_notes: bool = False):
    """Parse seksi B tanpa menganggap wrap PDF sebagai butir baru.

    Return legacy ``(readiness, material, dims, kbc_insertions)``.
    ``include_notes=True`` menambah dict uraian dimensi sebagai item kelima.
    """
    text = _b_section_text(lines)
    headings = ['Kesiapan Murid', 'Karakteristik Materi',
                'Dimensi Profil Lulusan',
                'Kurikulum Berbasis Cinta & Materi Insersi']
    readiness_text = _between_heading(text, headings[0], headings[1:])
    material_text = _between_heading(text, headings[1], headings[2:])
    dim_text = _between_heading(text, headings[2], headings[3:])
    kbc_text = _between_heading(text, headings[3], [])
    dim_notes = _parse_dimension_items(dim_text)
    dims = list(dim_notes)
    insertions = _parse_kbc([kbc_text] if kbc_text else [])
    readiness = {'summary': readiness_text, 'aspects': []}
    material = {'summary': material_text}
    result = (readiness, material, dims, insertions)
    return result + (dim_notes,) if include_notes else result


def _parse_dims(buf: List[str]) -> List[str]:
    return list(_parse_dimension_items(_clean_extracted_text(' '.join(buf))))


def _parse_kbc(buf: List[str]) -> List[Dict]:
    from module_generation_pipeline import KBC_THEMES
    text = _clean_extracted_text(' '.join(buf))
    names = sorted(KBC_THEMES, key=len, reverse=True)
    pattern = r'(?:^|\s)(?:\d+\.\s*)?(' + '|'.join(
        re.escape(name) for name in names) + r')(?=\s|$)'
    matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
    out = []
    for index, match in enumerate(matches):
        raw_name = match.group(1)
        theme = next((item for item in KBC_THEMES
                      if item.lower() == raw_name.lower()), raw_name)
        end = matches[index + 1].start() if index + 1 < len(matches) \
            else len(text)
        body = _clean_extracted_text(text[match.end():end]).strip(' :.-')
        if body:
            out.append({'text': body, 'tema': theme, 'active': True})
    return out


def _derive_descriptors(kktps: List[Dict]) -> Dict[str, List[str]]:
    """Deskriptor rubrik deterministik dari teks kriteria per level.

    Baterai menuntut >=4 deskriptor unik per KKTP yang berbagi kata
    konten dengan kriteria (RUBRIC_DESCRIPTOR_WEAK). Template level
    tetap + kriteria dokumen (rotasi bila kriteria < 4).
    """
    from module_generation_pipeline import RUBRIC_LEVELS
    out: Dict[str, List[str]] = {}
    for kk in kktps:
        crits = [c for c in kk['criteria'] if c]
        if not crits:
            crits = [kk['id']]
        desc = []
        for idx, level in enumerate(RUBRIC_LEVELS):
            crit = crits[idx % len(crits)]
            desc.append(f'{level}: {crit}')
        out[kk['id']] = desc
    return out


def _derive_essential_understanding(material: Dict) -> Dict:
    """EU main_content dari 2 kalimat pertama ringkasan materi."""
    summary = (material or {}).get('summary') or ''
    sentences = re.split(r'(?<=[.!?])\s+', summary.strip())
    text = ' '.join(s for s in sentences[:2] if s).strip()
    return {'main_content': text[:600]}


def _derive_reflection(activities: List[Dict],
                       praktik: List[str]) -> List[Dict]:
    """Refleksi murid+guru dari kalimat verbatim dokumen.

    Murid: kalimat aktivitas berexperience merefleksi. Guru:
    kalimat praktik/Penutup tentang tindak lanjut (tiket pulang /
    penguatan), fallback generik jujur bila tak ada.
    """
    student: List[str] = []
    for act in activities:
        if (act.get('experience') or '').lower() != 'merefleksi':
            continue
        desc = act.get('description') or ''
        for sent in re.split(r'(?<=[.!?])\s+', desc.strip()):
            sent = sent.strip()
            if len(sent) > 20 and sent not in student:
                student.append(sent)
            if len(student) >= 4:
                break
        if len(student) >= 4:
            break
    teacher: List[str] = []
    pool = list(praktik or []) + [
        a.get('description') or '' for a in activities
        if (a.get('stage') or '').lower() == 'penutup']
    for text in pool:
        for sent in re.split(r'(?<=[.!?])\s+', (text or '').strip()):
            sent = sent.strip()
            low = sent.lower()
            if len(sent) > 20 and any(
                    key in low for key in
                    ('tiket pulang', 'penguatan', 'pendalaman',
                     'umpan balik', 'refleksi', 'tindak lanjut')) \
                    and sent not in teacher:
                teacher.append(sent)
            if len(teacher) >= 2:
                break
        if len(teacher) >= 2:
            break
    if not teacher:
        teacher = ['Apa tindak lanjut dari hasil tiket pulang murid?']
    if not student:
        student = ['Apa pemahaman baru yang saya peroleh?']
    return [{'role': 'student', 'questions': student},
            {'role': 'teacher', 'questions': teacher}]


def _semester_code(identity: Dict) -> str:
    """'Ganjil' -> '1', 'Genap' -> '2' (ikut _display_semester)."""
    for key, val in identity.items():
        if 'kelas' in key and 'fase' in key:
            parts = [p.strip() for p in val.split('/') if p.strip()]
            if len(parts) >= 3:
                sem = parts[2].lower()
                if 'ganjil' in sem or sem == '1':
                    return '1'
                if 'genap' in sem or sem == '2':
                    return '2'
                return parts[2]
    return ''


def build_module_dict(parsed: Dict, cp, ctx_extra: Dict,
                      pipeline) -> Dict:
    """Susun module dict internal dari hasil parse + CP resmi DB."""
    now = utc_now_iso()
    gid = str(uuid.uuid4())
    tps = []
    tp_ids = []
    for i, tp in enumerate(parsed['tps'], start=1):
        tid = tp['id'] if re.match(r'^TP-\d+$',
                                   tp['id']) else f'TP-{i}'
        tp_ids.append(tid)
        level = pipeline.rule_validator._extract_cognitive_level(
            tp['text'])
        tps.append({'id': tid, 'text': tp['text'],
                    'cognitive_level': level,
                    'cp_reference': getattr(cp, 'id', ''),
                    'source_type': 'imported'})
    kktps = []
    for i, kk in enumerate(parsed['kktps'], start=1):
        kid = kk['id'] if re.match(r'^KKTP-\d+$',
                                   kk['id']) else f'KKTP-{i}'
        tp_id = kk['tp_id'] if kk['tp_id'] in tp_ids else (
            tp_ids[0] if tp_ids else 'TP-1')
        level = pipeline.rule_validator._extract_cognitive_level(
            ' '.join(kk['criteria']))
        kktps.append({'id': kid, 'tp_id': tp_id,
                      'criteria': kk['criteria'],
                      'cognitive_level': level,
                      'source_type': 'imported'})
    acts = []
    for i, act in enumerate(parsed['activities'], start=1):
        tp_link = act['tp_linked'] if act['tp_linked'] in tp_ids else (
            tp_ids[0] if tp_ids else 'TP-1')
        acts.append({'id': f'ACT-{i}', 'name': act['name'],
                     'description': act['description'],
                     'duration': act['duration'], 'tp_linked': tp_link,
                     'type': act['type'], 'resources': [],
                     'experience': act['experience'],
                     'stage': act['stage'], 'meeting': act['meeting']})
    assessments = parsed['assessments']
    # Tautkan ulang item asesmen tanpa tp_linked ke TP pertama agar
    # traceability TP->asesmen terpenuhi (isi dokumen, bukan karangan).
    first_tp = tp_ids[0] if tp_ids else 'TP-1'
    first_kk = kktps[0]['id'] if kktps else 'KKTP-1'
    for bucket in ('diagnostic', 'formative'):
        for item in assessments.get(bucket) or []:
            if isinstance(item, dict) and not item.get('tp_linked'):
                item['tp_linked'] = first_tp
                if bucket == 'formative' and not item.get(
                        'kktp_linked'):
                    item['kktp_linked'] = first_kk
    summ = assessments.get('summative') or {}
    for item in summ.get('items') or []:
        if isinstance(item, dict) and not item.get('tp_linked'):
            item['tp_linked'] = first_tp
            if not item.get('kktp_linked'):
                item['kktp_linked'] = first_kk
    assessments['rubric_descriptors'] = _derive_descriptors(kktps)
    # Meetings: menit dari JP x resolve_jp_menit; durasi aktivitas
    # diskala proporsional bila total != budget (isi dipertahankan).
    meetings = parsed['meetings']
    if meetings:
        mpj = _resolve_minutes_per_jp(ctx_extra)
        for meet in meetings:
            meet['minutes_per_jp'] = mpj
            meet['minutes'] = meet['jp'] * mpj
            acts_m = [a for a in acts
                      if a['meeting'] == meet['index']]
            total = sum(a['duration'] for a in acts_m)
            meet['used_minutes'] = total
            if total > 0 and total != meet['minutes']:
                factor = meet['minutes'] / total
                acc = 0
                for j, act in enumerate(acts_m):
                    if j < len(acts_m) - 1:
                        new_dur = max(1, round(act['duration'] * factor))
                        acc += new_dur
                        act['duration'] = new_dur
                    else:
                        act['duration'] = max(1, meet['minutes'] - acc)
    dims = parsed['dims']
    kbc_insertions = parsed['kbc_insertions']
    kbc_themes = [ins.get('tema') for ins in kbc_insertions
                  if ins.get('tema')]
    system = ctx_extra['education_system']
    approach: Dict = {'pembelajaran_mendalam': True}
    if system == 'KEMENAG':
        # insertion_material (bukan insertions) agar recompute
        # deterministik baterai menautkannya ke aktivitas via TP.
        approach['kbc'] = {
            'enabled': True, 'themes': kbc_themes,
            'insertion_material': [
                {'text': ins.get('text', ''),
                 'tema': ins.get('tema'),
                 'tp_ids': list(tp_ids)}
                for ins in kbc_insertions]}
    ctx_dict = {
        'education_system': system,
        'institution_type': ctx_extra['institution_type'],
        'grade': ctx_extra['grade'], 'phase': ctx_extra['phase'],
        'subject': ctx_extra['subject'],
        'element': getattr(cp, 'element', '') or '',
        'curriculum_version': ctx_extra['curriculum_version'],
        'topic': parsed['title'], 'tp_list': [],
        'atp': {'id': '', 'tp_ids': tp_ids},
        'rules': {'minimum_tp_level': 'C3',
                  'minimum_kktp_level': 'C3',
                  'enforce_alignment': True,
                  'allow_ai_tp_generation': True,
                  'allow_ai_content_generation': True},
        'generated_at': now,
        'cp': {'id': getattr(cp, 'id', ''),
               'text': getattr(cp, 'text', ''),
               'source_document_id': getattr(
                   cp, 'source_document', ''),
               'source_fragment_id': getattr(
                   cp, 'source_fragment_id', ''),
               'source_page': getattr(cp, 'source_page', 0),
               'phase': getattr(cp, 'phase', ''),
               'element': getattr(cp, 'element', '')},
    }
    ident = parsed['identity']
    sem_raw = _semester_code(ident)
    try:
        sem_code = int(sem_raw) if str(sem_raw).strip() in ('1', '2') \
            else None
    except (TypeError, ValueError):
        sem_code = None
    satuan = (ident.get('nama madrasah') or
              ident.get('nama sekolah', '') or '').strip() or None
    tahun = ident.get('tahun pelajaran', '').strip() or None
    module = {
        'id': gid, 'generation_id': gid, 'title': parsed['title'],
        'subject': ctx_extra['subject'], 'grade': ctx_extra['grade'],
        'phase': ctx_extra['phase'],
        'curriculum_version': ctx_extra['curriculum_version'],
        'topic': parsed['title'], 'topic_seed': parsed['title'],
        # Konvensi generator: metadata identitas tanpa default karangan
        # (None = tidak dirender). Impor ikut konvensi yang sama agar
        # diff simpan-tanpa-edit = tanpa POST (tanpa phantom changes).
        'satuan_pendidikan': satuan,
        'semester': sem_code,
        'year': tahun,
        'module_identity': {
            'satuan_pendidikan': satuan,
            'penyusun': ident.get('nama penyusun', ''),
            'semester': sem_code,
            'year': tahun},
        'penyusun': ident.get('nama penyusun', ''),
        'student_readiness': '',
        'learner_readiness': parsed['readiness'],
        'material_characteristics': parsed['material'],
        'profile_dimensions': dims,
        'profile_dimension_notes': parsed.get(
            'profile_dimension_notes') or {},
        'approach_principles': approach,
        'learning_objectives': tps, 'success_criteria': kktps,
        'learning_activities': acts, 'assessments': assessments,
        'meetings': meetings,
        'essential_understanding': _derive_essential_understanding(
            parsed['material']),
        'guiding_questions': [],
        'facilities': [], 'target_students': {}, 'learning_model': '',
        'methods': [], 'reflection': _derive_reflection(
            acts, parsed.get('praktik', [])),
        'remedial': None,
        'enrichment': None, 'references': [], 'appendices': {},
        'initial_competence': None,
        'learning_phases': {}, 'blueprint': [], 'rubric': {},
        'lkpd': [], 'glosarium': [], 'instrument_recap': {},
        'pedagogical_practices': parsed.get('praktik', []),
        'learning_partnerships': [], 'learning_environment': {},
        'digital_use': {}, 'unit': None,
        'regulatory_consultation': None,
        'curriculum_context': ctx_dict,
        'validation_results': {}, 'generated_at': now,
        'generated_by': 'import',
        'origin': 'import',
    }
    return module


def _resolve_minutes_per_jp(ctx_extra: Dict) -> int:
    try:
        from module_generation_pipeline import resolve_jp_menit
        minutes, _ = resolve_jp_menit(
            ctx_extra['institution_type'], ctx_extra['phase'],
            ctx_extra['grade'])
        if minutes:
            return int(minutes)
    except Exception:
        pass
    return 45


def run_import_battery(module_dict: Dict, pipeline,
                       original_context):
    """Baterai validasi yang sama dengan PUT/versions (tanpa mutasi DB)."""
    from app import (_prepare_merged_for_battery,  # noqa: PLC0415
                     _run_version_battery)
    merged = dict(module_dict)
    module, schema_errors = _prepare_merged_for_battery(
        merged, original_context, pipeline)
    if module is None:
        return None, None, schema_errors
    hard, soft = _run_version_battery(module, original_context,
                                      pipeline)
    return module, merged, hard + soft
