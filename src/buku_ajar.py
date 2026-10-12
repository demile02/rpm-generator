#!/usr/bin/env python3
"""Ingest buku ajar user sebagai sumber materi (R-43).

Upload PDF/DOCX -> ekstrak teks per halaman -> pecah fragmen ->
simpan ke source_documents + source_fragments dengan provenance
(nama file, halaman, tanggal upload). BUKAN regulasi: regulation_id
NULL, document_type='buku_ajar'.
"""
import hashlib
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MAX_BUKU_BYTES = 10 * 1024 * 1024


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ekstrak_pdf_per_halaman(path: str) -> List[Tuple[int, str, str]]:
    """Return [(halaman, teks, method)] using shared PDF extraction."""
    from pdf_extraction import PDFExtractor

    extractor = PDFExtractor(path)
    extractor.extract_text_with_pages()
    total_pages = extractor.metadata.get('total_pages', 0)
    return [
        (
            page_number,
            extractor.content.get(page_number, '').strip(),
            extractor.page_methods.get(page_number, 'scan'),
        )
        for page_number in range(1, total_pages + 1)
    ]


def ekstrak_docx_per_halaman(path: str) -> List[Tuple[int, str, str]]:
    """DOCX tanpa nomor halaman: 1 fragmen per ~3 paragraf."""
    from docx import Document
    doc = Document(path)
    paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    out = []
    buf: List[str] = []
    hal = 1
    for p in paras:
        buf.append(p)
        if len(buf) >= 30:
            out.append((hal, '\n'.join(buf), 'text_layer'))
            buf = []
            hal += 1
    if buf:
        out.append((hal, '\n'.join(buf), 'text_layer'))
    return out


