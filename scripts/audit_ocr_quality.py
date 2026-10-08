#!/usr/bin/env python3
"""Audit kualitas OCR — sampling acak reproducible + laporan HTML.

Membandingkan teks fragmen tersimpan di db/rpm_generator.db dengan
re-OCR fresh dari PDF kanonik Hukum/ (konfigurasi produksi: Tesseract
ind+eng, dpi 200). Tiga metrik per halaman sampel:

- ``containment``     : persen kata DB yang muncul di re-OCR mentah
                        (konten DB terdukung halaman asli?).
- ``similarity_raw``  : SequenceMatcher vs re-OCR mentah.
- ``similarity_fair`` : SequenceMatcher vs re-OCR yang dibersihkan
                        dengan filter remah yang sama (_is_fragment_
                        debris) — apple-to-apple dengan korpus DB.

Penggunaan::

    python scripts/audit_ocr_quality.py                    # seed default
    python scripts/audit_ocr_quality.py --seed 42 --pages 3
    python scripts/audit_ocr_quality.py --doc 020 --output out.html
    python scripts/audit_ocr_quality.py --json laporan.json

Laporan HTML self-contained ditulis ke audit/ (default) atau --output;
--json menyimpan metrik mentah untuk diff antar-run.
"""
import argparse
import base64
import html
import io
import json
import random
import re
import sqlite3
import sys
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from pdf_extraction import PDFExtractor, _is_fragment_debris  # noqa: E402

DEFAULT_SEED = 20260922
DEFAULT_PAGES = 6
DEFAULT_OUTPUT = PROJECT_ROOT / 'audit' / 'ocr_quality_audit.html'

# Dokumen OCR-scan yang diaudit (id DB -> PDF kanonik). Dokumen text-layer
# tidak diberi opsi --doc karena re-OCR-nya tidak bermakna.
SCAN_DOCS = {
    '020': (
        'DOC-REG-KEMENDIKDASMEN-BKPDM-020-2026',
        'Hukum/BKPDM No. 020 Tahun 2026.pdf',
    ),
    '1503': (
        'DOC-REG-KEMENAG-1503-2025',
        'Hukum/KMA No. 1503 Tahun 2025.pdf',
    ),
}


