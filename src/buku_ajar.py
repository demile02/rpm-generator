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
    """Return [(halaman, teks, method)]. method: text_layer/ocr/scan."""
    import fitz
    doc = fitz.open(path)
    out = []
    for i, page in enumerate(doc, start=1):
        teks = (page.get_text() or '').strip()
        method = 'text_layer' if len(teks) >= 50 else 'scan'
        out.append((i, teks, method))
    return out


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
                judul: Optional[str] = None) -> Dict:
    """Simpan file upload sebagai dokumen buku + fragmen. Return ringkas."""
    data = Path(file_path).read_bytes()
    if len(data) > MAX_BUKU_BYTES:
        raise ValueError('File melebihi 10MB.')
    suf = Path(nama_asli).suffix.lower()
    if suf == '.pdf':
        halaman = ekstrak_pdf_per_halaman(file_path)
    elif suf == '.docx':
        halaman = ekstrak_docx_per_halaman(file_path)
    else:
        raise ValueError('Hanya PDF/DOCX.')
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
            'extracted_at, notes) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)',
            (doc_id, judul or Path(nama_asli).stem, 'buku_ajar',
             f'source_documents/{nama_simpan} (asli: {nama_asli})',
             len(data), _hash(data), now,
             f'Upload user {now[:10]}; {len(halaman)} halaman; '
             f'nama asli: {nama_asli}.'))
        n_frag = 0
        for hal, teks, method in halaman:
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
        conn.commit()
    finally:
        conn.close()
    return {'document_id': doc_id, 'judul': judul or Path(nama_asli).stem,
            'halaman': len(halaman), 'fragmen': n_frag}


def daftar_buku(db_path: str) -> List[Dict]:
    """Daftar buku ajar user (bukan regulasi)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, title, local_path, file_size_bytes, extracted_at "
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
                        'diupload': r['extracted_at'], 'fragmen': n})
        return out
    finally:
        conn.close()


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