def normalisasi_judul(teks: str) -> str:
    """Rapikan judul mentah ("AL-QUR’AN-HADIS- KELAS XI i"
    -> "Al-Qur’an Hadis Kelas XI")."""
    t = re.sub(r'\s+', ' ', (teks or '')).strip()
    # Buang prefix nomor halaman di awal ("ii AL-QUR'AN" -> "AL-QUR'AN").
    t = re.sub(r'^(?:[ivxlcdm]+|\d+)\s+', '', t, flags=re.I)
    t = re.sub(r'\bkelas\s+(VII|VIII|IX|X|XI|XII|\d{1,2})\b',
               lambda m: 'Kelas ' + m.group(1).upper(), t, flags=re.I)
    # Buang nomor halaman di ujung, KECUALI frasa "Kelas XI" dsb.
    t = re.sub(r'(?<!\b[Kk]elas)\s+(?:[ivxlcdm]+|\d+)$', '', t)
    # Strip/garis sebagai pemisah kata -> spasi, kecuali strip DALAM kata.
    t = re.sub(r'(?<=\s)[-–—](?=\s)|(?<=\s)[-–—](?=$)|(?<=\w)[-–—](?=\s)', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    # Kapitalisasi per kata ("AL-QUR’AN" -> "Al-Qur’an").
    # Romawi dan angka dipertahankan ("Kelas XI").
    def _kap(w: str) -> str:
        out = []
        for seg in w.split('-'):
            if not seg:
                out.append(seg)
                continue
            bagian = seg.split('’')
            # Segmen setelah ’ di tengah kata tetap huruf kecil ("QUR’AN" -> "Qur’an").
            fixed = [bagian[0][:1].upper() + bagian[0][1:].lower() if bagian[0] else '']
            fixed += [p.lower() for p in bagian[1:]]
            out.append('’'.join(fixed))
        return '-'.join(out)
    t = ' '.join(_kap(w) for w in t.split())
    t = re.sub(r'\bKelas\s+(VII|VIII|IX|X|XI|XII|\d{1,2})\b',
               lambda m: 'Kelas ' + m.group(1).upper(), t, flags=re.I)
    return t


def ekstrak_identitas(teks_hal1: str, meta_title: str = '') -> Dict:
    """Tebak identitas buku dari halaman judul/teks awal.

    Prioritas: metadata PDF (bila ada dan bukan generik) lalu pola teks
    halaman judul: judul (baris terpanjang), pengarang (pola Oleh/...),
    tahun (4 digit 1900-2099), penerbit (pola Penerbit/...).
    Tak ada yang dipaksa: field kosong bila tak ditemukan, dan sumber
    dicatat ('metadata' / 'halaman_judul' / '').
    """
    out: Dict[str, str] = {'judul': '', 'pengarang': '', 'tahun': '',
                           'penerbit': '', 'sumber': ''}
    generik = {'untitled', 'tanpa judul', 'document', 'microsoft word',
               'pdf', 'hasil pemindaian'}
    mt = (meta_title or '').strip()
    if mt and len(mt) >= 4 and mt.lower() not in generik:
        out['judul'] = mt
        out['sumber'] = 'metadata'
        return out
    baris = [b.strip() for b in (teks_hal1 or '').splitlines()
             if b.strip() and len(b.strip()) >= 3]
    if not baris:
        return out
    isi = [b for b in baris
           if not re.match(r'^(kata pengantar|daftar isi|daftar pustaka|'
                           r'bab\s+\w+|bagian\s+\w+|oleh|penulis|disusun oleh|'
                           r'karya|penerbit|diterbitkan oleh)\b', b, re.I)]
    kandidat = isi if isi else baris
    # Judul: baris terpanjang <= 120 char yang bukan kop instansi.
    kop = re.compile(r'kementerian|direktorat|dinas|pemerintah|republik|'
                     r'universitas|sekolah|madrasah', re.I)
    for b in sorted(kandidat, key=len, reverse=True):
        if len(b) <= 120 and not kop.search(b):
            out['judul'] = normalisasi_judul(b)
            break
    # Normalisasi judul buku pelajaran dari running header:
    # "AL-QUR’AN HADIS KELAS X …" -> "Al-Qur’an Hadis Kelas X".
    if not out['judul']:
        m = re.search(r'(([A-Z][A-Z’\'\-\s]{4,60}?)\s+kelas\s+'
                      r'(VII|VIII|IX|X|XI|XII|\d{1,2}))',
                      teks_hal1 or '', re.I)
        if m:
            inti = normalisasi_judul(m.group(2))
            # Buang prefix nomor halaman romawi/angka ("ii AL-QUR'AN" -> "AL-QUR'AN").
            inti = re.sub(r'^(?:[ivxlcdm]+|\d+)\s+', '', inti, flags=re.I)
            out['judul'] = inti + ' Kelas ' + m.group(3).upper()
    for b in baris:
        if not out['pengarang']:
            m = re.match(r'^(?:oleh|penulis|disusun oleh|karya)\s*[:\-]?\s*(.+)',
                         b, re.I)
            if m and len(m.group(1).strip()) >= 3:
                out['pengarang'] = m.group(1).strip()[:120]
        if not out['penerbit']:
            m = re.match(r'^(?:penerbit|diterbitkan oleh)\s*[:\-]?\s*(.+)',
                         b, re.I)
            if m and len(m.group(1).strip()) >= 3:
                out['penerbit'] = m.group(1).strip()[:120]
        if not out['tahun']:
            m = re.search(r'\b((?:19|20)\d{2})\b', b)
            if m:
                out['tahun'] = m.group(1)
    if out['judul']:
        out['sumber'] = 'halaman_judul'
    # Fallback: pola inline dalam teks berjalan (fragmen hasil ekstraksi
    # menggabung banyak baris, mis. "…KELAS X Penulis : Syaifullah Amin …").
    if not out['pengarang']:
        m = re.search(r'(?:penulis|disusun oleh|karya)\s*:\s*'
                      r'([A-Z][A-Za-z.\'\s]{2,60}?)'
                      r'(?=\s+(?:editor|ilustrator|desain|penerbit|cetakan|'
                      r'tahun|hak|kata)|,|\.|$)',
                      teks_hal1 or '', re.I)
        if m:
            out['pengarang'] = m.group(1).strip()[:120]
    return out


def pecah_fragmen(teks: str, max_chars: int = 2000) -> List[str]:
    """Pecah teks halaman jadi fragmen <= max_chars per batas kalimat."""
    teks = re.sub(r'\s+', ' ', teks).strip()
    if not teks:
        return []
    if len(teks) <= max_chars:
        return [teks]
    bagian = re.split(r'(?<=[.!?])\s+', teks)
    out: List[str] = []
    buf = ''
    for k in bagian:
        if len(buf) + len(k) + 1 > max_chars and buf:
            out.append(buf)
            buf = k
        else:
            buf = (buf + ' ' + k).strip()
    if buf:
        out.append(buf)
    return out


def ingest_buku(db_path: str, file_path: str, nama_asli: str,
                judul: Optional[str] = None,
                lapor=None) -> Dict:
    """Simpan file upload sebagai dokumen buku + fragmen. Return ringkas.

    lapor(progress 0-100, tahap): callback opsional untuk progres riil
    (dipakai worker async; sinkron abaikan).
    """
    def _lapor(p, t):
        try:
            if lapor:
                lapor(p, t)
        except Exception:
            pass
    data = Path(file_path).read_bytes()
    if len(data) > MAX_BUKU_BYTES:
        raise ValueError('File melebihi 10MB.')
    suf = Path(nama_asli).suffix.lower()
    _lapor(5, 'Membaca file…')
    if suf == '.pdf':
        _lapor(10, 'Mengekstrak teks…')
        halaman = ekstrak_pdf_per_halaman(file_path)
        _lapor(70, 'Ekstraksi PDF selesai.')
    elif suf == '.docx':
        _lapor(10, 'Mengekstrak teks…')
        halaman = ekstrak_docx_per_halaman(file_path)
    else:
        raise ValueError('Hanya PDF/DOCX.')
    # Identitas buku dari metadata + halaman judul (bukan nama file).
    meta_title = ''
    if suf == '.pdf':
        try:
            import fitz
            _doc = fitz.open(file_path)
            meta_title = (_doc.metadata or {}).get('title') or ''
            _doc.close()
        except Exception:
            pass
    teks_hal1 = halaman[0][1] if halaman else ''
    identitas = ekstrak_identitas(teks_hal1, meta_title)
    doc_id = 'BUKU-' + uuid.uuid4().hex[:12].upper()
    now = datetime.now(timezone.utc).isoformat()
    # File asli disimpan di db/source_documents/ (sejajar database,
    # bukan templates): ID unik sebagai nama file, nama asli di
    # metadata local_path + notes.
    simpan_dir = Path(db_path).resolve().parent / 'source_documents'
    simpan_dir.mkdir(parents=True, exist_ok=True)
    nama_simpan = doc_id + suf
    (simpan_dir / nama_simpan).write_bytes(data)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            'INSERT INTO source_documents (id, regulation_id, title, '
            'document_type, local_path, file_size_bytes, document_hash, '
            'extracted_at, notes, book_title, book_author, book_year, '
            'book_publisher, book_identity_source) '
            'VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (doc_id, judul or Path(nama_asli).stem, 'buku_ajar',
             f'source_documents/{nama_simpan} (asli: {nama_asli})',
             len(data), _hash(data), now,
             f'Upload user {now[:10]}; {len(halaman)} halaman; '
             f'nama asli: {nama_asli}.',
             identitas['judul'] or None,
             identitas['pengarang'] or None,
             identitas['tahun'] or None,
             identitas['penerbit'] or None,
             identitas['sumber'] or None))
        n_frag = 0
        total_hal = max(1, len(halaman))
        _lapor(75, 'Menyimpan dokumen…')
        for idx_hal, (hal, teks, method) in enumerate(halaman):
            for idx, pot in enumerate(pecah_fragmen(teks)):
                fid = f'{doc_id}-H{hal}-{idx + 1}'
                conn.execute(
                    'INSERT INTO source_fragments (id, document_id, '
                    'page_number, section, paragraph, text, text_hash, '
                    'char_count, extraction_method) VALUES '
                    '(?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (fid, doc_id, hal, None, idx + 1, pot,
                     _hash(pot.encode('utf-8')), len(pot), method))
                n_frag += 1
            _lapor(75 + round(25 * (idx_hal + 1) / total_hal),
                   'Menyimpan fragmen (halaman %d dari %d)…' % (
                       idx_hal + 1, len(halaman)))
        conn.commit()
    finally:
        conn.close()
    return {'document_id': doc_id, 'judul': judul or Path(nama_asli).stem,
            'halaman': len(halaman), 'fragmen': n_frag,
            'identitas': identitas}