# ---------------------------------------------------------------------------
# Metrik murni (di-unit-test tanpa DB/PDF/Tesseract)
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Lowercase + buang non-alnum (untuk SequenceMatcher)."""
    return re.sub(r'[^a-z0-9\s]', ' ', (text or '').lower())


def word_set(text: str) -> set:
    return set(normalize_text(text).split())


def clean_fresh_ocr(raw: str) -> str:
    """Baris remah yang sama dengan filter korpus dibuang dari re-OCR
    agar perbandingan apple-to-apple dengan teks DB yang terfilter."""
    return '\n'.join(
        line for line in (raw or '').splitlines()
        if not _is_fragment_debris(line))


def page_metrics(db_text: str, fresh_ocr: str) -> dict:
    """Metrik satu halaman. Murni (tanpa I/O)."""
    db_words, ocr_words = word_set(db_text), word_set(fresh_ocr)
    containment = (
        len(db_words & ocr_words) / len(db_words) * 100 if db_words else 0.0)
    return {
        'containment': containment,
        'similarity_raw': SequenceMatcher(
            None, normalize_text(db_text), normalize_text(fresh_ocr)
        ).ratio() * 100,
        'similarity_fair': SequenceMatcher(
            None, normalize_text(db_text),
            normalize_text(clean_fresh_ocr(fresh_ocr))).ratio() * 100,
    }


def aggregate(metrics: list) -> dict:
    """Rata-rata metrik per dokumen (murni)."""
    if not metrics:
        return {'containment': 0.0, 'similarity_raw': 0.0,
                'similarity_fair': 0.0}
    n = len(metrics)
    return {k: sum(m[k] for m in metrics) / n
            for k in ('containment', 'similarity_raw', 'similarity_fair')}


# ---------------------------------------------------------------------------
# Pengambilan data
# ---------------------------------------------------------------------------

def db_page_text(conn, doc_id: str, page: int) -> str:
    rows = conn.execute(
        'SELECT text FROM source_fragments '
        'WHERE document_id = ? AND page_number = ? ORDER BY paragraph',
        (doc_id, page)).fetchall()
    return '\n'.join(r[0] for r in rows)


def audit_document(doc_id: str, pdf_path: str, seed: int, n_pages: int,
                   db_path: str, log=print) -> dict:
    """Sampling + re-OCR satu dokumen. Sampling pakai Random(seed) atas
    daftar halaman yang punya fragmen — reproducible antar-run."""
    conn = sqlite3.connect(db_path)
    try:
        pages = [r[0] for r in conn.execute(
            'SELECT DISTINCT page_number FROM source_fragments '
            'WHERE document_id = ? ORDER BY page_number', (doc_id,))]
        title_row = conn.execute(
            'SELECT title FROM source_documents WHERE id = ?',
            (doc_id,)).fetchone()
    finally:
        conn.close()
    if not pages:
        raise SystemExit(f'Tidak ada fragmen untuk {doc_id} di {db_path}')

    sample = sorted(random.Random(seed).sample(pages, min(n_pages,
                                                          len(pages))))
    log(f'  sampel halaman: {sample}')
    t0 = time.time()
    ocr_map = PDFExtractor(pdf_path)._ocr_pages(sample)
    log(f'  re-OCR {len(ocr_map)} halaman dalam {time.time() - t0:.1f}s')

    conn = sqlite3.connect(db_path)
    try:
        page_results = []
        for pg in sample:
            db_text = db_page_text(conn, doc_id, pg)
            metrics = page_metrics(db_text, ocr_map.get(pg) or '')
            page_results.append({
                'page': pg,
                'db_chars': len(db_text),
                'ocr_chars': len(ocr_map.get(pg) or ''),
                **metrics,
            })
    finally:
        conn.close()
    return {
        'document_id': doc_id,
        # sqlite3 default row factory: tuple -> akses via index.
        'document_title': title_row[0] if title_row else doc_id,
        'pdf_path': pdf_path,
        'seed': seed,
        'sample': sample,
        'pages': page_results,
        'summary': aggregate(page_results),
    }


# ---------------------------------------------------------------------------
# Laporan HTML
# ---------------------------------------------------------------------------

_TEMPLATE = '''<!DOCTYPE html><html lang="id"><head><meta charset="utf-8">
<title>Audit Kualitas OCR — seed __SEED__</title>
<style>
body{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#f6f7f9;color:#1c2733}
h1{font-size:22px} h2{margin-top:34px;border-bottom:2px solid #2b6cb0;padding-bottom:4px}
.page{display:flex;gap:16px;margin:14px 0;background:#fff;border:1px solid #d7dde5;border-radius:8px;padding:12px}
.col{flex:1;min-width:0}.col h4{margin:2px 0 8px;font-size:13px;color:#4a5568}
img{width:100%;border:1px solid #ccc;border-radius:4px}
pre{white-space:pre-wrap;font-size:11.5px;line-height:1.45;background:#f2f5f8;padding:10px;border-radius:6px;max-height:600px;overflow:auto;font-family:Consolas,monospace}
.metrics{font-size:13px;background:#eef4fb;border-radius:6px;padding:8px 12px;display:inline-block;margin:6px 0}
.summary{background:#eef4fb;border:1px solid #c3d7ee;border-radius:8px;padding:12px 16px;margin:14px 0;font-size:14px}
</style></head><body>
<h1>Audit Kualitas OCR — sampling acak reproducible (seed __SEED__)</h1>
<div class="summary">Metrik per halaman: <strong>containment</strong> = persen kata DB yang muncul di re-OCR mentah; <strong>similarity mentah</strong> = SequenceMatcher vs re-OCR mentah; <strong>apple-to-apple</strong> = vs re-OCR yang dibersihkan filter remah yang sama dengan korpus DB. Re-OCR memakai konfigurasi produksi (Tesseract, ind+eng, dpi 200).</div>
__BODY__
</body></html>'''


def render_html(results: list, seed: int) -> str:
    """Render laporan. MURNI: gambar halaman dibaca dari 'img_b64' yang
    sudah diisi pemanggil (CLI) — fungsi ini tidak menyentuh PDF/fitz
    sehingga dapat diuji tanpa file."""
    body = []
    for res in results:
        s = res['summary']
        body.append('<h2>' + html.escape(res['document_title']) + '</h2>')
        body.append('<p>Sampel halaman: <strong>' + str(res['sample'])
                    + '</strong> — rata-rata: containment='
                    + format(s['containment'], '.1f') + '%, similarity mentah='
                    + format(s['similarity_raw'], '.1f') + '%, apple-to-apple='
                    + format(s['similarity_fair'], '.1f') + '%</p>')
        for pr in res['pages']:
            img_tag = ''
            if pr.get('img_b64'):
                img_tag = ('<img src="data:image/jpeg;base64,' + pr['img_b64']
                           + '" alt="hal ' + str(pr['page']) + '">')
            body.append(
                '<div class="page"><div class="col"><h4>Halaman asli p'
                + str(pr['page']) + '</h4>' + img_tag + '</div>'
                '<div class="col"><h4>Teks DB</h4><pre>'
                + html.escape(pr.get('db_text', '')[:3000]) + '</pre>'
                '<p class="metrics">p' + str(pr['page'])
                + ': containment=' + format(pr['containment'], '.1f')
                + '%; similarity mentah=' + format(pr['similarity_raw'], '.1f')
                + '; apple-to-apple=' + format(pr['similarity_fair'], '.1f')
                + '%</p></div></div>')
    return _TEMPLATE.replace('__SEED__', str(seed)).replace(
        '__BODY__', '\n'.join(body))


def fitz_open_page(pdf_path: str, page: int) -> str:
    """Render satu halaman PDF ke JPEG base64 (untuk laporan)."""
    import fitz
    from PIL import Image
    doc = fitz.open(pdf_path)
    pix = doc[page - 1].get_pixmap(dpi=110)
    img = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=72)
    doc.close()
    return base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    # Portable UTF-8 untuk stdout/stderr Windows (konsol cp1252 gagal
    # mencetak emoji dari log OCR). Hanya encoding; tidak mengubah
    # logika, sampling, metrik, maupun rendering.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding='utf-8')
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        description='Audit kualitas OCR dokumen scan (sampling reproducible).')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                        help='seed sampling (default %d)' % DEFAULT_SEED)
    parser.add_argument('--pages', type=int, default=DEFAULT_PAGES,
                        help='jumlah halaman sampel per dokumen (default %d)'
                             % DEFAULT_PAGES)
    parser.add_argument('--doc', choices=sorted(SCAN_DOCS), action='append',
                        help='batasi ke dokumen tertentu (id pendek: %s); '
                             'boleh diulang. Default: semua.'
                             % ', '.join(SCAN_DOCS))
    parser.add_argument('--db', default=str(
        PROJECT_ROOT / 'db' / 'rpm_generator.db'),
        help='path DB (default db/rpm_generator.db)')
    parser.add_argument('--output', default=None,
                        help='path laporan HTML (default audit/)')
    parser.add_argument('--json', default=None, dest='json_out',
                        help='simpan metrik mentah JSON ke path ini')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)

    log = (lambda *a, **k: None) if args.quiet else print
    selected = (args.doc or list(SCAN_DOCS))
    results = []
    for key in selected:
        doc_id, pdf_path = SCAN_DOCS[key]
        log(f'== {doc_id}')
        results.append(audit_document(
            doc_id, pdf_path, args.seed, args.pages, args.db, log=log))

    out_path = Path(args.output) if args.output else Path(
        str(DEFAULT_OUTPUT).replace('.html', f'_{args.seed}.html'))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Teks DB per halaman + render gambar halaman (I/O PDF di sini,
    # render HTML tetap murni).
    conn = sqlite3.connect(args.db)
    try:
        for res in results:
            for pr in res['pages']:
                pr['db_text'] = db_page_text(
                    conn, res['document_id'], pr['page'])
    finally:
        conn.close()
    for res in results:
        for pr in res['pages']:
            pr['img_b64'] = fitz_open_page(res['pdf_path'], pr['page'])

    out_path.write_text(render_html(results, args.seed), encoding='utf-8')
    log(f'\nLaporan HTML: {out_path}')
    for res in results:
        s = res['summary']
        log(f"  {res['document_id']}: containment={s['containment']:.1f}% "
            f"similarity_raw={s['similarity_raw']:.1f}% "
            f"apple-to-apple={s['similarity_fair']:.1f}%")

    if args.json_out:
        payload = {
            'generated_at': datetime.now().isoformat(),
            'seed': args.seed,
            'results': [
                {k: v for k, v in res.items() if k != 'pdf_path'}
                for res in results
            ],
        }
        Path(args.json_out).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding='utf-8')
        log(f'Metrik JSON: {args.json_out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