def daftar_buku(db_path: str) -> List[Dict]:
    """Daftar buku ajar user (bukan regulasi)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, title, local_path, file_size_bytes, extracted_at, "
            "book_title, book_author, book_year, book_publisher "
            "FROM source_documents WHERE document_type = 'buku_ajar' "
            "ORDER BY extracted_at DESC").fetchall()
        out = []
        for r in rows:
            n = conn.execute(
                'SELECT COUNT(*) FROM source_fragments WHERE document_id=?',
                (r['id'],)).fetchone()[0]
            out.append({'document_id': r['id'], 'judul': r['title'],
                        'nama_file': r['local_path'],
                        'ukuran': r['file_size_bytes'],
                        'diupload': r['extracted_at'], 'fragmen': n,
                        'identitas': {
                            'judul': r['book_title'] or '',
                            'pengarang': r['book_author'] or '',
                            'tahun': r['book_year'] or '',
                            'penerbit': r['book_publisher'] or '',
                        }})
        return out
    finally:
        conn.close()


def hapus_buku(db_path: str, document_id: str) -> bool:
    """Hapus buku ajar permanen: baris dokumen + fragmen + file fisik."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT local_path FROM source_documents "
            "WHERE id = ? AND document_type = 'buku_ajar'",
            (document_id,)).fetchone()
        if row is None:
            return False
        conn.execute('DELETE FROM source_fragments WHERE document_id=?',
                     (document_id,))
        conn.execute("DELETE FROM source_documents "
                     "WHERE id = ? AND document_type = 'buku_ajar'",
                     (document_id,))
        conn.commit()
    finally:
        conn.close()
    # File fisik: local_path berbentuk 'source_documents/BUKU-xx.pdf
    # (asli: nama.pdf)' — ambil segmen path sebelum spasi kurung.
    try:
        mentah = (row[0] or '').split(' (asli:')[0].strip()
        kandidat = Path(db_path).resolve().parent / mentah
        if kandidat.is_file() and kandidat.parent.name == 'source_documents':
            kandidat.unlink()
    except OSError:
        pass
    return True


def cari_fragmen(db_path: str, document_id: str, topik: str,
                 maks: int = 8) -> List[Dict]:
    """Fragmen buku paling relevan dengan topik (skor kata kunci)."""
    stop = {'yang', 'dan', 'dari', 'dalam', 'adalah', 'untuk', 'dengan',
            'pada', 'sebagai', 'oleh', 'ini', 'itu', 'atau', 'juga',
            'akan', 'telah', 'sudah', 'dapat', 'bisa', 'agar', 'tentang'}
    kata = [k.lower() for k in re.findall(r'[a-zA-Z]{4,}', topik)
            if k.lower() not in stop]
    if not kata:
        kata = [topik.lower()]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            'SELECT id, page_number, text FROM source_fragments '
            'WHERE document_id = ?', (document_id,)).fetchall()
    finally:
        conn.close()
    skor = []
    for r in rows:
        low = (r['text'] or '').lower()
        hit = sum(1 for k in kata if k in low)
        if hit:
            skor.append((hit, len(r['text'] or ''), dict(r)))
    skor.sort(key=lambda x: (-x[0], x[1]))
    return [s[2] for s in skor[:maks]]
